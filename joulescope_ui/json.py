# Copyright 2022 Jetperch LLC
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



class CustomEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, bytes):
            return {
                '__type__': 'bytes',
                'data': base64.b64encode(obj).decode('utf-8')
            }
        elif type(obj) in [np.int8, np.int16, np.int32, np.int64,
                           np.uint8, np.uint16, np.uint32, np.uint64]:
            return int(obj)
        elif type(obj) in [np.float32, np.float64]:
            return float(obj)
        else:
            _log.warning('Cannot serialize object: %s %s', type(obj), obj)
            return None


def custom_decoder(obj):
    if '__type__' in obj:
        t = obj['__type__']
        if t == 'bytes':
            return base64.b64decode(obj['data'].encode('utf-8'))
    return obj


def dumps(obj, indent=2):
    return json.dumps(obj, cls=CustomEncoder, indent=indent)


def dump(obj, fh, indent=2):
    json.dump(obj, fh, cls=CustomEncoder, indent=indent)


def load(fh):
    return json.load(fh, object_hook=custom_decoder)


def loads(s):
    return json.loads(s, object_hook=custom_decoder)

