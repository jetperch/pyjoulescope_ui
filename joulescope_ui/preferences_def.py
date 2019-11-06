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

    # p.define('_window/', brief='Active UI window and tools configuration')
    # p.define('_window/geometry', default=None)
    # p.define('_window/contents', default=None)

    # --- GENERAL ---
    p.define('General/', 'General application settings.')
    p.define(
        name='General/data_path',
        brief='Default data directory',
        dtype='str',
        # dtype='path',
        # attributes=['exists', 'dir'],
        default=paths_current()['dirs']['data'])
    p.define(
        name='General/update_check',
        brief='Automatically check for software updates',
        dtype='bool',
        default=True)
    p.define(
        name='General/log_level',
        brief='The logging level',
        dtype='str',
        options=['OFF', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'ALL'],
        default='INFO')

    # --- DEVICE ---
    p.define('Device/', 'Joulescope device-specific default settings')
    p.define(
        name='Device/autostream',
        brief='Start streaming when the device connects',
        dtype='bool',
        default=True)
    p.define(
        name='Device/source',
        brief='Select the streaming data source',
        detail='Do not edit this setting for normal use',
        dtype='str',
        options=['off', 'raw', 'pattern_usb', 'pattern_control', 'pattern_sensor'],
        default='raw')
    p.define(
        name='Device/i_range',
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
        name='Device/v_range',
        brief='Select the voltage measurement range (gain)',
        dtype='str',
        options={
            '15V': {'brief': '15V range (recommended)', 'aliases': ['high']},
            '5V':  {'brief': '5V range with improved resolution for lower voltages', 'aliases': ['low']}},
        default='high')
    p.define(
        name='Device/rescan_interval',
        brief='The manual device rescan interval in seconds',
        detail='Device rescan normally happens when devices are connected' + \
            'to the computer.  For long running-tests, selecting an additional manual' +\
            'rescan interval assists recovery on USB and device failures.  However, ' +\
            'enabling this feature automatically selects a device on Device->disable.',
        dtype='str',
        options=['off', '1', '2', '5', '10', '20', '50'],
        default='off')
    p.define(
        name='Device/firmware_update',
        brief='Firmware update settings.',
        dtype='str',
        options=['never', 'auto', 'always'],
        default='auto')
    p.define(
        name='Device/on_close',
        brief='Device configuration on device close.',
        dtype='str',
        options=['keep', 'sensor_off', 'current_off', 'current_auto'],
        default='keep')
    p.define(
        name='Device/buffer_duration',
        brief='The stream buffer duration in seconds.',
        detail='Use care when setting this value. ' +\
            'The software requires 1.5 GB of RAM for every 60 seconds.',
        dtype='str',
        options=['15', '30', '60', '90', '120', '180', '240', '300'],
        default='30')

    # --- CURRENT RANGING ---
    p.define(
        name='Current Ranging/',
        brief='Configure the current range behavior including the filtering applied during range switches.')
    p.define(
        name='Current Ranging/type',
        brief='The filter type.',
        dtype='str',
        options=['off', 'mean', 'NaN'],
        default='mean')
    p.define(
        name='Current Ranging/samples_pre',
        brief='The number of samples before the range switch to include.',
        detail='Only valid for type "mean" - ignored for "off" and "NaN".',
        dtype='str',
        options=['0', '1', '2', '3', '4', '5', '6', '7', '8'],
        default='2')
    p.define(
        name='Current Ranging/samples_window',
        brief='The number of samples to adjust.',
        detail='Use "n" for automatic duration based upon known response time.',
        dtype='str',
        options=['n', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'],
        default='n')
    p.define(
        name='Current Ranging/samples_post',
        brief='The number of samples after the range switch to include.',
        detail='Only valid for type "mean" - ignored for "off" and "NaN".',
        dtype='str',
        options=['0', '1', '2', '3', '4', '5', '6', '7', '8'],
        default='2')

    # --- GPIO ---
    p.define('GPIO/', 'Joulescope device GPIO settings')
    p.define(
        name='GPIO/io_voltage',
        brief='The GPI/O high-level voltage.',
        dtype='str',
        options=['1.8V', '2.1V', '2.5V', '2.7V', '3.0V', '3.3V', '5.0V'],
        default='3.3V')
    p.define(
        name='GPIO/gpo0',
        brief='The GPO bit 0 output value.',
        dtype='str',
        options=['0', '1'],
        default='0')
    p.define(
        name='GPIO/gpo1',
        brief='The GPO bit 1 output value.',
        dtype='str',
        options=['0', '1'],
        default='0')
    p.define(
        name='GPIO/current_lsb',
        brief='The current signal least-significant bit mapping.',
        dtype='str',
        options=['normal', 'gpi0'],
        default='normal')
    p.define(
        name='GPIO/voltage_lsb',
        brief='The voltage signal least-significant bit mapping.',
        dtype='str',
        options=['normal', 'gpi1'],
        default='normal')

    # --- WAVEFORM ---
    p.define('Waveform/', 'Waveform display settings')
    p.define(
        name='Waveform/show_min_max',
        brief='Display the minimum and maximum for ease of finding short events.',
        dtype='str',
        options={
            'off':   {'brief': 'Hide the min/max indicators'},
            'lines': {'brief': 'Display minimum and maximum lines'},
            'fill':  {'brief': 'Fill the region between min and max, but may significantly reduce performance.'}},
        default='lines')
    p.define(
        name='Waveform/grid_x',
        brief='Display the x-axis grid',
        dtype='bool',
        default=True)
    p.define(
        name='Waveform/grid_y',
        brief='Display the y-axis grid',
        dtype='bool',
        default=True)
    p.define(
        name='Waveform/trace_width',
        brief='The trace width in pixels',
        detail='Increasing trace width SIGNIFICANTLY degrades performance',
        dtype='str',
        options=['1', '2', '4', '6', '8'],
        default='1')

    # --- DEVELOPER ---
    p.define('Developer/', 'Developer settings')
    p.define(
        name='Developer/compliance',
        brief='Compliance testing mode',
        dtype='bool',
        default=False)
    p.define(
        name='Developer/compliance_gpio_loopback',
        brief='GPI/O loopback for compliance testing',
        dtype='bool',
        default=False)

    return p
