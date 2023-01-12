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
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.units import unit_prefix
import numpy as np


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
        'show_fields': {
            'dtype': 'bool',
            'brief': N_('Show the statistics fields at the right.'),
            'default': True,
        },
        'show_sign': {
            'dtype': 'bool',
            'brief': N_('Show a leading + or - sign.'),
            'default': True,
        },
        'show_titles': {
            'dtype': 'bool',
            'brief': N_('Show the statistics section title for each signal.'),
            'default': True,
        },
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._menu = None
        self._sources: list[str] = []   # The list of available source unique_id's
        self._default_statistics_stream_source = None
        self._statistics_stream_source = None
        self._signals = ['current', 'voltage', 'power', 'charge', 'energy']
        self._main = 'avg'
        self._fields = ['std', 'min', 'max', 'p2p']
        self._on_cbk_statistics_fn = self.on_cbk_statistics
        self._statistics = None  # most recent statistics information

        self._subscribers = [
            ['registry/app/settings/defaults/statistics_stream_source', self._on_default_statistics_stream_source],
            [f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list', self._on_statistic_stream_source_list],
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
        pubsub_singleton.unsubscribe_all(self._on_cbk_statistics_fn)

    @property
    def source(self):
        source = self._statistics_stream_source
        if source in [None, 'default']:
            source = self._default_statistics_stream_source
        return source

    def _connect(self):
        self._disconnect()
        source = self.source
        if source is not None:
            topic = get_topic_name(source)
            pubsub_singleton.subscribe(f'{topic}/events/statistics/!data', self._on_cbk_statistics_fn, ['pub'])

    def _on_default_statistics_stream_source(self, value):
        source_prev = self.source
        self._default_statistics_stream_source = value
        source_next = self.source
        if source_prev != source_next:
            self._connect()

    def _on_statistic_stream_source_list(self, value):
        self._sources = list(value)

    def on_cbk_statistics(self, value):
        self._statistics = value
        self.repaint()

    def paintEvent(self, event):
        if self.source is None:
            return

        painter = QtGui.QPainter(self)
        v = self.style_manager_info['sub_vars']
        x_border, y_border = 10, 10
        y_sep = 6
        number_example = '8.88888'

        background_color = color_as_qcolor(v['value.background'])
        background_brush = QtGui.QBrush(background_color)

        title_color = color_as_qcolor(v['value.title_color'])
        title_font = font_as_qfont(v['value.title_font'])
        title_font_metrics = QtGui.QFontMetrics(title_font)
        title_space = np.ceil(title_font_metrics.ascent() * 0.05)
        title_height = title_font_metrics.height() + title_space if self.show_titles else 0

        main_color = color_as_qcolor(v['value.main_color'])
        main_font = font_as_qfont(v['value.main_font'])
        main_font_metrics = QtGui.QFontMetrics(main_font)
        main_number_width = main_font_metrics.boundingRect(number_example).width()
        main_char_width = _width(main_font_metrics)
        main_text_width = main_font_metrics.boundingRect('W').width()

        stats_color = color_as_qcolor(v['value.stats_color'])
        stats_font = font_as_qfont(v['value.stats_font'])
        stats_font_metrics = QtGui.QFontMetrics(stats_font)
        stats_number_width = stats_font_metrics.boundingRect(number_example).width()
        stats_char_width = _width(stats_font_metrics)
        stats_field_width_max = max([stats_font_metrics.boundingRect(field).width() for field in self._fields])
        stats_space = np.ceil(stats_font_metrics.ascent() * 0.05)

        line_color = color_as_qcolor(v['value.line_color'])

        x_max = x_border + main_char_width + main_number_width + main_char_width // 2 + main_text_width * 2 + x_border
        if self.show_fields and len(self._fields):
            x_max += (main_text_width // 2 + stats_char_width + stats_number_width +
                      stats_char_width + stats_field_width_max)
        field_count = len(self._fields) if self.show_fields else 0
        y1 = title_height + main_font_metrics.height()
        y2 = stats_font_metrics.height() * field_count
        if field_count > 1:
            y2 += (field_count - 1) * stats_space
        y_signal = max(y1, y2)
        signal_len = len(self._signals)
        y_max = y_signal * signal_len + y_border
        if signal_len > 1:
            y_max += (signal_len - 1) * y_sep

        self.setMinimumSize(x_max, y_max)
        self.setMaximumSize(x_max, y_max)
        painter.fillRect(0, 0, x_max, y_max, background_brush)

        for idx, signal_name in enumerate(self._signals):
            y = y_border + idx * (y_signal + y_sep)
            if idx != 0:
                y_line = y - y_sep // 2
                painter.setPen(line_color)
                painter.drawLine(x_border, y_line, x_max - x_border, y_line)
            y_start = y
            x = x_border

            if self.show_titles:
                painter.setPen(title_color)
                painter.setFont(title_font)
                y += title_font_metrics.ascent()
                signal_title_parts = [self.source, signal_name]
                if self._statistics is not None:
                    if signal_name not in self._statistics['accumulators'] and self._main != 'avg':
                        signal_title_parts.append(self._main)
                painter.drawText(x, y, ' . '.join(signal_title_parts))
                y += title_font_metrics.descent() + title_space

            if self._statistics is None:
                continue

            painter.setPen(main_color)
            painter.setFont(main_font)
            y += main_font_metrics.ascent() + (y_signal - title_height - main_font_metrics.height()) // 2

            if signal_name in self._statistics['accumulators']:
                signal = self._statistics['accumulators'][signal_name]
                fields = []
                signal_value = signal['value']
                signal_units = signal['units']
                _, prefix, scale = unit_prefix(signal_value)
            else:
                signal = self._statistics['signals'][signal_name]
                fields = self._fields if self.show_fields else []
                fields_all = [self._main] + fields
                max_value = max([abs(signal[s]['value']) for s in fields_all])
                _, prefix, scale = unit_prefix(max_value)
                signal_value = signal[self._main]['value']
                signal_units = signal[self._main]['units']
            if len(prefix) != 1:
                prefix = ' '
            v_str = ('%+6f' % (signal_value / scale))[:8]
            if v_str[0] == '-' or self.show_sign:
                painter.drawText(x, y, v_str[0])
            x += main_char_width
            painter.drawText(x, y, v_str[1:])
            x += main_number_width + main_char_width // 2
            w1 = main_font_metrics.boundingRect(signal_units).width()
            w2 = main_font_metrics.boundingRect(prefix + signal_units).width()
            x_offset = int(main_text_width * 1.5 - w1 / 2)
            painter.drawText(x + x_offset - (w2 - w1), y, prefix)
            painter.drawText(x + x_offset, y, signal_units)
            x += 2 * main_text_width

            painter.setPen(stats_color)
            painter.setFont(stats_font)
            y = y_start + (y_signal - y2) // 2
            x += main_text_width // 2
            x_start = x

            for idx, stat in enumerate(fields):
                if idx == 0:
                    y += stats_space
                y += stats_font_metrics.ascent()
                x = x_start
                v_str = ('%+6f' % (signal[stat]['value'] / scale))[:8]
                if v_str[0] == '-' or self.show_sign:
                    painter.drawText(x, y, v_str[0])
                x += stats_char_width
                painter.drawText(x, y, v_str[1:])
                x += stats_number_width + stats_char_width
                painter.drawText(x, y, stat)
                y += stats_font_metrics.descent()

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
