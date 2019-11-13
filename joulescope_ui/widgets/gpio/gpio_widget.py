# Copyright 2019 Jetperch LLC
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
from .gpio_widget_ui import Ui_GpioWidget
import numpy as np


VOLTAGES = ['1.8V', '2.1V', '2.5V', '2.7V', '3.0V', '3.3V', '5.0V']


class GpioWidget(QtWidgets.QWidget):
    on_changeSignal = QtCore.Signal(object)

    def __init__(self, parent, cmdp):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_GpioWidget()
        self.ui.setupUi(self)
        self._cmdp = cmdp
        self._state = None
        self._io_voltages = []
        self._update_active = False
        self._inputs = [('current_lsb', self.ui.input0CheckBox, self.ui.input0Label),
                        ('voltage_lsb', self.ui.input1CheckBox, self.ui.input1Label)]
        self.data_update_clear()
        self._cmdp.subscribe('DataView/#data', self._on_device_state_data)

    def __del__(self):
        self._cmdp.unsubscribe('DataView/#data', self._on_device_state_data)

    def init(self, voltages):
        self._io_voltages = voltages
        self.ui.voltageComboBox.clear()
        for idx, v in enumerate(self._io_voltages):
            self.ui.voltageComboBox.addItem(v)
        self._state = self.extract()
        self.ui.voltageComboBox.currentIndexChanged.connect(self._on_voltage_change)
        self.ui.output0Button.toggled.connect(self._on_butotn_change)
        self.ui.output1Button.toggled.connect(self._on_button_change)
        self.ui.input0CheckBox.toggled.connect(self._on_button_change)
        self.ui.input1CheckBox.toggled.connect(self._on_button_change)

    def update(self, state=None):
        if state is not None:
            self._state = state
        self._update_active = True
        for idx, v in enumerate(self._io_voltages):
            if v == self._state['Device/parameter/io_voltage']:
                if self.ui.voltageComboBox.currentIndex() != idx:
                    self.ui.voltageComboBox.setCurrentIndex(idx)
                break

        output_buttons = [
            (self.ui.output0Button, self._state['Device/parameter/gpo0']),
            (self.ui.output1Button, self._state['Device/parameter/gpo1']),
        ]
        for button, value in output_buttons:
            checked = bool(int(value))
            if button.isChecked() != checked:
                button.setChecked(checked)

        for name, checkbox, _ in self._inputs:
            value = self._state['Device/parameter/' + name]
            checked = (value != 'normal')
            if checkbox.isChecked() != checked:
                checkbox.setChecked(checked)
        self.data_update_clear()
        self._update_active = False

    def extract(self):
        state = {
            'io_voltage': str(self.ui.voltageComboBox.currentText()),
            'gpo0': '1' if self.ui.output0Button.isChecked() else '0',
            'gpo1': '1' if self.ui.output1Button.isChecked() else '0',
            'current_lsb': 'gpi0' if self.ui.input0CheckBox.isChecked() else 'normal',
            'voltage_lsb': 'gpi1' if self.ui.input1CheckBox.isChecked() else 'normal',
        }
        return state

    def _handle_event(self):
        if self._update_active:
            return
        state = self.extract()
        self.data_update_clear()
        if state != self._state:
            self._state = state
            self.on_changeSignal.emit(state)

    @QtCore.Slot(object)
    def _on_button_change(self, checked):
        self._handle_event()

    @QtCore.Slot(object)
    def _on_voltage_change(self, value):
        self._handle_event()

    def _on_device_state_data(self, topic, data):
        if not self.isVisible():
            return
        for signal_name, checkbox, label in self._inputs:
            if signal_name not in data['signals']:
                continue
            v = data['signals'][signal_name]['μ']
            if len(v) and np.isfinite(v[-1]):
                v = str(int(v[-1]))
            else:
                v = '_'
            label.setText(v)

    def data_update_clear(self):
        for _, checkbox, label in self._inputs:
            if not checkbox.isChecked():
                label.setStyleSheet('QLabel {color: rgba(255, 255, 255, 255); }')
            else:
                label.setStyleSheet('QLabel {color: blue; }')


def widget_register(cmdp):
    #io_voltage_def = self._cmdp.preferences.definition_get('Device/parameter/io_voltage')
    #self.gpio_widget.init(io_voltage_def['options'].keys())
    #self.gpio_widget.on_changeSignal.connect(self._on_gpio_cfg_change)

    return {
        'name': 'GPIO',
        'brief': 'General purpose input/output control and display',
        'class': GpioWidget,
        'location': QtCore.Qt.RightDockWidgetArea,
        'singleton': True,
    }
