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

from joulescope_ui import N_, CAPABILITIES, register, Metadata, get_topic_name
from .device import Device, CAPABILITIES_OBJECT_OPEN
import copy
import numpy as np
import queue
import threading


EVENTS = {
    'statistics/!data': Metadata('obj', 'Periodic statistics data for each signal.'),
}

_SETTINGS_OBJ_ONLY = {
    'name': {
        'dtype': 'str',
        'brief': N_('Device name'),
        'detail': N_("""\
            The Joulescope UI automatically populates the device name
            with the device type and serial number.
    
            This setting allows you to change the default, if you wish, to better
            reflect how you are using your JS110.  This setting is
            most useful when you are instrumenting a system using 
            multiple Joulescopes."""),
        'default': None,
    },
    'info': {
        'dtype': 'obj',
        'brief': N_('Device information'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],
    },
    'state': {
        'dtype': 'int',
        'brief': N_('Device state indicator'),
        'options': [
            [0, 'closed'],
            [1, 'opening'],
            [2, 'open'],
            [3, 'closing'],
        ],
        'default': 0,
        'flags': ['ro', 'hide', 'skip_undo'],
    },
    'auto_open': {
        'dtype': 'bool',
        'brief': N_('Attempt to automatically open'),
        'default': True,
        'flags': ['ro', 'hide'],
    },
    'sources/1/name': {
        'dtype': 'str',
        'brief': N_('Device name'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],  # duplicated from settings/name
    },
    'sources/1/info': {
        'dtype': 'obj',
        'brief': N_('Device information'),
        'default': None,
        'flags': ['ro', 'hide', 'skip_undo'],  # duplicated from settings/info['device']
    },
}


_SETTINGS_CLASS = {
    'signal_frequency': {
        'dtype': 'int',
        'brief': N_('Signal frequency'),
        'detail': N_("""\
        This setting controls the output sampling frequency for the 
        measurement signals current, voltage, and power.  Use this
        setting to reduce the data storage requirements for long
        captures where lower temporal accuracy is sufficient. 

        The JS110 instrument always samples at 2 MHz and sends the
        raw samples to the host.
        This setting controls additional optional downsampling
        that is performed on the host."""),
        'options': [
            [2000000, "2 MHz"],
            [1000000, "1 MHz"],
            [500000, "500 kHz"],
            [200000, "200 kHz"],
            [100000, "100 kHz"],
            [50000, "50 kHz"],
            [20000, "20 kHz"],
            [10000, "10 kHz"],
            [5000, "5 kHz"],
            [2000, "2 kHz"],
            [1000, "1 kHz"],
            [500, "500 Hz"],
            [200, "200 Hz"],
            [100, "100 Hz"],
            [50, "50 Hz"],
            [20, "20 Hz"],
            [10, "10 Hz"],
            [5, "5 Hz"],
            [2, "2 Hz"],
            [1, "1 Hz"],
        ],
        'default': 2_000_000,
    },
    'statistics_frequency': {
        'dtype': 'int',
        'brief': N_('Statistics frequency'),
        'detail': N_("""\
            This setting controls the output frequency for 
            the statistics data that is displayed in the
            multimeter and value widgets.  Statistics data
            is computed over the full rate 2 MHz samples."""),
        'options': [
            [100, '100 Hz'],
            [50, '50 Hz'],
            [20, '20 Hz'],
            [10, '10 Hz'],
            [5, '5 Hz'],
            [2, '2 Hz'],
            [1, '1 Hz'],
        ],
        'default': 2,
    },
    'target_power': {
        'dtype': 'bool',
        'brief': N_('Target power'),
        'detail': N_("""\
            Toggle the connection between the current terminals.

            When enabled, current flows between the current terminals.
            When disabled, current cannot flow between the current terminals.
            In common system setups, this inhibits target power, which can
            be used to power cycle reset the target device."""),
        'default': True,
        'flags': ['hide'],  # Display in ExpandingWidget's header_ex_widget
    },
    'current_range': {
        'dtype': 'int',
        'brief': N_('Current range'),
        'detail': N_("""\
            Configure the J110's current range.  Most applications should
            use the default, "auto".

            Use the other manual settings with care.  It is very easy to
            configure a setting that saturates, which will ignore regions
            of current draw larger than the current range setting."""),
        'options': [
            [0x80, 'auto'],
            [0x01, '10 A'],
            [0x02, '2 A'],
            [0x04, '180 mA'],
            [0x08, '18 mA'],
            [0x10, '1.8 mA'],
            [0x20, '180 µA'],
            [0x40, '18 µA'],
        ],
        'default': 0x80,  # auto
    },
    'voltage_range': {
        'dtype': 'int',
        'brief': N_('Voltage range'),
        'detail': N_("""\
            Configure the JS110's voltage range."""),
        'options': [
            [0, '15 V'],
            [1, '5 V'],
        ],
        'default': 0,
    },
    'gpio_voltage': {
        'dtype': 'int',
        'brief': N_('GPIO voltage'),
        'detail': N_("""\
            Configure the JS110's reference voltage for the general-purpose
            inputs and outputs.
            
            The JS110's general-purpose outputs always remain powered.
            When set to "1", this can backpower unpowered targets."""),
        'options': [
            [0,    'off'],
            [1800, '1.8 V'],
            [2100, '2.1 V'],
            [2500, '2.5 V'],
            [2700, '2.7 V'],
            [3000, '3.0 V'],
            [3300, '3.3 V'],
            [3600, '3.6 V'],
            [5000, '5.0 V'],
        ],
        'default': 0,  # Vref
    },
    'out/0': {
        'dtype': 'bool',
        'brief': N_('GPO 0 output value'),
        'detail': N_('Turn the general-purpose output 0 on or off.'),
        'default': False,
    },
    'out/1': {
        'dtype': 'bool',
        'brief': N_('GPO 1 output value'),
        'detail': N_('Turn the general-purpose output 1 on or off.'),
        'default': False,
    },
    'current_ranging/type': {
        'dtype': 'int',
        'brief': N_('IRF type'),
        'detail': N_("""\
            Configure the current range filter (IRF) type which determines
            the filtering mechanism applied on current range changes.
            We do not recommend changing these settings for normal operation.
                     
            "interp" is the default setting which interpolates over
            the samples in the window using the value computed by
            the pre and post values.  This gives the most intuitive behavior.
            
            "mean" sets all samples in the window to the mean value.
            This results in a straight horizontal line that allows
            you to clearly see current range changes while still
            providing the best long-term current range measurement.
            
            "NaN" sets all samples in the window to NaN.
            
            "off" disables the current range filtering, and you will ' +
            see additional current range switching artifacts."""),
        'default': 'interp',
        'options': [
            [0, 'off'],
            [1, 'mean'],
            [2, 'interp'],
            [3, 'NaN'],
        ],
    },
    'current_ranging/samples_pre': {
        'dtype': 'int',
        'brief': N_('IRF pre'),
        'detail': N_("""\
            The number of samples before the current range window
            used to determine the mean.
            This value is ignored for all other IRF types."""),
        'default': 1,
        'options': [(d, str(d)) for d in range(9)],
    },
    'current_ranging/samples_window': {
        'dtype': 'int',
        'brief': N_('IRF window'),
        'detail': N_("""\
            Use "n" for automatic duration based upon known response time.
            Use "m" for shorter automatic duration that may result in min/max distortion.
            Use any other value to specify a fixed, manual window duration in samples."""),
        'default': 2,
        'options': [[1, 'm'], [2, 'n']] + [(d + 256, str(d)) for d in range(32)]
    },
    'current_ranging/samples_post': {
        'dtype': 'int',
        'brief': N_('IRF post'),
        'detail': N_("""\
            The number of samples after the current range window
            used to determine the mean.
            This value is ignored for all other IRF types."""),
        'default': 1,
        'options': [(d, str(d)) for d in range(9)],
    },
}


_SIGNALS = {
    'i': {
        'name': 'current',
        'dtype': 'f32',
        'units': 'A',
        'brief': N_('Current'),
        'detail': N_("""Enable the current signal streaming."""),
        'default': True,
        'topics': ('s/i/ctrl', 's/i/!data'),
    },
    'v': {
        'name': 'voltage',
        'dtype': 'f32',
        'units': 'V',
        'brief': N_('Voltage'),
        'detail': N_("""Enable the voltage signal streaming."""),
        'default': True,
        'topics': ('s/v/ctrl', 's/v/!data'),
    },
    'p': {
        'name': 'power',
        'dtype': 'f32',
        'units': 'W',
        'brief': N_('Power'),
        'detail': N_("""Enable the power signal streaming."""),
        'default': True,
        'topics': ('s/p/ctrl', 's/p/!data'),
    },
    'r': {
        'name': 'current range',
        'dtype': 'u8',
        'units': '',
        'brief': N_('Current Range'),
        'detail': N_("""\
            Enable the streaming for the selected current range.

            The current range is useful for understanding how your Joulescope
            autoranges to measure your current signal.  It can also be helpful
            in separating target system behavior from the small current range
            switching artifacts."""),
        'default': True,
        'topics': ('s/i/range/ctrl', 's/i/range/!data'),

    },
    '0': {
        'name': 'gpi[0]',
        'dtype': 'u1',
        'units': '',
        'brief': N_('GPI 0'),
        'detail': N_('Enable the general purpose input 0 signal streaming.'),
        'default': True,
        'topics': ('s/gpi/0/ctrl', 's/gpi/0/!data'),
    },
    '1': {
        'name': 'gpi[1]',
        'dtype': 'u1',
        'units': '',
        'brief': N_('GPI 1'),
        'detail': N_('Enable the general purpose input 1 signal streaming.'),
        'default': True,
        'topics': ('s/gpi/1/ctrl', 's/gpi/1/!data'),
    },
}


def _populate():
    global _SETTINGS_OBJ_ONLY, EVENTS
    for signal_id, value in _SIGNALS.items():
        _SETTINGS_OBJ_ONLY[f'signals/{signal_id}/name'] = {
            'dtype': 'str',
            'brief': N_('Signal name'),
            'flags': ['hide'],
            'default': value['brief'],
        }
        _SETTINGS_OBJ_ONLY[f'signals/{signal_id}/enable'] = {
            'dtype': 'bool',
            'brief': value['brief'],
            'detail': value['detail'],
            'flags': ['hide'],
            'default': value['default'],
        }
        EVENTS[f'signals/{signal_id}/!data'] = Metadata('obj', 'Signal data')


_populate()


class Js110(Device):

    SETTINGS = _SETTINGS_CLASS

    def __init__(self, driver, device_path):
        super().__init__(driver, device_path)
        _, model, serial_number = device_path.split('/')
        name = f'{model.upper()}-{serial_number}'
        self.EVENTS = copy.deepcopy(EVENTS)
        self.SETTINGS = copy.deepcopy(_SETTINGS_CLASS)
        for key, value in _SETTINGS_OBJ_ONLY.items():
            self.SETTINGS[key] = copy.deepcopy(value)
        self.SETTINGS['name']['default'] = name
        self.SETTINGS['sources/1/name']['default'] = device_path
        self._info = {
            'vendor': 'Jetperch LLC',
            'model': 'JS110',
            'version': {
                'hw': '1',
                'fw': '0.0.0',
                'fpga': '0.0.0',
            },
            'serial_number': device_path.split('/')[-1],
        }
        self.SETTINGS['info']['default'] = self._info
        self.SETTINGS['sources/1/info']['default'] = self._info

        self._param_map = {
            'voltage_range': 's/v/range/select',
            'gpio_voltage': 's/extio/voltage',
            'out/0': 's/gpo/0/value',
            'out/1': 's/gpo/1/value',
            'current_ranging/type': 's/i/range/mode',
            'current_ranging/samples_pre': 's/i/range/pre',
            'current_ranging/samples_post': 's/i/range/post',
            'signal_frequency': 'h/fs',
        }

        self._thread = None
        self._quit = False
        self._target_power_app = False
        self._queue = queue.Queue()
        self._statistics_offsets = None

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        self.pubsub.subscribe('registry/app/settings/target_power', self._on_target_power_app, ['pub', 'retain'])
        self.pubsub.publish(f'{topic}/settings/info', self._info)
        self.pubsub.publish(f'{topic}/settings/sources/1/info', self._info)
        for key, value in _SIGNALS.items():
            self._signal_forward(key, value['topics'][1], self.unique_id)
        if self.auto_open:
            self._log.info('auto open')
            self._open_req()

    def signal_subtopics(self, signal_id, topic_type):
        """Query the signal topics.

        :param signal_id: The signal id, such as 'i'.
        :param topic_type: The topic type to get, one of ['ctrl', 'data'].
        :return: The subtopic for this device.
        """
        s = _SIGNALS[signal_id]
        topics = s['topics']
        if topic_type == 'ctrl':
            return topics[0]
        elif topic_type == 'data':
            return topics[1]
        raise ValueError(f'unsupported topic_type {topic_type}')

    def _signal_forward(self, signal_id, dtopic, unique_id):
        utopic = f'events/signals/{signal_id}/!data'
        t = f'{get_topic_name(unique_id)}/{utopic}'
        self.pubsub.topic_add(t, Metadata('obj', 'signal'), exists_ok=True)
        self._driver_subscribe(dtopic, ['pub'], self._signal_forward_factory(signal_id, t))

    def _signal_forward_factory(self, signal_id, utopic):
        signal_info = _SIGNALS[signal_id]
        dtype = signal_info['dtype']
        field = signal_info['name']
        units = signal_info['units']
        def fn(dtopic, value):
            fwd = {
                'source': self._info,
                'sample_id': value['sample_id'] // value['decimate_factor'],
                'sample_freq': value['sample_rate'] // value['decimate_factor'],
                'utc': value['utc'],
                'field': field,
                'dtype': dtype,
                'units': units,
                'data': value['data'],
                'origin_sample_id': value['sample_id'],
                'orig_sample_freq': value['sample_rate'],
                'orig_decimate_factor': value['decimate_factor'],
            }
            fwd['data'] = value['data']
            self.pubsub.publish(utopic, fwd)
        return fn

    def _send_to_thread(self, cmd, args=None):
        self._queue.put((cmd, args), block=False)

    def finalize(self):
        self.on_action_finalize()
        self.pubsub.unsubscribe('registry/app/settings/target_power', self._on_target_power_app)
        super().finalize()

    def _open_req(self):
        # must be called from UI pubsub thread
        if self._thread is not None and self._ui_query('settings/state') == 3:
            self._close_req()
        if self._thread is None:
            self._log.info('open req start')
            try:
                while True:
                    self._queue.get(block=False)
            except queue.Empty:
                pass  # done!
            self._ui_publish('settings/state', 'opening')
            self._quit = False
            self._thread = threading.Thread(target=self._run)
            self._thread.start()
            self._log.info('open req done')

    def _close_req(self):
        # must be called from UI pubsub thread
        if self._thread is not None:
            self._log.info('closing')
            self._ui_publish('settings/state', 'closing')
            self._send_to_thread('close')
            self._quit = True
            self._thread.join()
            self._thread = None
            self._ui_publish('settings/state', 'closed')
            self._log.info('closed')

    def on_action_finalize(self):
        self._log.info('finalize')
        self._close_req()

    def _run_cmd_settings(self, topic, value):
        self._log.info(f'js110 setting(%s): %s <= %s', self, topic, value)
        if topic.endswith('/enable'):
            signal_id = topic.split('/')[1]
            t = _SIGNALS[signal_id]['topics'][0]
            if t is not None:
                self._driver_publish(t, bool(value), timeout=0)
            else:
                self._log.warning('invalid enable: %s', topic)
        elif topic in ['target_power', 'current_range']:
            self._current_range_update()
        elif topic == 'statistics_frequency':
            scnt = 2_000_000 // value
            self._driver_publish('s/stats/scnt', scnt, timeout=0)
        elif topic == 'current_ranging/samples_window':
            if value in [1, 'm']:
                self._driver_publish('s/i/range/win', 'm', timeout=0)
            if value in [2, 'n']:
                self._driver_publish('s/i/range/win', 'n', timeout=0)
            else:
                self._driver_publish('s/i/range/win_sz', int(value) - 256, timeout=0)
                self._driver_publish('s/i/range/win', 'manual', timeout=0)
        elif topic in self._param_map:
            device_topic = self._param_map[topic]
            self._driver_publish(device_topic, value, timeout=0)
        elif topic == 'name':
            self._ui_publish('settings/sources/1/name', value)
        elif topic in ['info', 'state', 'auto_open', 'out', 'enable',
                       'sources', 'sources/1', 'sources/1/info', 'sources/1/name',
                       'signals', 'current_ranging']:
            pass
        elif topic.startswith('signals/'):
            pass
        elif topic in ['state_req']:
            pass  # ignore: obsolete and removed
        else:
            self._log.warning('Unsupported topic %s', f'{get_topic_name(self)}/settings/{topic}')

    def _current_range_update(self):
        if self._target_power_app and self.target_power:
            self._log.info('current_range on %s', self.current_range)
            self._driver_publish('s/i/range/select', self.current_range, timeout=0)
        else:
            self._log.info('current_range off')
            self._driver_publish('s/i/range/select', 'off', timeout=0)

    def _run_cmd(self, cmd, args):
        if cmd == 'settings':
            self._run_cmd_settings(*args)
        elif cmd == 'current_range_update':
            self._current_range_update()
        elif cmd == 'close':
            pass  # handled in outer wrapper
        else:
            self._log.warning('Unhandled cmd: %s', cmd)

    def _run(self):
        self._log.info('thread start')
        if self._open():
            self._log.info('thread exit due to open fail')
            return 1
        self._ui_publish('settings/state', 'open')
        self._log.info('thread open complete')
        self.pubsub.capabilities_append(self, CAPABILITIES_OBJECT_OPEN)
        while not self._quit:
            try:
                cmd, args = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if cmd == 'close':
                break
            self._run_cmd(cmd, args)
        self._close()
        self.pubsub.capabilities_remove(self, CAPABILITIES_OBJECT_OPEN)
        self._log.info('thread stop')
        return 0

    def _open(self):
        self._log.info('open start')
        try:
            self._driver.open(self._path, 'restore')
        except Exception:
            self._log.warning('driver open failed')
            self._ui_publish('settings/state', 'closing')
            return 1
        try:
            self._info['version'] = {'hw': 1}  # could get more info
            self._info = copy.deepcopy(self._info)
            self._ui_publish('settings/info', self._info)
            self._driver_publish('s/i/lsb_src', 2, timeout=0)
            self._driver_publish('s/v/lsb_src', 3, timeout=0)
            self._driver_publish('s/stats/ctrl', 1, timeout=0)
            self._driver_subscribe('s/stats/value', 'pub', self._on_stats)
            self._ui_subscribe('settings', self._on_settings, ['pub', 'retain'])
        except Exception:
            self._log.exception('driver config failed')
            self._ui_publish('settings/state', 'closing')
            return 1
        self._log.info('open %s done', self.unique_id)
        return 0

    def _close(self):
        if self.state == 0:  # already closed
            return
        self._log.info('close %s start', self.unique_id)
        self._ui_unsubscribe('settings', self._on_settings)
        self._ui_publish('settings/state', 'closing')
        self._driver_unsubscribe('s/stats/value', self._on_stats)
        try:
            for t in _SIGNALS.values():
                self._driver_publish(t['topics'][0], 0, timeout=0)
            self._driver_publish('s/stats/ctrl', 0)
        except RuntimeError as ex:
            self._log.info('Exception during close cleanup: %s', ex)
        self._driver.close(self._path)
        self._log.info('close %s done', self.unique_id)

    def _on_stats(self, topic, value):
        if self._statistics_offsets is None:
            accum_sample_start = value['time']['accum_samples']['value'][-1]
            charge = value['accumulators']['charge']['value']
            energy = value['accumulators']['energy']['value']
            self._statistics_offsets = [accum_sample_start, charge, energy]
        accum_sample_start, charge, energy = self._statistics_offsets
        value['time']['accum_samples']['value'][0] = accum_sample_start
        value['accumulators']['charge']['value'] -= charge
        value['accumulators']['energy']['value'] -= energy
        value['source'] = {
            'unique_id': self.unique_id,
        }
        self._ui_publish('events/statistics/!data', value)

    def on_action_state_req(self, value):
        self.auto_open = bool(value)
        if value == 0:
            self._close_req()
        else:
            self._open_req()

    def _on_settings(self, topic, value):
        if self._thread is None:
            return
        t = f'{get_topic_name(self)}/settings/'
        if not topic.startswith(t):
            if topic != t[:-1]:
                self._log.warning('Invalid settings topic %s', topic)
            return
        topic = topic[len(t):]
        self._send_to_thread('settings', (topic, value))

    def _on_target_power_app(self, value):
        self._target_power_app = bool(value)
        self._send_to_thread('current_range_update', None)

    def on_action_accum_clear(self, topic, value):
        prev_value = self._statistics_offsets
        if value is None:
            self._statistics_offsets = None
        else:
            self._statistics_offsets = list(value)
        return topic, prev_value


register(Js110, 'JS110')
