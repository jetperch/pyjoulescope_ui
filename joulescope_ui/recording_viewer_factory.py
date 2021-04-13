# Copyright 2018 Jetperch LLC
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


from .recording_viewer_device_v1 import RecordingViewerDeviceV1
from .recording_viewer_device_v2 import RecordingViewerDeviceV2


_V1_PREFIX = bytes([0xd3, 0x74, 0x61, 0x67, 0x66, 0x6d, 0x74, 0x20, 0x0d, 0x0a, 0x20, 0x0a, 0x20, 0x20, 0x1a, 0x1c])
_V2_PREFIX = bytes([0x6a, 0x6c, 0x73, 0x66, 0x6d, 0x74, 0x0d, 0x0a, 0x20, 0x0a, 0x20, 0x1a, 0x20, 0x20, 0xb2, 0x1c])


def factory(parent, filename, cmdp=None, current_ranging_format=None):
    """Open the correct JLS file version based upon the file header prefix."""
    if hasattr(filename, 'read') and hasattr(filename, 'seek'):
        d = filename.read(16)
        filename.seek(0)
    else:
        with open(filename, 'rb') as f:
            d = f.read(16)
    if d == _V2_PREFIX:
        return RecordingViewerDeviceV2(parent, filename, cmdp)
    elif d == _V1_PREFIX:
        return RecordingViewerDeviceV1(parent, filename, cmdp, current_ranging_format=current_ranging_format)
    else:
        raise RuntimeError('unsupported file prefix')
