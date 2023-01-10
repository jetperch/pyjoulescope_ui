# Copyright 2023 Jetperch LLC
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

from PySide6 import QtWidgets, QtCore
from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name
from joulescope_ui.widget_tools import settings_action_create
from joulescope_ui.styles import styled_widget
from joulescope_ui.units import unit_prefix


@register
@styled_widget(N_('Value'))
class ValueWidget(QtWidgets.QWidget):
    """Display a single value from a statistics stream."""

    CAPABILITIES = ['widget@', CAPABILITIES.STATISTIC_STREAM_SINK]
    SETTINGS = {
        'statistics_stream_source': {
            'dtype': 'str',
            'brief': N_('The statistics data stream source.'),
            'default': None,
        },
    }

    def __init__(self):
        super().__init__()
        self._menu = None
        self._layout = QtWidgets.QVBoxLayout(self)
        self._sources = []
        self._device_active = None
        self._statistics_stream_source = None
        self._source = None
        self._on_cbk_statistics_fn = self.on_cbk_statistics

        self._label1 = QtWidgets.QLabel()
        self._label1.setObjectName('label1')
        self._label1.setText('Label 1')
        self._layout.addWidget(self._label1)

        self._subscribers = [
            ['registry/app/settings/device_active', self._on_device_active]
        ]
        for topic, fn in self._subscribers:
            pubsub_singleton.subscribe(topic, fn, ['pub', 'retain'])
        self.mousePressEvent = self._on_mousePressEvent

    def closeEvent(self, event):
        self._disconnect()
        for topic, fn in self._subscribers:
            pubsub_singleton.unsubscribe(topic, fn)
        return super(ValueWidget, self).closeEvent(event)

    def _disconnect(self):
        if self._statistics_stream_source is not None:
            pubsub_singleton.unsubscribe_all(self._on_cbk_statistics_fn)

    def _connect(self):
        source = self._statistics_stream_source
        if self._statistics_stream_source in [None, 'default']:
            source = self._device_active
        if source != self._source:
            self._disconnect()
        self._source = source
        if source is None:
            pass  # todo
        else:
            topic = get_topic_name(self)
            pubsub_singleton.publish(f'{topic}/settings/statistics_stream_source', source)
            topic = get_topic_name(source)
            pubsub_singleton.subscribe(f'{topic}/events/statistics/!data', self._on_cbk_statistics_fn, ['pub'])

    def _on_device_active(self, value):
        self._device_active = value
        self._connect()

    def on_cbk_statistics(self, value):
        v = value['signals']['current']['avg']
        adjusted_value, prefix, _ = unit_prefix(v['value'])
        v_str = ('%+6f' % adjusted_value)[:8]
        if v_str[0] == '+':
            v_str = ' ' + v_str[1:]
        self._label1.setText(f'{v_str} {prefix}{v["units"]}')

    def _on_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            style_action = settings_action_create(self, menu)
            menu.popup(event.globalPos())
            self._menu = [menu, style_action]
            event.accept()
