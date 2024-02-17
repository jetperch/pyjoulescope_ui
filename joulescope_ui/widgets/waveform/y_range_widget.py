# Copyright 2023-2024 Jetperch LLC
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
Allow the user to manually specify the y-axis range.
"""

from joulescope_ui import N_
from joulescope_ui.ui_util import comboBoxConfig
from PySide6 import QtCore, QtGui, QtWidgets
import logging

log = logging.getLogger(__name__)


_PREFIXES = [
    ('n', 1e-9),
    ('µ', 1e-6),
    ('m', 1e-3),
    ('',  1),
]


def _prefix_select(value):
    value = abs(value)
    for idx, (unit_name, unit_scale) in enumerate(_PREFIXES):
        if value < unit_scale:
            break
    idx = max(0, idx - 1)
    txt, scale = _PREFIXES[idx]
    return idx, txt, scale


class YRangeWidget(QtWidgets.QWidget):

    value = QtCore.Signal(object)  # y_range = [y_min, y_max]

    def __init__(self, parent, y_range, unit, fn=None):
        self._widgets = {}
        self._y_range = y_range
        self._fn = fn
        QtWidgets.QWidget.__init__(self, parent)
        self._prefix_index = 0
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setObjectName('YRangeWidget')

        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setObjectName('YRangeWidgetLayout')
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._row = 0

        y_max = max(abs(y_range[0]), abs(y_range[1]))
        prefix = _prefix_select(y_max)

        self.construct('max', N_('max'), y_range[1] / prefix[-1])
        self.construct('min', N_('min'), y_range[0] / prefix[-1])
        self.construct_prefix(unit, prefix)

    def construct_prefix(self, unit, prefix):
        label = QtWidgets.QLabel(N_('Units'), self)
        self._layout.addWidget(label, self._row, 0, 1, 1)
        sel = QtWidgets.QComboBox(self)
        comboBoxConfig(sel, [x[0] + unit for x in _PREFIXES], prefix[1] + unit)
        self._layout.addWidget(sel, self._row, 1, 1, 1)
        self._prefix_index = sel.currentIndex()
        sel.currentIndexChanged.connect(self._on_prefix)

        self._widgets['prefix'] = [sel, label]
        self._row += 1

    def construct(self, name, txt, v):
        label = QtWidgets.QLabel(txt, self)
        self._layout.addWidget(label, self._row, 0, 1, 1)

        edit = QtWidgets.QLineEdit(self)
        edit.setText(f'{v:g}')
        validator = QtGui.QDoubleValidator(self)
        edit.setValidator(validator)
        self._layout.addWidget(edit, self._row, 1, 1, 1)
        edit.editingFinished.connect(self._on_value)

        self._widgets[name] = [edit, label, validator]
        self._row += 1

    @QtCore.Slot()
    def _on_value(self):
        y_range = []
        for field in ['min', 'max']:
            edit = self._widgets[field][0]
            v = float(edit.text())
            scale = _PREFIXES[self._prefix_index][-1]
            y_range.append(v * scale)
        self.value.emit(y_range)
        if callable(self._fn):
            self._fn(y_range)

    @QtCore.Slot(int)
    def _on_prefix(self, idx):
        s1 = _PREFIXES[self._prefix_index][1]
        s2 = _PREFIXES[idx][1]
        s = s1 / s2
        for field in ['min', 'max']:
            edit = self._widgets[field][0]
            v = float(edit.text())
            v *= s
            edit.setText(f'{v:g}')
        self._prefix_index = idx
