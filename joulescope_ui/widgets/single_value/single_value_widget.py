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
import numpy as np
from joulescope_ui import joulescope_rc
from joulescope.units import unit_prefix
from joulescope_ui.ui_util import rgba_to_css, comboBoxSelectItemByText
import logging
log = logging.getLogger(__name__)


FONT_SIZES = [24, 32, 40, 48, 56, 64]


STATISTICS_TRANSLATE = {
    'Mean': lambda s: s['μ'],
    'Standard Deviation': lambda s: np.sqrt(s['σ2']),
    'Minimum': lambda s: s['min'],
    'Maximum': lambda s: s['max'],
    'Peak-to-Peak': lambda s: s['p2p'],
}


class SingleValueWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._font_index = 2
        self._statistics = {}
        self._state_preference = state_preference
        self.setObjectName("SingleValueWidget")
        self.resize(387, 76)
        self.horizontalLayout = QtWidgets.QHBoxLayout(self)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.widget = QtWidgets.QWidget(self)
        self.widget.setObjectName("widget")
        self.formLayout = QtWidgets.QFormLayout(self.widget)
        self.formLayout.setObjectName("formLayout")
        self.fieldLabel = QtWidgets.QLabel(self.widget)
        self.fieldLabel.setObjectName("fieldLabel")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.fieldLabel)
        self.fieldComboBox = QtWidgets.QComboBox(self.widget)
        self.fieldComboBox.setObjectName("fieldComboBox")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.fieldComboBox)
        self.statisticLabel = QtWidgets.QLabel(self.widget)
        self.statisticLabel.setObjectName("statisticLabel")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.statisticLabel)
        self.statisticComboBox = QtWidgets.QComboBox(self.widget)
        self.statisticComboBox.setObjectName("statisticComboBox")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.statisticComboBox)
        self.horizontalLayout.addWidget(self.widget)
        self.spacerItem = QtWidgets.QSpacerItem(44, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(self.spacerItem)
        self.value_widget = QtWidgets.QWidget(self)
        self.value_widget.setObjectName("ValueWidget")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.value_widget)
        self.horizontalLayout_2.setContentsMargins(-1, 0, -1, 0)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.valueLabel = QtWidgets.QLabel(self.value_widget)
        self.valueLabel.setLineWidth(0)
        self.valueLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)
        self.valueLabel.setObjectName("valueLabel")
        self.horizontalLayout_2.addWidget(self.valueLabel)
        self.unitLabel = QtWidgets.QLabel(self.value_widget)
        self.unitLabel.setLineWidth(0)
        self.unitLabel.setObjectName("unitLabel")
        self.horizontalLayout_2.addWidget(self.unitLabel)
        self.horizontalLayout.addWidget(self.value_widget)

        self.retranslateUi()
        self.fieldComboBox.currentIndexChanged.connect(self.on_field_changed)
        self.statisticComboBox.currentIndexChanged.connect(self.on_statistic_changed)
        self._cmdp.subscribe('Device/#state/statistics', self._on_device_statistics, update_now=True)
        cmdp.subscribe('Widgets/Single Value/font', self._on_font, update_now=True)
        cmdp.subscribe('Widgets/Single Value/font-color', self._on_color, update_now=True)
        cmdp.subscribe('Widgets/Single Value/background-color', self._on_color, update_now=True)

        if self._state_preference not in cmdp:
            cmdp[self._state_preference] = {}
        cmdp.subscribe(self._state_preference, self._on_state, update_now=True)

    def _on_state(self, topic, value):
        if value is None:
            try:
                value = self._cmdp[self._state_preference]
            except KeyError:
                return
        if 'fieldComboBox' in value and value['fieldComboBox'] != self.fieldComboBox.currentText():
            comboBoxSelectItemByText(self.fieldComboBox, value['fieldComboBox'], block=True)
        if 'statisticComboBox' in value and value['statisticComboBox'] != self.statisticComboBox.currentText():
            comboBoxSelectItemByText(self.statisticComboBox, value['statisticComboBox'], block=True)

    def _state_update(self):
        self._cmdp[self._state_preference] = {
            'fieldComboBox': self.fieldComboBox.currentText(),
            'statisticComboBox': self.statisticComboBox.currentText(),
        }

    def _on_font(self, topic, value):
        font = QtGui.QFont()
        font.fromString(value)
        self.valueLabel.setFont(font)
        self.unitLabel.setFont(font)
        self.resizeEvent(None)

    def _on_color(self, topic, value):
        foreground = rgba_to_css(self._cmdp['Widgets/Multimeter/font-color'])
        background = rgba_to_css(self._cmdp['Widgets/Multimeter/background-color'])
        style = f"""
        QWidget {{ background-color : {background}; }}
        QLabel {{ background-color : {background}; color : {foreground}; }}
        """
        self.value_widget.setStyleSheet(style)

    @QtCore.Slot(object, str)
    def _on_device_statistics(self, topic, statistics):
        self._statistics = statistics
        self._update()

    def _update(self):
        if not len(self._statistics):
            return
        if self.fieldComboBox.count() == 0:
            fields = list(self._statistics['signals'].keys()) + \
                     list(self._statistics['accumulators'].keys())
            block_signals_state = self.fieldComboBox.blockSignals(True)
            for field in fields:
                self.fieldComboBox.addItem(field)
            self._on_state(None, None)  # restore
            self.fieldComboBox.blockSignals(block_signals_state)
        field = self.fieldComboBox.currentText()
        if field in self._statistics['signals']:
            self.statisticComboBox.setEnabled(True)
            stat = self.statisticComboBox.currentText()
            s = self._statistics['signals'][field]['statistics']
            units = self._statistics['signals'][field]['units']
            value = STATISTICS_TRANSLATE[stat](s)
        elif field in self._statistics['accumulators']:
            self.statisticComboBox.setEnabled(False)
            value = self._statistics['accumulators'][field]['value']
            units = self._statistics['accumulators'][field]['units']
        else:
            log.warning('unsupported field: %s', field)
            return

        _, prefix, scale = unit_prefix(value)
        value /= scale
        value_str = ('%+6f' % value)[:8]
        self.valueLabel.setText(value_str)
        self.unitLabel.setText(f"<html>&nbsp;{prefix}{units}&nbsp;</html>")

    @QtCore.Slot(int)
    def on_field_changed(self, index):
        self._update()
        self._state_update()

    @QtCore.Slot(int)
    def on_statistic_changed(self, index):
        self._update()
        self._state_update()

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.fieldLabel.setText(_translate("Form", "Field"))
        self.statisticLabel.setText(_translate("Form", "Statistic"))
        self.statisticComboBox.addItem(_translate("Form", "Mean"))
        self.statisticComboBox.addItem(_translate("Form", "Standard Deviation"))
        self.statisticComboBox.addItem(_translate("Form", "Minimum"))
        self.statisticComboBox.addItem(_translate("Form", "Maximum"))
        self.statisticComboBox.addItem(_translate("Form", "Peak-to-Peak"))
        self.valueLabel.setText("")
        self.unitLabel.setText(_translate("Form", ""))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.valueLabel.fontMetrics().boundingRect("i+0.00000").width()
        self.valueLabel.setMinimumWidth(width)
        width = self.unitLabel.fontMetrics().boundingRect("imW").width()
        self.unitLabel.setMinimumWidth(width)


def widget_register(cmdp):
    cmdp.define(
        topic='Widgets/Single Value/font',
        dtype='font',
        default="Lato,48,-1,5,87,0,0,0,0,0,Black")
    cmdp.define(
        topic='Widgets/Single Value/font-color',
        brief='The font color.',
        dtype='color',
        default=(0, 128, 0, 255))
    cmdp.define(
        topic='Widgets/Single Value/background-color',
        brief='The background color.',
        dtype='color',
        default=(0, 0, 0, 255))

    return {
        'name': 'Single Value',
        'brief': 'Select and display a single value.',
        'class': SingleValueWidget,
        'location': QtCore.Qt.RightDockWidgetArea,
        'sizePolicy': ['expanding', 'minimum'],
    }
