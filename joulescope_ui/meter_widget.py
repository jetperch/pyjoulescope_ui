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

from PySide2 import QtCore, QtWidgets
from . import joulescope_rc
from joulescope.units import three_sig_figs
from .meter_value_widget import MeterValueWidget
import logging
log = logging.getLogger(__name__)


FIELDS = [
    ('current', 'A', 'Amps'),
    ('voltage', 'V', 'Volts'),
    ('power', 'W', 'Watts'),
    ('energy', 'J', 'Joules'),
]


class MeterWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._accumulate_duration = 0.0
        self.verticalLayout = QtWidgets.QVBoxLayout(self)
        self.verticalLayout.setObjectName("verticalLayout")
        self.verticalLayout.setSpacing(0)

        self.controlWidget = QtWidgets.QWidget(self)
        self.controlLayout = QtWidgets.QHBoxLayout(self.controlWidget)
        self.verticalLayout.addWidget(self.controlWidget)

        self.accumulateButton = QtWidgets.QPushButton(self.controlWidget)
        self.accumulateButton.setCheckable(True)
        self.accumulateButton.setObjectName("accumulateButton")
        self.controlLayout.addWidget(self.accumulateButton)
        self.accumulateButton.toggled.connect(self.on_accumulate_toggled)

        self.accumulateDurationLabel = QtWidgets.QLabel(self)
        self.controlLayout.addWidget(self.accumulateDurationLabel)

        self.controlSpacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.controlLayout.addItem(self.controlSpacer)

        self.values = {}
        for name, units_short, units_long in FIELDS:
            w = MeterValueWidget(self)
            w.setStyleSheet("QWidget { background-color : black; color : green; }")
            w.configure(name.capitalize(), units_short, units_long)
            self.values[name] = w
            w.setContentsMargins(0, 0, 0, 0)
            self.verticalLayout.addWidget(w)
        self.values['energy'].configure_energy()

        self.sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.sizePolicy.setHorizontalStretch(0)
        self.sizePolicy.setVerticalStretch(0)
        self.setSizePolicy(self.sizePolicy)
        self.retranslateUi()
        self._cmdp.subscribe('Device/#state/statistics', self._on_device_statistics)

    def __del__(self):
        self._cmdp.unsubscribe('Device/#state/statistics', self._on_device_statistics)

    @QtCore.Slot(bool)
    def on_accumulate_toggled(self, checked):
        self.values['current'].accumulate_enable = checked
        self.values['voltage'].accumulate_enable = checked
        self.values['power'].accumulate_enable = checked

    def _on_device_statistics(self, topic, statistics):
        """Update the multimeter display

        :param statistics: The statistics data structure
        """
        if self.accumulateButton.isChecked():
            self._accumulate_duration += statistics['time']['delta']
        else:
            self._accumulate_duration = statistics['time']['delta']
        for name, field in statistics['signals'].items():
            if name not in self.values:
                continue
            d = field['statistics']
            self.values[name].update_value(mean=d['μ'], variance=d['σ2'], v_min=d['min'], v_max=d['max'])
        accum_time = statistics['time']['accumulator']
        energy = statistics['accumulators']['energy']['value']
        charge = statistics['accumulators']['charge']['value']
        self.values['energy'].update_energy(accum_time, energy, charge)
        self.accumulateDurationLabel.setText(three_sig_figs(self._accumulate_duration, 's'))

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.accumulateButton.setText(_translate("meter_widget", "Accumulate"))


def widget_register(cmdp):
    return {
        'name': 'Multimeter',
        'brief': 'Display the average values and statistics.',
        'class': MeterWidget,
        'location': QtCore.Qt.RightDockWidgetArea,
        'singleton': True,
    }
