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
from joulescope_ui.gpio_widget import Ui_Gpio

VOLTAGES = ['1.8V', '2.1V', '2.5V', '2.7V', '3.0V', '3.3V', '5.0V']


class GpioWidget(QtWidgets.QWidget):
    on_changeSignal = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.ui = Ui_Gpio()
        self.ui.setupUi(self)
        self._state = None
        self._io_voltages = []
        self._update_active = False

    def init(self, voltages):
        self._io_voltages = voltages
        self.ui.voltageComboBox.clear()
        for idx, v in enumerate(self._io_voltages):
            self.ui.voltageComboBox.addItem(v)
        self._state = self.extract()
        self.ui.voltageComboBox.currentIndexChanged.connect(self._on_voltage_change)
        self.ui.output0Button.toggled.connect(self._on_button_change)
        self.ui.output1Button.toggled.connect(self._on_button_change)
        self.ui.input0Button.toggled.connect(self._on_button_change)
        self.ui.input1Button.toggled.connect(self._on_button_change)

    def update(self, state=None):
        if state is not None:
            self._state = state
        self._update_active = True
        for idx, v in enumerate(self._io_voltages):
            if v == self._state['io_voltage']:
                if self.ui.voltageComboBox.currentIndex() != idx:
                    self.ui.voltageComboBox.setCurrentIndex(idx)
                break

        output_buttons = [
            (self.ui.output0Button, self._state['gpo0']),
            (self.ui.output1Button, self._state['gpo1']),
        ]
        for button, value in output_buttons:
            checked = bool(int(value))
            if button.isChecked() != checked:
                button.setChecked(checked)

        input_buttons = [
            (self.ui.input0Button, self._state['current_lsb']),
            (self.ui.input1Button, self._state['voltage_lsb']),
        ]
        for button, value in input_buttons:
            checked = (value != 'normal')
            if button.isChecked() != checked:
                button.setChecked(checked)
        self._update_active = False

    def extract(self):
        state = {
            'io_voltage': str(self.ui.voltageComboBox.currentText()),
            'gpo0': '1' if self.ui.output0Button.isChecked() else '0',
            'gpo1': '1' if self.ui.output1Button.isChecked() else '0',
            'current_lsb': 'gpi0' if self.ui.input0Button.isChecked() else 'normal',
            'voltage_lsb': 'gpi1' if self.ui.input1Button.isChecked() else 'normal',
        }
        return state

    def _handle_event(self):
        if self._update_active:
            return
        state = self.extract()
        if state != self._state:
            self._state = state
            self.on_changeSignal.emit(state)

    @QtCore.Slot(object)
    def _on_button_change(self, checked):
        self._handle_event()

    @QtCore.Slot(object)
    def _on_voltage_change(self, value):
        self._handle_event()

    def data_update(self, data):
        if not self.isVisible():
            return
        for signal_name, label in [('current_lsb', self.ui.input0Label), ('voltage_lsb', self.ui.input1Label)]:
            if signal_name not in data['signals']:
                continue
            v = data['signals'][signal_name]['μ']
            if len(v):
                v = str(int(v[-1]))
            else:
                v = ' '
            label.setText(v)
