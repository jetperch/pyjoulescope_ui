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


from PySide2 import QtWidgets, QtGui, QtCore
from joulescope_ui.widgets.switch import Switch
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

PLAY_TOOLTIP = """\
<html><head/><body><p>
Click to stream data from the selected Joulescope.<br/>
Click again to stop data streaming.
</p></body></html>
"""

RECORD_TOOLTIP = """\
<html><head/><body>
<p>Click to recording streaming Joulescope data to a file.</p>
<p>
Click again to stop the recording.<br/>
Only new data is recorded.
</p></body></html>
"""

IRANGE_TOOLTIP = """\
<html><head/><body>
<p>Select the Joulescope current range.</p>
<p>
"Auto" allows Joulescope to dynamically adjust the current range.<br/>
"Off" disconnects IN+ from OUT+.
</p></body></html>
"""

ON_OFF_SWITCH_TOOLTIP = """\
<html><head/><body>
<p>Switch the target device on or off.</p>
<p>
"Off" disconnects IN+ from OUT+.<br/>
"On" configures the current range to the most recent 
value that was not "off".
</p></body></html>
"""


VRANGE_TOOLTIP = """\
<html><head/><body>
<p>Select the Joulescope voltage range.</p>
<p>No autoranging option exists.
</p></body></html>
"""

ACCUM_TOOLTIP = """\
<html><head/><body>
<p>The accumulated charge or energy.</p>
<p>Left click to clear, same as Tools \u2192 Clear Accumulators.<br/>
Right click for more options.
</p></body></html>",
"""

PLAY_STYLESHEET = """\
QPushButton {
    border-radius: 12;
    image: url(":/joulescope/resources/play.svg"); 
}
QPushButton:enabled       { background: #008000; }
QPushButton:enabled:hover { background: #00A000; }
QPushButton:checked       { background: #008000; }
QPushButton:checked:hover { background: #00A000; }
QPushButton[blink=true]:checked       { background: #00A000; }
QPushButton:disabled      { background: #808080; }

"""

RECORD_STYLESHEET = """\
QPushButton {
    border-radius: 12;
    image: url(":/joulescope/resources/record.svg"); 
}
QPushButton:enabled       { background: #A00000; }
QPushButton:enabled:hover { background: #C00000; }
QPushButton:checked       { background: #A00000; }
QPushButton:checked:hover { background: #D00000; }
QPushButton[blink=true]:checked       { background: #C00000; }
QPushButton:disabled      { background: #808080; }
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

    def _on_field_switch(self):
        self._cmdp.publish('Units/accumulator', self._next_field)


class ControlWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(-1, 1, -1, 1)

        self._playButton = QtWidgets.QPushButton(self)
        self._playButton.setObjectName('playButton')
        self._playButton.setCheckable(True)
        self._playButton.setFlat(True)
        self._playButton.setProperty('blink', False)
        self._playButton.setStyleSheet(PLAY_STYLESHEET)
        self._playButton.setFixedSize(24, 24)
        self._layout.addWidget(self._playButton)

        self._recordButton = QtWidgets.QPushButton(self)
        self._recordButton.setObjectName('recordButton')
        self._recordButton.setEnabled(True)
        self._recordButton.setProperty('blink', False)
        self._recordButton.setStyleSheet(RECORD_STYLESHEET)
        self._recordButton.setCheckable(True)
        self._recordButton.setFlat(True)
        self._recordButton.setFixedSize(24, 24)
        self._layout.addWidget(self._recordButton)

        self._iRangeLabel = QtWidgets.QLabel(self)
        self._iRangeLabel.setObjectName('iRangeLabel')
        self._iRangeLabel.setText('Current Range')
        self._iRangeLabel.setToolTip(IRANGE_TOOLTIP)
        self._layout.addWidget(self._iRangeLabel)

        self._iRangeComboBox = QtWidgets.QComboBox(self)
        self._iRangeComboBox.setObjectName('iRangeComboBox')
        self._iRangeComboBox.setToolTip(IRANGE_TOOLTIP)
        self._layout.addWidget(self._iRangeComboBox)

        self._current_range_when_on = 'auto'
        self._switch = Switch(thumb_radius=11, track_radius=8)
        self._switch.setToolTip(ON_OFF_SWITCH_TOOLTIP)
        self._layout.addWidget(self._switch)

        self._vRangeLabel = QtWidgets.QLabel(self)
        self._vRangeLabel.setObjectName('vRangeLabel')
        self._vRangeLabel.setText('Voltage Range')
        self._vRangeLabel.setToolTip(VRANGE_TOOLTIP)
        self._layout.addWidget(self._vRangeLabel)

        self._vRangeComboBox = QtWidgets.QComboBox(self)
        self._vRangeComboBox.setObjectName('vRangeComboBox')
        self._vRangeComboBox.setToolTip(VRANGE_TOOLTIP)
        self._layout.addWidget(self._vRangeComboBox)

        self._horizontalSpacer = QtWidgets.QSpacerItem(40, 20,
                                                       QtWidgets.QSizePolicy.Expanding,
                                                       QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._horizontalSpacer)

        self._accumLabel = QtWidgets.QLabel(self)
        self._accumLabel.setObjectName(u"accumLabel")
        self._accumLabel.setTextFormat(QtGui.Qt.RichText)
        self._accumLabel.setText('<html><header/><body></body</html>')
        self._accumLabel.setToolTip(ACCUM_TOOLTIP)
        self._layout.addWidget(self._accumLabel)

        self._playButton.setToolTip(PLAY_TOOLTIP)
        self._recordButton.setToolTip(RECORD_TOOLTIP)

        self.setVisible(False)
        self._accum_history = None
        self._accum_menu = None

        self._populate_combobox(self._iRangeComboBox, 'Device/setting/i_range')
        self._populate_combobox(self._vRangeComboBox, 'Device/setting/v_range')

        self._cmdp.subscribe('Device/setting/', self._on_device_parameter, update_now=True)
        self._cmdp.subscribe('Device/#state/', self._on_device_state, update_now=True)
        self._cmdp.subscribe('Units/accumulator', self._on_accumulator)
        self._cmdp.subscribe('!Accumulators/reset', self._on_accumulator_reset)
        self._playButton.toggled.connect(self._on_play_button_toggled)
        self._recordButton.toggled.connect(self._on_record_button_toggled)
        self._switch.toggled.connect(self._on_switch_toggled)
        self._accumLabel.mousePressEvent = self._on_accum_mousePressEvent

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        h = self.minimumSizeHint().height()
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)

        self._blink = True
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(1000)

    def _on_timer(self):
        self._blink = not self._blink
        for b in [self._recordButton]:  # self._playButton
            b.setProperty('blink', self._blink)
            b.style().unpolish(b)
            b.style().polish(b)

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

    def _on_switch_toggled(self, checked):
        log.info('on_off_widget switch %s', checked)
        value = self._current_range_when_on if checked else 'off'
        self._cmdp.publish('Device/setting/i_range', value)

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
            self._update_combobox(self._iRangeComboBox, data)
            block_state = self._switch.blockSignals(True)
            if data == 'off':
                self._switch.setChecked(False)
            else:
                self._switch.setChecked(True)
                self._current_range_when_on = data
            self._switch.blockSignals(block_state)
        elif topic == 'Device/setting/v_range':
            self._update_combobox(self._vRangeComboBox, data)

    def _on_accumulator(self, topic, value):
        self.accum_update()

    def _on_accumulator_reset(self, topic, value):
        self._accum_history = None
        self.accum_update()

    def accum_update(self):
        field = self._cmdp['Units/accumulator']
        if self._accum_history is None:
            time_str = '0 s'
            units = self._cmdp.preferences.get('Units/' + field)
            v = convert_units(0.0, units, units)
        else:
            time_str = self._accum_history['time_str']
            a = self._accum_history['accumulators']
            v = a[field]
            units = self._cmdp.preferences.get('Units/' + field, default=v['units'])
            v = convert_units(v['value'], v['units'], units)
        s = three_sig_figs(v['value'], v['units'])
        txt = ACCUM_TEMPLATE.format(field=field.capitalize(), value=s, time=time_str)
        self._accumLabel.setText(txt)

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
                self._playButton.setEnabled(True)
                self._switch.setEnabled(True)
                self._iRangeComboBox.setEnabled(True)
                self._vRangeComboBox.setEnabled(True)
            elif data == 'Buffer':
                self._playButton.setEnabled(True)
                self._recordButton.setEnabled(False)
                self._switch.setEnabled(False)
                self._iRangeComboBox.setEnabled(False)
                self._vRangeComboBox.setEnabled(False)
            else:
                self._playButton.setChecked(False)
                self._playButton.setEnabled(False)
                self._recordButton.setChecked(False)
                self._recordButton.setEnabled(False)
                self._switch.setEnabled(False)
                self._iRangeComboBox.setEnabled(False)
                self._vRangeComboBox.setEnabled(False)
        elif self._cmdp['Device/#state/source'] in ['USB', 'Buffer']:
            if topic == 'Device/#state/play':
                self._playButton.setChecked(data)
                self._recordButton.setEnabled(data)
                self._switch.setEnabled(data)
            elif topic == 'Device/#state/record':
                self._recordButton.setChecked(data)


def widget_register(cmdp):
    return {
        'name': 'Control',
        'brief': 'Control the connected Joulescope device.',
        'class': ControlWidget,
        'location': QtCore.Qt.TopDockWidgetArea,
        'singleton': True,
    }
