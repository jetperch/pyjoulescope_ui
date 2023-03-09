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

"""
Common definitions for JLS v2 file format use.
"""


TO_JLS_SIGNAL_NAME = {
    'i': 'current',
    'v': 'voltage',
    'p': 'power',
    'r': 'current_range',
    '0': 'gpi[0]',
    '1': 'gpi[1]',
    '2': 'gpi[2]',
    '3': 'gpi[3]',
    'T': 'trigger_in',
}


TO_UI_SIGNAL_NAME = {}


def _init():
    for key, value in list(TO_JLS_SIGNAL_NAME.items()):
        TO_JLS_SIGNAL_NAME[value] = value
        TO_UI_SIGNAL_NAME[value] = key
        TO_UI_SIGNAL_NAME[key] = key

_init()
