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

"""
Allow the user to manually specify the dual marker spacing interval.
"""

from joulescope_ui.ui_util import comboBoxConfig
from PySide6 import QtCore, QtGui, QtWidgets
import logging

log = logging.getLogger(__name__)


_TIME_UNITS = [
    ('ns', 1e-9),
    ('µs', 1e-6),
    ('ms', 1e-3),
    ('s',  1),
    ('m',  60),
    ('h',  60 * 60),
    ('d',  60 * 60 * 24),
]


def _unit_select(interval_seconds):
    interval_seconds = abs(interval_seconds)
    if interval_seconds < 1e-14:
        idx = 4
    else:
        for idx, (unit_name, unit_scale) in enumerate(_TIME_UNITS):
            if interval_seconds < unit_scale:
                break
    idx = max(0, idx - 1)
    txt, scale = _TIME_UNITS[idx]
    return idx, txt, scale


def str_to_float(s):
    try:
        return float(s)
    except ValueError:
        return 0.0


class IntervalWidget(QtWidgets.QWidget):

    value_edit_finished = QtCore.Signal(float)  # on edit completed
    value_changed = QtCore.Signal(float)  # on any change

    def __init__(self, parent, interval_seconds=None, name=None):
        self._unit_idx = 0
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setObjectName('IntervalWidget')

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName('IntervalWidgetLayout')
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)

        if name is not None:
            label = QtWidgets.QLabel(name)
            self._layout.addWidget(label)

        self._value = QtWidgets.QLineEdit(self)
        self._value.setText(f'0.0')
        self._value_validator = QtGui.QDoubleValidator(self)
        self._value.setValidator(self._value_validator)
        self._value.editingFinished.connect(self._on_value)
        self._value.textEdited.connect(self._on_edit)
        self._layout.addWidget(self._value)

        self._units = QtWidgets.QComboBox(self)
        self._units.currentIndexChanged.connect(self._on_units)
        self._layout.addWidget(self._units)

        self.value = 0.0 if interval_seconds is None else str_to_float(interval_seconds)

    @property
    def value(self):
        txt = self._value.text()
        value = str_to_float(txt)
        idx = self._units.currentIndex()
        scale = _TIME_UNITS[idx][1]
        value *= scale
        return value

    @value.setter
    def value(self, interval_seconds):
        self._unit_idx, unit_name, unit_scale = _unit_select(interval_seconds)
        v = interval_seconds / unit_scale
        block = self._value.blockSignals(True)
        self._value.setText(f'{v:g}')
        self._value.blockSignals(block)
        comboBoxConfig(self._units, [x[0] for x in _TIME_UNITS], unit_name)

    @QtCore.Slot()
    def _on_value(self):
        self.value_edit_finished.emit(self.value)

    @QtCore.Slot()
    def _on_edit(self):
        self.value_changed.emit(self.value)

    @QtCore.Slot(int)
    def _on_units(self, idx):
        txt = self._value.text()
        value = str_to_float(txt)

        s1 = _TIME_UNITS[self._unit_idx][1]
        s2 = _TIME_UNITS[idx][1]
        value = (value * s1) / s2
        self._value.setText(f'{value:g}')
        self._unit_idx = idx
