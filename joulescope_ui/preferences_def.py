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

from joulescope_ui import VERSION
from joulescope_ui.paths import paths_current


def preferences_def(p):
    # --- METADATA ---
    p.define('_meta/', 'Preferences metadata')
    p.define('_meta/def_version', dtype='int', default=1)
    p.define('_meta/app_version', dtype='str', default=VERSION)

    # --- WINDOW ---
    # p.define('_window/', brief='Active UI window and tools configuration')
    # p.define('_window/geometry', default=None)
    # p.define('_window/contents', default=None)

    # --- GENERAL ---
    p.define('General/', 'General application settings.')
    p.define(
        topic='General/starting_profile',
        brief='The profile to use when launching the application.',
        dtype='str',
        options=lambda: ['previous', 'factory defaults'] + p.preferences.profiles,
        default='previous',
    )
    p.define(
        topic='General/data_path',
        brief='Default data directory',
        dtype='str',
        # dtype='path',
        # attributes=['exists', 'dir'],
        default=paths_current()['dirs']['data'])
    p.define(
        topic='General/update_check',
        brief='Automatically check for software updates',
        dtype='bool',
        default=True)
    p.define(
        topic='General/log_level',
        brief='The logging level',
        dtype='str',
        options=['OFF', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'ALL'],
        default='INFO')

    # --- DEVICE ---
    p.define('Device/', 'Joulescope device-specific default settings')
    p.define(
        topic='Device/autostream',
        brief='Start streaming when the device connects',
        dtype='bool',
        default=True)
    p.define('Device/parameter/', 'Joulescope device-specific parameters')
    p.define(
        topic='Device/parameter/source',
        brief='Select the streaming data source',
        detail='Do not edit this setting for normal use',
        dtype='str',
        options=['off', 'raw', 'pattern_usb', 'pattern_control', 'pattern_sensor'],
        default='raw')
    p.define(
        topic='Device/parameter/i_range',
        brief='Select the current measurement range (shunt resistor)',
        dtype='str',
        options={
            'auto':   {'brief': 'Perform fast autoranging to select the best shunt value'},
            'off':    {'brief': 'Disable the shunt for high impedance'},
            '10 A':   {'aliases': ['0'], 'brief': 'Least resistance (highest current range)'},
            '2 A':    {'aliases': ['1']},
            '180 mA': {'aliases': ['2']},
            '18 mA':  {'aliases': ['3']},
            '1.8 mA': {'aliases': ['4']},
            '180 µA': {'aliases': ['5']},
            '18 µA':  {'aliases': ['6'], 'brief': 'Most resistance (lowest current range)'}},
        default='auto')
    p.define(
        topic='Device/parameter/v_range',
        brief='Select the voltage measurement range (gain)',
        dtype='str',
        options={
            '15V': {'brief': '15V range (recommended)', 'aliases': ['high']},
            '5V':  {'brief': '5V range with improved resolution for lower voltages', 'aliases': ['low']}},
        default='15V')
    p.define(
        topic='Device/rescan_interval',
        brief='The manual device rescan interval in seconds',
        detail='Device rescan normally happens when devices are connected' + \
            'to the computer.  For long running-tests, selecting an additional manual' +\
            'rescan interval assists recovery on USB and device failures.  However, ' +\
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
    p.define(
        topic='Device/buffer_duration',
        brief='The stream buffer duration in seconds.',
        detail='Use care when setting this value. ' +\
            'The software requires 1.5 GB of RAM for every 60 seconds.',
        dtype='str',
        options=['15', '30', '60', '90', '120', '180', '240', '300'],
        default='30')
    p.define('Device/#state/name', dtype=str, default='')
    p.define('Device/#state/source', dtype=str, options=['None', 'USB', 'Buffer', 'File'], default='None')
    p.define('Device/#state/sample_drop_color', dtype=str, default='')
    p.define('Device/#state/play',   dtype=bool, default=False)
    p.define('Device/#state/record', dtype=bool, default=False)
    p.define('Device/#state/energy', dtype=str, default='')
    p.define('Device/#state/sampling_frequency', dtype=float, default=0.0)
    p.define('Device/#state/status', dtype=dict, default={})
    p.define('Device/#state/statistics', dtype=dict, default={})
    p.define('Device/#state/x_limits', dtype=object)  # [x_min, x_max]

    # --- CURRENT RANGING ---
    p.define(
        topic='Current Ranging/',
        brief='Configure the current range behavior including the filtering applied during range switches.')
    p.define(
        topic='Current Ranging/type',
        brief='The filter type.',
        dtype='str',
        options=['off', 'mean', 'NaN'],
        default='mean')
    p.define(
        topic='Current Ranging/samples_pre',
        brief='The number of samples before the range switch to include.',
        detail='Only valid for type "mean" - ignored for "off" and "NaN".',
        dtype='str',
        options=['0', '1', '2', '3', '4', '5', '6', '7', '8'],
        default='2')
    p.define(
        topic='Current Ranging/samples_window',
        brief='The number of samples to adjust.',
        detail='Use "n" for automatic duration based upon known response time.',
        dtype='str',
        options=['n', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'],
        default='n')
    p.define(
        topic='Current Ranging/samples_post',
        brief='The number of samples after the range switch to include.',
        detail='Only valid for type "mean" - ignored for "off" and "NaN".',
        dtype='str',
        options=['0', '1', '2', '3', '4', '5', '6', '7', '8'],
        default='2')

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

    # --- GPIO ---
    p.define('GPIO/', 'Joulescope device GPIO settings')
    p.define(
        topic='GPIO/io_voltage',
        brief='The GPI/O high-level voltage.',
        dtype='str',
        options=['1.8V', '2.1V', '2.5V', '2.7V', '3.0V', '3.3V', '5.0V'],
        default='3.3V')
    p.define(
        topic='GPIO/gpo0',
        brief='The GPO bit 0 output value.',
        dtype='str',
        options=['0', '1'],
        default='0')
    p.define(
        topic='GPIO/gpo1',
        brief='The GPO bit 1 output value.',
        dtype='str',
        options=['0', '1'],
        default='0')
    p.define(
        topic='GPIO/current_lsb',
        brief='The current signal least-significant bit mapping.',
        dtype='str',
        options=['normal', 'gpi0'],
        default='normal')
    p.define(
        topic='GPIO/voltage_lsb',
        brief='The voltage signal least-significant bit mapping.',
        dtype='str',
        options=['normal', 'gpi1'],
        default='normal')

    return p
