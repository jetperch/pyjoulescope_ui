# Copyright 2024 Jetperch LLC
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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import CAPABILITIES, get_topic_name
from joulescope_ui.ui_util import comboBoxConfig
from joulescope_ui.styles import styled_widget
from pyjoulescope_driver import time64
import numpy as np
import pyqtgraph as pg


_SECONDS_MAX = 60 * 60 * 24 * 7  # 1 week
_COLORS = [
    '#40c040',
    '#4080c8',
    '#a040a0',
    '#40a0a0',
    '#e29740',
    '#a0a0a0',
]


DIRECTIONS = """\
<html><body>
<p>Connect a pulse-per-second (PPS) signal from a GNSS / GPS receiver
to the same input on each of your Joulescopes.  Ensure that your
host computer is connected to the network and has time synchronized
using NTP.</p>
</html></body>
"""


@styled_widget('Timesync')
class TimesyncWidget(QtWidgets.QWidget):
    """A widget for evaluation instrument time synchronization."""

    CAPABILITIES = ['widget@']
    SETTINGS = {
        'signal': {
            'dtype': 'str',
            'brief': 'The general purpose input signal with the PPS signal.',
            'default': '0',
            'options': ['0', '1', '2', '3', 'T']
        },
    }

    def __init__(self, parent=None):
        self._signal_prev = None
        self._devices = {}
        self._device_idx = 0
        super().__init__(parent=parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._directions = QtWidgets.QLabel(DIRECTIONS)
        self._directions.setWordWrap(True)
        self._layout.addWidget(self._directions)
        self._status_widget = QtWidgets.QLabel()
        self._layout.addWidget(self._status_widget)

        self._row = 0
        self._grid = QtWidgets.QGridLayout()
        self._signal_sel = QtWidgets.QComboBox()
        self._signal_sel.currentTextChanged.connect(self._on_signal)
        self._grid.addWidget(QtWidgets.QLabel('Signal'), self._row, 0)
        self._grid.addWidget(self._signal_sel, self._row, 1)
        self._layout.addLayout(self._grid)
        self._row += 1

        self._avg_value = QtWidgets.QLabel()
        self._grid.addWidget(QtWidgets.QLabel('avg'), self._row, 0)
        self._grid.addWidget(self._avg_value, self._row, 1)
        self._grid.addWidget(QtWidgets.QLabel('µs'), self._row, 2)
        self._row += 1

        self._p2p_value = QtWidgets.QLabel()
        self._grid.addWidget(QtWidgets.QLabel('p2p'), self._row, 0)
        self._grid.addWidget(self._p2p_value, self._row, 1)
        self._grid.addWidget(QtWidgets.QLabel('µs'), self._row, 2)
        self._row += 1

        self._plot = pg.PlotWidget(name='Timesync')
        self._plot.showGrid(x=True, y=True)
        self._layout.addWidget(self._plot)

        self._x = np.arange(_SECONDS_MAX, dtype=float)
        self._avg = np.arange(_SECONDS_MAX, dtype=float)  # relative to the x value

    def _status(self, txt):
        self._status_widget.setText(txt)

    def _on_signal(self, signal):
        self.signal = signal

    def on_setting_signal(self, signal):
        if self._signal_prev is not None:
            for data in self._devices.values():
                topic = data['topic']
                self.pubsub.unsubscribe(f'{topic}/events/signals/{self._signal_prev}/!data', self._on_gpi)
                self.pubsub.publish(f'{topic}/settings/signals/{self._signal_prev}/enable', False)
        for data in self._devices.values():
            topic = data['topic']
            self.pubsub.subscribe(f'{topic}/events/signals/{signal}/!data', self._on_gpi, ['pub'])
            self.pubsub.publish(f'{topic}/settings/signals/{signal}/enable', True)
        self._signal_prev = signal

    def on_pubsub_register(self):
        comboBoxConfig(self._signal_sel, ['0', '1', '2', '3', 'T'], self.signal)
        self._x_offset = time64.now() // time64.SECOND
        self.pubsub.subscribe(f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_STREAM_SOURCE}/list',
                              self._on_sources, ['pub', 'retain'])

    def _on_sources(self, value):
        for device in list(self._devices.keys()):
            if device not in value:
                d = self._devices.pop(device)
                d['plot'].close()
        for device in value:
            if device not in self._devices:
                topic = get_topic_name(device)
                self.pubsub.subscribe(f'{topic}/events/signals/{self.signal}/!data', self._on_gpi, ['pub'])
                self.pubsub.publish(f'{topic}/settings/signals/{self.signal}/enable', True)
                data = np.empty(_SECONDS_MAX, dtype=float)
                data[:] = np.nan
                plot = self._plot.plot()
                plot.setPen(_COLORS[self._device_idx])
                self._devices[device] = {
                    'device': device,
                    'topic': topic,
                    'value_last': 0,
                    'detect': None,
                    'data': data,
                    'idx_max': 0,
                    'timemap': None,  # most recent, for troubleshooting
                    'plot': plot,
                }
                self._device_idx = (self._device_idx + 1) % len(_COLORS)

    def _detect_match(self):
        for d in self._devices.values():
            if d['detect'] is None:
                return None

        # use python's infinite precision integer type (intentionally avoid numpy)
        t_raw = [d['detect'] for d in self._devices.values()]
        t_mean = sum(t_raw) // len(t_raw)
        t = [(x - t_mean) * (1e6 / time64.SECOND) for x in t_raw]
        t_raw_str = ','.join([str(x) for x in t_raw])
        t_us_str = ','.join([f'{x:.1f}' for x in t])
        row = f'{time64.as_datetime(t_mean).isoformat()},{t_mean},{t_raw_str},{t_us_str}'

        for d in self._devices.values():
            d['detect'] = None

        print(row)
        return row

    def _stats_update(self):
        idx = [d['idx_max'] for d in self._devices.values()]
        idx_min = min(idx)
        idx_max = max(idx)
        if idx_min + 1 < idx_max:
            self._status('devices not updating')
        y = [d['data'][idx_min] for d in self._devices.values()]
        avg = np.mean(y)
        self._avg[idx_min] = avg
        self._avg_value.setText(f'{avg * 1e6:.1f}')
        p2p = np.max(y) - np.min(y)
        self._p2p_value.setText(f'{p2p * 1e6:.1f}')

    def _on_gpi(self, topic, value):
        device = topic.split('/')[1]
        d = self._devices[device]
        k = np.unpackbits(value['data'], bitorder='little')
        if d['value_last'] == 0 and k[0] == 1:
            found = 0  # found first sample
        elif k[0] == 0:
            idx = np.where(k)[0]
            if len(idx):
                found = idx[0]
            else:
                return  # not found
        else:
            return
        d['value_last'] = k[-1]
        sample_id = value['origin_sample_id'] + found * value['origin_decimate_factor']
        time_map = value['time_map']
        dc = sample_id - time_map['offset_counter']
        utc = time_map['offset_time']
        utc += int(dc / time_map['counter_rate'] * time64.SECOND)
        utc_second = int(round(utc / time64.SECOND))
        idx = utc_second - self._x_offset

        utc_remainder = (utc - (utc_second * time64.SECOND)) / time64.SECOND
        d['data'][idx] = utc_remainder
        idx_max = max(d['idx_max'], idx)
        d['idx_max'] = idx_max
        d['plot'].setData(x=self._x[:idx_max], y=d['data'][:idx_max])
        self._stats_update()
