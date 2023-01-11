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

from PySide6 import QtWidgets, QtGui, QtCore
from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name
from joulescope_ui.widget_tools import settings_action_create
from joulescope_ui.styles import styled_widget, color_as_qcolor
from joulescope_ui.units import unit_prefix
import numpy as np


def font_as_qfont(s):
    font = QtGui.QFont()
    parts = s.split()
    while len(parts):
        p = parts.pop(0)
        if p[0] == '"':
            fontname = ' '.join([p] + parts)[1:-1]
            font.setFamily(fontname)
            parts.clear()
        elif p == 'bold':
            font.setBold(True)
        elif p == 'italic':
            font.setItalic(True)
        elif p[0] in '0123456789':
            if p.endswith('pt'):
                sz = float(p[:-2])
                font.setPointSizeF(sz)
            elif p.endswith('px'):
                sz = int(p[:-2])
                font.setPixelSize(sz)
            else:
                raise ValueError(f'unsupported font size: {p}')
        else:
            raise ValueError(f'unsupported font specification: {s}')
    return font


def _width(font_metrics):
    w = max([font_metrics.boundingRect(c).width() for c in '0123456789+-'])
    return np.ceil(w * 1.05)


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
        self._signals = ['current', 'voltage', 'power']
        self._main = 'avg'
        self._fields = ['std', 'min', 'max', 'p2p']
        self.show_sign = False
        self._on_cbk_statistics_fn = self.on_cbk_statistics
        self._statistics = None  # most recent statistics information

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
        self._statistics = None
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
        self._statistics = value
        self.repaint()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        v = self.style_manager_info['sub_vars']
        x_border, y_border = 10, 10
        y_sep = 6
        y = y_border

        for idx, signal_name in enumerate(self._signals):
            if idx != 0:
                y_line = y + y_sep // 2
                color = color_as_qcolor(v['value.line_color'])
                painter.setPen(color)
                painter.drawLine(x_border, y_line, x_max, y_line)
                y += y_sep
            y_start = y
            x = x_border
            color = color_as_qcolor(v['value.title_color'])
            font = font_as_qfont(v['value.title_font'])
            painter.setPen(color)
            painter.setFont(font)
            m = QtGui.QFontMetrics(font)
            y += m.ascent()
            painter.drawText(x, y, f'{self._source} . {signal_name}')
            y += m.descent() + np.ceil(m.ascent() * 0.05)

            color = color_as_qcolor(v['value.main_color'])
            font = font_as_qfont(v['value.main_font'])
            painter.setPen(color)
            painter.setFont(font)

            m = QtGui.QFontMetrics(font)
            char_width = _width(m)
            txt_w = m.boundingRect('W').width() + 1
            y += m.ascent()

            if self._statistics is None:
                return
            fields_all = [self._main] + self._fields
            signal = self._statistics['signals'][signal_name]
            max_value = max([abs(signal[s]['value']) for s in fields_all])
            _, prefix, scale = unit_prefix(max_value)
            if len(prefix) != 1:
                prefix = ' '
            v_str = ('%+6f' % (signal[self._main]['value'] / scale))[:8]
            if v_str[0] != '-' and not self.show_sign:
                v_str = ' ' + v_str[1:]
            for c in v_str:
                w = m.boundingRect(c).width()
                x_offset = (char_width - w) // 2
                painter.drawText(x + x_offset, y, c)
                x += char_width
            x += char_width
            for c in prefix + signal[self._main]['units']:
                w = m.boundingRect(c).width()
                x_offset = (txt_w - w) // 2
                painter.drawText(x + x_offset, y, c)
                x += txt_w
            x += txt_w // 2
            y_max1 = y + m.descent()

            color = color_as_qcolor(v['value.stats_color'])
            font = font_as_qfont(v['value.stats_font'])
            painter.setPen(color)
            painter.setFont(font)
            m = QtGui.QFontMetrics(font)

            y = y_start
            char_width = _width(m)
            x_start = x

            for idx, stat in enumerate(self._fields):
                if idx == 0:
                    y += m.ascent()
                else:
                    y += np.ceil(m.ascent() * 1.05)
                x = x_start
                v_str = ('%+6f' % (signal[stat]['value'] / scale))[:8]
                if v_str[0] != '-' and not self.show_sign:
                    v_str = ' ' + v_str[1:]
                for c in v_str:
                    w = m.boundingRect(c).width()
                    x_offset = (char_width - w) // 2
                    painter.drawText(x + x_offset, y, c)
                    x += char_width
                x += char_width
                painter.drawText(x, y, stat)
                y += m.descent()
            x_max = x + max([m.boundingRect(field).width() for field in self._fields])
            y_max2 = y + m.descent()
            y = max(y_max1, y_max2)

        #color = color_as_qcolor('#ff000040')
        #painter.setPen(color)
        #painter.drawRect(x_border, y_border, x_max - x_border, y - y_border)

    def _on_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            style_action = settings_action_create(self, menu)
            menu.popup(event.globalPos())
            self._menu = [menu, style_action]
            event.accept()
