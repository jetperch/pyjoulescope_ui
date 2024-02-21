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

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui.widgets import DoubleSlider
from joulescope_ui.ui_util import comboBoxConfig


_CURRENT_RANGE_MAP = {
    0: '10 A',
    1: '180 mA',
    2: '18 mA',
    3: '1.8 mA',
    4: '180 µA',
    5: '18 µA',
}


class CurrentLimits(QtWidgets.QWidget):

    values_changed = QtCore.Signal(int, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._spacer = QtWidgets.QSpacerItem(20, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer)

        self.v_min = QtWidgets.QComboBox(self)
        self.slider = DoubleSlider(self, [5, 0])
        self.slider.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.slider.values_changed.connect(self._on_slider_values_changed)
        self.v_max = QtWidgets.QComboBox(self)

        for w in [self.v_min, self.v_max]:
            comboBoxConfig(w, _CURRENT_RANGE_MAP.values())
            w.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
            w.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.v_min.currentIndexChanged.connect(self._on_v_min_changed)
        self.v_max.currentIndexChanged.connect(self._on_v_max_changed)

        self._layout.addWidget(self.v_min)
        self._layout.addWidget(self.slider)
        self._layout.addWidget(self.v_max)

    def _on_slider_values_changed(self, v0, v1):
        v_min_block = self.v_min.blockSignals(True)
        self.v_min.setCurrentIndex(v0)
        self.v_min.blockSignals(v_min_block)

        v_max_block = self.v_max.blockSignals(True)
        self.v_max.setCurrentIndex(v1)
        self.v_max.blockSignals(v_max_block)

    def _on_v_min_changed(self, index):
        index = max(index, self.values[1])
        self.values = index, self.values[1]

    def _on_v_max_changed(self, index):
        index = min(index, self.values[0])
        self.values = self.values[0], index

    @property
    def values_changed(self):
        return self.slider.values_changed

    @property
    def values(self):
        return self.slider.values

    @values.setter
    def values(self, value):
        self.v_min.setCurrentIndex(value[0])
        self.v_max.setCurrentIndex(value[1])
        self.slider.values = value

    def values_set(self, value):
        self.values = value

