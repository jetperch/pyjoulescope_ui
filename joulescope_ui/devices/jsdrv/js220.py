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

from joulescope_ui.capabilities import CAPABILITIES
from .device import Device
from joulescope_ui.metadata import Metadata


EVENTS = {
    'statistics/!data': Metadata('obj', 'Periodic statistics data for each signal.'),
    'signals/current/!data': Metadata('obj', 'Streaming sample data for the current signal.'),
    'signals/voltage/!data': Metadata('obj', 'Streaming sample data for the voltage signal.'),
    'signals/power/!data': Metadata('obj', 'Streaming sample data for the power signal.'),
    # todo other signals, INx, TRIGGER, UART, ...
}


class Js220(Device):

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
        print(value)
        self._ui_publish('events/statistics/!data', value)
