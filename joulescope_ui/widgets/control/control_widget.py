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


from PySide2 import QtWidgets, QtCore
from .control_widget_ui import Ui_ControlWidget
import logging


log = logging.getLogger(__name__)


class ControlWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._ui = Ui_ControlWidget()
        self._ui.setupUi(self)
        self.setVisible(False)

        self._populate_combobox(self._ui.iRangeComboBox, 'Device/parameter/i_range')
        self._populate_combobox(self._ui.vRangeComboBox, 'Device/parameter/v_range')

        self._cmdp.subscribe('Device/parameter/', self._on_device_parameter, update_now=True)
        self._cmdp.subscribe('Device/#state/', self._on_device_state, update_now=True)
        self._ui.playButton.toggled.connect(self._on_play_button_toggled)
        self._ui.recordButton.toggled.connect(self._on_record_button_toggled)

    def __del__(self):
        self._cmdp.unsubscribe('Device/parameter/', self._on_device_parameter)
        self._cmdp.unsubscribe('Device/#state/', self._on_device_state)

    def _on_play_button_toggled(self, checked):
        log.info('control_widget play button %s', checked)
        self._cmdp.publish('Device/#state/play', checked)

    def _on_record_button_toggled(self, checked):
        log.info('control_widget record button %s %s', checked)
        self._cmdp.publish('Device/#state/record', checked)

    def _populate_combobox(self, combobox, topic):
        try:
            combobox.currentIndexChanged.disconnect()
        except Exception:
            pass
        combobox.clear()
        for option in self._cmdp.preferences.definition_options(topic):
            combobox.addItem(option)
        combobox.currentIndexChanged.connect(lambda *args: self._cmdp.publish(topic, str(combobox.currentText())))

    def _update_combobox(self, combobox, value):
        index = None
        for i in range(combobox.count()):
            if value == str(combobox.itemText(i)):
                index = i
                combobox.setCurrentIndex(index)
                break
        if index is None:
            log.warning('Could not find item %s in combobox', value)

    def _on_device_parameter(self, topic, data):
        if topic == 'Device/parameter/i_range':
            self._update_combobox(self._ui.iRangeComboBox, data)
        elif topic == 'Device/parameter/v_range':
            self._update_combobox(self._ui.vRangeComboBox, data)

    def _on_device_state(self, topic, data):
        if topic == 'Device/#state/energy':
            self._ui.energyValueLabel.setText(data)
        elif topic == 'Device/#state/source':
            if data in 'USB':
                self._ui.playButton.setEnabled(True)
                self._ui.iRangeComboBox.setEnabled(True)
                self._ui.vRangeComboBox.setEnabled(True)
            elif data == 'Buffer':
                self._ui.playButton.setEnabled(True)
                self._ui.recordButton.setEnabled(False)
                self._ui.iRangeComboBox.setEnabled(False)
                self._ui.vRangeComboBox.setEnabled(False)
            else:
                self._ui.playButton.setChecked(False)
                self._ui.playButton.setEnabled(False)
                self._ui.recordButton.setChecked(False)
                self._ui.recordButton.setEnabled(False)
                self._ui.iRangeComboBox.setEnabled(False)
                self._ui.vRangeComboBox.setEnabled(False)
        elif self._cmdp['Device/#state/source'] in ['USB', 'Buffer']:
            if topic == 'Device/#state/play':
                self._ui.playButton.setChecked(data)
                self._ui.recordButton.setEnabled(data)
            elif topic == 'Device/#state/record':
                self._ui.recordButton.setChecked(data)


def widget_register(cmdp):
    return {
        'name': 'Control',
        'brief': 'Control the connected Joulescope device.',
        'class': ControlWidget,
        'location': QtCore.Qt.TopDockWidgetArea,
        'singleton': True,
    }
