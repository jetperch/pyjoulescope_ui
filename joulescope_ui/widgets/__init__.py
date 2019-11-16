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

from . import control
from . import developer
from . import gpio
from . import multimeter
from . import single_value
# from . import uart
from . import waveform

WIDGETS = [
    control,
    developer,
    gpio,
    multimeter,
    single_value,
    waveform,
]


def widget_register(cmdp):
    widgets = {}
    cmdp.define('Widgets/', 'Widget settings.')
    cmdp.define('Widgets/active', 'The Widgets active in this profile.', dtype='obj', default=[])
    cmdp.define('Widgets/#enum',
                brief='Map of widget name to widget definition',
                dtype=object,
                default_profile_only=True)

    for widget in WIDGETS:
        r = widget.widget_register(cmdp)
        widgets[r['name']] = r
    cmdp['Widgets/#enum'] = widgets
    return widgets
