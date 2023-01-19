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

from joulescope_ui.capabilities import CAPABILITIES
from .device import Device
from joulescope_ui import N_, get_topic_name
from joulescope_ui.metadata import Metadata
import copy
import queue
import threading


EVENTS = {
    'statistics/!data': Metadata('obj', 'Periodic statistics data for each signal.'),
    'signals/current/!data': Metadata('obj', 'Streaming sample data for the current signal.'),
    'signals/voltage/!data': Metadata('obj', 'Streaming sample data for the voltage signal.'),
    'signals/power/!data': Metadata('obj', 'Streaming sample data for the power signal.'),
    # todo other signals, INx, TRIGGER, UART, ...
}

SETTINGS = {
    'name': {
        'dtype': 'str',
        'brief': N_('Device name'),
        'detail': N_("""\
        The Joulescope UI automatically populates the device name
        with the device type and serial number.
        
        This setting allows you to change the default, if you wish, to better
        reflect how you are using your JS220.  This setting is
        most useful when you are instrumenting a system using 
        multiple Joulescopes."""),
        'default': None,
    },
    'info': {
        'dtype': 'obj',
        'brief': N_('Device information'),
        'default': None,
        'flags': ['ro', 'hidden'],
    },
    'signal_frequency': {
        'dtype': 'int',
        'brief': N_('Signal frequency'),
        'detail': N_("""\
        This setting controls the output sampling frequency for the 
        measurement signals current, voltage, and power.  Use this
        setting to reduce the data storage requirements for long
        captures where lower temporal accuracy is sufficient. 
        
        The JS220 instrument always samples at 2 MHz and 
        then downsamples to 1 MHz.  This setting controls 
        additional optional downsampling."""),
        'options': [
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
        'default': 1_000_000,
    },
    'statistics_frequency': {
        'dtype': 'int',
        'brief': N_('Statistics frequency'),
        'detail': N_("""\
            This setting controls the output frequency for 
            the statistics data that is displayed in the
            multimeter and value widgets.  Statistics data
            is computed over the full rate 1 MHz samples."""),
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
    'current_range': {
        'dtype': 'int',
        'brief': N_('Current range'),
        'detail': N_("""\
            Configure the JS220's current range.  Most applications should
            use the default, "auto".  "off" prohibits current from flowing
            between the current terminals, which can be used to power off
            the device under test.  
            
            Use the other manual settings with care.  It is very easy to
            configure a setting that saturates, which will ignore regions
            of current draw larger than the current range setting."""),
        'options': [
            [-1, 'auto'],
            [129, '10 A'],
            [130, '180 mA'],
            [132, '18 mA'],
            [136, '1.8 mA'],
            [144, '180 µA'],
            [160, '18 µA'],
            [0, 'off'],
        ],
        'default': -1,  # auto
    },
    # current range min
    # current range max
    'voltage_range': {
        'dtype': 'int',
        'brief': N_('Voltage range'),
        'detail': N_("""\
            Configure the JS220's voltage range.  Most applications should
            use the default, "auto"."""),
        'options': [
            # [-1, 'auto'],
            [0, '15 V'],
            [1, '2 V'],
        ],
        'default': 0,  # todo auto
    },
    'gpio_voltage': {
        'dtype': 'int',
        'brief': N_('GPIO voltage'),
        'detail': N_("""\
            Configure the JS220's reference voltage for the general-purpose
            inputs and outputs.
            
            We recommend using "Vref" when attaching
            general-purpose outputs (GPO) to other equipment.  Using Vref
            prevents the GPO from backpowering target devices when they
            powered down.  The Vref signal and general-purpose inputs
            are all extremely high impedance to minimize leakage currents.
            
            "3.3 V" uses an internally-generated 3.3V reference voltage."""),
        'options': [
            [0, 'Vref'],
            [1, '3.3 V'],
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
    'out/T': {
        'dtype': 'bool',
        'brief': N_('Trigger output value'),
        'detail': N_("""Turn the trigger output on or off.
        
            The trigger must also be configured for output for this
            setting to have any effect."""),
        'default': False,
    },
    'enable/i': {
        'dtype': 'bool',
        'brief': N_('Current'),
        'detail': N_("""Enable the current signal streaming."""),
        'default': True,
    },
    'enable/v': {
        'dtype': 'bool',
        'brief': N_('Voltage'),
        'detail': N_("""Enable the voltage signal streaming."""),
        'default': True,
    },
    'enable/p': {
        'dtype': 'bool',
        'brief': N_('Power'),
        'detail': N_("""Enable the power signal streaming."""),
        'default': False,
    },
    'enable/r': {
        'dtype': 'bool',
        'brief': N_('Current Range'),
        'detail': N_("""\
            Enable the streaming for the selected current range.
        
            The current range is useful for understanding how your Joulescope
            autoranges to measure your current signal.  It can also be helpful
            in separating target system behavior from the small current range
            switching artifacts."""),
        'default': False,
    },
    'enable/0': {
        'dtype': 'bool',
        'brief': N_('GPI 0'),
        'detail': N_('Enable the general purpose input 0 signal streaming.'),
        'default': False,
    },
    'enable/1': {
        'dtype': 'bool',
        'brief': N_('GPI 1'),
        'detail': N_('Enable the general purpose input 0 signal streaming.'),
        'default': False,
    },
    'enable/2': {
        'dtype': 'bool',
        'brief': N_('GPI 2'),
        'detail': N_('Enable the general purpose input 2 signal streaming.'),
        'default': False,
    },
    'enable/3': {
        'dtype': 'bool',
        'brief': N_('GPI 3'),
        'detail': N_('Enable the general purpose input 3 signal streaming.'),
        'default': False,
    },
    'enable/T': {
        'dtype': 'bool',
        'brief': N_('Trigger input'),
        'detail': N_('Enable the trigger input signal streaming.'),
        'default': False,
    },
}


_SETTINGS_MAP = {
    'signal_frequency': 'h/fs',

}


_ENABLE_MAP = {
    'enable/i': 's/i/ctrl',
    'enable/v': 's/v/ctrl',
    'enable/p': 's/p/ctrl',
    'enable/r': 's/i/range/ctrl',
    'enable/0': 's/gpi/0/ctrl',
    'enable/1': 's/gpi/1/ctrl',
    'enable/2': 's/gpi/2/ctrl',
    'enable/3': 's/gpi/3/ctrl',
    'enable/T': 's/gpi/7/ctrl',
}


_GPO_BIT = {
    '0': 1 << 0,
    '1': 1 << 1,
    'T': 1 << 7,
}


class Js220(Device):

    SETTINGS = SETTINGS

    def __init__(self, driver, device_path):
        super().__init__(driver, device_path)
        self.EVENTS = EVENTS
        self.SETTINGS = copy.deepcopy(SETTINGS)
        print(f'device_path = {device_path}')
        self.SETTINGS['name']['default'] = device_path
        self.SETTINGS['info']['default'] = {
            'vendor': 'Jetperch LLC',
            'model': 'JS220',
            'serial_number': device_path.split('/')[-1],
        }
        self._statistics_offsets = []
        self._on_settings_fn = self._on_settings
        self._on_stats_fn = self._on_stats  # for unsub
        self._thread = None
        self._queue = queue.Queue()

    def _send_to_thread(self, cmd, args=None):
        self._queue.put((cmd, args), block=False)

    def finalize(self):
        self._log.info('finalize')
        self.on_action_close()

    def on_action_open(self):
        self.on_action_close()
        self._log.info('open')
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def on_action_close(self):
        if self._thread is not None:
            self._log.info('close')
            self._send_to_thread('close')
            self._thread.join()
            self._thread = None

    def _run_cmd_settings(self, topic, value):
        self._log.info(f'setting: %s <= %s', topic, value)
        if topic.startswith('enable/'):
            t = _ENABLE_MAP.get(topic)
            if t is not None:
                self._driver_publish(t, bool(value))
            else:
                self._log.warning('invalid enable: %s', topic)
        elif topic.startswith('out/'):
            v = _GPO_BIT[topic[4:]]
            t = 's/gpo/+/!set' if bool(value) else 's/gpo/+/!clr'
            self._driver_publish(t, v)
        elif topic == 'signal_frequency':
            self._driver_publish('h/fs', int(value))
        elif topic == 'statistics_frequency':
            scnt = 1_000_000 // value
            self._driver_publish('s/stats/scnt', scnt)
        elif topic == 'current_range':
            value = int(value)
            if value == 7:
                self._driver_publish('s/i/range/mode', 'off')
            elif value == -1:
                self._driver_publish('s/i/range/mode', 'auto')
            else:
                self._driver_publish('s/i/range/select', value)
                self._driver_publish('s/i/range/mode', 'manual')
        elif topic == 'voltage_range':
            self._driver_publish('s/v/range/mode', 'manual')  # todo auto
            self._driver_publish('s/v/range/select', value)

    def _run_cmd(self, cmd, args):
        if cmd == 'settings':
            self._run_cmd_settings(*args)
        elif cmd == 'close':
            pass  # handled in outer wrapper
        else:
            self._log.warning('Unhandled cmd: %s', cmd)

    def _run(self):
        self._log.info('thread start')
        self._open()
        self._log.info('thread open complete')
        while True:
            cmd, args = self._queue.get()
            if cmd == 'close':
                self._close()
                break
            self._run_cmd(cmd, args)
        self._log.info('thread stop')
        return 0

    def _open(self):
        self._log.info('open %s start', self.unique_id)
        self._driver.open(self._path, 'restore')
        self._driver_publish('s/stats/ctrl', 1)
        self._driver_subscribe('s/stats/value', 'pub', self._on_stats_fn)
        self._ui_subscribe('settings', self._on_settings_fn, ['pub', 'retain'])
        self._log.info('open %s done', self.unique_id)

    def _close(self):
        self._log.info('close %s start', self.unique_id)
        self._driver_unsubscribe('s/stats/value', self._on_stats_fn)
        try:
            for t in _ENABLE_MAP.values():
                self._driver_publish(t, 0)
            self._driver_publish('s/stats/ctrl', 0)
        except RuntimeError as ex:
            self._log.info('Exception during close cleanup: %s', ex)
        self._driver.close(self._path)
        self._log.info('close %s done', self.unique_id)

    def _on_stats(self, topic, value):
        period = 1 / 2e6
        s_start, s_stop = [x * period for x in value['time']['samples']['value']]

        if not len(self._statistics_offsets):
            duration = s_start
            charge = value['accumulators']['charge']['value']
            energy = value['accumulators']['energy']['value']
            offsets = [duration, charge, energy]
            self._statistics_offsets = [duration, charge, energy]
        duration, charge, energy = self._statistics_offsets
        value['time']['range'] = {
            'value': [s_start - duration, s_stop - duration],
            'units': 's'
        }
        value['time']['delta'] = {'value': s_stop - s_start, 'units': 's'}
        value['accumulators']['charge']['value'] -= charge
        value['accumulators']['energy']['value'] -= energy
        for k in value['signals'].values():
            k['µ'] = k['avg']
            k['σ2'] = {'value': k['std']['value'] ** 2, 'units': k['std']['units']}
            if 'integral' in k:
                k['∫'] = k['integral']
        value['source'] = {
            'unique_id': self.unique_id,
        }
        self._ui_publish('events/statistics/!data', value)

    def _on_settings(self, topic, value):
        if self._thread is None:
            return
        t = f'{get_topic_name(self)}/settings/'
        if not topic.startswith(t):
            self._log.warning('Invalid settings topic %s', topic)
        topic = topic[len(t):]
        self._send_to_thread('settings', (topic, value))
