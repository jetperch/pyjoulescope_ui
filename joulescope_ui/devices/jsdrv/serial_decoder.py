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

from enum import Enum
import numpy as np
import logging


class _State(Enum):
    WAIT_FOR_IDLE = 0
    WAIT_FOR_START_BIT = 1
    PARSE_FRAME = 2


class SerialDecoder:
    """Decode digital samples into serial messages

    :param sample_rate: The sample rate of the incoming digital data.
    :param baud_rate: The serial port baud rate.

    Messages are framed by either newline / carriage returns or
    serial line idle gaps.
    """
    def __init__(self, sample_rate=2000000, baud_rate=115200):
        self._sample_rate = sample_rate
        self._baud_rate = 0
        self._idle_level = 1  # 1 is "normal", 0 is inverted
        self._idle_threshold = 0
        self._idle_count = 0
        self._state = _State.WAIT_FOR_IDLE          # State machine state for bit processing.
        self._buffer = None                         # unpacked binary bit buffer.
        self._buffer_start_sample_id = None         # sample id for first bit in _buffer.
        self._message = []                          # current message being assembled.
        self._message_start_sample_id = None        # timestamp for the current message.
        self._previous_frame_end_sample_id = None   # timestamp for end of previous serial frame for idle detection.
        self._output_messages = []                  # the available output messages.
        self._log = logging.getLogger(__name__)
        self.baud_rate = baud_rate

    @property
    def baud_rate(self):
        return self._baud_rate

    @baud_rate.setter
    def baud_rate(self, value):
        self._message_complete()
        self._baud_rate = float(value)
        self._samples_per_bit = self._sample_rate / self._baud_rate
        self._idle_threshold = self._samples_per_bit * 10  # 10 bits per serial frame in N81.

    def _message_complete(self):
        if len(self._message):
            self._output_messages.append((self._message_start_sample_id, bytes(self._message)))
            self._message = []
            self._message_start_sample_id = None
        self._previous_frame_end_sample_id = None

    def process_block(self, block):
        """Process a new block of data.

        :param block: The map containing a new block of data.  Keys include:
            'sample_id' : integer, the starting sample id of this block
            'data'      : packed np.array (uint8) of digital samples.
                          Unpack with np.unpackbits(..., bitorder='little').

        :return: A list of (sample_id, message) tuples for any complete messages decoded.
            The sample_id is the start bit in the first character in the message.
        """
        block_sample_id = block['sample_id']
        unpacked = np.unpackbits(block['data'], bitorder='little')

        if self._buffer_start_sample_id is None:  # first block
            self._buffer = unpacked
            self._buffer_start_sample_id = block_sample_id
        else:
            # Check if there is a gap between blocks.
            expected_next_sample = self._buffer_start_sample_id + len(self._buffer)
            if block_sample_id > expected_next_sample:
                # detected missing samples
                self._message_complete()
                # Reset the buffer with the new block data.
                self._buffer = unpacked
                self._buffer_start_sample_id = block_sample_id
            else:
                # If the new block overlaps with existing data (should rarely happen), trim the overlap.
                if block_sample_id < expected_next_sample:
                    offset = expected_next_sample - block_sample_id
                    unpacked = unpacked[offset:]
                # Append the new samples to our existing buffer.
                self._buffer = np.concatenate((self._buffer, unpacked))

        buffer_idx = 0
        while buffer_idx < len(self._buffer):
            if self._state == _State.WAIT_FOR_IDLE:
                if self._buffer[buffer_idx] != self._idle_level:  # not idle
                    self._idle_count = 0
                    buffer_idx += 1
                else:  # idle
                    self._idle_count += 1
                    buffer_idx += 1
                    if self._idle_count >= self._idle_threshold:
                        self._idle_count = 0
                        self._state = _State.WAIT_FOR_START_BIT
            elif self._state == _State.WAIT_FOR_START_BIT:
                if self._buffer[buffer_idx] != self._idle_level:
                    self._state = _State.PARSE_FRAME
                else:
                    if self._previous_frame_end_sample_id is not None:
                        gap = self._buffer_start_sample_id + buffer_idx - self._previous_frame_end_sample_id
                        if gap > self._idle_threshold:
                            self._message_complete()
                    buffer_idx += 1
            elif self._state == _State.PARSE_FRAME:
                frame_start_sample_id = self._buffer_start_sample_id + buffer_idx
                last_bit_end = buffer_idx + int(10 * self._samples_per_bit * 0.997)
                if last_bit_end >= len(self._buffer):
                    # not enough data for full 10 bits.  Wait until next time
                    break

                # For each of the 10 bits, sample a window around the expected bit center.
                bits = []
                for bit_index in range(10):
                    # Expected center for this bit:
                    center = buffer_idx + (bit_index + 0.5) * self._samples_per_bit
                    center_idx = int(round(center))
                    # Use a small window (center_idx ±1 sample) for majority vote.
                    vote = int(np.median(self._buffer[center_idx - 1:center_idx + 2]))
                    bits.append(vote)

                if (bits[0] == self._idle_level) or (bits[-1] != self._idle_level):  # framing error
                    self._log.warning(f'framing error at {frame_start_sample_id}')
                    self._message_complete()
                    self._state = _State.WAIT_FOR_IDLE
                    buffer_idx = last_bit_end
                    continue

                # Assemble the data byte (bits 1 through 8); data is transmitted LSB first.
                byte_val = 0
                for bit_index in range(1, 9):
                    byte_val |= (bits[bit_index] << (bit_index - 1))
                if len(self._message) == 0:
                    self._message_start_sample_id = frame_start_sample_id

                if byte_val in b'\r\n':
                    self._message_complete()
                else:
                    self._message.append(byte_val)

                buffer_idx = last_bit_end
                self._previous_frame_end_sample_id = self._buffer_start_sample_id + buffer_idx
                self._state = _State.WAIT_FOR_START_BIT

        self._buffer_start_sample_id += buffer_idx
        self._buffer = self._buffer[buffer_idx:]
        output_messages, self._output_messages = self._output_messages, []
        return output_messages
