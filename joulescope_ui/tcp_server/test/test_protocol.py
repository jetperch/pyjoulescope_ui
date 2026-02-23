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

import unittest
import numpy as np
from joulescope_ui.tcp_server.protocol import (
    encode, FrameDecoder,
    encode_publish_data, decode_publish_data,
    MSG_SUBSCRIBE, MSG_PUBLISH, MSG_PUBLISH_DATA,
    MSG_QUERY, MSG_QUERY_RESPONSE, MSG_CLOSE,
    PROTOCOL_VERSION,
)


class TestEncodeDecode(unittest.TestCase):

    def setUp(self):
        self.decoder = FrameDecoder()

    def test_encode_no_header_no_payload(self):
        frame = encode(MSG_CLOSE)
        frames = self.decoder.feed(frame)
        self.assertEqual(len(frames), 1)
        msg_type, header, payload = frames[0]
        self.assertEqual(msg_type, MSG_CLOSE)
        self.assertEqual(header, {})
        self.assertEqual(payload, b'')

    def test_encode_with_header(self):
        frame = encode(MSG_SUBSCRIBE, {'topic': 'test/topic', 'flags': ['pub']})
        frames = self.decoder.feed(frame)
        self.assertEqual(len(frames), 1)
        msg_type, header, payload = frames[0]
        self.assertEqual(msg_type, MSG_SUBSCRIBE)
        self.assertEqual(header['topic'], 'test/topic')
        self.assertEqual(header['flags'], ['pub'])
        self.assertEqual(payload, b'')

    def test_encode_with_payload(self):
        data = b'\x01\x02\x03\x04'
        frame = encode(MSG_PUBLISH, {'topic': 'test'}, data)
        frames = self.decoder.feed(frame)
        self.assertEqual(len(frames), 1)
        msg_type, header, payload = frames[0]
        self.assertEqual(msg_type, MSG_PUBLISH)
        self.assertEqual(header['topic'], 'test')
        self.assertEqual(payload, data)

    def test_roundtrip_query_response(self):
        frame = encode(MSG_QUERY_RESPONSE, {'topic': 'a/b', 'value': 42, 'id': 1})
        frames = self.decoder.feed(frame)
        self.assertEqual(len(frames), 1)
        msg_type, header, _ = frames[0]
        self.assertEqual(msg_type, MSG_QUERY_RESPONSE)
        self.assertEqual(header['value'], 42)
        self.assertEqual(header['id'], 1)

    def test_multiple_frames_in_single_feed(self):
        f1 = encode(MSG_SUBSCRIBE, {'topic': 'a'})
        f2 = encode(MSG_SUBSCRIBE, {'topic': 'b'})
        frames = self.decoder.feed(f1 + f2)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0][1]['topic'], 'a')
        self.assertEqual(frames[1][1]['topic'], 'b')

    def test_incremental_feed(self):
        frame = encode(MSG_PUBLISH, {'topic': 'test', 'value': 'hello'})
        mid = len(frame) // 2
        frames = self.decoder.feed(frame[:mid])
        self.assertEqual(len(frames), 0)
        frames = self.decoder.feed(frame[mid:])
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0][1]['topic'], 'test')

    def test_reset(self):
        frame = encode(MSG_CLOSE)
        self.decoder.feed(frame[:2])
        self.decoder.reset()
        frames = self.decoder.feed(frame)
        self.assertEqual(len(frames), 1)


class TestPublishData(unittest.TestCase):

    def test_f32_roundtrip(self):
        data = np.arange(1000, dtype=np.float32)
        msg = {
            'source': {'serial_number': 'JS220-001'},
            'sample_id': 0,
            'sample_freq': 1000000.0,
            'time': 12345678,
            'field': 'current',
            'data': data,
            'dtype': 'f32',
            'units': 'A',
            'origin_sample_id': 0,
            'origin_sample_freq': 1000000.0,
            'origin_decimate_factor': 1,
        }
        frame = encode_publish_data('registry/js220/events/signals/i/!data', msg)
        decoder = FrameDecoder()
        frames = decoder.feed(frame)
        self.assertEqual(len(frames), 1)
        msg_type, header, payload = frames[0]
        self.assertEqual(msg_type, MSG_PUBLISH_DATA)
        reconstructed = decode_publish_data(header, payload)
        np.testing.assert_array_equal(reconstructed['data'], data)
        self.assertEqual(reconstructed['field'], 'current')
        self.assertEqual(reconstructed['sample_freq'], 1000000.0)
        self.assertEqual(reconstructed['topic'], 'registry/js220/events/signals/i/!data')

    def test_u8_roundtrip(self):
        data = np.array([0, 1, 2, 255], dtype=np.uint8)
        msg = {
            'source': None,
            'sample_id': 100,
            'sample_freq': 1000000.0,
            'time': 0,
            'field': 'current_range',
            'data': data,
            'dtype': 'u8',
            'units': '',
            'origin_sample_id': 100,
            'origin_sample_freq': 1000000.0,
            'origin_decimate_factor': 1,
        }
        frame = encode_publish_data('test/range', msg)
        decoder = FrameDecoder()
        frames = decoder.feed(frame)
        reconstructed = decode_publish_data(frames[0][1], frames[0][2])
        np.testing.assert_array_equal(reconstructed['data'], data)

    def test_large_array_performance(self):
        """Verify encoding a 1M-sample f32 array (4 MB) completes quickly."""
        data = np.random.randn(1_000_000).astype(np.float32)
        msg = {
            'data': data,
            'dtype': 'f32',
            'sample_id': 0,
            'sample_freq': 1000000.0,
        }
        frame = encode_publish_data('test/perf', msg)
        # Frame should be ~4 MB payload + small header
        self.assertGreater(len(frame), 3_900_000)
        self.assertLess(len(frame), 4_100_000)

        decoder = FrameDecoder()
        frames = decoder.feed(frame)
        reconstructed = decode_publish_data(frames[0][1], frames[0][2])
        np.testing.assert_array_equal(reconstructed['data'], data)

    def test_no_data_field(self):
        msg = {'field': 'test', 'dtype': 'f32'}
        frame = encode_publish_data('test', msg)
        decoder = FrameDecoder()
        frames = decoder.feed(frame)
        reconstructed = decode_publish_data(frames[0][1], frames[0][2])
        self.assertIsNone(reconstructed['data'])


if __name__ == '__main__':
    unittest.main()
