# Copyright 2018 Jetperch LLC
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

from PySide2 import QtCore, QtGui, QtWidgets
from . import joulescope_rc
from joulescope.units import unit_prefix
import numpy as np


styleSheetMain = """
QLabel { font-weight: bold; font-size: 48pt; }
"""

styleSheetStats = """
QLabel { font-weight: bold; }
"""

styleSheetStatsHide = """
QLabel { font-weight: bold; font-color: black}
"""


class MeterValueWidget(QtWidgets.QWidget):
    on_update = QtCore.Signal(object, str)  # [mean, std_dev, min, max, p2p], units : values are formatted strings!

    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self._units_short = ''
        self._units_long = ''
        self.v_mean = 0.0
        self.v_var = 0.0
        self.v_std_dev = 0.0
        self.v_min = 0.0
        self.v_max = 0.0
        self.v_p2p = 0.0

        self._accum_enable = False
        self._accum_count = 0

        self.horizontalLayout = QtWidgets.QHBoxLayout(self)
        self.horizontalLayout.setContentsMargins(2, 2, 2, 2)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.valueLabel = QtWidgets.QLabel(self)
        self.valueLabel.setStyleSheet(styleSheetMain)
        self.valueLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)
        self.valueLabel.setObjectName("valueLabel")
        self.horizontalLayout.addWidget(self.valueLabel)
        self.unitLabel = QtWidgets.QLabel(self)
        self.unitLabel.setStyleSheet(styleSheetMain)
        self.unitLabel.setObjectName("unitLabel")
        self.horizontalLayout.addWidget(self.unitLabel)
        self.frame = QtWidgets.QFrame(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy)
        self.frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.frame.setFrameShadow(QtWidgets.QFrame.Plain)
        self.frame.setLineWidth(0)
        self.frame.setObjectName("frame")
        self.gridLayout = QtWidgets.QGridLayout(self.frame)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName("gridLayout")
        self.stdLabel = QtWidgets.QLabel(self.frame)
        self.stdLabel.setStyleSheet(styleSheetStats)
        self.stdLabel.setLineWidth(0)
        self.stdLabel.setObjectName("stdLabel")
        self.gridLayout.addWidget(self.stdLabel, 0, 0, 1, 1)
        self.stdName = QtWidgets.QLabel(self.frame)
        self.stdName.setStyleSheet(styleSheetStats)
        self.stdName.setLineWidth(0)
        self.stdName.setObjectName("stdName")
        self.gridLayout.addWidget(self.stdName, 0, 1, 1, 1)
        self.minLabel = QtWidgets.QLabel(self.frame)
        self.minLabel.setStyleSheet(styleSheetStats)
        self.minLabel.setLineWidth(0)
        self.minLabel.setObjectName("minLabel")
        self.gridLayout.addWidget(self.minLabel, 1, 0, 1, 1)
        self.minName = QtWidgets.QLabel(self.frame)
        self.minName.setStyleSheet(styleSheetStats)
        self.minName.setLineWidth(0)
        self.minName.setObjectName("minName")
        self.gridLayout.addWidget(self.minName, 1, 1, 1, 1)
        self.maxLabel = QtWidgets.QLabel(self.frame)
        self.maxLabel.setStyleSheet(styleSheetStats)
        self.maxLabel.setLineWidth(0)
        self.maxLabel.setObjectName("maxLabel")
        self.gridLayout.addWidget(self.maxLabel, 2, 0, 1, 1)
        self.maxName = QtWidgets.QLabel(self.frame)
        self.maxName.setStyleSheet(styleSheetStats)
        self.maxName.setLineWidth(0)
        self.maxName.setObjectName("maxName")
        self.gridLayout.addWidget(self.maxName, 2, 1, 1, 1)
        self.p2pLabel = QtWidgets.QLabel(self.frame)
        self.p2pLabel.setStyleSheet(styleSheetStats)
        self.p2pLabel.setLineWidth(0)
        self.p2pLabel.setObjectName("p2pLabel")
        self.gridLayout.addWidget(self.p2pLabel, 3, 0, 1, 1)
        self.p2pName = QtWidgets.QLabel(self.frame)
        self.p2pName.setStyleSheet(styleSheetStats)
        self.p2pName.setLineWidth(0)
        self.p2pName.setObjectName("p2pName")
        self.gridLayout.addWidget(self.p2pName, 3, 1, 1, 1)
        self.horizontalLayout.addWidget(self.frame)

        self._stats_widgets = [
            (self.stdLabel, self.stdName),
            (self.minLabel, self.minName),
            (self.maxLabel, self.maxName),
            (self.p2pLabel, self.p2pName),
        ]

        self.retranslateUi()

    @property
    def accumulate_enable(self):
        return self._accum_enable

    @accumulate_enable.setter
    def accumulate_enable(self, value):
        self._accum_enable = value
        self.v_mean = 0.0
        self.v_var = 0.0
        self._accum_count = 0

    def configure(self, name, units_short, units_long):
        self._units_short = units_short
        self._units_long = units_long
        self.update_value(0, 0, 0, 0)
        self.setToolTip(name)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.unitLabel.setText(_translate("Form", "    "))
        self.stdName.setText(_translate("Form", " σ "))
        self.minName.setText(_translate("Form", " min "))
        self.maxName.setText(_translate("Form", " max "))
        self.p2pName.setText(_translate("Form", " p2p "))

    def stats_stylesheet(self, stylesheet):
        for widgets in self._stats_widgets:
            for widget in widgets:
                widget.setStyleSheet(stylesheet)

    def _update_value(self, mean, variance, v_min, v_max):
        self._accum_count += 1
        if self._accum_enable:
            self.v_min = min(self.v_min, v_min)
            self.v_max = max(self.v_max, v_max)
            self.v_p2p = max(self.v_p2p, self.v_p2p)

            m = self.v_mean + (mean - self.v_mean) / self._accum_count
            if self._accum_count <= 1:
                self.v_mean = m
            v = (mean - self.v_mean) * (mean - m) + variance
            dv = (v - self.v_var) / self._accum_count
            self.v_var += dv
            self.v_mean = m
        else:
            self.v_mean = mean
            self.v_var = variance
            self.v_min = v_min
            self.v_max = v_max
            self.v_p2p = v_max - v_min
        self.v_std_dev = np.sqrt(self.v_var)

    def _update_ui(self):
        values = [self.v_mean, self.v_std_dev, self.v_min, self.v_max]
        max_value = max(*[abs(x) for x in values])
        _, prefix, scale = unit_prefix(max_value)
        scale = 1.0 / scale
        if not len(prefix):
            prefix = '&nbsp;'
        units = f'{prefix}{self._units_short}'
        self.unitLabel.setText(f"<html>&nbsp;{units}&nbsp;</html>")
        fields = [
            [self.v_mean, self.valueLabel],
            [self.v_std_dev, self.stdLabel],
            [self.v_min, self.minLabel],
            [self.v_max, self.maxLabel],
            [self.v_p2p, self.p2pLabel],
        ]
        values = []
        for v, label in fields:
            v *= scale
            if abs(v) < 0.000005:  # minimum display resolution
                v = 0
            v_str = ('%+6f' % v)[:8]
            # v_str = v_str.replace('+', '')
            label.setText(v_str)
            values.append(v_str)
        self.on_update.emit(values, units)

    def update_value(self, *values):
        self._update_value(*values)
        self._update_ui()
