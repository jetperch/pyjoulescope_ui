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
from joulescope_ui import CAPABILITIES, register, N_, get_topic_name, tooltip_format
from joulescope_ui.widget_tools import settings_action_create, context_menu_show
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
from joulescope_ui.units import UNITS_SETTING, convert_units, unit_prefix, three_sig_figs
from joulescope_ui.ui_util import comboBoxConfig, comboBoxSelectItemByText
from joulescope_ui.source_selector import SourceSelector
import datetime
import numpy as np
import copy
import logging


SETTINGS = {
    'statistics_stream_source': {
        'dtype': 'str',
        'brief': N_('The statistics data stream source.'),
        'default': None,
    },
    'show_device_selection': {
        'dtype': 'bool',
        'brief': N_('Show the device selection header.'),
        'default': True,
    },
    'show_accrue': {
        'dtype': 'bool',
        'brief': N_('Show the accrue header.'),
        'default': True,
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
    'units': UNITS_SETTING,
}


def _settings_alter(**kwargs):
    d = copy.deepcopy(SETTINGS)
    for key, default in kwargs.items():
        d[key]['default'] = default
    return d


_MULTIMETER_SETTINGS = _settings_alter(show_titles=False)
_VALUE_SETTINGS = _settings_alter(show_device_selection=False, show_accrue=False, show_fields=False)
_VALUE_SETTINGS['signal'] = {
    'dtype': 'str',
    'brief': N_('The signal to display.'),
    'options': [
        ['current'],
        ['voltage'],
        ['power'],
        ['charge'],
        ['energy'],
    ],
    'default': 'current',
}


_DEVICE_TOOLTIP = tooltip_format(
    N_('Select the source device'),
    N_("""\
       The values displayed by this widget come from a single
       source device.  Select the source device here. 
       """))

_HOLD_TOOLTIP = tooltip_format(
    N_("Hold the display"),
    N_("""\
    When selected, prevent the display from updating.
    
    The UI also includes a global statistics hold button
    on the sidebar.  When the global statistics hold button
    is selected, this button is disabled and has no effect.
    
    The displayed values normally update with each new statistics
    data computed by the device.  When this button is selected,
    the display will not be updated.  However, the statistics
    will continue accumulate and accrue (if selected)."""))

_ACCRUE_TOOLTIP = tooltip_format(
    N_("Accrue values over time"),
    N_("""\
    Current, voltage, and power are normally computed
    over a single statistics frequency interval.  Press
    this button to accrue the values indefinitely.
    Press again to return to normal operation.
    
    Note that this button does not affect the charge and energy
    accumulation.  Both accumulate indefinitely regardless of
    this button state."""))


def duration_to_str(value):
    if value > 60:
        h = int(value // 3600)
        value -= h * 3600
        m = int(value // 60)
        value -= m * 60
        s = int(value // 1)
        value -= s
        fract = f'{value:.2f}'[1:]  # remove leading zero
        msg = f'{h:d}:{m:02d}:{s:02d}{fract}'
    else:
        msg = three_sig_figs(value, 's')
    return msg


def _width(font_metrics):
    w = max([font_metrics.boundingRect(c).width() for c in '0123456789+-'])
    return np.ceil(w * 1.05)


class _DeviceWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        super().__init__(parent=parent)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(5, 5, 5, 2)

        self._device_unique_ids = []
        self._device_names = []
        self._device_fixed_label = QtWidgets.QLabel(N_('Device'), self)
        self._device_fixed_label.setToolTip(_DEVICE_TOOLTIP)
        self._device_select = QtWidgets.QComboBox(parent=self)
        self._device_select.setToolTip(_DEVICE_TOOLTIP)
        self._device_select.currentIndexChanged.connect(self._on_device_select)
        self._device_select.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._device_label = QtWidgets.QLabel(self)
        self._device_label.hide()

        self._layout.addWidget(self._device_fixed_label)
        self._layout.addWidget(self._device_select)
        self._layout.addWidget(self._device_label)
        self._horizontalSpacer = QtWidgets.QSpacerItem(0, 0,
                                                       QtWidgets.QSizePolicy.Expanding,
                                                       QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._horizontalSpacer)

    def _on_device_select(self, idx):
        device = self._device_unique_ids[idx]
        self.parent().source_selector.source_set(device)

    def _unique_id_to_name(self, unique_id):
        pubsub = self.parent().pubsub
        return pubsub.query(f'{get_topic_name(unique_id)}/settings/name', default=unique_id)

    def _name_to_unique_id(self, name):
        try:
            idx = self._device_unique_ids.index(self.parent().source_selector.value)
            return self._device_names[idx]
        except Exception:
            return name

    def device_list(self, devices):
        self._device_unique_ids = list(devices)
        self._device_names = [self._unique_id_to_name(unique_id) for unique_id in devices]
        comboBoxConfig(self._device_select, self._device_names)
        self.device_select()

    def device_select(self):
        try:
            idx = self._device_unique_ids.index(self.parent().source_selector.value)
            self._device_select.setCurrentIndex(idx)
        except Exception:
            pass

    def device_show(self, unique_id):
        if unique_id is None:
            self._device_label.show()
            self._device_label.setText(N_('Not present'))
        elif self._device_select.currentText() == 'default':
            self._device_label.show()
            self._device_label.setText(self._unique_id_to_name(unique_id))
        else:
            self._device_label.hide()


class _AccrueWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        self._log = logging.getLogger(__name__ + '.accrue')
        self._hold_local = False
        self._hold_global = False
        self.accrue = False
        super().__init__(parent=parent)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(5, 2, 5, 5)

        self._hold_button = QtWidgets.QPushButton(self)
        self._hold_button.setText(N_('Hold'))
        self._hold_button.setCheckable(True)
        self._hold_button.setObjectName('hold_button')
        self._layout.addWidget(self._hold_button)
        self._hold_button.toggled.connect(self._on_hold_toggled)
        self._hold_button.setToolTip(_HOLD_TOOLTIP)

        self._accrue_button = QtWidgets.QPushButton(self)
        self._accrue_button.setText(N_('Accrue'))
        self._accrue_button.setCheckable(True)
        self._accrue_button.setObjectName('accrue_button')
        self._layout.addWidget(self._accrue_button)
        self._accrue_button.toggled.connect(self._on_accrue_toggled)
        self._accrue_button.setToolTip(_ACCRUE_TOOLTIP)

        self._accrue_duration = QtWidgets.QLabel(self)
        self._layout.addWidget(self._accrue_duration)

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer)

    @property
    def is_accrue(self):
        return self._accrue_button.isChecked()

    def accrue_duration(self, value, t_start=None):
        msg = duration_to_str(value)
        if t_start is not None:
            msg = f'{msg} | Started at {t_start}'
        self._accrue_duration.setText(msg)

    @property
    def hold(self):
        return self._hold_local or self._hold_global

    @property
    def hold_global(self):
        return self._hold_global

    @hold_global.setter
    def hold_global(self, value):
        value = bool(value)
        self._log.info('Hold global %s', 'start' if value else 'stop')
        self._hold_button.setEnabled(not value)
        self._hold_global = value

    def _on_hold_toggled(self, checked):
        self._hold_local = bool(checked)
        self._log.info('Hold local %s', 'start' if self._hold_local else 'stop')

    def _on_hold_global(self, value):
        self._hold_global = bool(value)
        self._log.info('Hold global %s', 'start' if self._hold_global else 'stop')

    def _on_accrue_toggled(self, checked):
        self.accrue = bool(checked)
        self._log.info('Accrue %s', 'start' if self.accrue else 'stop')


class _InnerWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        self._log = logging.getLogger(__name__ + '.inner')
        self._statistics = None  # most recent statistics information
        super().__init__(parent=parent)
        self._size = (10, 10)
        self.setFixedSize(*self._size)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self._signals = ['current', 'voltage', 'power', 'charge', 'energy']
        self._main = 'avg'
        self._fields = ['avg', 'std', 'min', 'max', 'p2p']
        self._geometry = None
        self._clipboard = None
        self.setMouseTracking(True)

    def _on_statistics(self, value):
        self._statistics = copy.deepcopy(value)
        self.repaint()

    def paintEvent(self, event):
        fields = [field for field in self._fields if field != self._main]
        parent: ValueWidget = self.parent()
        resolved = parent.source_selector.resolved()
        if resolved is None or parent.style_obj is None:
            return

        painter = QtGui.QPainter(self)
        v = parent.style_obj['vars']
        x_border, y_border = 10, 10
        y_sep = 6
        number_example = '8.88888'

        background_color = color_as_qcolor(v['value.background'])
        background_brush = QtGui.QBrush(background_color)

        title_color = color_as_qcolor(v['value.title_color'])
        title_font = font_as_qfont(v['value.title_font'])
        title_font_metrics = QtGui.QFontMetrics(title_font)
        title_space = np.ceil(title_font_metrics.ascent() * 0.05)
        title_height = title_font_metrics.height() + title_space if parent.show_titles else 0

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
        if parent.show_fields and len(fields):
            x_max += (main_text_width // 2 + stats_char_width + stats_number_width +
                      stats_char_width + stats_field_width_max)
        field_count = len(fields) if parent.show_fields else 0
        y1 = title_height + main_font_metrics.height()
        y2 = stats_font_metrics.height() * field_count
        if field_count > 1:
            y2 += (field_count - 1) * stats_space
        y_signal = max(y1, y2)
        signal_len = len(self._signals)
        y_max = y_signal * signal_len + y_border
        if signal_len > 1:
            y_max += (signal_len - 1) * y_sep

        sz = (x_max, y_max)
        if self._size != sz:
            self._size = sz
            self.setMinimumSize(x_max, y_max)
            self.setMaximumSize(x_max, y_max)
            self.setFixedSize(x_max, y_max)
            self.geometry()

        if self._statistics is not None:
            a_start, a_end = self._statistics['time']['accum_samples']['value']
            sample_freq = self._statistics['time']['sample_freq']['value']
            a_duration = (a_end - a_start) / sample_freq
            a_duration_txt = duration_to_str(a_duration)

        painter.fillRect(0, 0, x_max, y_max, background_brush)

        self._geometry = {
            'y_border': y_border,
            'y_signal': y_signal,
            'y_sep': y_sep,
            'y_stats_space': stats_space,
            'y_stats': stats_font_metrics.height(),
            'x_stats': None,
            'fields': {},  # signal_idx -> list of available fields
            'values': {},  # signal_idx -> field_name -> value
        }

        for idx, signal_name in enumerate(self._signals):
            y = y_border + idx * (y_signal + y_sep)
            if idx != 0:
                y_line = y - y_sep // 2
                painter.setPen(line_color)
                painter.drawLine(x_border, y_line, x_max - x_border, y_line)
            y_start = y
            x = x_border

            if parent.show_titles:
                painter.setPen(title_color)
                painter.setFont(title_font)
                y += title_font_metrics.ascent()
                signal_title_parts = [resolved, signal_name]
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
                fields = ['accumulate_duration']
                signal_value, signal_units = convert_units(signal['value'], signal['units'], parent.units)
                _, prefix, scale = unit_prefix(signal_value)
            else:
                signal = self._statistics['signals'][signal_name]
                fields = fields if parent.show_fields else []
                fields_all = [self._main] + fields
                max_value = max([abs(signal[s]['value']) for s in fields_all])
                _, prefix, scale = unit_prefix(max_value)
                signal_value = signal[self._main]['value']
                signal_units = signal[self._main]['units']
            if len(prefix) != 1:
                prefix = ' '
            v_str = ('%+6f' % (signal_value / scale))[:8]
            v_str_idx = 1
            if v_str[0] == '-' or parent.show_sign:
                painter.drawText(x, y, v_str[0])
                v_str_idx = 0
            x += main_char_width
            painter.drawText(x, y, v_str[1:])
            x += main_number_width + main_char_width // 2
            w1 = main_font_metrics.boundingRect(signal_units).width()
            w2 = main_font_metrics.boundingRect(prefix + signal_units).width()
            x_offset = int(main_text_width * 1.5 - w1 / 2)
            painter.drawText(x + x_offset - (w2 - w1), y, prefix)
            painter.drawText(x + x_offset, y, signal_units)
            x += 2 * main_text_width
            self._geometry['values'][idx] = {'avg': f'{v_str[v_str_idx:]} {prefix}{signal_units}'}

            painter.setPen(stats_color)
            painter.setFont(stats_font)
            y = y_start + (y_signal - y2) // 2
            x += main_text_width // 2
            x_start = x
            self._geometry['fields'][idx] = fields

            for field_idx, stat in enumerate(fields):
                if field_idx == 0:
                    y += stats_space
                y += stats_font_metrics.ascent()
                x = x_start
                self._geometry['x_stats'] = x
                if stat == 'accumulate_duration':
                    painter.drawText(x, y, a_duration_txt)
                else:
                    v_str = ('%+6f' % (signal[stat]['value'] / scale))[:8]
                    v_str_idx = 1
                    if v_str[0] == '-' or parent.show_sign:
                        painter.drawText(x, y, v_str[0])
                        v_str_idx = 0
                    x += stats_char_width
                    painter.drawText(x, y, v_str[1:])
                    x += stats_number_width + stats_char_width
                    painter.drawText(x, y, stat)
                    self._geometry['values'][idx][stat] = f'{v_str[v_str_idx:]} {prefix}{signal_units}'
                y += stats_font_metrics.descent()

        #color = color_as_qcolor('#ff000040')
        #painter.setPen(color)
        #painter.drawRect(x_border, y_border, x_max - x_border, y - y_border)
        painter.end()

    def _pos_to_item(self, x, y):
        if self._geometry is None:
            return None
        if y < self._geometry['y_border']:
            return None
        y -= self._geometry['y_border']
        y_signal = self._geometry['y_signal']
        y_sep = self._geometry['y_sep']
        y_height = y_signal + y_sep
        idx = int(y // y_height)
        if idx >= len(self._signals):
            return None
        z = y - idx * y_height
        if z > y_signal:  # in separator
            return None
        x_stats = self._geometry.get('x_stats')
        result = {
            'signal_idx': idx,
        }
        if x_stats is not None and x >= x_stats:
            fields = self._geometry['fields'][idx]
            y_stats_space = self._geometry['y_stats_space']
            y_stats = self._geometry['y_stats']
            if z < y_stats_space:
                return None
            k = int(z // y_stats)
            if k >= len(fields):
                return None
            result['field'] = fields[k]
        else:
            result['field'] = 'avg'
        return result

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return super().mousePressEvent(event)
        if self._geometry is None:
            return
        x, y = event.position().x(), event.position().y()
        item = self._pos_to_item(x, y)
        if item is None:
            return
        try:
            value = self._geometry['values'][item['signal_idx']][item['field']]
        except KeyError:
            return
        self._log.info('copy value to clipboard: %s', value)
        self._clipboard = value
        QtWidgets.QApplication.clipboard().setText(self._clipboard)


class _BaseWidget(QtWidgets.QWidget):
    CAPABILITIES = ['widget@', CAPABILITIES.STATISTIC_STREAM_SINK]

    def __init__(self, parent=None):
        self._log = logging.getLogger(__name__ + '.base')
        self._menu = None
        super().__init__(parent=parent)
        self.setObjectName('value_widget')

        self.source_selector = SourceSelector(self, 'statistics_stream')
        self.source_selector.source_changed.connect(self._on_source_changed)
        self.source_selector.sources_changed.connect(self._on_sources_changed)
        self.source_selector.resolved_changed.connect(self._on_resolved_changed)

        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._device_widget = _DeviceWidget(self)
        self._accrue_widget = _AccrueWidget(self)
        self._inner = _InnerWidget(self)
        self._layout.addWidget(self._device_widget)
        self._layout.addWidget(self._accrue_widget)
        self._layout.addWidget(self._inner)
        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._statistics = None  # most recent statistics information
        self.mousePressEvent = self._on_mousePressEvent

    def on_pubsub_register(self):
        topic = f'{get_topic_name(self)}/settings/statistics_stream_source'
        self.source_selector.on_pubsub_register(self.pubsub, topic)
        self.pubsub.subscribe('registry/app/settings/statistics_stream_enable',
                              self._on_global_statistics_stream_enable)
        self.pubsub.subscribe('registry/app/settings/units', lambda: self.update())
        self._connect()

    @QtCore.Slot(object)
    def _on_source_changed(self, value):
        self._device_widget.device_select()
        self._device_widget.device_show(value)
        self.repaint()

    @QtCore.Slot(object)
    def _on_sources_changed(self, value):
        self._device_widget.device_list(value)

    @QtCore.Slot(object)
    def _on_resolved_changed(self, value):
        self._connect()

    def _connect(self):
        self.pubsub.unsubscribe_all(self._on_statistics)
        resolved = self.source_selector.resolved()
        if resolved is None:
            self._device_widget.device_show(None)
        else:
            topic = get_topic_name(resolved)
            self.pubsub.subscribe(f'{topic}/events/statistics/!data', self._on_statistics, ['pub'])
        self.repaint()

    def _accum(self, stats):
        if self._statistics is None:
            return stats
        if stats['source']['unique_id'] != self._statistics['source']['unique_id']:
            return stats
        v_start, v_end = self._statistics['time']['samples']['value']
        v_duration = v_end - v_start
        x_start, x_end = stats['time']['samples']['value']
        x_duration = x_end - x_start
        for signal_name, v in self._statistics['signals'].items():
            x = stats['signals'][signal_name]
            x_min, x_max = x['min']['value'], x['max']['value']
            if np.isfinite(x_min) and np.isfinite(x_max):
                v['min']['value'] = min(v['min']['value'], x_min)
                v['max']['value'] = max(v['max']['value'], x_max)
                v['p2p']['value'] = v['max']['value'] - v['min']['value']
            x_avg, x_std = x['avg']['value'], x['std']['value']
            if np.isfinite(x_avg) and np.isfinite(x_std):
                v_avg, v_std = v['avg']['value'], v['std']['value']
                avg = v_avg + ((x_avg - v_avg) * (x_duration / (x_duration + v_duration)))
                v['avg']['value'] = avg
                x_diff = x_avg - avg
                v_diff = v_avg - avg
                x_var = x_std * x_std
                v_var = v_std * v_std
                s = ((v_var + v_diff * v_diff) * v_duration +
                     (x_var + x_diff * x_diff) * x_duration)
                v['std']['value'] = np.sqrt(s / (x_duration + v_duration - 1))
        self._statistics['time']['accum_samples'] = stats['time']['accum_samples']
        self._statistics['accumulators'] = stats['accumulators']
        self._statistics['time']['samples']['value'] = [v_start, x_end]
        return self._statistics

    def _on_statistics(self, value):
        if self._accrue_widget.is_accrue:
            self._statistics = self._accum(value)
            if 'accum_start' not in self._statistics:
                self._statistics['accum_start'] = datetime.datetime.now().isoformat().split('.')[0]
        else:
            self._statistics = value
        v_start, v_end = self._statistics['time']['samples']['value']
        sample_freq = self._statistics['time']['sample_freq']['value']
        self._device_widget.device_show(self.source_selector.resolved())
        if not self._accrue_widget.hold:
            self._accrue_widget.accrue_duration((v_end - v_start) / sample_freq, self._statistics.get('accum_start'))
            self._inner._on_statistics(self._statistics)

    def _on_global_statistics_stream_enable(self, value):
        self._accrue_widget.hold_global = not bool(value)

    def on_setting_show_device_selection(self, value):
        self._device_widget.setVisible(bool(value))

    def on_setting_show_accrue(self, value):
        self._accrue_widget.setVisible(bool(value))

    def _on_mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton:
            pass
        elif event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            self.source_selector.submenu_factory(menu)
            settings_action_create(self, menu)
            context_menu_show(menu, event)

    def on_style_change(self):
        self.update()


@register
@styled_widget(N_('Multimeter'))
class MultimeterWidget(_BaseWidget):
    SETTINGS = _MULTIMETER_SETTINGS

    def __init__(self, parent=None):
        super().__init__(parent)


@register
@styled_widget(N_('Value'))
class ValueWidget(_BaseWidget):
    SETTINGS = _VALUE_SETTINGS

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inner._signals = ['current']

    def on_setting_signal(self, value):
        self._inner._signals = [value]
