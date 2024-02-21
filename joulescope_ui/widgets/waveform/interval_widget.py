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
    for idx, (unit_name, unit_scale) in enumerate(_TIME_UNITS):
        if interval_seconds < unit_scale:
            break
    idx = max(0, idx - 1)
    txt, scale = _TIME_UNITS[idx]
    return idx, txt, scale


class IntervalWidget(QtWidgets.QWidget):

    value = QtCore.Signal(float)

    def __init__(self, parent, interval_seconds):
        self._interval_seconds = interval_seconds
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setObjectName('IntervalWidget')

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName('IntervalWidgetLayout')
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)

        self._unit_idx, unit_name, unit_scale = _unit_select(interval_seconds)
        value = interval_seconds / unit_scale

        self._value = QtWidgets.QLineEdit(self)
        self._value.setText(f'{value:g}')
        self._value_validator = QtGui.QDoubleValidator(self)
        self._value.setValidator(self._value_validator)
        self._value.editingFinished.connect(self._on_value)
        self._layout.addWidget(self._value)

        self._units = QtWidgets.QComboBox(self)
        comboBoxConfig(self._units, [x[0] for x in _TIME_UNITS], unit_name)
        self._units.currentIndexChanged.connect(self._on_units)
        self._layout.addWidget(self._units)

    @QtCore.Slot()
    def _on_value(self):
        txt = self._value.text()
        value = float(txt)
        idx = self._units.currentIndex()
        scale = _TIME_UNITS[idx][1]
        value *= scale
        self.value.emit(value)

    @QtCore.Slot(int)
    def _on_units(self, idx):
        txt = self._value.text()
        value = float(txt)

        s1 = _TIME_UNITS[self._unit_idx][1]
        s2 = _TIME_UNITS[idx][1]
        value = (value * s1) / s2
        self._value.setText(f'{value:g}')
        self._unit_idx = idx
