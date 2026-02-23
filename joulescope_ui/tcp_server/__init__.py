# Copyright 2026 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TCP socket server for remote PubSub access and Qt inspection.

The server runs an asyncio event loop in a dedicated thread, accepting
TCP connections from external processes.  It bridges PubSub messages
between the local application and remote clients, and provides Qt
widget inspection for test automation.
"""

import asyncio
import logging
import os
import secrets
import threading

from joulescope_ui.tcp_server.protocol import (
    DEFAULT_PORT, FrameDecoder,
    MSG_AUTH, MSG_AUTH_OK, MSG_CLOSE, MSG_ERROR,
    encode,
)

_log = logging.getLogger(__name__)

_SETTINGS = {
    'enable': {
        'dtype': 'bool',
        'brief': 'Enable TCP server',
        'detail': 'When enabled, a TCP socket server listens for connections from external processes.',
        'default': False,
    },
    'host': {
        'dtype': 'str',
        'brief': 'Server bind address',
        'detail': 'The network interface to bind to.  Use 127.0.0.1 for localhost only.',
        'default': '127.0.0.1',
    },
    'port': {
        'dtype': 'u16',
        'brief': 'Server TCP port',
        'detail': 'The TCP port number for the server.',
        'default': DEFAULT_PORT,
    },
}


class _ClientState:
    """Track per-client connection state."""

    _next_id = 0

    def __init__(self, reader, writer):
        _ClientState._next_id += 1
        self.id = _ClientState._next_id
        self.reader = reader
        self.writer = writer
        self.authenticated = False
        self.decoder = FrameDecoder()
        self.subscribed_topics = set()
        addr = writer.get_extra_info('peername')
        self.addr = f'{addr[0]}:{addr[1]}' if addr else 'unknown'

    def __str__(self):
        return f'Client({self.id}, {self.addr})'


class TcpServer:
    """TCP socket server running in a dedicated asyncio thread.

    :param pubsub: The PubSub singleton instance.
    :param host: Bind address (default '127.0.0.1').
    :param port: TCP port (default 21861).
    :param token: Authentication token.  None generates a random token.
    """

    def __init__(self, pubsub, host=None, port=None, token=None):
        self._pubsub = pubsub
        self._host = host if host is not None else '127.0.0.1'
        self._port = port if port is not None else DEFAULT_PORT
        self._token = token or secrets.token_hex(32)
        self._loop = None
        self._thread = None
        self._server = None
        self._clients = {}  # client_id -> _ClientState
        self._bridge = None
        self._started = threading.Event()

    @property
    def token(self):
        return self._token

    @property
    def port(self):
        return self._port

    @property
    def loop(self):
        return self._loop

    @property
    def client_count(self):
        return len(self._clients)

    def start(self):
        """Start the server in a background thread."""
        if self._thread is not None:
            _log.warning('Server already started')
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            name='tcp_server',
            target=self._run_loop,
            daemon=True,
        )
        self._thread.start()
        self._started.wait(timeout=5.0)
        if not self._started.is_set():
            raise RuntimeError('Server failed to start within timeout')
        _log.info('TCP server started on %s:%d', self._host, self._port)

    def stop(self):
        """Stop the server and close all client connections."""
        if self._loop is None:
            return
        loop = self._loop
        self._loop = None
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        _log.info('TCP server stopped')

    def _run_loop(self):
        loop = self._loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._start_server())
        except Exception:
            _log.exception('Server startup failed')
            self._started.set()  # unblock the waiting thread
            return
        self._started.set()
        loop.run_forever()
        # Cleanup after loop.stop()
        loop.run_until_complete(self._stop_server())
        loop.close()

    async def _start_server(self):
        from joulescope_ui.tcp_server.bridge import PubSubBridge
        self._bridge = PubSubBridge(self._pubsub, self)
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._host,
            port=self._port,
        )
        # Update port in case 0 was used (OS-assigned)
        for sock in self._server.sockets:
            addr = sock.getsockname()
            self._port = addr[1]
            break

    async def _stop_server(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        # Close all clients
        for client in list(self._clients.values()):
            await self._close_client(client)
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None

    async def _handle_client(self, reader, writer):
        client = _ClientState(reader, writer)
        self._clients[client.id] = client
        _log.info('Client connected: %s', client)
        try:
            await self._client_loop(client)
        except asyncio.CancelledError:
            pass
        except ConnectionResetError:
            _log.info('Client disconnected: %s', client)
        except Exception:
            _log.exception('Error handling client %s', client)
        finally:
            await self._close_client(client)

    async def _client_loop(self, client):
        while True:
            data = await client.reader.read(65536)
            if not data:
                break
            frames = client.decoder.feed(data)
            for msg_type, header, payload in frames:
                if not client.authenticated:
                    if msg_type == MSG_AUTH:
                        await self._handle_auth(client, header)
                    else:
                        await self._send(client, MSG_ERROR,
                                         {'message': 'Authentication required'})
                        return
                elif msg_type == MSG_CLOSE:
                    return
                else:
                    await self._bridge.handle_message(client, msg_type, header, payload)

    async def _handle_auth(self, client, header):
        token = header.get('token', '')
        if token == self._token:
            client.authenticated = True
            await self._send(client, MSG_AUTH_OK)
            _log.info('Client authenticated: %s', client)
        else:
            await self._send(client, MSG_ERROR, {'message': 'Invalid token'})
            _log.warning('Authentication failed for %s', client)
            await self._close_client(client)

    async def _close_client(self, client):
        if client.id not in self._clients:
            return
        del self._clients[client.id]
        if self._bridge is not None:
            self._bridge.client_disconnected(client)
        try:
            client.writer.close()
            await client.writer.wait_closed()
        except Exception:
            pass
        _log.info('Client closed: %s', client)

    async def _send(self, client, msg_type, header=None, payload=None):
        """Send a message to a specific client."""
        try:
            frame = encode(msg_type, header, payload)
            client.writer.write(frame)
            await client.writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            _log.debug('Send failed to %s, closing', client)
            await self._close_client(client)

    def send_to_client(self, client, frame_bytes):
        """Send pre-encoded frame bytes to a client (thread-safe).

        Called from PubSub thread via bridge. Uses call_soon_threadsafe
        to schedule the write on the asyncio event loop.
        """
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._send_frame_sync, client, frame_bytes)

    def _send_frame_sync(self, client, frame_bytes):
        """Write pre-encoded frame bytes to a client (on asyncio thread)."""
        if client.id not in self._clients:
            return
        try:
            buf_size = client.writer.transport.get_write_buffer_size()
            if buf_size > 32 * 1024 * 1024:  # 32 MB backpressure threshold
                return  # drop frame for slow client
            client.writer.write(frame_bytes)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass

    def broadcast(self, frame_bytes, exclude_client_id=None):
        """Broadcast pre-encoded frame bytes to all authenticated clients.

        Called from PubSub thread. Thread-safe.
        """
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(
            self._broadcast_sync, frame_bytes, exclude_client_id)

    def _broadcast_sync(self, frame_bytes, exclude_client_id):
        for client in self._clients.values():
            if client.authenticated and client.id != exclude_client_id:
                self._send_frame_sync(client, frame_bytes)
