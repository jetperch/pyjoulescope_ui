# Copyright 2019 Jetperch LLC
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


signal_def = [
    {
        'name': 'current',
        'units': 'A',
        'y_limit': [-2.0, 10.0],
        'y_log_min': 1e-9,
        'y_range': 'auto',
        'show': True,
    },
    {
        'name': 'voltage',
        'units': 'V',
        'y_limit': [-1.2, 15.0],
        'y_range': 'auto',
        'show': True,
    },
    {
        'name': 'power',
        'units': 'W',
        'y_limit': [-2.4, 150.0],
        'y_log_min': 1e-9,
        'y_range': 'auto',
    },
    {
        'name': 'current_range',
        'y_limit': [-0.1, 8.1],
        'y_range': 'manual',
    },
    {
        'name': 'current_lsb',
        'display_name': 'in0',
        'y_limit': [-0.1, 1.1],
        'y_range': 'manual',
    },
    {
        'name': 'voltage_lsb',
        'display_name': 'in1',
        'y_limit': [-0.1, 1.1],
        'y_range': 'manual',
    },
]
