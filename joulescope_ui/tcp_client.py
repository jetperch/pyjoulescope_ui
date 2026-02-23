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

"""Python client library for the Joulescope UI TCP server.

Provides a PubSubProxy-like API for connecting to the UI's TCP server
from external processes (test automation, monitoring, scripting).

Example usage::

    from joulescope_ui.tcp_client import Client

    client = Client(token='<server_token>')
    client.open()
    client.subscribe('registry/+/events/statistics/!data', my_callback)
    value = client.query('registry/.../settings/name')
    tree = client.qt_inspect()
    png = client.qt_screenshot()
    client.close()
"""

import base64
import json
import logging
import socket
import struct
import threading
import numpy as np

from joulescope_ui.tcp_server.protocol import (
    DEFAULT_PORT, PROTOCOL_VERSION, FrameDecoder, DTYPE_MAP,
    MSG_AUTH, MSG_AUTH_OK, MSG_SUBSCRIBE, MSG_UNSUBSCRIBE,
    MSG_PUBLISH, MSG_PUBLISH_DATA,
    MSG_QUERY, MSG_QUERY_RESPONSE,
    MSG_ENUMERATE, MSG_ENUMERATE_RESPONSE,
    MSG_QT_INSPECT, MSG_QT_INSPECT_RESPONSE,
    MSG_QT_ACTION, MSG_QT_SCREENSHOT, MSG_QT_SCREENSHOT_RESPONSE,
    MSG_ERROR, MSG_CLOSE,
    encode, decode_publish_data,
)

_log = logging.getLogger(__name__)


def _deserialize_value(value):
    """Deserialize a value received from the server."""
    if isinstance(value, dict):
        t = value.get('__type__')
        if t == 'ndarray':
            return np.array(value['data'], dtype=value.get('dtype', 'float32'))
        elif t == 'bytes':
            return base64.b64decode(value['data'].encode('utf-8'))
    return value


class Client:
    """TCP client for the Joulescope UI server.

    :param host: Server address (default '127.0.0.1').
    :param port: Server TCP port (default 21861).
    :param token: Authentication token string.
    :param timeout: Socket timeout in seconds for synchronous operations.
    """

    def __init__(self, host=None, port=None, token=None, timeout=5.0):
        self._host = host if host is not None else '127.0.0.1'
        self._port = port if port is not None else DEFAULT_PORT
        self._token = token if token is not None else ''
        self._timeout = timeout
        self._sock = None
        self._recv_thread = None
        self._running = False
        self._lock = threading.Lock()
        self._subscribers = {}          # topic -> list of callables
        self._pending = {}              # request_id -> threading.Event, result
        self._next_id = 0
        self._decoder = FrameDecoder()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def open(self):
        """Connect to the server and authenticate."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self._timeout)
        self._sock.connect((self._host, self._port))
        self._sock.settimeout(None)  # blocking for recv thread

        # Authenticate
        self._send_frame(MSG_AUTH, {'token': self._token})
        # Read auth response synchronously
        data = self._sock.recv(4096)
        frames = self._decoder.feed(data)
        if not frames:
            raise ConnectionError('No response from server')
        msg_type, header, payload = frames[0]
        if msg_type == MSG_ERROR:
            raise ConnectionError(f'Authentication failed: {header.get("message", "")}')
        if msg_type != MSG_AUTH_OK:
            raise ConnectionError(f'Unexpected response: msg_type=0x{msg_type:02x}')

        # Start receive thread
        self._running = True
        self._recv_thread = threading.Thread(
            name='joulescope_client_recv',
            target=self._recv_loop,
            daemon=True,
        )
        self._recv_thread.start()
        _log.info('Connected to %s:%d', self._host, self._port)

    def close(self):
        """Disconnect from the server."""
        self._running = False
        if self._sock is not None:
            try:
                self._send_frame(MSG_CLOSE)
            except Exception:
                pass
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self._sock.close()
            self._sock = None
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=2.0)
            self._recv_thread = None
        self._subscribers.clear()
        self._pending.clear()
        _log.info('Disconnected')

    def subscribe(self, topic, callback, flags=None):
        """Subscribe to a PubSub topic.

        :param topic: The topic string.
        :param callback: Called as callback(topic, value) for each publish.
        :param flags: Subscription flags list (default ['pub']).
        """
        if flags is None:
            flags = ['pub']
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)
        header = {'topic': topic, 'flags': flags}
        self._send_frame(MSG_SUBSCRIBE, header)

    def unsubscribe(self, topic, callback=None):
        """Unsubscribe from a PubSub topic.

        :param topic: The topic string.
        :param callback: Specific callback to remove, or None to remove all.
        """
        if topic in self._subscribers:
            if callback is None:
                del self._subscribers[topic]
            else:
                self._subscribers[topic] = [
                    cb for cb in self._subscribers[topic] if cb is not callback
                ]
                if not self._subscribers[topic]:
                    del self._subscribers[topic]
        if topic not in self._subscribers:
            self._send_frame(MSG_UNSUBSCRIBE, {'topic': topic})

    def publish(self, topic, value):
        """Publish a value to a PubSub topic.

        :param topic: The topic string.
        :param value: The value to publish (must be JSON-serializable).
        """
        self._send_frame(MSG_PUBLISH, {'topic': topic, 'value': value})

    def query(self, topic):
        """Query the retained value of a PubSub topic.

        :param topic: The topic string.
        :return: The retained value.
        :raises TimeoutError: If no response within timeout.
        """
        return self._request(MSG_QUERY, {'topic': topic}, MSG_QUERY_RESPONSE)['value']

    def enumerate(self, topic, absolute=None):
        """Enumerate child topics.

        :param topic: The parent topic string.
        :param absolute: If True, return absolute topic paths.
        :return: List of topic name strings.
        """
        header = {'topic': topic}
        if absolute is not None:
            header['absolute'] = absolute
        return self._request(MSG_ENUMERATE, header, MSG_ENUMERATE_RESPONSE)['topics']

    def qt_inspect(self, path='', max_depth=50):
        """Inspect the Qt widget tree.

        :param path: Widget path (empty for root window).
        :param max_depth: Maximum tree depth.
        :return: dict describing the widget tree.
        """
        header = {'path': path, 'max_depth': max_depth}
        return self._request(MSG_QT_INSPECT, header, MSG_QT_INSPECT_RESPONSE)

    def qt_action(self, action, path='', **kwargs):
        """Perform a Qt action.

        :param action: Action name ('click', 'key', 'set_property', 'get_property').
        :param path: Widget path.
        :param kwargs: Action-specific parameters.
        :return: Action result dict.
        """
        header = {'action': action, 'path': path}
        header.update(kwargs)
        return self._request(MSG_QT_ACTION, header, MSG_QT_INSPECT_RESPONSE)

    def qt_screenshot(self, path=''):
        """Capture a screenshot of a widget.

        :param path: Widget path (empty for root window).
        :return: PNG image as bytes.
        """
        header = {'path': path}
        result = self._request_raw(MSG_QT_SCREENSHOT, header, MSG_QT_SCREENSHOT_RESPONSE)
        return result[2]  # payload = PNG bytes

    def _send_frame(self, msg_type, header=None, payload=None):
        with self._lock:
            frame = encode(msg_type, header, payload)
            self._sock.sendall(frame)

    def _request(self, msg_type, header, expected_response_type):
        """Send a request and wait for the response header."""
        _, resp_header, _ = self._request_raw(msg_type, header, expected_response_type)
        return resp_header

    def _request_raw(self, msg_type, header, expected_response_type):
        """Send a request and wait for the full response tuple."""
        request_id = self._allocate_id()
        header['id'] = request_id
        event = threading.Event()
        self._pending[request_id] = {'event': event, 'result': None}
        self._send_frame(msg_type, header)
        if not event.wait(timeout=self._timeout):
            self._pending.pop(request_id, None)
            raise TimeoutError(f'Request {request_id} timed out')
        entry = self._pending.pop(request_id)
        result = entry['result']
        if result[0] == MSG_ERROR:
            raise RuntimeError(result[1].get('message', 'Server error'))
        return result

    def _allocate_id(self):
        self._next_id += 1
        return self._next_id

    def _recv_loop(self):
        while self._running:
            try:
                data = self._sock.recv(65536)
                if not data:
                    break
                frames = self._decoder.feed(data)
                for msg_type, header, payload in frames:
                    self._dispatch(msg_type, header, payload)
            except OSError:
                break
            except Exception:
                _log.exception('Error in receive loop')

    def _dispatch(self, msg_type, header, payload):
        # Check if this is a response to a pending request
        request_id = header.get('id')
        if request_id is not None and request_id in self._pending:
            entry = self._pending[request_id]
            entry['result'] = (msg_type, header, payload)
            entry['event'].set()
            return

        # Handle incoming publishes
        if msg_type == MSG_PUBLISH:
            topic = header.get('topic', '')
            value = _deserialize_value(header.get('value'))
            self._notify_subscribers(topic, value)
        elif msg_type == MSG_PUBLISH_DATA:
            data_msg = decode_publish_data(header, payload)
            topic = data_msg.pop('topic', '')
            self._notify_subscribers(topic, data_msg)
        elif msg_type == MSG_ERROR:
            _log.warning('Server error: %s', header.get('message', ''))

    def _notify_subscribers(self, topic, value):
        callbacks = self._subscribers.get(topic, [])
        for cb in callbacks:
            try:
                cb(topic, value)
            except Exception:
                _log.exception('Subscriber callback error for topic %s', topic)
