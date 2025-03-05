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

import numpy as np
import logging


class SerialEncoder:
    """Encode UART messages into digital data."""
    def __init__(self, sample_rate=2000000, baud_rate=115200):
        self._sample_rate = sample_rate
        self._baud_rate = baud_rate
        self._samples_per_bit = sample_rate / baud_rate
        self._sample_id = 0

    def encode(self, *args):
        data = self.encode_idle()
        for msg in args:
            d = self.encode_message(msg)
            k = self.encode_idle()
            data['data'] = np.concatenate((data['data'], d['data'], k['data']))
        return data

    def encode_message(self, message):
        """Encode a message into digital data.

        :param message: The message to encode.
        :return: the array of digital samples.
        """
        if isinstance(message, str):
            message = message.encode('utf-8')
        if not isinstance(message, bytes):
            raise ValueError('message must be bytes')
        bits = []
        for b in message:
            bits.append(0)  # start bit
            for bit_index in range(8):
                bits.append((b >> bit_index) & 1)  # LSB first
            bits.append(1)  # stop bit

        sample_id_start = int(self._sample_id)
        data = []
        for b in bits:
            sample_id_next = self._sample_id + self._samples_per_bit
            bit_len = int(sample_id_next) - int(self._sample_id)
            data.extend([b] * bit_len)
            self._sample_id = sample_id_next

        while len(data) % 8 != 0:
            data.append(1)
        self._sample_id = sample_id_start + len(data) * 8

        return {
            'sample_id': sample_id_start,
            'data': np.packbits(data, bitorder='little'),
        }

    def encode_idle(self, duration=None):
        """Generate idle samples for the specified duration in characters."""
        if duration is None:
            duration = 1
        samples = int(self._samples_per_bit * 10 * duration)
        bytes = (samples + 7) >> 3
        sample_id_start = int(self._sample_id)
        self._sample_id += bytes << 3
        data = np.empty(bytes, dtype=np.uint8)
        data[:] = 0xff
        return {
            'sample_id': sample_id_start,
            'data': data,
        }
