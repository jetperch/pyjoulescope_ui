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
from joulescope_ui import N_, P_, tooltip_format, register, CAPABILITIES, get_topic_name
from joulescope_ui.ui_util import comboBoxConfig, comboBoxSelectItemByText
from joulescope_ui.styles import styled_widget
from joulescope_ui.widgets.waveform.interval_widget import IntervalWidget
from joulescope_ui.source_selector import SourceSelector
import logging


_RUN_MODE_TOOLTIP = tooltip_format(
    N_('Configure run mode'),
    P_([
        N_('''Select the run mode, which is either "single" or "continuous"'''),
        N_('"single" mode performs one capture and then returns to inactive mode'),
        N_('"continuous" mode repeats indefinitely until manually stopped'),
    ])
)

_STATUS_TOOLTIP = tooltip_format(
    N_('Status button and indicator'),
    P_([
        N_('When inactive, press to run the trigger sequence. '
           + 'When "searching", press to return to inactive. '
           + 'When "active", press to stop and return to "inactive".'),
        N_('"inactive" allows you to configure the trigger options.'),
        N_('"search" looks for the configured start conditions. '
           + 'When the start conditions are met, it performs the start actions '
           + 'and advances to "active". '),
        N_('"stop" looks for the configured stop conditions. '
           + 'When the stop conditions are met, it performs the stop actions. '
           + 'It then advances to "inactive" for "single" run mode '
           + 'or "search" for "continuous" run mode..')
    ])
)


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

_DURATION_META_SIGNALS = [
    ['always', N_('Always')],
    ['never', N_('Never')],
]

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
            ['single', N_('Single')],
            ['continuous', N_('Continuous')],
        ],
    },
    'status': {
        'dtype': 'str',
        'brief': 'Arm the trigger.',
        'default': 'inactive',
        'options': [
            ['inactive'],
            ['searching'],
            ['active'],
        ],
        'flags': ['ro', 'hide', 'tmp'],
    },
    'config': {
        'dtype': 'obj',
        'brief': 'The trigger configuration.',
        'default': None,
    },
}


def _is_digital_signal(s):
    return s in ['0', '1', '2', '3', 'T']


class ConditionWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._signal_list = []
        self._value_scale = 1.0
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)
        self._layout.addWidget(QtWidgets.QLabel(N_('Type')), 0, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Signal')), 1, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Condition')), 2, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Duration')), 3, 0, 1, 1)

        self._type = QtWidgets.QComboBox()
        comboBoxConfig(self._type, [x[1] for x in _CONDITION_TYPE_LIST])
        self._type.currentIndexChanged.connect(self._on_type)

        self._layout.addWidget(self._type, 0, 1, 1, 1)

        self._source_widget = QtWidgets.QWidget()
        self._source_layout = QtWidgets.QHBoxLayout(self._source_widget)
        self._source_layout.setContentsMargins(0, 0, 0, 0)
        self._signal = QtWidgets.QComboBox()
        self._signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._signal.currentIndexChanged.connect(self._on_signal)
        self._source_layout.addWidget(self._signal)
        self._layout.addWidget(self._source_widget, 1, 1, 1, 1)

        self._condition_widget = QtWidgets.QWidget()
        self._condition_layout = QtWidgets.QHBoxLayout(self._condition_widget)
        self._condition_layout.setContentsMargins(0, 0, 0, 0)
        self._condition = QtWidgets.QComboBox()
        self._condition.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._condition.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        self._condition_layout.addWidget(self._condition)
        self._condition.currentIndexChanged.connect(self._on_condition)

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

        self._on_type(0)

    @QtCore.Slot()
    def _on_config_update(self):
        cfg = self.config
        self.config_changed.emit(cfg)

    @property
    def config(self):
        type_name = _CONDITION_TYPE_LIST[self._type.currentIndex()][0]
        signal = self._signal_list_with_meta()[self._signal.currentIndex()][0]
        if signal in _DURATION_META_SIGNALS:
            condition = None
        elif type_name == 'edge':
            condition = _EDGE_CONDITION_LIST[self._condition.currentIndex()][0]
        elif _is_digital_signal(signal):
            condition = _DIGITAL_DURATION_CONDITION_LIST[self._condition.currentIndex()][0]
        else:
            condition = _DURATION_CONDITION_LIST[self._condition.currentIndex()][0]

        v1 = float(self._value1.text())
        v2 = float(self._value2.text())
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
        self._condition_field_visibility_update()

        signal_list = self._signal_list_with_meta()
        signals = [x[0] for x in signal_list]
        signal_idx = signals.index(value.get('signal'))
        signal = signal_list[signal_idx][0]
        block = self._signal.blockSignals(True)
        self._signal.setCurrentIndex(signal_idx)
        self._signal.blockSignals(block)
        self._condition_field_visibility_update()

        condition = value['condition']
        if condition is not None:
            if type_name == 'edge':
                conditions = [x[0] for x in _EDGE_CONDITION_LIST]
            elif _is_digital_signal(signal):
                conditions = [x[0] for x in _DIGITAL_DURATION_CONDITION_LIST]
            elif signal in _DURATION_META_SIGNALS:
                pass
            else:
                conditions = [x[0] for x in _DURATION_CONDITION_LIST]
            block = self._condition.blockSignals(True)
            self._condition.setCurrentIndex(conditions.index(condition))
            self._condition.blockSignals(block)

        v_unit = value.get('value_unit', '')
        v_scale = _SI_PREFIX[v_unit]
        block = self._value1.blockSignals(True)
        self._value1.setText(f'{value["value1"] / v_scale:g}')
        self._value1.blockSignals(block)
        block = self._value2.blockSignals(True)
        self._value2.setText(f'{value["value2"] / v_scale:g}')
        self._value1.blockSignals(block)
        unit = _SIGNAL_UNITS.get(signal, None)
        if unit is not None:
            comboBoxSelectItemByText(self._value_units, v_unit + unit, block=True)

        self._duration.value = value['duration']

    def row_set_visible(self, row, visible):
        for col in range(self._layout.columnCount()):
            item = self._layout.itemAtPosition(row, col)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setVisible(visible)

    @QtCore.Slot(int)
    def _on_type(self, index):
        if index == 0:  # edge
            self.row_set_visible(3, False)
            self._value2.setVisible(False)
        elif index == 1:  # duration
            self.row_set_visible(3, True)
            self._value2.setVisible(True)
        self._condition_field_visibility_update()

    def _condition_field_visibility_update(self):
        t = self._type.currentIndex()
        signal_list = self._signal_list_with_meta()
        comboBoxConfig(self._signal, [s[1] for s in signal_list])
        try:
            s = signal_list[self._signal.currentIndex()][0]
        except IndexError:
            return
        if s in ['always', 'never']:
            self.row_set_visible(2, False)
            return
        self.row_set_visible(2, True)
        is_digital = _is_digital_signal(s)
        if t == 0:  # edge
            comboBoxConfig(self._condition, [x[1] for x in _EDGE_CONDITION_LIST])
            if is_digital:
                visibility = [False, False, False]
            else:
                visibility = [True, False, True]
        elif t == 1:  # duration
            conditions_list = _DIGITAL_DURATION_CONDITION_LIST if is_digital else _DURATION_CONDITION_LIST
            comboBoxConfig(self._condition, [x[1] for x in conditions_list])
            if is_digital:
                comboBoxConfig(self._condition, [x[1] for x in _DIGITAL_DURATION_CONDITION_LIST])
                duration = _DIGITAL_DURATION_CONDITIONS[self._condition.currentIndex()]
            else:
                comboBoxConfig(self._condition, [x[1] for x in _DURATION_CONDITION_LIST])
                duration = _DURATION_CONDITIONS[self._condition.currentIndex()]
            if duration in ['0', '1']:
                visibility = [False, False, False]
            elif duration in ['between', 'outside']:
                visibility = [True, True, True]
            else:
                visibility = [True, False, not is_digital]
        self._value1.setVisible(visibility[0])
        self._value2.setVisible(visibility[1])
        self._value_units.setVisible(visibility[2] and s not in ['r'])

    @QtCore.Slot(int)
    def _on_condition(self, index):
        self._condition_field_visibility_update()

    def _signal_list_with_meta(self):
        if self._type.currentIndex() == 1:  # duration
            return self._signal_list + _DURATION_META_SIGNALS
        else:
            return list(self._signal_list)

    def on_signal_list(self, value):
        self._signal_list = value
        self._on_signal(self._signal.currentIndex())

    @QtCore.Slot(int)
    def _on_signal(self, index):
        signal_list = self._signal_list_with_meta()
        signal = signal_list[index][0]
        unit = _SIGNAL_UNITS.get(signal, None)
        if unit is None:
            self._value_units.clear()
        else:
            prefixes = ['m', ''] if signal == 'v' else ['n', 'µ', 'm', '']
            unit_enum = [prefix + unit for prefix in prefixes]
            comboBoxConfig(self._value_units, unit_enum, unit)
        self._condition_field_visibility_update()

    @QtCore.Slot(int)
    def _on_value_units(self, index):
        value = self._value_units.currentText()
        prefix = '' if len(value) <= 1 else value[0]
        scale = _SI_PREFIX[prefix]
        for w in [self._value1, self._value2]:
            v = float(w.text()) * (self._value_scale / scale)
            w.setText(f'{v:g}')
        self._value_scale = scale


class StartActionsWidget(QtWidgets.QFrame):

    config_changed = QtCore.Signal(object)

    def __init__(self, parent):
        self._output_list = []
        super().__init__(parent=parent)
        self._layout = QtWidgets.QGridLayout(self)

        self._sample_record = QtWidgets.QCheckBox()
        self._layout.addWidget(self._sample_record, 0, 0, 1, 1)
        self._sample_record1 = QtWidgets.QHBoxLayout()
        self._sample_record1.addWidget(QtWidgets.QLabel(N_('Start signal sample recording')))
        self._sample_record_config = QtWidgets.QPushButton(N_('Config'))
        self._sample_record1.addWidget(self._sample_record_config)
        self._layout.addLayout(self._sample_record1, 0, 1, 1, 1)
        self._sample_record2 = QtWidgets.QHBoxLayout()
        self._sample_record2.addWidget(QtWidgets.QLabel(N_('Pretrigger duration')))
        self._sample_record_pre = IntervalWidget(None, 0)
        self._sample_record2.addWidget(self._sample_record_pre)
        self._layout.addLayout(self._sample_record2, 1, 1, 1, 1)

        self._stats_record = QtWidgets.QCheckBox()
        self._layout.addWidget(self._stats_record, 2, 0, 1, 1)
        self._stats_record1 = QtWidgets.QHBoxLayout()
        self._stats_record1.addWidget(QtWidgets.QLabel(N_('Start statistics recording')))
        self._stats_record_config = QtWidgets.QPushButton(N_('Config'))
        self._stats_record1.addWidget(self._stats_record_config)
        self._layout.addLayout(self._stats_record1, 2, 1, 1, 1)

        self._output = QtWidgets.QCheckBox()
        self._layout.addWidget(self._output, 3, 0, 1, 1)
        output_layout = QtWidgets.QHBoxLayout()
        output_layout.addWidget(QtWidgets.QLabel(N_('Set output')))
        self._output_signal = QtWidgets.QComboBox()
        self._output_signal.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._output_value = QtWidgets.QComboBox()
        comboBoxConfig(self._output_value, ['0', '1'], '1')
        output_layout.addWidget(self._output_signal)
        output_layout.addWidget(QtWidgets.QLabel('→'))
        output_layout.addWidget(self._output_value)
        self._layout.addLayout(output_layout, 3, 1, 1, 1, QtCore.Qt.AlignmentFlag.AlignTop)

        self._single_marker = QtWidgets.QCheckBox()
        self._layout.addWidget(self._single_marker, 4, 0, 1, 1)
        self._layout.addWidget(QtWidgets.QLabel(N_('Add single marker')), 4, 1, 1, 1)

        self._layout.setColumnStretch(1, 1)

        self._checkboxes = ['sample_record', 'stats_record', 'output', 'single_marker']

        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.toggled.connect(self._on_config_update)
        signals = [
            self._sample_record_pre.value_changed,
            self._output_signal.currentIndexChanged,
            self._output_value.currentIndexChanged,
        ]
        for signal in signals:
            signal.connect(self._on_config_update)

    @QtCore.Slot()
    def _on_config_update(self):
        cfg = self.config
        self.config_changed.emit(cfg)

    @property
    def config(self):
        rv = {
            'sample_record_pre': self._sample_record_pre.value,
            'output_signal': self._output_signal.currentText(),
            'output_value': self._output_value.currentIndex(),
        }
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            rv[checkbox_name] = checkbox.checked()
        return rv

    @config.setter
    def config(self, value):
        if value is None:
            value = self.config
        for checkbox_name in self._checkboxes:
            checkbox = getattr(self, f'_{checkbox_name}')
            checkbox.setChecked(value[checkbox_name])
        self._sample_record_pre.value = value['sample_record_pre']
        comboBoxSelectItemByText(self._output_signal, value['output_signal'])
        block = self._output_value.blockSignals(True)
        self._output_value.setCurrentIndex(value['output_value'])
        self._output_value.blockSignals(block)

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


@register
@styled_widget(N_('Trigger'))
class TriggerWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']
    SETTINGS = SETTINGS

    def __init__(self, parent=None):
        self._connected = False
        self._log = logging.getLogger(__name__)
        super().__init__(parent=parent)
        self.setObjectName('jls_info_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(10)

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

        self._status_button = QtWidgets.QPushButton()
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

        self._stop_actions = StartActionsWidget(self)
        self._layout.addWidget(SectionWidget(self, N_('Stop Actions'), self._stop_actions))

        spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(spacer)

    @QtCore.Slot()
    def _on_status_button_pressed(self):
        status = self._status_button.property('status')
        if status == 'inactive':
            status = 'searching'
            # todo start searching
        elif status == 'searching':
            status = 'inactive'
        elif status == 'active':
            # todo stop!
            status = 'inactive'
        else:
            self._log.error('invalid status: %s', status)
            status = 'inactive'
        self._status_button.setProperty('status', status)
        style = self._status_button.style()
        style.unpolish(self._status_button)
        style.polish(self._status_button)

    def _connect(self):
        resolved = self._source_selector.resolved()
        if resolved is None:
            self._connected = False
        else:
            topic = f'{get_topic_name(resolved)}/settings/signals'
            signals = self.pubsub.enumerate(topic)
            signal_names = [[s, self.pubsub.query(f'{topic}/{s}/name')] for s in signals]
            self._start_condition.on_signal_list(signal_names)
            self._stop_condition.on_signal_list(signal_names)
            output = self.pubsub.enumerate(f'{get_topic_name(resolved)}/settings/out')
            self._start_actions.on_output_list(output)
            self._stop_actions.on_output_list(output)
            if not self._connected:
                self._config_set(self.config)
            self._connected = True
        for item in range(self._layout.count()):
            w = self._layout.itemAt(item).widget()
            if w is not None:
                w.setVisible((w is self._error) ^ (resolved is not None))

    @QtCore.Slot(object)
    def _on_source_changed(self, value):
        self._connect()

    @QtCore.Slot(object)
    def _on_sources_changed(self, value):
        comboBoxConfig(self._source, value)

    @QtCore.Slot(object)
    def _on_resolved_changed(self, value):
        self._connect()

    def _config_get(self):
        return {
            'start_condition': self._start_condition.config,
            'start_actions': self._start_actions.config,
            'stop_condition': self._stop_condition.config,
            'stop_actions': self._stop_actions.config,
        }

    def _config_set(self, value):
        if not self._connected:
            return
        if value is None:
            value = self.config
        self._start_condition.config = value['start_condition']
        self._start_actions.config = value['start_actions']
        self._stop_condition.config = value['stop_condition']
        self._stop_actions.config = value['stop_actions']

    def on_setting_config(self, value):
        self._config_set(value)

    def on_pubsub_register(self, pubsub):
        topic = f'{self.topic}/settings/source'
        self._source_selector.on_pubsub_register(pubsub, topic)
