# Copyright 2025 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from joulescope_ui.devices.jsdrv.serial_decoder import SerialDecoder
from joulescope_ui.devices.jsdrv.serial_encoder import SerialEncoder


class TestUartDecoder(unittest.TestCase):

    def test_character(self):
        encoder = SerialEncoder()
        decoder = SerialDecoder()
        messages = decoder.process_block(encoder.encode_idle())
        self.assertEqual(0, len(messages))

        messages = decoder.process_block(encoder.encode_message(b'a'))
        self.assertEqual(0, len(messages))

        messages = decoder.process_block(encoder.encode_idle())
        self.assertEqual(1, len(messages))
        self.assertEqual(176, messages[0][0])
        self.assertEqual(b'a', messages[0][1])

    def test_message(self):
        msg = b'hello world'
        decoder = SerialDecoder()
        messages = decoder.process_block(SerialEncoder().encode(msg))
        self.assertEqual(1, len(messages))
        self.assertEqual(msg, messages[0][1])

    def test_message_newline(self):
        msg = b'hello\r\nworld'
        decoder = SerialDecoder()
        messages = decoder.process_block(SerialEncoder().encode(msg))
        self.assertEqual(2, len(messages))
        self.assertEqual(176, messages[0][0])
        self.assertEqual(b'hello', messages[0][1])
        self.assertEqual(1391, messages[1][0])
        self.assertEqual(b'world', messages[1][1])

    def test_long_idle(self):
        encoder = SerialEncoder()
        decoder = SerialDecoder()
        self.assertEqual(1, len(decoder.process_block(encoder.encode('hello'))))
        self.assertEqual(0, len(decoder.process_block(encoder.encode_idle(100))))
        messages = decoder.process_block(encoder.encode('world'))
        self.assertEqual(1, len(messages))
        self.assertEqual(b'world', messages[0][1])

    def test_noise_set_bit(self):
        encoder = SerialEncoder()
        decoder = SerialDecoder()
        self.assertEqual(0, len(decoder.process_block(encoder.encode_idle(5))))
        msg = b'This long message should allow the bits to align in every possible way to test frame corruption'
        msg_block = encoder.encode_message(msg)
        data = msg_block['data']
        for i in range(len(data)):
            data[i] |= 0x01
        self.assertEqual(0, len(decoder.process_block(msg_block)))
        messages = decoder.process_block(encoder.encode_idle(2))
        self.assertEqual(1, len(messages))
        self.assertEqual(msg, messages[0][1])

    def test_noise_clear_bit(self):
        encoder = SerialEncoder()
        decoder = SerialDecoder()
        self.assertEqual(0, len(decoder.process_block(encoder.encode_idle(5))))
        msg = b'This long message should allow the bits to align in every possible way to test frame corruption'
        msg_block = encoder.encode_message(msg)
        data = msg_block['data']
        for i in range(len(data)):
            data[i] &= 0xfe
        self.assertEqual(0, len(decoder.process_block(msg_block)))
        messages = decoder.process_block(encoder.encode_idle(2))
        self.assertEqual(1, len(messages))
        self.assertEqual(msg, messages[0][1])

    def test_framing_error(self):
        encoder = SerialEncoder()
        decoder = SerialDecoder()
        self.assertEqual(0, len(decoder.process_block(encoder.encode_idle(1))))
        self.assertEqual(0, len(decoder.process_block(encoder.encode_message(b'hello'))))

        # All zeros for an idle duration is invalid framing
        block = encoder.encode_idle(1)
        block['data'][:] = 0
        messages = decoder.process_block(block)
        self.assertEqual(1, len(messages))
        self.assertEqual(b'hello', messages[0][1])

        # decoder should drop all data until the next idle
        self.assertEqual(0, len(decoder.process_block(encoder.encode_message(b'there'))))
        self.assertEqual(0, len(decoder.process_block(encoder.encode_idle(1))))

        # and then resume normal operation
        messages = decoder.process_block(encoder.encode(b'world'))
        self.assertEqual(1, len(messages))
        self.assertEqual(b'world', messages[0][1])
