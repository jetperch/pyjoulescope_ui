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


class CustomEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, bytes):
            return {
                '__type__': 'bytes',
                'data': base64.b64encode(obj).decode('utf-8')
            }
        else:
            return obj


def custom_decoder(obj):
    if '__type__' in obj:
        t = obj['__type__']
        if t == 'bytes':
            return base64.b64decode(obj['data'].encode('utf-8'))
    return obj


def dump(obj, fh):
    json.dump(obj, fh, cls=CustomEncoder, indent=2)


def load(fh):
    return json.load(fh, object_hook=custom_decoder)


def loads(s):
    return json.loads(s, object_hook=custom_decoder)

