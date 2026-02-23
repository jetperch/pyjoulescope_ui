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

"""PubSub network bridge.

Bridges the local PubSub instance to remote TCP clients, managing
subscriptions, message forwarding, and serialization.
"""

import concurrent.futures
import logging
import numpy as np

from joulescope_ui.tcp_server.protocol import (
    MSG_SUBSCRIBE, MSG_UNSUBSCRIBE, MSG_PUBLISH, MSG_PUBLISH_DATA,
    MSG_QUERY, MSG_QUERY_RESPONSE,
    MSG_ENUMERATE, MSG_ENUMERATE_RESPONSE,
    MSG_QT_INSPECT, MSG_QT_ACTION, MSG_QT_SCREENSHOT,
    MSG_ERROR,
    encode, encode_publish_data,
)

_log = logging.getLogger(__name__)


class _TopicSubscription:
    """Track one PubSub subscription shared across clients."""

    def __init__(self, topic, unsub_fn):
        self.topic = topic
        self.unsub_fn = unsub_fn
        self.client_ids = set()


class PubSubBridge:
    """Bridge between PubSub and remote TCP clients.

    :param pubsub: The PubSub singleton.
    :param server: The TcpServer instance.
    """

    def __init__(self, pubsub, server):
        self._pubsub = pubsub
        self._server = server
        self._subscriptions = {}   # topic -> _TopicSubscription
        self._client_topics = {}   # client_id -> set of topics
        self._qt_inspector = None

    def close(self):
        """Unsubscribe all topics and clean up."""
        for sub in list(self._subscriptions.values()):
            try:
                self._pubsub.unsubscribe(sub.unsub_fn)
            except Exception:
                pass
        self._subscriptions.clear()
        self._client_topics.clear()

    def client_disconnected(self, client):
        """Clean up when a client disconnects."""
        topics = self._client_topics.pop(client.id, set())
        for topic in topics:
            self._remove_client_subscription(client.id, topic)

    async def handle_message(self, client, msg_type, header, payload):
        """Dispatch an inbound message from a client."""
        try:
            if msg_type == MSG_SUBSCRIBE:
                self._handle_subscribe(client, header)
            elif msg_type == MSG_UNSUBSCRIBE:
                self._handle_unsubscribe(client, header)
            elif msg_type == MSG_PUBLISH:
                self._handle_publish(client, header)
            elif msg_type == MSG_QUERY:
                await self._handle_query(client, header)
            elif msg_type == MSG_ENUMERATE:
                await self._handle_enumerate(client, header)
            elif msg_type in (MSG_QT_INSPECT, MSG_QT_ACTION, MSG_QT_SCREENSHOT):
                await self._handle_qt(client, msg_type, header, payload)
            else:
                _log.warning('Unknown message type 0x%02x from %s', msg_type, client)
        except Exception as ex:
            _log.exception('Error handling message from %s', client)
            frame = encode(MSG_ERROR, {'message': str(ex)})
            self._server.send_to_client(client, frame)

    def _handle_subscribe(self, client, header):
        topic = header.get('topic', '')
        flags = header.get('flags', ['pub'])
        if not topic:
            return

        # Track per-client subscriptions
        if client.id not in self._client_topics:
            self._client_topics[client.id] = set()
        self._client_topics[client.id].add(topic)

        # Reference-counted PubSub subscription
        if topic not in self._subscriptions:
            def forwarder(t, value):
                self._forward_to_clients(t, value, topic)
            unsub = self._pubsub.subscribe(topic, forwarder, flags)
            sub = _TopicSubscription(topic, unsub)
            self._subscriptions[topic] = sub
        self._subscriptions[topic].client_ids.add(client.id)

    def _handle_unsubscribe(self, client, header):
        topic = header.get('topic', '')
        if not topic:
            return
        if client.id in self._client_topics:
            self._client_topics[client.id].discard(topic)
        self._remove_client_subscription(client.id, topic)

    def _remove_client_subscription(self, client_id, topic):
        sub = self._subscriptions.get(topic)
        if sub is None:
            return
        sub.client_ids.discard(client_id)
        if not sub.client_ids:
            try:
                self._pubsub.unsubscribe(sub.unsub_fn)
            except Exception:
                pass
            del self._subscriptions[topic]

    def _handle_publish(self, client, header):
        topic = header.get('topic', '')
        value = header.get('value')
        if not topic:
            return
        self._pubsub.publish(topic, value)

    async def _handle_query(self, client, header):
        topic = header.get('topic', '')
        request_id = header.get('id')
        if not topic:
            return
        try:
            value = self._pubsub.query(topic)
            # Serialize value safely
            response_header = {'topic': topic, 'value': _serialize_value(value)}
            if request_id is not None:
                response_header['id'] = request_id
            frame = encode(MSG_QUERY_RESPONSE, response_header)
        except Exception as ex:
            frame = encode(MSG_ERROR, {'message': str(ex), 'id': request_id})
        self._server.send_to_client(client, frame)

    async def _handle_enumerate(self, client, header):
        topic = header.get('topic', '')
        absolute = header.get('absolute')
        request_id = header.get('id')
        try:
            topics = self._pubsub.enumerate(topic, absolute=absolute)
            response_header = {'topics': topics}
            if request_id is not None:
                response_header['id'] = request_id
            frame = encode(MSG_ENUMERATE_RESPONSE, response_header)
        except Exception as ex:
            frame = encode(MSG_ERROR, {'message': str(ex), 'id': request_id})
        self._server.send_to_client(client, frame)

    async def _handle_qt(self, client, msg_type, header, payload):
        """Handle Qt inspection requests by dispatching to the Qt thread."""
        if self._qt_inspector is None:
            from joulescope_ui.tcp_server.qt_inspector import QtInspector
            self._qt_inspector = QtInspector(self._pubsub)
        future = concurrent.futures.Future()
        self._qt_inspector.dispatch(msg_type, header, payload, future)
        try:
            result_msg_type, result_header, result_payload = await asyncio.get_event_loop().run_in_executor(
                None, future.result, 5.0)
            frame = encode(result_msg_type, result_header, result_payload)
        except Exception as ex:
            frame = encode(MSG_ERROR, {'message': str(ex)})
        self._server.send_to_client(client, frame)

    def _forward_to_clients(self, topic, value, subscribed_topic):
        """Forward a PubSub publish to subscribed remote clients.

        Called on the PubSub/Qt thread. Must not block.
        """
        sub = self._subscriptions.get(subscribed_topic)
        if sub is None or not sub.client_ids:
            return

        # Determine if this is streaming data with numpy payload
        if isinstance(value, dict) and 'data' in value and isinstance(value.get('data'), np.ndarray):
            frame = encode_publish_data(topic, value)
        else:
            frame = encode(MSG_PUBLISH, {'topic': topic, 'value': _serialize_value(value)})

        for client_id in sub.client_ids:
            client = self._server._clients.get(client_id)
            if client is not None:
                self._server.send_to_client(client, frame)


def _serialize_value(value):
    """Serialize a PubSub value for JSON transport."""
    if isinstance(value, np.ndarray):
        return {
            '__type__': 'ndarray',
            'dtype': str(value.dtype),
            'shape': list(value.shape),
            'data': value.tolist(),
        }
    elif isinstance(value, bytes):
        import base64
        return {
            '__type__': 'bytes',
            'data': base64.b64encode(value).decode('utf-8'),
        }
    elif isinstance(value, np.integer):
        return int(value)
    elif isinstance(value, np.floating):
        return float(value)
    else:
        return value


# Required import at module level for await
import asyncio
