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
from joulescope.units import unit_prefix
import numpy as np
import math


class MeterValueWidget(QtCore.QObject):
    on_update = QtCore.Signal(object, str)  # [mean, std_dev, min, max, p2p], units : values are formatted strings!

    def __init__(self, parent, cmdp, row, name):
        QtCore.QObject.__init__(self, parent)
        self._cmdp = cmdp
        self._units_short = ''
        self._units_long = ''
        self.v_mean = 0.0
        self.v_var = 0.0
        self.v_std_dev = 0.0
        self.v_min = 0.0
        self.v_max = 0.0
        self.v_p2p = 0.0
        self._clipboard_text = ''

        self._accum_enable = False
        self._accum_count = 0
        layout = parent.layout()

        self.valueLabel = QtWidgets.QLabel(parent)
        self.valueLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)
        self.valueLabel.setObjectName(f'{name}_valueLabel')
        layout.addWidget(self.valueLabel, row, 0, 4, 1)

        self.unitLabel = QtWidgets.QLabel(parent)
        self.unitLabel.setObjectName(f'{name}_unitLabel')
        layout.addWidget(self.unitLabel, row, 1, 4, 1)

        self.stdLabel = QtWidgets.QLabel(parent)
        self.stdLabel.setLineWidth(0)
        self.stdLabel.setObjectName(f'{name}_stdLabel')
        layout.addWidget(self.stdLabel, row, 2, 1, 1)

        self.stdName = QtWidgets.QLabel(parent)
        self.stdName.setLineWidth(0)
        self.stdName.setObjectName(f'{name}_stdName')
        layout.addWidget(self.stdName, row, 3, 1, 1)

        self.minLabel = QtWidgets.QLabel(parent)
        self.minLabel.setLineWidth(0)
        self.minLabel.setObjectName(f'{name}_minLabel')
        layout.addWidget(self.minLabel, row + 1, 2, 1, 1)

        self.minName = QtWidgets.QLabel(parent)
        self.minName.setLineWidth(0)
        self.minName.setObjectName(f'{name}_minName')
        layout.addWidget(self.minName, row + 1, 3, 1, 1)

        self.maxLabel = QtWidgets.QLabel(parent)
        self.maxLabel.setLineWidth(0)
        self.maxLabel.setObjectName(f'{name}_maxLabel')
        layout.addWidget(self.maxLabel, row + 2, 2, 1, 1)

        self.maxName = QtWidgets.QLabel(parent)
        self.maxName.setLineWidth(0)
        self.maxName.setObjectName(f'{name}_maxName')
        layout.addWidget(self.maxName, row + 2, 3, 1, 1)

        self.p2pLabel = QtWidgets.QLabel(parent)
        self.p2pLabel.setLineWidth(0)
        self.p2pLabel.setObjectName(f'{name}_p2pLabel')
        layout.addWidget(self.p2pLabel, row + 3, 2, 1, 1)

        self.p2pName = QtWidgets.QLabel(parent)
        self.p2pName.setLineWidth(0)
        self.p2pName.setObjectName(f'{name}_p2pName')
        layout.addWidget(self.p2pName, row + 3, 3, 1, 1)

        self.main_widgets = [self.valueLabel, self.unitLabel]
        for w in self.main_widgets:
            w.setProperty('multimeter_label', True)
            w.setProperty('multimeter_main', True)
            w.mousePressEvent = self._mouse_press_event_factory(self.valueLabel)

        self.stats_widgets = [
            (self.stdLabel, self.stdName),
            (self.minLabel, self.minName),
            (self.maxLabel, self.maxName),
            (self.p2pLabel, self.p2pName),
        ]
        for value_widget, name_widget in self.stats_widgets:
            for w in [value_widget, name_widget]:
                w.setProperty('multimeter_label', True)
                w.setProperty('multimeter_statistic', True)
            value_widget.mousePressEvent = self._mouse_press_event_factory(value_widget)
            name_widget.mousePressEvent = self._mouse_press_event_factory(value_widget)

        self.retranslateUi()

    def _mouse_press_event_factory(self, label):
        def on_mouse_press_event(event: QtGui.QMouseEvent):
            # if event.button() == QtCore.Qt.LeftButton:
            self._clipboard_text = f'{label.text()} {self.unitLabel.text()}'
            QtWidgets.QApplication.clipboard().setText(self._clipboard_text)
        return on_mouse_press_event

    def _widgets(self):
        widgets = [self.valueLabel, self.unitLabel]
        for w in self.stats_widgets:
            widgets.extend(w)
        return widgets

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
        # self.setToolTip(name)

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
        units = f'{prefix}{self._units_short}'
        self.unitLabel.setText(units)
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
        self.unitLabel.setText(units)
        energy_str = ('%+6f' % energy)[:8]
        self.valueLabel.setText(energy_str)
        self.on_update.emit([energy_str, '0.0000', energy_str, energy_str, '0.0000'], units)

        charge_c, prefix_c, _ = unit_prefix(charge)
        self.stdName.setText(f"{prefix_c}C")
        self.stdLabel.setText(('%+6f' % charge_c)[:8])

        charge_ah, prefix_ah, _ = unit_prefix(charge / 3600.0)
        self.minName.setText(f"{prefix_ah}Ah")
        self.minLabel.setText(('%+6f' % charge_ah)[:8])

        self.maxName.setText('')
        self.maxLabel.setText('')

        time_parts = self._cmdp.elapsed_time_formatter(duration).split(' ')
        if len(time_parts) > 1:
            self.p2pLabel.setText(time_parts[0])
            self.p2pName.setText(time_parts[1])
        else:
            self.p2pLabel.setText(time_parts[0])
            self.p2pName.setText('')

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
