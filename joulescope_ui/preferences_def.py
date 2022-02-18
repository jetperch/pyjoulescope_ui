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

from joulescope.parameters_v1 import PARAMETERS
from joulescope_ui import __version__
from joulescope_ui.paths import paths_current


FONT_SIZES = [6, 7, 8, 9, 10, 11, 12, 14, 16, 20, 24, 30, 36, 48, 72]


_DEVICE_PARAMETER_DEFAULT_OVERRIDE = {
    'source': 'raw',
    'i_range': 'auto',
}


def preferences_def(p):
    # --- METADATA ---
    p.define('_meta/', 'Preferences metadata')
    p.define('_meta/def_version', dtype='int', default=1)
    p.define('_meta/app_version', dtype='str', default=__version__)

    # --- GENERAL ---
    p.define('General/', 'General application settings.')
    p.define(
        topic='General/starting_profile',
        brief='The profile to use when launching the application.',
        detail='Use "previous" to automatically restore the previous state. ' +
               'Since this preference selects the starting profile, the ' +
               'value is shared between all profiles.',
        dtype='str',
        options=lambda: ['previous', 'app defaults'] + [x for x in p.preferences.profiles if x != 'defaults'],
        default='previous',
        default_profile_only=True,
    )
    p.define(
        topic='General/data_path',
        brief='Default data directory',
        dtype='str',
        # dtype='path',
        # attributes=['exists', 'dir'],
        default=paths_current()['dirs']['data'])
    p.define(
        topic='General/data_path_type',
        brief='Specify the default data path.',
        dtype='str',
        options=['Use fixed data_path', 'Most recently saved', 'Most recently used'],
        default='Most recently used'),
    p.define('General/_path_most_recently_saved', dtype='str', default=paths_current()['dirs']['data']),
    p.define('General/_path_most_recently_used', dtype='str', default=paths_current()['dirs']['data']),
    p.define(
        topic='General/update_check',
        brief='Automatically check for software updates',
        dtype='bool',
        default=True)
    p.define(
        topic='General/update_channel',
        brief='The software release channel for updates',
        dtype='str',
        options=['alpha', 'beta', 'stable'],
        default='stable')
    p.define(
        topic='General/log_level',
        brief='The logging level',
        dtype='str',
        options=['OFF', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'ALL'],
        default='INFO')
    p.define(
        topic='General/window_location',
        brief='The window location',
        dtype='str',
        options=['center', 'previous'],
        default='center')
    p.define(
        topic='General/window_size',
        brief='The window size',
        dtype='str',
        options=['previous', 'minimum', '50%', '75%', '100%'],
        default='previous')
    p.define(
        topic='General/window_on_top',
        brief='Force the Joulescope UI window to stay on top.',
        detail='This feature keeps the Joulescope UI in the foreground, ' +
               'even if other applications are selected. ' +
               'This feature does not take effect until the Joulescope UI ' +
               'restarts.',
        dtype='bool',
        default=False)
    p.define(
        topic='General/developer',
        brief='Enable developer features',
        dtype='bool',
        default=False,
        default_profile_only=True)
    p.define(
        topic='General/process_priority',
        brief='The OS process priority',
        detail='This feature is currently only supported on Windows.',
        dtype='str',
        options=['normal', 'elevated'],
        default='elevated')
    p.define(
        topic='General/mru',
        brief='The number of most recently used files to remember.',
        dtype='str',
        options=['0', '3', '5', '10', '20'],
        default='10')
    p.define(topic='General/_mru_open', dtype=object, default=[])

    # --- UNITS ---
    p.define('Units/', 'Units to display.')
    p.define(
        topic='Units/accumulator',
        brief='The accumulation field to display.',
        dtype='str',
        options=['energy', 'charge'],
        default='energy')
    p.define(
        topic='Units/charge',
        brief='The units to display for charge, the integral of current.',
        dtype='str',
        options=['C', 'Ah'],
        default='C')
    p.define(
        topic='Units/energy',
        brief='The units to display for energy, the integral of power.',
        dtype='str',
        options=['J', 'Wh'],
        default='J')
    p.define('Units/elapsed_time',
        brief='The elapsed time format.',
        dtype='str',
        options=['seconds', 'D:hh:mm:ss'],
        default='seconds')

    # --- DEVICE ---
    p.define('Device/', 'Joulescope device-specific default settings')
    p.define(
        topic='Device/autostream',
        brief='Start streaming when the device connects',
        dtype='bool',
        default=True)
    p.define(
        topic='Device/rescan_interval',
        brief='The manual device rescan interval in seconds',
        detail='Device rescan normally happens when devices are connected ' +
               'to the computer.  For long running-tests, selecting an additional manual ' +
               'rescan interval assists recovery on USB and device failures.  However, ' +
               'enabling this feature automatically selects a device on Device->disable.',
        dtype='str',
        options=['off', '1', '2', '5', '10', '20', '50'],
        default='off')
    p.define(
        topic='Device/firmware_update',
        brief='Firmware update settings.',
        dtype='str',
        options=['never', 'auto', 'always'],
        default='auto')
    p.define(
        topic='Device/on_close',
        brief='Device configuration on device close.',
        dtype='str',
        options=['keep', 'sensor_off', 'current_off', 'current_auto'],
        default='keep')
    p.define('Device/setting/', 'Joulescope device-specific settings.')
    p.define('Device/extio/', 'Joulescope external general purpose input/output control.')
    p.define(
        topic='Device/Current Ranging/',
        brief='Configure the current range behavior including the filtering applied during range switches.')
    for parameter in PARAMETERS:
        if 'developer' in parameter.flags or 'hidden' in parameter.flags:
            prefix = '_'
        else:
            prefix = ''
        default = _DEVICE_PARAMETER_DEFAULT_OVERRIDE.get(parameter.name, parameter.default)
        if parameter.path in ['setting', 'extio']:
            topic = f'Device/{parameter.path}/{prefix}{parameter.name}'
        elif parameter.path == 'current_ranging':
            if parameter.name == 'current_ranging':
                continue
            name = parameter.name.replace('current_ranging_', '')
            topic = f'Device/Current Ranging/{name}'
        else:
            continue
        p.define(
            topic=topic,
            brief=parameter.brief,
            detail=parameter.detail,
            dtype='str',
            options=[x[0] for x in parameter.options],
            default=default)

    p.define('Device/#state/name', dtype=str, default='')
    p.define('Device/#state/source', dtype=str, options=['None', 'USB', 'Buffer', 'File'], default='None')
    p.define('Device/#state/stream', dtype=str, default='inactive')
    p.define('Device/#state/play',   dtype=bool, default=False)
    p.define('Device/#state/record', dtype=bool, default=False)
    p.define('Device/#state/record_statistics', dtype=bool, default=False)
    p.define('Device/#state/sampling_frequency', dtype=float, default=0.0)
    p.define('Device/#state/status', dtype=dict, default={})
    p.define('Device/#state/statistics', dtype=dict, default={})
    p.define('Device/#state/x_limits', dtype=object)  # [x_min, x_max]

    # --- Appearance ---
    p.define('Appearance/', 'Adjust the UI appearance')
    p.define('Appearance/Theme', dtype=str, options=['system', 'js1.dark', 'js1.light'], default='js1.dark')
    p.define('Appearance/__index__', dtype=dict, default={})
    p.define('Appearance/Fonts/', 'Adjust fonts')
    p.define('Appearance/Colors/', 'Adjust colors')
    p.define('Appearance/Colors/ui_override', dtype=str, default='')

    # --- Plugins ---
    p.define('Plugins/', 'Joulescope UI Plugins')
    p.define('Plugins/#registered', dtype=object, default=None)

    # --- DataView ---
    p.define('DataView/', 'Data view configuration for waveform')
    p.define(
        'DataView/#service/x_change_request', dtype=object,
        brief='Request an x-axis range change.',
        detail='List of [x_min: float, x_max: float, x_count: int] where\n' +
               'x_min: The minimum x_axis value to display in the range.\n' +
               'x_max: The maximum x_axis value to display in the range.\n' +
               'x_count: The desired number of samples in the range.\n')
    p.define(
        'DataView/#service/range_statistics', dtype=object,
        brief='Request statistics over data ranges.',
        detail='dict containing:\n' +
               'ranges: list of (x_start, x_stop) ranges in view seconds\n' +
               'source_id: Source indicator to allow for coalescence.\n' +
               'reply_topic: The topic for the response which is a dict with\n' +
               'request and response.  On error, response is None.\n' +
               'On success, response is a list of joulescope.view.View.statistics_get\n' +
               'return values.')
    p.define(
        'DataView/#data', dtype=object,
        brief='The latest data from the view.')

    return p
