# Copyright 2018-2024 Jetperch LLC
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


from joulescope_ui import N_
import sys


_TITLE = N_('Getting Started with Your Joulescope')

_SAFETY_TITLE = N_('Safety')
_SAFETY_CAUTION = N_('The voltage between any sensor port must never exceed ±15V.')
_SAFETY_JS220 = N_('The JS220 sensor ports are Current+, Current-, Voltage+, Voltage-.')
_SAFETY_JS110 = N_('The JS110 sensor ports are IN+, IN- OUT+, and OUT-.')
_SAFETY_ALL = N_("""The sensor ports are electrically isolated from USB.  The voltage between 
any sensor port and USB ground must never exceed ±48V. 
The GPI/O and trigger ports are referenced to USB ground.""")

_CONNECT_TITLE = N_('Connect')
_CONNECT_1 = N_("""Connect Joulescope's USB port to your computer using the provided cable.
Use an adapter or suitable cable if your computer only has USB Type C ports.""")
_CONNECT_JS220 = N_("""For the JS220, connect the current port between the power supply and
the device under test.  Connect the voltage port to the power supply.
See the Joulescope JS220 User's Guide for more connection examples.""")
_CONNECT_JS110 = N_("""For the JS110, connect the Joulescope IN port to your power supply.
Connect the Joulescope OUT port to your target device.""")

_MEASURE_TITLE = N_('Measure')
_MEASURE_MULTIMETER = N_("""The Joulescope software starts in the Multimeter View displaying
the value current, voltage, power, and energy.""")
_MEASURE_OSCILLOSCOPE = N_("""Select View → Oscilloscope to switch to the Oscilloscope View
and explore changes over time.""")
_OSCILLOSCOPE_1 = N_('Press the Play/Pause button to start and stop sample streaming.')
_OSCILLOSCOPE_2 = N_('Use the scroll wheel to zoom the time x-axis.')
_OSCILLOSCOPE_3 = N_('Left-click and drag to pan in time.')
_OSCILLOSCOPE_4 = N_('Right-click for context sensitive menus and more options.')
_OSCILLOSCOPE_4b = N_('Control-click or two finger click for context sensitive menus and more options.')

if sys.platform == 'darwin':
    _OSCILLOSCOPE_4 = _OSCILLOSCOPE_4b

_SUPPORT_TITLE = N_('Support')
_SUPPORT_BODY = N_('Click on the help icon at the bottom left for more information and support options.')


GETTING_STARTED = f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
  <title>{_TITLE}</title>
  {{style}}
</head>

<body>

<h1>{_SAFETY_TITLE}</h1>
<p>⚠ {_SAFETY_CAUTION} ⚠</p>
<p>{_SAFETY_JS220}</p>
<p>{_SAFETY_JS110}</p>
<p>{_SAFETY_ALL}</p>

<h1>{_CONNECT_TITLE}</h1>
<p>{_CONNECT_1}</p>
<p>{_CONNECT_JS220}</p>
<p>{_CONNECT_JS110}</p>

<h1>{_MEASURE_TITLE}</h1>
<p>{_MEASURE_MULTIMETER}</p>
<p>{_MEASURE_OSCILLOSCOPE}</p>
<ul>
  <li>{_OSCILLOSCOPE_1}</li>
  <li>{_OSCILLOSCOPE_2}</li>
  <li>{_OSCILLOSCOPE_3}</li>
  <li>{_OSCILLOSCOPE_4}</li>
</ul>

<h1>{_SUPPORT_TITLE}</h1>
<p>{_SUPPORT_BODY}</p>

</body>
</html>
"""

