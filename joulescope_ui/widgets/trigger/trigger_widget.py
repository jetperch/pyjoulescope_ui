# Copyright 2024 Jetperch LLC
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

from PySide6 import QtCore, QtGui, QtWidgets
from .condition_detector import condition_detector_factory, is_digital_signal
from joulescope_ui import N_, P_, tooltip_format, register, CAPABILITIES, get_topic_name, time64
from joulescope_ui.ui_util import comboBoxConfig, comboBoxSelectItemByText
from joulescope_ui.styles import styled_widget, color_as_qcolor
from joulescope_ui.widgets.signal_record import SignalRecord, signal_record_config_widget
from joulescope_ui.widgets.statistics_record import StatisticsRecord, statistics_record_config_widget
from joulescope_ui.widgets.waveform.interval_widget import IntervalWidget, str_to_float
from joulescope_ui.source_selector import SourceSelector
import copy
import logging
import numpy as np


_STYLE = """\
<style>
table {
  border-collapse: collapse
}
th, td {
  padding: 5px;
  border: 1px solid;
}
</style>
"""
_DEVICE_TOOLTIP = tooltip_format(
    N_('Select the source device'),
    N_("The device to use for the start condition and stop condition."))

_RUN_MODE_TITLE = N_('Configure run mode')
_RUN_MODE_SINGLE = N_('Single')
_RUN_MODE_SINGLE_DETAIL = N_('Perform one trigger sequence and then return to inactive mode.')
_RUN_MODE_CONTINUOUS = N_('Continuous')
_RUN_MODE_CONTINUOUS_DETAIL = N_('Repeat the trigger sequence indefinitely until manually stopped.')
_RUN_MODE_TOOLTIP = f"""\
<html><header>{_STYLE}</header>
<body>
<h3>{_RUN_MODE_TITLE}</h3>
<p><table>
  <tr>
    <td>{_RUN_MODE_SINGLE}</td>
    <td>{_RUN_MODE_SINGLE_DETAIL}</td>
  </tr>
  <tr>
    <td>{_RUN_MODE_CONTINUOUS}</td>
    <td>{_RUN_MODE_CONTINUOUS_DETAIL}</td>
  </tr>
</table></p></body></html>
"""

_STATUS_TITLE = N_('Start, stop and indicate status')
_STATUS_INACTIVE = N_('Inactive')
_STATUS_INACTIVE_DETAIL = N_('Configure trigger options and then press to start.')
_STATUS_SEARCHING = N_('Searching')
_STATUS_SEARCHING_DETAIL = N_(
    'Look for the configured start condition. '
    'On match, perform the start actions and advance to active. '
    'Press to halt and return to inactive.')
_STATUS_ACTIVE = N_('Active')
_STATUS_ACTIVE_DETAIL = N_(
    'Look for the configured stop condition. '
    'On match, perform the stop actions. '
    'For run mode single, transition to inactive. '
    'For run mode continuous, transition to searching. '
    'Press to halt and return to inactive.')
_STATUS_ACTIVE_DESCRIPTION = N_
_STATUS_TOOLTIP = f"""\
<html><header>{_STYLE}</header>
<body>
<h3>{_STATUS_TITLE}</h3>
<p><table>
  <tr>
    <td>{_STATUS_INACTIVE}</td>
    <td>{_STATUS_INACTIVE_DETAIL}</td>
  </tr>
  <tr>
    <td>{_STATUS_SEARCHING}</td>
    <td>{_STATUS_SEARCHING_DETAIL}</td>
  </tr>
  <tr>
    <td>{_STATUS_ACTIVE}</td>
    <td>{_STATUS_ACTIVE_DETAIL}</td>
  </tr>
</table></p></body></html>
"""


def generate_map(value):
    m = {}
    for idx, args in enumerate(value):
        v = args[0]
        m[idx] = v
        for arg in args:
            m[arg] = v
    return m


_CONDITION_TYPE_LIST = [
    ['edge', N_('Edge')],
    ['duration', N_('Duration')],
]
_CONDITION_TYPES = generate_map(_CONDITION_TYPE_LIST)

_EDGE_CONDITION_LIST = [
    ['rising', '↑'],
    ['falling', '↓'],
    ['both', '↕'],
]
_EDGE_CONDITIONS = generate_map(_EDGE_CONDITION_LIST)

_DURATION_META_SIGNAL_LIST = [
    ['always', N_('Always')],
    ['never', N_('Never')],
]
_DURATION_META_SIGNALS = generate_map(_DURATION_META_SIGNAL_LIST)

_DURATION_CONDITION_LIST = [
    ['>', '>'],
    ['<', '<'],
    ['between', N_('between')],
    ['outside', N_('outside')],
]
_DURATION_CONDITIONS = generate_map(_DURATION_CONDITION_LIST)

_DIGITAL_DURATION_CONDITION_LIST = [
    ['0', '0'],
    ['1', '1'],
]
_DIGITAL_DURATION_CONDITIONS = generate_map(_DIGITAL_DURATION_CONDITION_LIST)

_SIGNAL_UNITS = {
    'i': 'A',
    'v': 'V',
    'p': 'W',
}

_SI_PREFIX = {
    'n': 1e-9,
    'µ': 1e-6,
    'm': 1e-3,
    '': 1e0,
    None: 1e0,
    'k': 1e3,
}


SETTINGS = {
    'source': {
        'dtype': 'str',
        'brief': N_('The source instrument.'),
        'default': None,
    },
    'mode': {
        'dtype': 'str',
        'brief': 'The trigger mode.',
        'default': 'single',
        'options': [
            ['single', _RUN_MODE_SINGLE],
            ['continuous', _RUN_MODE_CONTINUOUS],
        ],
    },
    'status': {
        'dtype': 'str',
        'brief': 'Arm the trigger.',
        'default': 'inactive',
        'options': [
            ['inactive', _STATUS_INACTIVE],
            ['searching', _STATUS_SEARCHING],
            ['active', _STATUS_ACTIVE],
        ],
        'flags': ['ro', 'hide', 'tmp'],
    },
    'config': {
        'dtype': 'obj',
        'brief': 'The trigger configuration.',
        'default': None,
    },
}


def _sample_utc_end(value):
    fs = value['sample_freq']
    return int(len(value['data']) / fs * time64.SECOND) + value['utc']


def _grid_row_set_visible(layout, row, visible):
    visible = bool(visible)
    for col in range(layout.columnCount()):
        item = layout.itemAtPosition(row, col)
        if item is not None:
            widget = item.widget()
            if widget is not None:
                widget.setVisible(visible)


class ConditionWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._signal_list = []
        self._value_scale = None
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.addWidget(QtWidgets.QLabel(N_('Type')), 0, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Signal')), 1, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Condition')), 2, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Duration')), 3, 0, 1, 1)

        self._type = QtWidgets.QComboBox()
        comboBoxConfig(self._type, [x[1] for x in _CONDITION_TYPE_LIST])
        self._type.currentIndexChanged.connect(self._visibility_update)

        self._layout.addWidget(self._type, 0, 1, 1, 1)

        self._source_widget = QtWidgets.QWidget()
        self._source_layout = QtWidgets.QHBoxLayout(self._source_widget)
        self._source_layout.setContentsMargins(0, 0, 0, 0)
        self._signal = QtWidgets.QComboBox()
        self._signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._signal.currentIndexChanged.connect(self._visibility_update)
        self._source_layout.addWidget(self._signal)
        self._layout.addWidget(self._source_widget, 1, 1, 1, 1)

        self._condition_widget = QtWidgets.QWidget()
        self._condition_layout = QtWidgets.QHBoxLayout(self._condition_widget)
        self._condition_layout.setContentsMargins(0, 0, 0, 0)
        self._condition = QtWidgets.QComboBox()
        self._condition.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._condition.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        self._condition_layout.addWidget(self._condition)
        self._condition.currentIndexChanged.connect(self._visibility_update)

        self._value1 = QtWidgets.QLineEdit('0')
        self._value1_validator = QtGui.QDoubleValidator(self)
        self._value1.setValidator(self._value1_validator)
        self._condition_layout.addWidget(self._value1)

        self._value2 = QtWidgets.QLineEdit('0')
        self._value2_validator = QtGui.QDoubleValidator(self)
        self._value2.setValidator(self._value2_validator)
        self._condition_layout.addWidget(self._value2)

        self._value_units = QtWidgets.QComboBox()
        self._value_units.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._value_units.currentIndexChanged.connect(self._on_value_units)
        self._condition_layout.addWidget(self._value_units)

        spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._condition_layout.addItem(spacer)
        self._layout.addWidget(self._condition_widget, 2, 1, 1, 1)

        self._duration = IntervalWidget(self, 1)
        self._layout.addWidget(self._duration, 3, 1, 1, 1)

        signals = [
            self._type.currentIndexChanged,
            self._signal.currentIndexChanged,
            self._condition.currentIndexChanged,
            self._value1.textChanged,
            self._value2.textChanged,
            self._value_units.currentIndexChanged,
            self._duration.value_changed,
        ]
        for signal in signals:
            signal.connect(self._on_config_update)
        self._visibility_update()

    @QtCore.Slot(object)
    def _on_config_update(self, value=None):
        cfg = self.config
        self.config_changed.emit(cfg)

    def _condition_list_get(self):
        type_idx = self._type.currentIndex()
        signal = self._signal_list_with_meta()[self._signal.currentIndex()][0]
        if type_idx == 0:
            return _EDGE_CONDITION_LIST
        elif is_digital_signal(signal):
            return _DIGITAL_DURATION_CONDITION_LIST
        elif signal in _DURATION_META_SIGNALS:
            return None
        else:
            return _DURATION_CONDITION_LIST

    @property
    def config(self):
        type_name = _CONDITION_TYPE_LIST[self._type.currentIndex()][0]
        signal = self._signal_list_with_meta()[self._signal.currentIndex()][0]
        condition_list = self._condition_list_get()
        if condition_list is None:
            condition = None
        else:
            condition = condition_list[self._condition.currentIndex()][0]

        v1 = str_to_float(self._value1.text())
        v2 = str_to_float(self._value2.text())
        v_unit = self._value_units.currentText()
        v_unit = '' if len(v_unit) <= 1 else v_unit[0]
        v_scale = _SI_PREFIX[v_unit]
        v1 *= v_scale
        v2 *= v_scale

        return {
            'type': type_name,
            'signal': signal,
            'condition': condition,
            'value1': v1,
            'value2': v2,
            'value_unit': v_unit,
            'duration': self._duration.value,
        }

    @config.setter
    def config(self, value):
        if value is None:
            value = self.config
        type_name = value.get('type', 'edge')
        condition_types = [x[0] for x in _CONDITION_TYPE_LIST]
        block = self._type.blockSignals(True)
        self._type.setCurrentIndex(condition_types.index(type_name))
        self._type.blockSignals(block)
        self._visibility_update()

        signal_list = self._signal_list_with_meta()
        if len(signal_list):
            signals = [x[0] for x in signal_list]
            try:
                signal_idx = signals.index(value.get('signal'))
            except ValueError:
                signal_idx = 0
            signal = signal_list[signal_idx][0]
            block = self._signal.blockSignals(True)
            self._signal.setCurrentIndex(signal_idx)
            self._signal.blockSignals(block)
        self._visibility_update()

        condition = value['condition']
        condition_list = self._condition_list_get()
        try:
            condition_idx = [x[0] for x in condition_list].index(condition)
            self._condition.setCurrentIndex(condition_idx)
        except (TypeError, IndexError):
            pass
        self._visibility_update()

        v_unit = value.get('value_unit', '')
        unit = _SIGNAL_UNITS.get(signal, None)
        if unit is not None:
            comboBoxSelectItemByText(self._value_units, v_unit + unit, block=True)
            self._value_units_update()
        v_scale = _SI_PREFIX[v_unit]
        block = self._value1.blockSignals(True)
        self._value1.setText(f'{value["value1"] / v_scale:g}')
        self._value1.blockSignals(block)
        block = self._value2.blockSignals(True)
        self._value2.setText(f'{value["value2"] / v_scale:g}')
        self._value2.blockSignals(block)

        self._duration.value = value['duration']

    def _value_units_update(self):
        self._value_scale = 1.0 if self._value_scale is None else float(self._value_scale)
        value = self._value_units.currentText()
        prefix = '' if len(value) <= 1 else value[0]
        scale = _SI_PREFIX[prefix]
        for w in [self._value1, self._value2]:
            v = str_to_float(w.text()) * (self._value_scale / scale)
            w.setText(f'{v:g}')
        self._value_scale = scale

    @QtCore.Slot()
    def _visibility_update(self):
        type_index = self._type.currentIndex()
        _grid_row_set_visible(self._layout, 3, type_index != 0)

        signal_list = self._signal_list_with_meta()
        comboBoxConfig(self._signal, [s[1] for s in signal_list])
        try:
            signal = signal_list[self._signal.currentIndex()][0]
        except IndexError:
            return
        if signal in ['always', 'never']:
            _grid_row_set_visible(self._layout, 2, False)
            return
        _grid_row_set_visible(self._layout, 2, True)
        is_digital = is_digital_signal(signal)
        condition_list = self._condition_list_get()
        if condition_list is None:
            self._condition.clear()
        else:
            comboBoxConfig(self._condition, [x[1] for x in condition_list])

        if type_index == 0:  # edge
            visibility = [not is_digital, False, not is_digital]
        elif type_index == 1:  # duration
            if is_digital:
                duration = _DIGITAL_DURATION_CONDITIONS[self._condition.currentIndex()]
            else:
                duration = _DURATION_CONDITIONS[self._condition.currentIndex()]
            if duration in ['0', '1']:
                visibility = [False, False, False]
            elif duration in ['between', 'outside']:
                visibility = [True, True, True]
            else:
                visibility = [True, False, not is_digital]
        self._value1.setVisible(visibility[0])
        self._value2.setVisible(visibility[1])

        try:
            unit = _SIGNAL_UNITS.get(signal, None)
        except (IndexError, ValueError, KeyError):
            unit = None
        if unit is None:
            self._value_units.clear()
        else:
            prefixes = ['m', ''] if signal == 'v' else ['n', 'µ', 'm', '']
            unit_enum = [prefix + unit for prefix in prefixes]
            comboBoxConfig(self._value_units, unit_enum, unit)
            self._value_units_update()
        self._value_units.setVisible(visibility[2] and signal not in ['r'])

    def _signal_list_with_meta(self):
        if self._type.currentIndex() == 1:  # duration
            return self._signal_list + _DURATION_META_SIGNAL_LIST
        else:
            return list(self._signal_list)

    def on_signal_list(self, value):
        self._signal_list = value
        self._visibility_update()

    @QtCore.Slot(int)
    def _on_value_units(self, index):
        self._value_units_update()


class StartActionsWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._output_list = []
        self._sample_record_config = None
        self._stats_record_config = None
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)

        self._sample_record = QtWidgets.QCheckBox()
        self._layout.addWidget(self._sample_record, 0, 0, 1, 1)
        self._sample_record1 = QtWidgets.QHBoxLayout()
        self._sample_record1.addWidget(QtWidgets.QLabel(N_('Record samples')))
        self._sample_record_config_button = QtWidgets.QPushButton(N_('Config'))
        self._sample_record_config_button.pressed.connect(self._on_sample_record_config)
        self._sample_record1.addWidget(self._sample_record_config_button)
        self._layout.addLayout(self._sample_record1, 0, 1, 1, 1)
        self._sample_record_pre = IntervalWidget(None, 1.0, name=N_('Start buffer'))
        self._layout.addWidget(self._sample_record_pre, 1, 1, 1, 1)
        self._sample_record_post = IntervalWidget(None, 1.0, name=N_('Stop delay'))
        self._layout.addWidget(self._sample_record_post, 2, 1, 1, 1)

        self._stats_record = QtWidgets.QCheckBox()
        self._layout.addWidget(self._stats_record, 3, 0, 1, 1)
        self._stats_record1 = QtWidgets.QHBoxLayout()
        self._stats_record1.addWidget(QtWidgets.QLabel(N_('Record statistics')))
        self._stats_record_config_button = QtWidgets.QPushButton(N_('Config'))
        self._stats_record_config_button.pressed.connect(self._on_statistics_record_config)
        self._stats_record1.addWidget(self._stats_record_config_button)
        self._layout.addLayout(self._stats_record1, 3, 1, 1, 1)
        self._stats_record_pre = IntervalWidget(None, 1.0, name=N_('Start buffer'))
        self._layout.addWidget(self._stats_record_pre, 4, 1, 1, 1)
        self._stats_record_post = IntervalWidget(None, 1.0, name=N_('Stop delay'))
        self._layout.addWidget(self._stats_record_post, 5, 1, 1, 1)

        self._output = QtWidgets.QCheckBox()
        self._layout.addWidget(self._output, 6, 0, 1, 1)
        output_layout = QtWidgets.QHBoxLayout()
        output_layout.addWidget(QtWidgets.QLabel(N_('Set output')))
        self._output_signal = QtWidgets.QComboBox()
        self._output_signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._output_value = QtWidgets.QComboBox()
        comboBoxConfig(self._output_value, ['0', '1'], '1')
        output_layout.addWidget(self._output_signal)
        self._output_arrow = QtWidgets.QLabel('→')
        self._output_arrow.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(self._output_arrow)
        output_layout.addWidget(self._output_value)
        self._layout.addLayout(output_layout, 6, 1, 1, 1, QtCore.Qt.AlignmentFlag.AlignTop)

        self._single_marker = QtWidgets.QCheckBox()
        self._layout.addWidget(self._single_marker, 7, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Add single marker')), 7, 1, 1, 1)

        self._layout.setColumnStretch(1, 1)

        self._checkboxes = ['sample_record', 'stats_record', 'output', 'single_marker']

        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.toggled.connect(self._on_config_update)
        signals = [
            self._sample_record_pre.value_changed,
            self._sample_record_post.value_changed,
            self._stats_record_pre.value_changed,
            self._stats_record_post.value_changed,
            self._output_signal.currentIndexChanged,
            self._output_value.currentIndexChanged,
        ]
        for signal in signals:
            signal.connect(self._on_config_update)
        self._visibility_update()

    @QtCore.Slot(object)
    def _on_sample_record_config_update(self, value):
        self._sample_record_config = value
        self._on_config_update()

    @QtCore.Slot()
    def _on_sample_record_config(self):
        dialog = signal_record_config_widget.SignalRecordConfigDialog(skip_default_actions=True,
                                                                      config=self._sample_record_config)
        dialog.config_changed.connect(self._on_sample_record_config_update)

    @QtCore.Slot(object)
    def _on_statistics_record_config_update(self, value):
        self._stats_record_config = value
        self._on_config_update()

    def _on_statistics_record_config(self):
        cls = statistics_record_config_widget.StatisticsRecordConfigDialog
        dialog = cls(skip_default_actions=True, config=self._stats_record_config)
        dialog.config_changed.connect(self._on_statistics_record_config_update)

    def _visibility_update(self):
        sample_record = self._sample_record.isChecked()
        self._sample_record_config_button.setVisible(sample_record)
        _grid_row_set_visible(self._layout, 1, sample_record)
        _grid_row_set_visible(self._layout, 2, sample_record)

        stats_record = self._stats_record.isChecked()
        self._stats_record_config_button.setVisible(stats_record)
        _grid_row_set_visible(self._layout, 4, stats_record)
        _grid_row_set_visible(self._layout, 5, stats_record)

        output = self._output.isChecked()
        for w in [self._output_signal, self._output_arrow, self._output_value]:
            w.setVisible(output)

    @QtCore.Slot()
    def _on_config_update(self):
        cfg = self.config
        self._visibility_update()
        self.config_changed.emit(cfg)

    @property
    def config(self):
        rv = {
            'sample_record_pre': self._sample_record_pre.value,
            'sample_record_post': self._sample_record_post.value,
            'sample_record_config': self._sample_record_config,
            'stats_record_pre': self._stats_record_pre.value,
            'stats_record_post': self._stats_record_post.value,
            'stats_record_config': self._stats_record_config,
            'output_signal': self._output_signal.currentText(),
            'output_value': self._output_value.currentIndex(),
        }
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            rv[checkbox_name] = checkbox.isChecked()
        return rv

    @config.setter
    def config(self, value):
        if value is None:
            value = self.config
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.setChecked(value[checkbox_name])
        self._sample_record_pre.value = value['sample_record_pre']
        self._sample_record_post.value = value['sample_record_post']
        self._sample_record_config = value.get('sample_record_config', None)
        self._stats_record_pre.value = value['stats_record_pre']
        self._stats_record_post.value = value['stats_record_post']
        self._stats_record_config = value.get('stats_record_config', None)
        comboBoxSelectItemByText(self._output_signal, value['output_signal'])
        block = self._output_value.blockSignals(True)
        self._output_value.setCurrentIndex(value['output_value'])
        self._output_value.blockSignals(block)
        self._visibility_update()

    def on_output_list(self, value):
        self._output_list = value
        comboBoxConfig(self._output_signal, value)


class StopActionsWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._output_list = []
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)

        self._output = QtWidgets.QCheckBox()
        self._layout.addWidget(self._output, 0, 0, 1, 1)
        output_layout = QtWidgets.QHBoxLayout()
        output_layout.addWidget(QtWidgets.QLabel(N_('Set output')))
        self._output_signal = QtWidgets.QComboBox()
        self._output_signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._output_value = QtWidgets.QComboBox()
        comboBoxConfig(self._output_value, ['0', '1'], '0')
        output_layout.addWidget(self._output_signal)
        self._output_arrow = QtWidgets.QLabel('→')
        self._output_arrow.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(self._output_arrow)
        output_layout.addWidget(self._output_value)
        self._layout.addLayout(output_layout, 0, 1, 1, 1, QtCore.Qt.AlignmentFlag.AlignTop)

        self._single_marker = QtWidgets.QCheckBox()
        self._layout.addWidget(self._single_marker, 1, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Add single marker')), 1, 1, 1, 1)

        self._dual_marker = QtWidgets.QCheckBox()
        self._layout.addWidget(self._dual_marker, 2, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Add dual markers')), 2, 1, 1, 1)

        self._buffer_stop = QtWidgets.QCheckBox()
        self._layout.addWidget(self._buffer_stop, 3, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Stop sample buffer')), 3, 1, 1, 1)
        self._buffer_stop_delay = IntervalWidget(None, 1.0, name=N_('Delay'))
        self._layout.addWidget(self._buffer_stop_delay, 4, 1, 1, 1)

        self._layout.setColumnStretch(1, 1)
        self._checkboxes = ['output', 'single_marker', 'dual_marker', 'buffer_stop']

        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.toggled.connect(self._on_config_update)
        signals = [
            self._output_signal.currentIndexChanged,
            self._output_value.currentIndexChanged,
            self._buffer_stop_delay.value_changed,
        ]
        for signal in signals:
            signal.connect(self._on_config_update)
        self._visibility_update()

    def _visibility_update(self):
        output = self._output.isChecked()
        for w in [self._output_signal, self._output_arrow, self._output_value]:
            w.setVisible(output)

        _grid_row_set_visible(self._layout, 4, self._buffer_stop.isChecked())

    @QtCore.Slot()
    def _on_config_update(self):
        cfg = self.config
        self._visibility_update()
        self.config_changed.emit(cfg)

    @property
    def config(self):
        rv = {
            'output_signal': self._output_signal.currentText(),
            'output_value': self._output_value.currentIndex(),
            'buffer_stop_delay': self._buffer_stop_delay.value,
        }
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            rv[checkbox_name] = checkbox.isChecked()
        return rv

    @config.setter
    def config(self, value):
        if value is None:
            value = self.config
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.setChecked(value.get(checkbox_name, False))
        comboBoxSelectItemByText(self._output_signal, value.get('output_signal', '0'))
        block = self._output_value.blockSignals(True)
        self._output_value.setCurrentIndex(value.get('output_value', 0))
        self._output_value.blockSignals(block)
        self._buffer_stop_delay.value = value.get('buffer_stop_delay', 0.0)

    def on_output_list(self, value):
        self._output_list = value
        comboBoxConfig(self._output_signal, value)


class SectionWidget(QtWidgets.QFrame):

    def __init__(self, parent, heading: str, body: QtWidgets.QFrame):
        super().__init__(parent=parent)
        self.setObjectName('SectionWidget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        heading = QtWidgets.QLabel(heading)
        heading.setProperty('section_heading', True)
        self._layout.addWidget(heading)
        body.setProperty('section_body', True)
        self._layout.addWidget(body)


class StatusButton(QtWidgets.QPushButton):

    def __init__(self, parent=None):
        self._interval_ms = 30
        self._angle = 0.0
        self._brush = None
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._on_timer)
        self.setProperty('status', 'inactive')

    @property
    def status(self):
        return self.property('status')

    @status.setter
    def status(self, value):
        if value not in ['inactive', 'searching', 'active']:
            raise ValueError(f'invalid status: {value}')
        self.setProperty('status', value)
        if value == 'active':
            self._timer.start(30)
        else:
            self._timer.stop()

    def _on_timer(self):
        self._angle -= (360 * self._interval_ms) / 1000
        self.repaint()

    def on_style_change(self, fg):
        self._brush = QtGui.QBrush(color_as_qcolor(fg))

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.status != 'active':
            return
        w, h = self.width(), self.height()
        r = min(w, h) // 2
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.translate(w / 2, h / 2)
        painter.rotate(self._angle)
        painter.setBrush(self._brush)
        r_sz = (1.5 * r) / 10
        p = QtCore.QPointF(r / 2, 0)
        for i in range(7):
            scale = (8 - i) / 8
            k = r_sz * scale
            painter.drawEllipse(p, k, k)
            painter.rotate(45)
        painter.end()


@register
@styled_widget(N_('Trigger'))
class TriggerWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']
    SETTINGS = SETTINGS

    def __init__(self, parent=None):
        self._count = 0
        self._utc = None  # time64 for the most recently detected event
        self._utc_start = None  # time64 for the most recent start
        self._utc_stop = None  # time64 for the most recent stop
        self._config = None  # config for activated trigger sequence
        self._config_update_ignore = False
        self._connected = False
        self._log = logging.getLogger(__name__)
        self._resolved_source = None
        self._signal_record = None
        self._signal_record_buffer = {}  # (source, signal) -> list of messages
        self._stats_record = None
        self._stats_record_buffer = {}  # source -> list of messages
        super().__init__(parent=parent)
        self.setObjectName('jls_info_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(6)

        self._always_condition_timer = QtCore.QTimer(self)
        self._always_condition_timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._always_condition_timer.setSingleShot(True)
        self._always_condition_timer.timeout.connect(self._on_always_condition_timer)

        self._buffer_stop_timer = QtCore.QTimer(self)
        self._buffer_stop_timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._buffer_stop_timer.setSingleShot(True)
        self._buffer_stop_timer.timeout.connect(self._on_buffer_stop_timer)

        self._source_selector = SourceSelector(self, 'signal_stream')
        self._source_selector.source_changed.connect(self._on_source_changed)
        self._source_selector.sources_changed.connect(self._on_sources_changed)
        self._source_selector.resolved_changed.connect(self._on_resolved_changed)

        self._error = QtWidgets.QLabel(N_('No sources found'))
        self._error.setVisible(False)
        self._layout.addWidget(self._error)

        self._header = QtWidgets.QWidget()
        self._header_layout = QtWidgets.QHBoxLayout(self._header)
        self._source = QtWidgets.QComboBox()
        self._source.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._source.setToolTip(_DEVICE_TOOLTIP)
        self._header_layout.addWidget(self._source)
        header_spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._header_layout.addItem(header_spacer)

        self._run_mode_button = QtWidgets.QPushButton()
        self._run_mode_button.setObjectName('run_mode')
        self._run_mode_button.setFlat(True)
        self._run_mode_button.setFixedSize(32, 32)
        self._run_mode_button.setCheckable(True)
        self._run_mode_button.setToolTip(_RUN_MODE_TOOLTIP)
        self._header_layout.addWidget(self._run_mode_button)
        self._run_mode_button.toggled.connect(self._on_config_update)

        self._status_button = StatusButton()
        self._status_button.setObjectName('status')
        self._status_button.setProperty('status', 'inactive')
        self._status_button.setFlat(True)
        self._status_button.setFixedSize(32, 32)
        self._status_button.setCheckable(True)
        self._status_button.setToolTip(_STATUS_TOOLTIP)
        self._status_button.pressed.connect(self._on_status_button_pressed)
        self._header_layout.addWidget(self._status_button)
        self._layout.addWidget(self._header)

        self._start_condition = ConditionWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Start Condition'), self._start_condition))

        self._start_actions = StartActionsWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Start Actions'), self._start_actions))

        self._stop_condition = ConditionWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Stop Condition'), self._stop_condition))

        self._stop_actions = StopActionsWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Stop Actions'), self._stop_actions))

        self._config_widgets = [self._start_condition, self._start_actions, self._stop_condition, self._stop_actions]
        for w in self._config_widgets:
            w.config_changed.connect(self._on_config_changed)

        spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(spacer)

    def _status_update(self, status):
        self._status_button.status = status
        style = self._status_button.style()
        style.unpolish(self._status_button)
        style.polish(self._status_button)

    def _condition_enter(self, condition):
        signal = condition['signal']
        if signal == 'always':
            duration_ms = int(np.ceil(condition['duration'] * 1000))
            self._always_condition_timer.start(duration_ms)
        elif signal == 'never':
            pass  # never expire, need manual intervention
        else:
            fn = condition.get('fn')
            if hasattr(fn, 'clear'):
                fn.clear()
            data = copy.copy(condition.get('data'))
            if data is not None and data['utc'] <= self._utc:
                fs = data['sample_freq']
                idx = int((self._utc - data['utc']) / time64.SECOND * fs)
                if idx < len(data['data']):
                    data['sample_id'] += idx
                    data['origin_sample_id'] += int(idx * data['orig_sample_freq'] / fs)
                    data['utc'] += int((idx / fs) * time64.SECOND)
                    data['data'] = data['data'][idx:]
                    self._process_signal_data(data)

    def _output_perform(self, actions):
        if not actions['output']:
            return
        source = self._config['source']
        signal = actions['output_signal']
        value = actions['output_value']
        topic = f'{get_topic_name(source)}/settings/out/{signal}'
        self.pubsub.publish(topic, value)

    def _waveform_widget(self):
        view = self.pubsub.query('registry/view/settings/active', default=None)
        if view is None:
            return
        children = self.pubsub.query(f'{get_topic_name(view)}/children')
        children = [c for c in children if c.startswith('WaveformWidget:')]
        if len(children) == 0:
            return None
        return children[0]

    def single_marker_add(self, utc):
        waveform_widget = self._waveform_widget()
        if waveform_widget is None:
            self._log.warning('single_marker_add but no waveform widget found')
            return
        self.pubsub.publish(f'{get_topic_name(waveform_widget)}/actions/!x_markers',
                            ['add_single', utc])

    def dual_marker_add(self, utc_start, utc_end):
        waveform_widget = self._waveform_widget()
        if waveform_widget is None:
            self._log.warning('single_marker_add but no waveform widget found')
            return
        self.pubsub.publish(f'{get_topic_name(waveform_widget)}/actions/!x_markers',
                            ['add_dual', utc_start, utc_end])

    def _start_actions_perform(self):
        actions = self._config['start_actions']
        if actions['sample_record']:
            config = actions['sample_record_config']
            config = signal_record_config_widget.config_update(config, count=self._count)
            self._signal_record = SignalRecord(config)
            for topic, buffer in self._signal_record_buffer.items():
                for b in buffer:
                    self._signal_record._on_data(topic, b)
        if actions['stats_record']:
            config = actions['stats_record_config']
            config = statistics_record_config_widget.config_update(config, count=self._count)
            self._stats_record = {}
            for source_id, source in config['sources'].items():
                if not source['enabled']:
                    continue
                topic = f'{get_topic_name(source_id)}/events/statistics/!data'
                obj = StatisticsRecord(topic, source['path'], config)
                self._stats_record[source_id] = obj
                for b in self._stats_record_buffer.get(source_id, []):
                    obj._on_data(topic, b)

        self._output_perform(actions)
        if actions['single_marker']:
            self.single_marker_add(self._utc_start)

    def _stop_actions_perform(self):
        signal_record, self._signal_record = self._signal_record, None
        if signal_record is not None:
            post = self._config['start_actions']['sample_record_post']
            utc = self._utc_stop + int(post * time64.SECOND)
            signal_record.stop_pend(utc, [self._utc_start, self._utc_stop])
        stats_record, self._stats_record = self._stats_record, None
        if stats_record is not None:
            post = self._config['start_actions']['stats_record_post']
            utc = self._utc_stop + int(post * time64.SECOND)
            for obj in stats_record.values():
                obj.stop_pend(utc)
        actions = self._config['stop_actions']
        self._output_perform(actions)
        if actions['single_marker']:
            self.single_marker_add(self._utc_stop)
        if actions['dual_marker']:
            self.dual_marker_add(self._utc_start, self._utc_stop)
        if actions['buffer_stop']:
            delay = actions['buffer_stop_delay']
            if delay <= 0:
                self._on_buffer_stop_timer()
            else:
                self._buffer_stop_timer.start(int(np.ceil(delay * 1000)))

    def _on_buffer_stop_timer(self):
        self.pubsub.publish('registry/app/settings/signal_stream_enable', False)

    def _on_detect(self):
        status = self._status_button.status
        if status == 'searching':
            self._utc_start = self._utc
            self._start_actions_perform()
            self._status_update('active')
            self._condition_enter(self._config['stop_condition'])
        elif status == 'active':
            self._utc_stop = self._utc
            self._stop_actions_perform()
            if self._config['run_mode'] == 'single':
                self._deactivate()
            else:
                self._count += 1
                self._status_update('searching')
                self._condition_enter(self._config['start_condition'])

    @QtCore.Slot()
    def _on_always_condition_timer(self):
        self._utc = time64.now()
        self._on_detect()

    def _on_signal_data(self, topic, value):
        parts = topic.split('/')
        topic_source = parts[1]
        topic_signal = parts[4]
        data_type = value['dtype']
        y = value['data']
        if data_type in ['f32', 'f64', 'u8', 'u16', 'u32', 'u64', 'i8', 'i16', 'i32', 'i64']:
            pass
        elif data_type == 'u1':
            y = np.unpackbits(y, bitorder='little')
        elif data_type in ['u4', 'i4']:
            d = np.empty(len(y) * 2, dtype=np.uint8)
            d[0::2] = np.bitwise_and(y, 0x0f)
            d[1::2] = np.bitwise_and(np.right_shift(y, 4), 0x0f)
            y = d
        value = copy.copy(value)
        value['topic'] = topic
        value['data'] = y
        value['topic_source'] = topic_source
        value['topic_signal'] = topic_signal
        self._process_signal_data(value)

    def _process_signal_data(self, value):
        topic_source, topic_signal = value['topic_source'], value['topic_signal']
        cfg = self._config
        start_condition = cfg['start_condition']
        stop_condition = cfg['stop_condition']
        status = self._status_button.status
        if status == 'inactive':
            return
        condition = start_condition if status == 'searching' else stop_condition
        if topic_source == cfg['source']:
            for c in [start_condition, stop_condition]:
                if topic_signal == c['signal']:
                    c['data'] = value
            if topic_signal == condition['signal']:
                fs = value['sample_freq']
                data = value['data']
                rv = condition['fn'](fs, data)
                if rv is not None:
                    self._utc = int((rv / fs) * time64.SECOND) + value['utc']
                    self._on_detect()

    def _on_signal_record_data(self, topic, value):
        if self._config is None:
            return
        pre = self._config['start_actions']['sample_record_pre']
        if pre <= 0:
            return
        if topic not in self._signal_record_buffer:
            self._signal_record_buffer[topic] = []
        b = self._signal_record_buffer[topic]
        b.append(value)
        utc_start = value['utc'] - int(pre * time64.SECOND)  # keep at least one buffer by using start
        while len(b) and _sample_utc_end(b[0]) < utc_start:
            b.pop(0)

    def _on_statistics_record_data(self, topic, value):
        if self._config is None:
            return
        pre = self._config['start_actions']['stats_record_pre']
        if pre <= 0:
            return
        source_id = topic.split('/')[1]
        if source_id not in self._stats_record_buffer:
            self._stats_record_buffer[source_id] = []
        b = self._stats_record_buffer[source_id]
        b.append(value)
        utc_start = value['time']['utc']['value'][0] - int(pre * time64.SECOND)
        while len(b) and (b[0]['time']['utc']['value'][1] <= utc_start):
            b.pop(0)

    def _activate(self):
        if 'inactive' != self._status_button.status:
            self._deactivate()
        for w in self._config_widgets:
            w.setEnabled(False)
        self._status_update('searching')
        self._config = copy.deepcopy(self.config)
        source = self._config['source']
        for condition_name in ['start_condition', 'stop_condition']:
            condition = self._config[condition_name]
            condition['fn'] = condition_detector_factory(condition)

        start_signal = self._config['start_condition']['signal']
        if start_signal not in _DURATION_META_SIGNALS:
            topic = f'{get_topic_name(source)}/events/signals/{start_signal}/!data'
            self._log.info('start_condition subscribe: %s', topic)
            self.pubsub.subscribe(topic, self._on_signal_data, ['pub'])

        stop_signal = self._config['stop_condition']['signal']
        if stop_signal not in _DURATION_META_SIGNALS and start_signal != stop_signal:
            topic = f'{get_topic_name(source)}/events/signals/{stop_signal}/!data'
            self._log.info('stop_condition subscribe: %s', topic)
            self.pubsub.subscribe(topic, self._on_signal_data, ['pub'])

        if self._config['start_actions']['sample_record']:
            config = self._config['start_actions']['sample_record_config']
            for source in config['sources'].values():
                for signal in source.values():
                    if signal['enabled'] and signal['selected']:
                        self.pubsub.subscribe(signal['data_topic'], self._on_signal_record_data, ['pub'])

        if self._config['start_actions']['stats_record']:
            config = self._config['start_actions']['stats_record_config']
            for source_id, source in config['sources'].items():
                if source['enabled']:
                    topic = f'{get_topic_name(source_id)}/events/statistics/!data'
                    self.pubsub.subscribe(topic, self._on_statistics_record_data, ['pub'])

        self._condition_enter(self._config['start_condition'])

    def _deactivate(self):
        self.pubsub.unsubscribe_all(self._on_signal_data)
        self.pubsub.unsubscribe_all(self._on_signal_record_data)
        self.pubsub.unsubscribe_all(self._on_statistics_record_data)
        if 'inactive' == self._status_button.status:
            return
        for w in self._config_widgets:
            w.setEnabled(True)
        self._config = None
        self._signal_record_buffer.clear()
        self._stats_record_buffer.clear()
        self._count = 0
        self._status_update('inactive')

    @QtCore.Slot()
    def _on_status_button_pressed(self):
        status = self._status_button.status
        if status == 'inactive':
            self._activate()
        elif status in ['searching', 'active']:
            self._deactivate()
        else:
            self._log.error('invalid status: %s', status)

    def _signal_list(self):
        topic = f'{get_topic_name(self._resolved_source)}/settings/signals'
        signals = self.pubsub.enumerate(topic)
        signal_list = [[s, self.pubsub.query(f'{topic}/{s}/name')]
                       for s in signals if self.pubsub.query(f'{topic}/{s}/enable')]
        return signal_list

    def _on_signals_changed(self):
        signal_list = self._signal_list()
        self._start_condition.on_signal_list(signal_list)
        self._stop_condition.on_signal_list(signal_list)

    def _connect(self):
        self.pubsub.unsubscribe_all(self._on_signals_changed)
        self._resolved_source = self._source_selector.resolved()
        if self._resolved_source is None:
            self._connected = False
        else:
            topic = f'{get_topic_name(self._resolved_source)}/settings/signals'
            self.pubsub.subscribe(topic, self._on_signals_changed, ['pub'])
            self._on_signals_changed()
            output = self.pubsub.enumerate(f'{get_topic_name(self._resolved_source)}/settings/out')
            self._start_actions.on_output_list(output)
            self._stop_actions.on_output_list(output)
            self._connected = True
            self._config_set(self.config)
        for item in range(self._layout.count()):
            w = self._layout.itemAt(item).widget()
            if w is not None:
                w.setVisible((w is self._error) ^ (self._resolved_source is not None))

    @QtCore.Slot(object)
    def _on_source_changed(self, value):
        self._connect()

    @QtCore.Slot(object)
    def _on_sources_changed(self, value):
        comboBoxConfig(self._source, value)

    @QtCore.Slot(object)
    def _on_resolved_changed(self, value):
        self._connect()

    @QtCore.Slot(object)
    def _on_config_changed(self, config):
        if self._config_update_ignore:
            return
        self.config = self._config_get()

    def _config_get(self):
        return {
            'source': self._resolved_source,
            'run_mode': 'continuous' if self._run_mode_button.isChecked() else 'single',
            'start_condition': self._start_condition.config,
            'start_actions': self._start_actions.config,
            'stop_condition': self._stop_condition.config,
            'stop_actions': self._stop_actions.config,
        }

    def _config_set(self, value):
        if not self._connected:
            return
        if value is None:
            return
        self._config_update_ignore = True
        self._run_mode_button.setChecked(value.get('run_mode', 'single') == 'continuous')
        self._start_condition.config = value['start_condition']
        self._start_actions.config = value['start_actions']
        self._stop_condition.config = value['stop_condition']
        self._stop_actions.config = value['stop_actions']
        self._config_update_ignore = False

    @QtCore.Slot()
    def _on_config_update(self):
        if self._config_update_ignore:
            return
        cfg = self._config_get()
        if cfg != self.config:
            self._config_set(cfg)
            self.config = cfg

    def on_setting_config(self, value):
        if value != self.config:
            self._config_set(value)

    def on_style_change(self):
        v = self.style_obj['vars']
        self._status_button.on_style_change(v['trigger.title_foreground'])

    def on_pubsub_register(self, pubsub):
        topic = f'{self.topic}/settings/source'
        self._source_selector.on_pubsub_register(pubsub, topic)
