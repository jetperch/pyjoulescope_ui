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
from joulescope_ui import joulescope_rc
from joulescope.units import unit_prefix
import numpy as np
import math
from joulescope_ui.ui_util import rgba_to_css


class MeterValueWidget(QtWidgets.QWidget):
    on_update = QtCore.Signal(object, str)  # [mean, std_dev, min, max, p2p], units : values are formatted strings!

    def __init__(self, parent, cmdp):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
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
        self.valueLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)
        self.valueLabel.setObjectName("valueLabel")
        self.horizontalLayout.addWidget(self.valueLabel)
        self.unitLabel = QtWidgets.QLabel(self)
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
        self.stdLabel.setLineWidth(0)
        self.stdLabel.setObjectName("stdLabel")
        self.gridLayout.addWidget(self.stdLabel, 0, 0, 1, 1)
        self.stdName = QtWidgets.QLabel(self.frame)
        self.stdName.setLineWidth(0)
        self.stdName.setObjectName("stdName")
        self.gridLayout.addWidget(self.stdName, 0, 1, 1, 1)
        self.minLabel = QtWidgets.QLabel(self.frame)
        self.minLabel.setLineWidth(0)
        self.minLabel.setObjectName("minLabel")
        self.gridLayout.addWidget(self.minLabel, 1, 0, 1, 1)
        self.minName = QtWidgets.QLabel(self.frame)
        self.minName.setLineWidth(0)
        self.minName.setObjectName("minName")
        self.gridLayout.addWidget(self.minName, 1, 1, 1, 1)
        self.maxLabel = QtWidgets.QLabel(self.frame)
        self.maxLabel.setLineWidth(0)
        self.maxLabel.setObjectName("maxLabel")
        self.gridLayout.addWidget(self.maxLabel, 2, 0, 1, 1)
        self.maxName = QtWidgets.QLabel(self.frame)
        self.maxName.setLineWidth(0)
        self.maxName.setObjectName("maxName")
        self.gridLayout.addWidget(self.maxName, 2, 1, 1, 1)
        self.p2pLabel = QtWidgets.QLabel(self.frame)
        self.p2pLabel.setLineWidth(0)
        self.p2pLabel.setObjectName("p2pLabel")
        self.gridLayout.addWidget(self.p2pLabel, 3, 0, 1, 1)
        self.p2pName = QtWidgets.QLabel(self.frame)
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

        cmdp.subscribe('Widgets/Multimeter/font-main', self._on_font_main, update_now=True)
        cmdp.subscribe('Widgets/Multimeter/font-stats', self._on_font_stats, update_now=True)
        cmdp.subscribe('Widgets/Multimeter/font-color', self._on_color, update_now=True)
        cmdp.subscribe('Widgets/Multimeter/background-color', self._on_color, update_now=True)

    def _widgets(self):
        widgets = [self.valueLabel, self.unitLabel]
        for w in self._stats_widgets:
            widgets.extend(w)
        return widgets

    def _on_font_main(self, topic, value):
        font = QtGui.QFont()
        font.fromString(value)
        self.valueLabel.setFont(font)
        self.unitLabel.setFont(font)

    def _on_font_stats(self, topic, value):
        font = QtGui.QFont()
        font.fromString(value)
        for widgets in self._stats_widgets:
            for widget in widgets:
                widget.setFont(font)

    def _on_color(self, topic, value):
        foreground = rgba_to_css(self._cmdp['Widgets/Multimeter/font-color'])
        background = rgba_to_css(self._cmdp['Widgets/Multimeter/background-color'])
        style = 'QLabel { background-color: %s; color: %s; }' % (background, foreground)
        for widget in self._widgets():
            widget.setStyleSheet(style)

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
        self.update_value()
        self.setToolTip(name)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.unitLabel.setText(_translate("Form", "    "))
        self.stdName.setText(_translate("Form", " σ "))
        self.minName.setText(_translate("Form", " min "))
        self.maxName.setText(_translate("Form", " max "))
        self.p2pName.setText(_translate("Form", " p2p "))

    def _update_value(self, statistics=None):
        if statistics is None:
            v_mean = 0.0
            v_var = 0.0
            v_min = 0.0
            v_max = 0.0
        else:
            v_mean = statistics['µ']['value']
            v_var = statistics['σ2']['value']
            v_min = statistics['min']['value']
            v_max = statistics['max']['value']

        if self._accum_enable:
            if np.isfinite(v_min) and np.isfinite(v_max):
                self.v_min = min(self.v_min, v_min)
                self.v_max = max(self.v_max, v_max)
                self.v_p2p = self.v_max - self.v_min

            if np.isfinite(v_mean) and np.isfinite(v_var):
                self._accum_count += 1
                m = self.v_mean + (v_mean - self.v_mean) / self._accum_count
                if self._accum_count <= 1:
                    self.v_mean = m
                v = (v_mean - self.v_mean) * (v_mean - m) + v_var
                dv = (v - self.v_var) / self._accum_count
                self.v_var += dv
                self.v_mean = m
        else:
            self._accum_count += 1
            self.v_mean = v_mean
            self.v_var = v_var
            self.v_min = v_min
            self.v_max = v_max
            self.v_p2p = v_max - v_min
        self.v_std_dev = math.sqrt(self.v_var)

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

    def update_value(self, statistics=None):
        self._update_value(statistics)
        self._update_ui()

    def update_energy(self, duration, energy, charge):
        v = self._cmdp.convert_units('energy', energy, self._units_short)
        energy, prefix, _ = unit_prefix(v['value'])
        units = f'{prefix}{v["units"]}'
        self.unitLabel.setText(f"<html>&nbsp;{units}&nbsp;</html>")
        energy_str = ('%+6f' % energy)[:8]
        self.valueLabel.setText(energy_str)
        self.on_update.emit([energy_str, '0.0000', energy_str, energy_str, '0.0000'], units)

        charge_c, prefix_c, _ = unit_prefix(charge)
        self.stdName.setText(f"<html>&nbsp;{prefix_c}C&nbsp;</html>")
        self.stdLabel.setText(('%+6f' % charge_c)[:8])

        charge_ah, prefix_ah, _ = unit_prefix(charge / 3600.0)
        self.minName.setText(f"<html>&nbsp;{prefix_ah}Ah&nbsp;</html>")
        self.minLabel.setText(('%+6f' % charge_ah)[:8])

        self.maxName.setText('')
        self.maxLabel.setText('')

        duration_c, prefix_t, _ = unit_prefix(duration)
        self.p2pName.setText(f"<html>&nbsp;{prefix_t}s&nbsp;</html>")
        self.p2pLabel.setText(('%.1f' % duration_c))

    def configure_energy(self):
        self.stdName.setText('')
        self.stdLabel.setText('')
        self.minName.setText('')
        self.minLabel.setText('')
        self.maxName.setText('')
        self.maxLabel.setText('')
        self.p2pName.setText('')
        self.p2pLabel.setText('')
        self.update_energy(0.0, 0.0, 0.0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.valueLabel.fontMetrics().boundingRect("i+0.00000").width()
        self.valueLabel.setMinimumWidth(width)
        width = self.unitLabel.fontMetrics().boundingRect("imWi").width()
        self.unitLabel.setMinimumWidth(width)

        width = self.stdLabel.fontMetrics().boundingRect("i+0.00000").width()
        for label, _ in self._stats_widgets:
            label.setMinimumWidth(width)
