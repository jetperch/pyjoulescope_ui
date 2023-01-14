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
from joulescope_ui import N_
from joulescope_ui.metadata import Metadata


EVENTS = {
    'statistics/!data': Metadata('obj', 'Periodic statistics data for each signal.'),
    'signals/current/!data': Metadata('obj', 'Streaming sample data for the current signal.'),
    'signals/voltage/!data': Metadata('obj', 'Streaming sample data for the voltage signal.'),
    'signals/power/!data': Metadata('obj', 'Streaming sample data for the power signal.'),
    # todo other signals, INx, TRIGGER, UART, ...
}

SETTINGS = {
    'signal_frequency': {
        'dtype': 'float',
        'brief': N_('Signal frequency'),
        'default': 1_000_000,
    },
    'statistics_frequency': {
        'dtype': 'int',
        'brief': N_('Statistics frequency'),
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
        'default': -1,  # auto
    },
    # current range min
    # current range max
    'voltage_range': {
        'dtype': 'int',
        'brief': N_('Voltage range'),
        'default': -1,  # auto
    },
    'gpio_voltage': {
        'dtype': 'int',
        'brief': N_('GPIO voltage'),
        'default': 0,  # Vref
    },
    'out/0': {
        'dtype': 'bool',
        'brief': N_('GPO 0 output value'),
        'default': False,
    },
    'out/1': {
        'dtype': 'bool',
        'brief': N_('GPO 1 output value'),
        'default': False,
    },
    'out/T': {
        'dtype': 'bool',
        'brief': N_('Trigger output value'),
        'default': False,
    },
    'enable/i': {
        'dtype': 'bool',
        'brief': N_('Current'),
        'default': True,
    },
    'enable/v': {
        'dtype': 'bool',
        'brief': N_('Voltage'),
        'default': True,
    },
    'enable/p': {
        'dtype': 'bool',
        'brief': N_('Power'),
        'default': False,
    },
    'enable/r': {
        'dtype': 'bool',
        'brief': N_('Current Range'),
        'default': False,
    },
    'enable/0': {
        'dtype': 'bool',
        'brief': N_('General-purpose input 0'),
        'default': False,
    },
    'enable/1': {
        'dtype': 'bool',
        'brief': N_('General-purpose input 1'),
        'default': False,
    },
    'enable/2': {
        'dtype': 'bool',
        'brief': N_('General-purpose input 2'),
        'default': False,
    },
    'enable/3': {
        'dtype': 'bool',
        'brief': N_('General-purpose input 3'),
        'default': False,
    },
    'enable/T': {
        'dtype': 'bool',
        'brief': N_('Trigger input'),
        'default': False,
    },
}


class Js220(Device):

    SETTINGS = SETTINGS

    def __init__(self, driver, device_path):
        super().__init__(driver, device_path)
        self.EVENTS = EVENTS
        self._cmd_complete_fn = self._cmd_complete
        self._statistics_offsets = []
        self._on_stats_fn = self._on_stats  # for unsub

    def _cmd_complete(self, topic, value):
        if not topic.startswith(self._path):
            self._log.warning('Unexpect topic: %s', topic)
            return
        if not topic[-1] == '#':
            self._log.warning('Unexpect topic not return_code: %s', topic)
            return
        topic = topic[(len(self._path) + 1):-1]
        if self._topic_return_code_expect == topic:
            self._log
        print(f'{topic} -> {value}')

    def on_action_open(self):
        self.open()

    def on_action_close(self):
        self.close()

    def open(self):
        self._log.info('open %s start', self.topic)
        #self._driver.subscribe(self._path, ['return_code'], self._cmd_complete_fn, timeout=0)
        # self._on_return_code = ['@/!open', self.
        self._driver.open(self._path, 'restore')
        self._driver_publish('s/stats/ctrl', 1)
        self._driver_subscribe('s/stats/value', 'pub', self._on_stats_fn)
        self._driver_publish('s/i/range/mode', 'auto')
        self._driver_publish('s/v/range/select', '15 V')
        self._driver_publish('s/v/range/mode', 'manual')
        self._log.info('open %s done', self.topic)

    def close(self):
        self._log.info('close %s start', self.topic)
        self._driver_unsubscribe('s/stats/value', self._on_stats_fn)
        self._log.info('close %s done', self.topic)

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

    def on_setting_statistics_frequency(self, value):
        scnt = 1_000_000 // value
        self._driver_publish('s/stats/scnt', scnt)
