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
import weakref
from joulescope_ui import joulescope_rc
from joulescope.units import unit_prefix
import logging
log = logging.getLogger(__name__)


FONT_SIZES = [24, 32, 40, 48, 56, 64]


STYLE_FSTR = """
QWidget {{ background-color : black; }}
QLabel {{ color : green; font-weight: bold; font-size: {font_size}pt; }}
"""

STATISTICS_TRANSLATE = {
    'Mean': lambda s: s['μ'],
    'Standard Deviation': lambda s: np.sqrt(s['σ2']),
    'Minimum': lambda s: s['min'],
    'Maximum': lambda s: s['max'],
    'Peak-to-Peak': lambda s: s['p2p'],
}


class SingleValueWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._font_index = 2
        self._statistics = {}
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
        self.fieldComboBox.currentIndexChanged.connect(self.on_field_changed)
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.fieldComboBox)
        self.statisticLabel = QtWidgets.QLabel(self.widget)
        self.statisticLabel.setObjectName("statisticLabel")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.statisticLabel)
        self.statisticComboBox = QtWidgets.QComboBox(self.widget)
        self.statisticComboBox.setObjectName("statisticComboBox")
        self.statisticComboBox.addItem("")
        self.statisticComboBox.addItem("")
        self.statisticComboBox.addItem("")
        self.statisticComboBox.addItem("")
        self.statisticComboBox.addItem("")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.statisticComboBox)
        self.horizontalLayout.addWidget(self.widget)
        self.spacerItem = QtWidgets.QSpacerItem(44, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(self.spacerItem)
        self.value_widget = QtWidgets.QWidget(self)
        self.value_widget.setObjectName("ValueWidget")
        self._font_size_delta()
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.value_widget)
        self.horizontalLayout_2.setContentsMargins(-1, 0, -1, 0)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.valueLabel = QtWidgets.QLabel(self.value_widget)
        self.valueLabel.setLineWidth(0)
        self.valueLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.valueLabel.setObjectName("valueLabel")
        self.horizontalLayout_2.addWidget(self.valueLabel)
        self.unitLabel = QtWidgets.QLabel(self.value_widget)
        self.unitLabel.setLineWidth(0)
        self.unitLabel.setObjectName("unitLabel")
        self.horizontalLayout_2.addWidget(self.unitLabel)
        self.horizontalLayout.addWidget(self.value_widget)

        self.retranslateUi()
        self._cmdp.subscribe('Device/#state/statistics', weakref.WeakMethod(self._on_device_statistics),
                             update_now=True)

    def _font_size_delta(self, delta=None):
        delta = 0 if delta is None else int(delta)
        idx = self._font_index + delta
        idx = max(idx, 0)
        idx = min(idx, len(FONT_SIZES) - 1)
        self._font_index = idx
        font_size = FONT_SIZES[self._font_index]
        self.value_widget.setStyleSheet(STYLE_FSTR.format(font_size=font_size))

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
            for field in fields:
                self.fieldComboBox.addItem(field)
        field = self.fieldComboBox.currentText()
        if field in self._statistics['signals']:
            self.statisticComboBox.setEnabled(True)
            stat = self.statisticComboBox.currentText()
            s = self._statistics['signals'][field]['statistics']
            units = self._statistics['signals'][field]['units']
            value = STATISTICS_TRANSLATE[stat](s)
        elif field in self._statistics['accumulators']:
            self.statisticComboBox.setEnabled(False)
            v = self._statistics['accumulators'][field]['value']
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

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.fieldLabel.setText(_translate("Form", "Field"))
        self.statisticLabel.setText(_translate("Form", "Statistic"))
        self.statisticComboBox.setItemText(0, _translate("Form", "Mean"))
        self.statisticComboBox.setItemText(1, _translate("Form", "Standard Deviation"))
        self.statisticComboBox.setItemText(2, _translate("Form", "Minimum"))
        self.statisticComboBox.setItemText(3, _translate("Form", "Maximum"))
        self.statisticComboBox.setItemText(4, _translate("Form", "Peak-to-Peak"))
        self.valueLabel.setText(_translate("Form", "0.000"))
        self.unitLabel.setText(_translate("Form", " mA "))


def widget_register(cmdp):
    return {
        'name': 'Single Value',
        'brief': 'Select and display a single value.',
        'class': SingleValueWidget,
        'location': QtCore.Qt.RightDockWidgetArea,
    }
