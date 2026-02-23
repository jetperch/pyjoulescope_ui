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

"""Wire protocol for the TCP socket API.

Frame format::

    [4B total_length][1B version][1B msg_type][2B header_length][header_json][binary_payload]

- total_length: uint32 big-endian, length of everything after total_length
- version: protocol version (currently 1)
- msg_type: message type identifier
- header_length: uint16 big-endian, length of JSON header bytes
- header_json: UTF-8 JSON-encoded header dict
- binary_payload: optional raw bytes (e.g. numpy array data)
"""

import json
import struct
import numpy as np

PROTOCOL_VERSION = 1
DEFAULT_PORT = 21861

# Frame header: version(1) + msg_type(1) + header_length(2) = 4 bytes
_FRAME_PREFIX = struct.Struct('>I')       # total_length
_FRAME_HEADER = struct.Struct('>BBH')     # version, msg_type, header_length

# Message types: client → server
MSG_AUTH = 0x00
MSG_SUBSCRIBE = 0x01
MSG_UNSUBSCRIBE = 0x02
MSG_PUBLISH = 0x03
MSG_PUBLISH_DATA = 0x04
MSG_QUERY = 0x05
MSG_QUERY_RESPONSE = 0x06
MSG_ENUMERATE = 0x07
MSG_ENUMERATE_RESPONSE = 0x08

# Message types: Qt inspection
MSG_QT_INSPECT = 0x10
MSG_QT_INSPECT_RESPONSE = 0x11
MSG_QT_ACTION = 0x12
MSG_QT_SCREENSHOT = 0x13
MSG_QT_SCREENSHOT_RESPONSE = 0x14

# Message types: control
MSG_AUTH_OK = 0xFD
MSG_ERROR = 0xFE
MSG_CLOSE = 0xFF

MSG_NAMES = {
    MSG_AUTH: 'auth',
    MSG_SUBSCRIBE: 'subscribe',
    MSG_UNSUBSCRIBE: 'unsubscribe',
    MSG_PUBLISH: 'publish',
    MSG_PUBLISH_DATA: 'publish_data',
    MSG_QUERY: 'query',
    MSG_QUERY_RESPONSE: 'query_response',
    MSG_ENUMERATE: 'enumerate',
    MSG_ENUMERATE_RESPONSE: 'enumerate_response',
    MSG_QT_INSPECT: 'qt_inspect',
    MSG_QT_INSPECT_RESPONSE: 'qt_inspect_response',
    MSG_QT_ACTION: 'qt_action',
    MSG_QT_SCREENSHOT: 'qt_screenshot',
    MSG_QT_SCREENSHOT_RESPONSE: 'qt_screenshot_response',
    MSG_AUTH_OK: 'auth_ok',
    MSG_ERROR: 'error',
    MSG_CLOSE: 'close',
}

# numpy dtype string ↔ numpy dtype mapping
DTYPE_MAP = {
    'f32': np.float32,
    'f64': np.float64,
    'u8': np.uint8,
    'u16': np.uint16,
    'u32': np.uint32,
    'u64': np.uint64,
    'i8': np.int8,
    'i16': np.int16,
    'i32': np.int32,
    'i64': np.int64,
    'u1': np.uint8,   # packed bits stored as uint8 bytes
}

DTYPE_REVERSE = {v: k for k, v in DTYPE_MAP.items() if k != 'u1'}
DTYPE_REVERSE[np.float32] = 'f32'  # ensure canonical names


def encode(msg_type, header=None, payload=None):
    """Encode a message into a wire frame.

    :param msg_type: The message type constant (MSG_*).
    :param header: Optional dict to JSON-encode as the header.
    :param payload: Optional bytes for the binary payload.
    :return: bytes ready to send on the wire.
    """
    if header is None:
        header_bytes = b''
    else:
        header_bytes = json.dumps(header, separators=(',', ':')).encode('utf-8')
    if payload is None:
        payload = b''
    frame_header = _FRAME_HEADER.pack(PROTOCOL_VERSION, msg_type, len(header_bytes))
    total_length = len(frame_header) + len(header_bytes) + len(payload)
    return _FRAME_PREFIX.pack(total_length) + frame_header + header_bytes + payload


def encode_publish_data(topic, data_msg):
    """Encode a streaming data publish message with numpy payload.

    :param topic: The PubSub topic string.
    :param data_msg: The data message dict containing 'data' (ndarray)
        and metadata fields.
    :return: bytes ready to send on the wire.
    """
    header = {
        'topic': topic,
        'source': data_msg.get('source'),
        'sample_id': data_msg.get('sample_id'),
        'sample_freq': data_msg.get('sample_freq'),
        'time': data_msg.get('time'),
        'field': data_msg.get('field'),
        'dtype': data_msg.get('dtype'),
        'units': data_msg.get('units'),
        'origin_sample_id': data_msg.get('origin_sample_id'),
        'origin_sample_freq': data_msg.get('origin_sample_freq'),
        'origin_decimate_factor': data_msg.get('origin_decimate_factor'),
    }
    data = data_msg.get('data')
    if data is not None and isinstance(data, np.ndarray):
        header['shape'] = list(data.shape)
        payload = data.tobytes()
    else:
        payload = b''
    return encode(MSG_PUBLISH_DATA, header, payload)


def decode_publish_data(header, payload):
    """Decode a streaming data publish message, reconstructing the numpy array.

    :param header: The decoded JSON header dict.
    :param payload: The raw binary payload bytes.
    :return: The reconstructed data message dict with 'data' as ndarray.
    """
    msg = dict(header)
    if payload and 'dtype' in header and 'shape' in header:
        dtype = DTYPE_MAP.get(header['dtype'], np.float32)
        shape = tuple(header['shape'])
        msg['data'] = np.frombuffer(payload, dtype=dtype).reshape(shape)
    else:
        msg['data'] = None
    msg.pop('shape', None)
    return msg


class FrameDecoder:
    """Incremental frame decoder for reading from a TCP stream."""

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data):
        """Feed raw bytes from the socket.

        :param data: bytes received from the socket.
        :return: List of decoded (msg_type, header_dict, payload_bytes) tuples.
        """
        self._buffer.extend(data)
        frames = []
        while len(self._buffer) >= _FRAME_PREFIX.size:
            total_length = _FRAME_PREFIX.unpack_from(self._buffer, 0)[0]
            frame_size = _FRAME_PREFIX.size + total_length
            if len(self._buffer) < frame_size:
                break
            frame_data = bytes(self._buffer[_FRAME_PREFIX.size:frame_size])
            del self._buffer[:frame_size]
            version, msg_type, header_length = _FRAME_HEADER.unpack_from(frame_data, 0)
            if version != PROTOCOL_VERSION:
                continue  # skip unknown versions
            offset = _FRAME_HEADER.size
            if header_length > 0:
                header = json.loads(frame_data[offset:offset + header_length])
            else:
                header = {}
            offset += header_length
            payload = frame_data[offset:]
            frames.append((msg_type, header, payload))
        return frames

    def reset(self):
        """Clear the internal buffer."""
        self._buffer.clear()
