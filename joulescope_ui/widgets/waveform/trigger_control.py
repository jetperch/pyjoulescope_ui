# Copyright 2026 Jetperch LLC
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

"""The Waveform widget trigger controls.

TriggerControlWidget is the group in the Waveform control bar.
TriggerSettingsPopup configures the trigger source, edge, level,
position, holdoff, and noise rejection.  Both only communicate with the
Waveform widget through its pubsub settings and actions.
"""

from joulescope_ui import N_, P_, tooltip_format
from joulescope_ui.ui_util import comboBoxConfig
from .interval_widget import IntervalWidget
from .quantities import si_format
from . import trigger as trigger_mod
from PySide6 import QtCore, QtGui, QtWidgets
import logging


log = logging.getLogger(__name__)

QUANTITY_UNITS = {'i': 'A', 'v': 'V', 'p': 'W'}

_TOOLTIP_MODE = tooltip_format(
    N_('Trigger mode'),
    P_([
        N_('The trigger holds repeating waveforms steady while streaming. '
           'It places a level crossing of the trigger source at the trigger position.'),
        N_('Off follows the newest data.'),
        N_('Auto displays each trigger, and follows the newest data when no trigger occurs.'),
        N_('Normal displays each trigger, and holds the last trigger when no trigger occurs.'),
        N_('Single displays the next trigger, then holds it.  Press Arm to capture another.'),
        N_('Drag the T markers to change the trigger level and position. '
           'Right-click a plot and select "Trigger here" to trigger at that level.'),
    ]))

_TOOLTIP_ARM = tooltip_format(
    N_('Arm'),
    N_('Capture the next trigger in single mode.'))

_TOOLTIP_SETTINGS = tooltip_format(
    N_('Trigger settings'),
    N_('Configure the trigger source, edge, level, position, holdoff, and noise rejection.'))

_TOOLTIP_LEVEL_CENTER = tooltip_format(
    N_('Center level'),
    N_('Set the trigger level to the middle of the displayed trigger source signal.'))

_TOOLTIP_HOLDOFF = tooltip_format(
    N_('Holdoff'),
    N_('Ignore triggers for this duration after each trigger. '
       'Set the holdoff slightly longer than a burst to trigger on the first edge of each burst.'))


def level_format(value, units):
    """Format a trigger level for display and editing."""
    value_strs, prefix_units = si_format([float(value)], units, precision=4)
    txt = value_strs[0].lstrip('+')
    return f'{txt} {prefix_units}'.strip()


class TriggerSettingsPopup(QtWidgets.QFrame):
    """The trigger settings popup, which closes on any outside click."""

    def __init__(self, parent, pubsub, topic):
        self._pubsub = pubsub
        self._topic = topic
        self._subscriptions = []
        self._combo_values = {}
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self.setObjectName('waveform_trigger_settings')
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self._layout = QtWidgets.QFormLayout(self)

        self._source = self._combo('trigger_source')
        self._layout.addRow(N_('Source'), self._source)
        self._edge = self._combo('trigger_edge')
        self._layout.addRow(N_('Edge'), self._edge)

        level_row = QtWidgets.QWidget(self)
        level_layout = QtWidgets.QHBoxLayout(level_row)
        level_layout.setContentsMargins(0, 0, 0, 0)
        self._level = QtWidgets.QLineEdit(level_row)
        self._level.setObjectName('trigger_level')
        self._level.editingFinished.connect(self._on_level_edit)
        level_layout.addWidget(self._level)
        self._level_center = QtWidgets.QPushButton(N_('Center'), level_row)
        self._level_center.setObjectName('trigger_level_center')
        self._level_center.setToolTip(_TOOLTIP_LEVEL_CENTER)
        self._level_center.clicked.connect(self._on_level_center)
        level_layout.addWidget(self._level_center)
        self._layout.addRow(N_('Level'), level_row)

        self._position = QtWidgets.QDoubleSpinBox(self)
        self._position.setObjectName('trigger_position')
        self._position.setRange(0.0, 100.0)
        self._position.setDecimals(1)
        self._position.setSingleStep(5.0)
        self._position.setSuffix(' %')
        self._position.setKeyboardTracking(False)
        self._position.valueChanged.connect(self._on_position)
        self._layout.addRow(N_('Position'), self._position)

        self._holdoff = IntervalWidget(self, 0.0)
        self._holdoff.setObjectName('trigger_holdoff')
        self._holdoff.setToolTip(_TOOLTIP_HOLDOFF)
        self._holdoff.value_edit_finished.connect(self._on_holdoff)
        self._layout.addRow(N_('Holdoff'), self._holdoff)

        self._hysteresis = self._combo('trigger_hysteresis')
        self._layout.addRow(N_('Noise reject'), self._hysteresis)

        self._subscribe('trigger_source', self._on_source)
        self._subscribe('trigger_edge', self._on_edge)
        self._subscribe('trigger_level', self._on_level)
        self._subscribe('trigger_position', self._on_position_setting)
        self._subscribe('trigger_holdoff', self._on_holdoff_setting)
        self._subscribe('trigger_hysteresis', self._on_hysteresis)

    def _setting_topic(self, name):
        return f'{self._topic}/settings/{name}'

    def _combo(self, name):
        combo = QtWidgets.QComboBox(self)
        combo.setObjectName(name)
        meta = self._pubsub.metadata(self._setting_topic(name))
        options = meta.options
        comboBoxConfig(combo, [x[1] for x in options])
        values = [x[0] for x in options]

        def on_index(index):
            if 0 <= index < len(values):
                self._pubsub.publish(self._setting_topic(name), values[index])
                if name == 'trigger_source':
                    # the previous level is in the previous source units
                    self._pubsub.publish(f'{self._topic}/actions/!trigger', 'level_center')

        combo.currentIndexChanged.connect(on_index)
        self._combo_values[combo] = values
        return combo

    def _combo_set(self, combo, value):
        values = self._combo_values.get(combo, [])
        try:
            index = values.index(value)
        except ValueError:
            return
        block = combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(block)

    def _subscribe(self, name, fn):
        self._pubsub.subscribe(self._setting_topic(name), fn, ['pub', 'retain'])
        self._subscriptions.append(fn)

    def _query(self, name, default=None):
        return self._pubsub.query(self._setting_topic(name), default=default)

    def closeEvent(self, event):
        for fn in self._subscriptions:
            self._pubsub.unsubscribe_all(fn)
        self._subscriptions.clear()
        super().closeEvent(event)

    def _units(self):
        return QUANTITY_UNITS.get(self._query('trigger_source', 'i'), '')

    def _on_source(self, value):
        self._combo_set(self._source, value)
        is_digital = trigger_mod.is_digital(value)
        self._level.setEnabled(not is_digital)
        self._level_center.setEnabled(not is_digital)
        self._on_level(self._query('trigger_level', 0.0))

    def _on_edge(self, value):
        self._combo_set(self._edge, value)

    def _on_level(self, value):
        if trigger_mod.is_digital(self._query('trigger_source', 'i')):
            value = trigger_mod.DIGITAL_LEVEL
        self._level.setText(level_format(value, self._units()))
        self._level.setStyleSheet('')

    @QtCore.Slot()
    def _on_level_edit(self):
        try:
            value = trigger_mod.si_parse(self._level.text(), self._units())
        except ValueError:
            self._level.setStyleSheet('QLineEdit { color: red; }')
            return
        self._level.setStyleSheet('')
        self._pubsub.publish(self._setting_topic('trigger_level'), value)

    @QtCore.Slot(bool)
    def _on_level_center(self, checked=False):
        self._pubsub.publish(f'{self._topic}/actions/!trigger', 'level_center')

    def _on_position_setting(self, value):
        block = self._position.blockSignals(True)
        self._position.setValue(float(value))
        self._position.blockSignals(block)

    @QtCore.Slot(float)
    def _on_position(self, value):
        self._pubsub.publish(self._setting_topic('trigger_position'), float(value))

    def _on_holdoff_setting(self, value):
        self._holdoff.value = float(value)

    @QtCore.Slot(float)
    def _on_holdoff(self, value):
        self._pubsub.publish(self._setting_topic('trigger_holdoff'), max(0.0, float(value)))

    def _on_hysteresis(self, value):
        self._combo_set(self._hysteresis, value)


class TriggerControlWidget(QtWidgets.QWidget):
    """The trigger group for the Waveform control bar."""

    mode_changed = QtCore.Signal(str)

    def __init__(self, parent):
        self.pubsub = None
        self.topic = ''
        self._popup = None
        self._mode_values = []
        super().__init__(parent)
        self.setObjectName('waveform_trigger_control')
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)

        self._label = QtWidgets.QLabel(N_('Trigger') + ':', self)
        self._label.setToolTip(_TOOLTIP_MODE)
        self._layout.addWidget(self._label)

        self._mode = QtWidgets.QComboBox(self)
        self._mode.setObjectName('trigger_mode')
        self._mode.setToolTip(_TOOLTIP_MODE)
        self._mode.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._mode.currentIndexChanged.connect(self._on_mode_index)
        self._layout.addWidget(self._mode)

        self._arm = QtWidgets.QPushButton(N_('Arm'), self)
        self._arm.setObjectName('trigger_arm')
        self._arm.setToolTip(_TOOLTIP_ARM)
        self._arm.clicked.connect(self._on_arm)
        self._arm.setVisible(False)
        self._layout.addWidget(self._arm)

        self._settings = QtWidgets.QPushButton('…', self)
        self._settings.setObjectName('trigger_settings')
        self._settings.setToolTip(_TOOLTIP_SETTINGS)
        self._settings.setFixedWidth(24)
        self._settings.clicked.connect(self._on_settings)
        self._layout.addWidget(self._settings)

    def on_pubsub_register(self, pubsub, topic):
        self.pubsub = pubsub
        self.topic = topic
        meta = pubsub.metadata(f'{topic}/settings/trigger_mode')
        self._mode_values = [x[0] for x in meta.options]
        block = self._mode.blockSignals(True)
        comboBoxConfig(self._mode, [x[1] for x in meta.options])
        self._mode.blockSignals(block)
        pubsub.subscribe(f'{topic}/settings/trigger_mode', self._on_mode, ['pub', 'retain'])

    def _on_mode(self, value):
        try:
            index = self._mode_values.index(value)
        except ValueError:
            return
        block = self._mode.blockSignals(True)
        self._mode.setCurrentIndex(index)
        self._mode.blockSignals(block)
        self._arm.setVisible(value == 'single')
        self.mode_changed.emit(value)

    @QtCore.Slot(int)
    def _on_mode_index(self, index):
        if 0 <= index < len(self._mode_values):
            self.pubsub.publish(f'{self.topic}/settings/trigger_mode', self._mode_values[index])

    @QtCore.Slot(bool)
    def _on_arm(self, checked=False):
        self.pubsub.publish(f'{self.topic}/actions/!trigger', 'arm')

    @QtCore.Slot(bool)
    def _on_settings(self, checked=False):
        if self._popup is not None:
            try:
                self._popup.close()
            except RuntimeError:
                pass  # already deleted
        popup = TriggerSettingsPopup(self, self.pubsub, self.topic)
        popup.destroyed.connect(self._on_popup_destroyed)
        self._popup = popup
        popup.adjustSize()
        # open above the control bar, which is usually at the widget bottom
        pos = self._settings.mapToGlobal(QtCore.QPoint(0, 0))
        y = pos.y() - popup.height()
        if y < 0:
            y = pos.y() + self._settings.height()
        x = pos.x() + self._settings.width() - popup.width()
        popup.move(max(0, x), y)
        popup.show()

    @QtCore.Slot()
    def _on_popup_destroyed(self):
        self._popup = None
