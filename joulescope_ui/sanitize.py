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

import re
import unicodedata
import hashlib


_re_str_to_filename = re.compile(r'[/\\?%*: ^\.|"<>\x7F\x00-\x1F]')

# https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
_WINDOWS_RESERVED = [
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
]


def str_to_filename(s: str, maxlen=None) -> str:
    """Convert a string to a safe filename.

    :param s: The string to convert to a filename.
    :param maxlen: The maximum length for the string.
    """
    if maxlen is None:
        maxlen = 255 - 16  # 255 FAT - room for extension
    s_no_sub = unicodedata.normalize('NFKD', s)
    s = _re_str_to_filename.sub('_', s_no_sub)
    if len(s) > maxlen:
        h = hashlib.sha256(s_no_sub.encode('utf-8')).hexdigest()
        h_len = len(h)
        if h_len >= maxlen:
            s = h[:maxlen]
        else:
            s = s[:maxlen - h_len] + h
    if s.split('.')[0].upper() in _WINDOWS_RESERVED:
        s = f'_{s}'
    if s[0] == '-':  # just because files starting with a dash can be annoying with command line tools
        s = '_' + s[1:]
    return s
