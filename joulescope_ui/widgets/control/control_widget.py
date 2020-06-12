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
from joulescope.units import three_sig_figs
from joulescope_ui.units import convert_units
import logging
import weakref


log = logging.getLogger(__name__)


ACCUM_TEMPLATE = """\
<html><head/><body><p>
<span style="font-size:8pt;">{field}</span>
<span style="font-size:12pt;">{value}</span>
<span style="font-size:8pt;">in</span>
<span style="font-size:12pt;">{time}</span>
</p></body></html>
"""


class AccumMenu(QtWidgets.QMenu):

    def __init__(self, parent, cmdp):
        self.parent = weakref.ref(parent)
        self._cmdp = cmdp
        QtWidgets.QMenu.__init__(self, 'Accumulator menu', parent)

        self.accum_clear = self.addAction('&Clear')
        self.accum_clear.triggered.connect(self._on_clear)

        field = cmdp['Units/accumulator']
        self._next_field = 'energy' if field == 'charge' else 'charge'
        self.field = self.addAction(f'&Show {self._next_field}')
        self.field.triggered.connect(self._on_field_switch)

    def _on_clear(self):
        self._cmdp.invoke('!Accumulators/reset', None)
        self.parent().accum_update(True)

    def _on_field_switch(self):
        self._cmdp.publish('Units/accumulator', self._next_field)


class ControlWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._ui = Ui_ControlWidget()
        self._ui.setupUi(self)
        self.setVisible(False)
        self._accum_history = None
        self._accum_menu = None

        self._populate_combobox(self._ui.iRangeComboBox, 'Device/setting/i_range')
        self._populate_combobox(self._ui.vRangeComboBox, 'Device/setting/v_range')

        self._cmdp.subscribe('Device/setting/', self._on_device_parameter, update_now=True)
        self._cmdp.subscribe('Device/#state/', self._on_device_state, update_now=True)
        self._cmdp.subscribe('Units/accumulator', self._on_accumulator)
        self._ui.playButton.toggled.connect(self._on_play_button_toggled)
        self._ui.recordButton.toggled.connect(self._on_record_button_toggled)
        self._ui.accumLabel.mousePressEvent = self._on_accum_mousePressEvent

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        h = self.minimumSizeHint().height()
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)

    def _on_accum_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._cmdp.invoke('!Accumulators/reset', None)
            event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            self._accum_menu = AccumMenu(self, self._cmdp).popup(event.globalPos())
            event.accept()

    def _on_play_button_toggled(self, checked):
        log.info('control_widget play button %s', checked)
        self._cmdp.publish('Device/#state/play', checked)

    def _on_record_button_toggled(self, checked):
        log.info('control_widget record button %s', checked)
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
                block_signals_state = combobox.blockSignals(True)
                combobox.setCurrentIndex(index)
                combobox.blockSignals(block_signals_state)
                break
        if index is None:
            log.warning('Could not find item %s in combobox', value)

    def _on_device_parameter(self, topic, data):
        if topic == 'Device/setting/i_range':
            self._update_combobox(self._ui.iRangeComboBox, data)
        elif topic == 'Device/setting/v_range':
            self._update_combobox(self._ui.vRangeComboBox, data)

    def _on_accumulator(self, topic, value):
        self.accum_update()

    def accum_update(self, clear=None):
        if bool(clear):
            self._accum_history = None
        if self._accum_history is None:
            txt = ''
        else:
            field = self._cmdp['Units/accumulator']
            time_str = self._accum_history['time_str']
            a = self._accum_history['accumulators']
            v = a[field]
            units = self._cmdp.preferences.get('Units/' + field, default=v['units'])
            v = convert_units(v['value'], v['units'], units)
            s = three_sig_figs(v['value'], v['units'])
            txt = ACCUM_TEMPLATE.format(field=field.capitalize(), value=s, time=time_str)
        self._ui.accumLabel.setText(txt)

    def _on_device_state(self, topic, data):
        if topic == 'Device/#state/statistics':
            try:
                t = data['time']['accumulator']
                time_str = f"{int(t['value'])} {t['units']}"
                a = data.get('accumulators', {})
                self._accum_history = {
                    'time_str': time_str,
                    'accumulators': a,
                }
            except:
                self._accum_history = None
            self.accum_update()
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
