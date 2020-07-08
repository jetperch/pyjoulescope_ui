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
from joulescope_ui.template import render
from joulescope.units import three_sig_figs
from .meter_value_widget import MeterValueWidget
from joulescope_ui.ui_util import rgba_to_css
import datetime
import logging
log = logging.getLogger(__name__)


STYLESHEET = """\
QWidget[multimeter=true] {
  padding: 0px;
  color: {% multimeter_color %};
}

QWidget[multimeter_spacer=true] {
  background-color: {% multimeter_background_half %};
}

QLabel[multimeter_label=true] {
  padding-left: 2px;
  padding-right: 2px;
  padding-top: 2px;
  padding-bottom: 2px; 
  background-color: {% multimeter_background_color %}; 
  color: {% multimeter_color %};
  border-color: white;
}
"""


FIELDS = [
    ('current', 'A', 'Amps'),
    ('voltage', 'V', 'Volts'),
    ('power', 'W', 'Watts'),
    ('energy', 'J', 'Joules'),
]


ACCUMULATE_TOOLTIP = """\
<html><head/><body>
<p>Accumulate current, voltage, and power over time.</p>
<p>Current, voltage, and power are normally computed
over the statistics duration, which you can set using:<br/>
<b>File → Preferences → Device → setting → reduction_frequency</b></p>

<p>Press this button to compute the mean, standard deviation,
minimum, maximum, and peak-to-peak statistics
over multiple statistics durations.  Press again
to return to single statistics duration.</p>

<p>Note that this button does not affect the charge and energy
accumulation.  Select <b>Tools → Clear Accumulator</b> to reset them.</p>
</body></html>
"""


class MeterWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._accumulate_duration = 0.0
        self._accumulate_start = None

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
        self.accumulateButton.setToolTip(ACCUMULATE_TOOLTIP)

        self.accumulateDurationLabel = QtWidgets.QLabel(self)
        self.controlLayout.addWidget(self.accumulateDurationLabel)

        self.controlSpacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.controlLayout.addItem(self.controlSpacer)

        self._grid_widget = QtWidgets.QWidget(self)
        self.verticalLayout.addWidget(self._grid_widget)
        self._grid_widget.setProperty('multimeter', True)

        self._grid_layout = QtWidgets.QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setMargin(0)
        self._grid_layout.setHorizontalSpacing(0)
        self._grid_layout.setVerticalSpacing(0)

        self.spacers = []
        self.values = {}
        for idx, (name, units_short, units_long) in enumerate(FIELDS):
            if idx:
                spacer = QtWidgets.QWidget(self._grid_widget)
                spacer.setProperty('multimeter_spacer', True)
                spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
                spacer.setMinimumHeight(2)
                self._grid_layout.addWidget(spacer, idx * 5 - 1, 0, 1, 4)
                self.spacers.append(spacer)
            w = MeterValueWidget(self._grid_widget, cmdp, idx * 5, name)
            w.configure(name.capitalize(), units_short, units_long)
            self.values[name] = w
        self.values['energy'].configure_energy()

        self._grid_layout.setColumnStretch(0, 1)
        self._grid_layout.setColumnStretch(1, 1)
        self.sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.sizePolicy.setHorizontalStretch(0)
        self.sizePolicy.setVerticalStretch(0)
        self.setSizePolicy(self.sizePolicy)
        self.retranslateUi()
        self._cmdp.subscribe('Device/#state/statistics', self._on_device_statistics, update_now=True)

        cmdp.subscribe('Widgets/Multimeter/font-main', self._on_font_main, update_now=True)
        cmdp.subscribe('Widgets/Multimeter/font-stats', self._on_font_stats, update_now=True)
        cmdp.subscribe('Widgets/Multimeter/font-color', self._on_color)
        cmdp.subscribe('Widgets/Multimeter/background-color', self._on_color, update_now=True)
        self._cmdp.subscribe('!Accumulators/reset', self._on_accumulator_reset)

    def _on_font_main(self, topic, value):
        font = QtGui.QFont()
        font.fromString(value)
        metrics = QtGui.QFontMetrics(font)
        w1 = metrics.boundingRect("i+0.00000i").width()
        w2 = metrics.boundingRect("iMW").width()
        for value in self.values.values():
            for w, width in zip(value.main_widgets, [w1, w2]):
                w.setFont(font)
                w.setMinimumWidth(width)

    def _on_font_stats(self, topic, value):
        font = QtGui.QFont()
        font.fromString(value)
        metrics = QtGui.QFontMetrics(font)
        width = metrics.boundingRect("i+0.00000i").width()
        for value in self.values.values():
            for w1, w2 in value.stats_widgets:
                w1.setFont(font)
                w1.setMinimumWidth(width)
                w2.setFont(font)

    def _on_color(self, topic, value):
        foreground = rgba_to_css(self._cmdp['Widgets/Multimeter/font-color'])
        bg = self._cmdp['Widgets/Multimeter/background-color']
        background = rgba_to_css(bg)
        r, g, b, a = bg
        bg_half = rgba_to_css([r, g, b, a * 0.75])
        style = render(STYLESHEET,
                       multimeter_background_color=background,
                       multimeter_color=foreground,
                       multimeter_background_half=bg_half)
        self._grid_widget.setStyleSheet(style)

    @QtCore.Slot(bool)
    def on_accumulate_toggled(self, checked):
        self._accumulate_start = None
        self.values['current'].accumulate_enable = checked
        self.values['voltage'].accumulate_enable = checked
        self.values['power'].accumulate_enable = checked

    def _on_accumulator_reset(self, topic, statistics):
        self.values['energy'].update_energy(0, 0, 0)

    def _on_device_statistics(self, topic, statistics):
        """Update the multimeter display

        :param statistics: The statistics data structure
        """
        if not statistics:
            return
        if self.accumulateButton.isChecked():
            self._accumulate_duration += statistics['time']['delta']['value']
            if self._accumulate_start is None:
                self._accumulate_start = datetime.datetime.now().isoformat().split('.')[0]
            accum_txt = f'{int(self._accumulate_duration)} s | Started at {self._accumulate_start}'
        else:
            self._accumulate_duration = statistics['time']['delta']['value']
            accum_txt = three_sig_figs(self._accumulate_duration, 's')
        for name, field in statistics['signals'].items():
            if name not in self.values:
                continue
            self.values[name].update_value(field)
        accum_time = statistics['time']['accumulator']
        energy = statistics['accumulators']['energy']['value']
        charge = statistics['accumulators']['charge']['value']
        self.values['energy'].update_energy(accum_time['value'], energy, charge)
        self.accumulateDurationLabel.setText(accum_txt)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.accumulateButton.setText(_translate("meter_widget", "Accumulate"))


def widget_register(cmdp):
    # https://blog.graphiq.com/finding-the-best-free-fonts-for-numbers-25c54002a895
    cmdp.define(
        topic='Widgets/Multimeter/font-main',
        dtype='font',
        default="Lato,48,-1,5,87,0,0,0,0,0,Black")
    cmdp.define(
        topic='Widgets/Multimeter/font-stats',
        dtype='font',
        default="Lato,10,-1,5,87,0,0,0,0,0,Black")
    cmdp.define(
        topic='Widgets/Multimeter/font-color',
        brief='The font color.',
        dtype='color',
        default=(0, 128, 0, 255))
    cmdp.define(
        topic='Widgets/Multimeter/background-color',
        brief='The background color.',
        dtype='color',
        default=(0, 0, 0, 255))

    return {
        'name': 'Multimeter',
        'brief': 'Display the average values and statistics.',
        'class': MeterWidget,
        'location': QtCore.Qt.RightDockWidgetArea,
        'singleton': True,
    }
