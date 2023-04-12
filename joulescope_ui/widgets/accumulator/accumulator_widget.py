# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtWidgets, QtGui, QtCore
from joulescope_ui import N_, register, CAPABILITIES, pubsub_singleton, get_topic_name
from joulescope_ui.widget_tools import settings_action_create
from joulescope_ui.styles import styled_widget
from joulescope_ui.units import unit_prefix, elapsed_time_formatter
import logging


SETTINGS = {
    'statistics_stream_source': {
        'dtype': 'str',
        'brief': N_('The statistics data stream source.'),
        'default': None,
    },
    'field': {
        'dtype': 'str',
        'brief': N_('The signal to display.'),
        'options': [
            ['charge', N_('charge')],
            ['energy', N_('energy')],
        ],
        'default': 'charge',
    },
    'show_titles': {
        'dtype': 'bool',
        'brief': N_('Show the statistics section title for each signal.'),
        'default': True,
    },
    'units': {
        'dtype': 'str',
        'brief': N_('The units to display.'),
        'options': [
            ['SI'],
            ['Xh'],
        ],
        'default': 'SI',
    }
}

@register
@styled_widget(N_('Accumulator'))
class AccumulatorWidget(QtWidgets.QWidget):
    CAPABILITIES = ['widget@', CAPABILITIES.STATISTIC_STREAM_SINK]
    SETTINGS = SETTINGS

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__)
        self._menu = None
        self._clipboard = None
        self._default_statistics_stream_source = None
        self._statistics_stream_source = None
        self._statistics = None
        self._on_statistics_fn = self._on_statistics
        self._devices = ['default']
        super().__init__(parent=parent)
        self.setObjectName('accumulator_widget')
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setLayout(self._layout)

        self._accum_label = QtWidgets.QLabel(parent=self)
        self._accum_label.setObjectName('accum')
        self._layout.addWidget(self._accum_label)

        self._subscribers = [
            ['registry/app/settings/defaults/statistics_stream_source',
             self._on_default_statistics_stream_source],
            [f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list',
             self._on_statistic_stream_source_list],
        ]

    def on_pubsub_register(self):
        for topic, fn in self._subscribers:
            pubsub_singleton.subscribe(topic, fn, ['pub', 'retain'])

    def closeEvent(self, event):
        self._disconnect()
        self._statistics = None
        return super().closeEvent(event)

    def _disconnect(self):
        pubsub_singleton.unsubscribe_all(self._on_statistics_fn)
        for topic, fn in self._subscribers:
            pubsub_singleton.unsubscribe(topic, fn)
        self.repaint()

    @property
    def source(self):
        source = self._statistics_stream_source
        if source in [None, 'default']:
            source = self._default_statistics_stream_source
        return source

    @source.setter
    def source(self, value):
        s1 = self.source
        self._statistics_stream_source = value
        s2 = self.source
        if s1 != s2:
            self._connect()

    def _connect(self):
        self._disconnect()
        source = self.source
        if source is not None:
            topic = get_topic_name(source)
            pubsub_singleton.subscribe(f'{topic}/events/statistics/!data', self._on_statistics_fn, ['pub'])
        self.repaint()

    def _on_default_statistics_stream_source(self, value):
        source_prev = self.source
        self._default_statistics_stream_source = value
        source_next = self.source
        if source_prev != source_next:
            self._connect()

    def _on_statistic_stream_source_list(self, value):
        self._devices = ['default'] + value

    def _on_statistics(self, value):
        self._statistics = value
        signal = value['accumulators'][self.field]
        signal_value = signal['value']
        signal_units = signal['units']
        if self.units == 'Xh':
            signal_value /= 3600.0
            signal_units = 'Wh' if signal_units == 'J' else 'Ah'

        _, prefix, scale = unit_prefix(signal_value)
        v_str = ('%+6f' % (signal_value / scale))[:8]

        a_start, a_end = self._statistics['time']['accum_samples']['value']
        sample_freq = self._statistics['time']['sample_freq']['value']
        duration = (a_end - a_start) / sample_freq
        duration_txt, duration_units = elapsed_time_formatter(duration, fmt='standard', precision=3)
        if duration_units == 's':
            duration_units = ' s'
        else:
            duration_units = ''
        s = f'{v_str} {prefix}{signal_units} in {duration_txt}{duration_units}'
        self._accum_label.setText(s)

    def _on_field(self, value):
        self.field = value
        self.repaint()

    def _on_units(self, value):
        self.units = value
        self.repaint()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._clipboard = self._accum_label.text()
            self._log.info('copy value to clipboard: %s', self._clipboard)
            QtWidgets.QApplication.clipboard().setText(self._clipboard)
        else:
            menu = QtWidgets.QMenu(self)
            if self.field == 'energy':
                toggle_field = 'charge'
                action = N_('Show charge')
            else:
                toggle_field = 'energy'
                action = N_('Show energy')
            field_toggle = QtGui.QAction(action)
            menu.addAction(field_toggle)
            field_toggle.triggered.connect(lambda: self._on_field(toggle_field))

            if self.units == 'SI':
                toggle_units = 'Xh'
                action_units = 'Wh' if self.field == 'energy' else 'Ah'
            else:
                toggle_units = 'SI'
                action_units = 'J' if self.field == 'energy' else 'C'
            units_toggle = QtGui.QAction(N_('Set units') + ': ' + action_units)
            menu.addAction(units_toggle)
            units_toggle.triggered.connect(lambda: self._on_units(toggle_units))

            style_action = settings_action_create(self, menu)
            menu.popup(event.globalPos())
            self._menu = [menu, field_toggle, units_toggle, style_action]
            event.accept()
