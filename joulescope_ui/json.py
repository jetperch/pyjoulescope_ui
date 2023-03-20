# Copyright 2022-2023 Jetperch LLC
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

import base64
import json
import numpy as np
import logging


_log = logging.getLogger(__name__)
_DTYPE_MAP = {
    np.float32: 'float32',
    np.float64: 'float64',
    np.uint8:  'uint8',
    np.uint16: 'uint16',
    np.uint32: 'uint32',
    np.uint64: 'uint64',
    np.int8:  'int8',
    np.int16: 'int16',
    np.int32: 'int32',
    np.int64: 'int64',
}


def _typed_copy_encoder(item):
    if isinstance(item, tuple):
        return {
            '__type__': 'tuple',
            'data': item,
        }
    elif isinstance(item, list):
        return [_typed_copy_encoder(i) for i in item]
    elif isinstance(item, dict):
        return {key: _typed_copy_encoder(value) for key, value in item.items()}
    elif isinstance(item, bytes):
        return {
            '__type__': 'bytes',
            'data': base64.b64encode(item).decode('utf-8')
        }
    elif isinstance(item, np.ndarray):
        return {
            '__type__': 'ndarray',
            'dtype': _DTYPE_MAP.get(item.dtype),
            'data': item.tolist(),
        }
    else:
        return item


class CustomEncoder(json.JSONEncoder):

    def default(self, obj):
        if type(obj) in [np.int_, np.intc, np.intp,
                         np.int8, np.int16, np.int32, np.int64,
                         np.uint8, np.uint16, np.uint32, np.uint64]:
            return int(obj)
        elif type(obj) in [np.float_, np.float16, np.float32, np.float64]:
            return float(obj)
        else:
            _log.warning('Cannot serialize object: %s %s', type(obj), obj)
            return {
                '__type__': 'unserializable',
            }


def custom_decoder(obj):
    if '__type__' in obj:
        t = obj['__type__']
        if t == 'bytes':
            return base64.b64decode(obj['data'].encode('utf-8'))
        elif t == 'ndarray':
            return np.array(obj['data'], dtype=obj['dtype'])
        elif t == 'tuple':
            return tuple(obj['data'])
        elif t == 'unserializable':
            return None
    return obj


def dumps(obj, indent=2):
    obj = _typed_copy_encoder(obj)
    return json.dumps(obj, cls=CustomEncoder, indent=indent)


def dump(obj, fh, indent=2):
    obj = _typed_copy_encoder(obj)
    json.dump(obj, fh, cls=CustomEncoder, indent=indent)


def load(fh):
    return json.load(fh, object_hook=custom_decoder)


def loads(s):
    return json.loads(s, object_hook=custom_decoder)
