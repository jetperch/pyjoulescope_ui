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

"""Integration tests for TCP server and client."""

import asyncio
import concurrent.futures
import unittest
import threading
import time
import numpy as np
from joulescope_ui.pubsub import PubSub
from joulescope_ui.tcp_server import TcpServer
from joulescope_ui.tcp_client import Client
from joulescope_ui.tcp_server.bridge import PubSubBridge
from joulescope_ui.tcp_server.protocol import (
    FrameDecoder, MSG_QT_INSPECT, MSG_QT_INSPECT_RESPONSE,
    MSG_QT_SCREENSHOT, MSG_QT_SCREENSHOT_RESPONSE, MSG_ERROR,
)


class TestServerClient(unittest.TestCase):

    def setUp(self):
        self.pubsub = PubSub(app='test', skip_core_undo=True)
        self.pubsub.topic_add('test', dtype='node', brief='test root')
        self.pubsub.topic_add('test/value', dtype='str', brief='test value', default='')
        self.pubsub.topic_add('test/number', dtype='int', brief='test number', default=0)
        self.pubsub.topic_add('test/!event', dtype='obj', brief='test event')

        # Set notify_fn to process queued commands from other threads
        self._process_event = threading.Event()
        def _notify():
            self._process_event.set()
        self.pubsub.notify_fn = _notify

        self.server = TcpServer(self.pubsub, host='127.0.0.1', port=0, token='test_token')
        self.server.start()
        self.client = Client(host='127.0.0.1', port=self.server.port, token='test_token')
        self.client.open()

    def _process_pubsub(self, timeout=0.5):
        """Process pending PubSub commands from other threads."""
        if self._process_event.wait(timeout=timeout):
            self._process_event.clear()
        self.pubsub.process()

    def tearDown(self):
        self.client.close()
        self.server.stop()

    def test_connect_and_auth(self):
        self.assertEqual(self.server.client_count, 1)

    def test_auth_failure(self):
        with self.assertRaises(ConnectionError):
            bad_client = Client(host='127.0.0.1', port=self.server.port, token='wrong')
            bad_client.open()

    def test_query(self):
        self.pubsub.publish('test/value', 'hello')
        self.pubsub.process()
        value = self.client.query('test/value')
        self.assertEqual(value, 'hello')

    def test_publish_from_client(self):
        received = []

        def on_value(value):
            received.append(value)

        self.pubsub.subscribe('test/value', on_value, ['pub'])
        self.client.publish('test/value', 'from_client')
        # Give time for the message to arrive and process
        self._process_pubsub()
        self.assertIn('from_client', received)

    def test_subscribe_and_receive(self):
        received = []
        event = threading.Event()

        def on_value(topic, value):
            received.append((topic, value))
            event.set()

        self.client.subscribe('test/value', on_value, ['pub'])
        # Process the subscription command queued from the asyncio thread
        self._process_pubsub()

        self.pubsub.publish('test/value', 'broadcast_test')
        self.pubsub.process()

        event.wait(timeout=2.0)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], 'test/value')
        self.assertEqual(received[0][1], 'broadcast_test')

    def test_enumerate(self):
        topics = self.client.enumerate('test')
        self.assertIn('value', topics)
        self.assertIn('number', topics)

    def test_unsubscribe(self):
        received = []

        def on_value(topic, value):
            received.append(value)

        self.client.subscribe('test/value', on_value)
        self._process_pubsub()
        self.client.unsubscribe('test/value')
        self._process_pubsub()

        self.pubsub.publish('test/value', 'should_not_receive')
        self.pubsub.process()
        time.sleep(0.2)
        self.assertEqual(len(received), 0)

    def test_streaming_data(self):
        """Test receiving numpy array data through the bridge."""
        received = []
        event = threading.Event()

        def on_data(topic, value):
            received.append(value)
            event.set()

        self.client.subscribe('test/!event', on_data, ['pub'])
        self._process_pubsub()

        data = np.arange(100, dtype=np.float32)
        msg = {
            'source': {'serial_number': 'test'},
            'sample_id': 0,
            'sample_freq': 1000000.0,
            'time': 0,
            'field': 'current',
            'data': data,
            'dtype': 'f32',
            'units': 'A',
            'origin_sample_id': 0,
            'origin_sample_freq': 1000000.0,
            'origin_decimate_factor': 1,
        }
        self.pubsub.publish('test/!event', msg)
        self.pubsub.process()

        event.wait(timeout=2.0)
        self.assertEqual(len(received), 1)
        np.testing.assert_array_equal(received[0]['data'], data)

    def test_query_nested_numpy_scalars(self):
        # Regression: an x_range-like [int64, int64] must serialize over the wire
        # (top-level numpy scalars worked, but nested ones raised "not JSON
        # serializable").
        self.pubsub.topic_add('test/range', dtype='obj', brief='range', default=None)
        self.pubsub.publish('test/range', [np.int64(10), np.int64(2000)])
        self.pubsub.process()
        self.assertEqual(self.client.query('test/range'), [10, 2000])

        self.pubsub.publish('test/range', {'x': [np.float64(1.5)], 'n': np.int32(3)})
        self.pubsub.process()
        self.assertEqual(self.client.query('test/range'), {'x': [1.5], 'n': 3})

    def test_multiple_clients(self):
        client2 = Client(host='127.0.0.1', port=self.server.port, token='test_token')
        client2.open()
        try:
            self.assertEqual(self.server.client_count, 2)
            # Both clients can query
            self.pubsub.publish('test/value', 'multi')
            self.pubsub.process()
            v1 = self.client.query('test/value')
            v2 = client2.query('test/value')
            self.assertEqual(v1, 'multi')
            self.assertEqual(v2, 'multi')
        finally:
            client2.close()


class _CaptureServer:
    """Minimal TcpServer stand-in that records frames sent to a client."""

    def __init__(self):
        self.frames = []

    def send_to_client(self, client, frame_bytes):
        self.frames.append(frame_bytes)


class _StubInspector:
    """QtInspector stand-in: completes the future with a header lacking 'id'.

    Mirrors the real inspector, which builds its response header from the Qt
    widget tree and therefore does not carry the request correlation id.
    """

    def __init__(self, result):
        self._result = result

    def dispatch(self, msg_type, header, payload, future):
        future.set_result(self._result)


class TestQtResponseCorrelation(unittest.TestCase):
    """Regression: Qt responses must echo the request id so the client can
    correlate them (otherwise ``client.qt_inspect()`` hangs until timeout)."""

    def setUp(self):
        self.pubsub = PubSub(app='test', skip_core_undo=True)
        self.server = _CaptureServer()
        self.bridge = PubSubBridge(self.pubsub, self.server)
        self.client = object()  # opaque token; _CaptureServer ignores it

    def _run_qt(self, msg_type, header, payload=b''):
        asyncio.run(self.bridge._handle_qt(self.client, msg_type, header, payload))
        self.assertEqual(len(self.server.frames), 1)
        decoder = FrameDecoder()
        frames = decoder.feed(self.server.frames[0])
        self.assertEqual(len(frames), 1)
        return frames[0]  # (msg_type, header, payload)

    def test_inspect_response_carries_id(self):
        self.bridge._qt_inspector = _StubInspector(
            (MSG_QT_INSPECT_RESPONSE, {'class': 'MainWindow'}, None))
        msg_type, header, _ = self._run_qt(MSG_QT_INSPECT, {'id': 42, 'path': ''})
        self.assertEqual(msg_type, MSG_QT_INSPECT_RESPONSE)
        self.assertEqual(header['id'], 42)
        self.assertEqual(header['class'], 'MainWindow')

    def test_screenshot_response_carries_id_and_payload(self):
        png = b'\x89PNG\r\n\x1a\n' + b'fakepngdata'
        self.bridge._qt_inspector = _StubInspector(
            (MSG_QT_SCREENSHOT_RESPONSE, {'format': 'png'}, png))
        msg_type, header, payload = self._run_qt(MSG_QT_SCREENSHOT, {'id': 7})
        self.assertEqual(msg_type, MSG_QT_SCREENSHOT_RESPONSE)
        self.assertEqual(header['id'], 7)
        self.assertEqual(payload, png)

    def test_large_qt_response_moves_to_payload(self):
        # Regression: a widget tree larger than the uint16 header limit must be
        # delivered in the binary payload (the header_length field is a uint16,
        # so a >64 KB header overflows with "'H' format requires 0 <= number").
        import json
        from joulescope_ui.tcp_server.bridge import _encode_qt_response
        big = {'id': 5, 'children': ['x' * 100 for _ in range(2000)]}  # > 60 KB
        frames = FrameDecoder().feed(
            _encode_qt_response(MSG_QT_INSPECT_RESPONSE, big, None))
        msg_type, header, payload = frames[0]
        self.assertEqual(msg_type, MSG_QT_INSPECT_RESPONSE)
        self.assertTrue(header.get('json_in_payload'))
        self.assertEqual(header.get('id'), 5)
        self.assertEqual(json.loads(payload), big)

    def test_small_qt_response_stays_inline(self):
        from joulescope_ui.tcp_server.bridge import _encode_qt_response
        small = {'id': 6, 'class': 'MainWindow'}
        frames = FrameDecoder().feed(
            _encode_qt_response(MSG_QT_INSPECT_RESPONSE, small, None))
        _, header, payload = frames[0]
        self.assertEqual(header, small)
        self.assertEqual(payload, b'')

    def test_error_response_carries_id(self):
        def _boom(msg_type, header, payload, future):
            future.set_exception(RuntimeError('inspect failed'))
        self.bridge._qt_inspector = type('E', (), {'dispatch': staticmethod(_boom)})()
        msg_type, header, _ = self._run_qt(MSG_QT_INSPECT, {'id': 99})
        self.assertEqual(msg_type, MSG_ERROR)
        self.assertEqual(header['id'], 99)
        self.assertIn('inspect failed', header['message'])


if __name__ == '__main__':
    unittest.main()
