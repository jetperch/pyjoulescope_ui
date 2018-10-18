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
from . import joulescope_rc
import logging
log = logging.getLogger(__name__)


FONT_SIZES = [24, 32, 40, 48, 56, 64]


STYLE_FSTR = """
QWidget {{ background-color : black; }}
QLabel {{ color : green; font-weight: bold; font-size: {font_size}pt; }}
"""


class SingleValueWidget(QtWidgets.QWidget):

    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self._font_index = 2
        self._meter_source = None
        self._meter_value_source = None
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
        self.fieldComboBox.addItem("")
        self.fieldComboBox.addItem("")
        self.fieldComboBox.addItem("")
        self.fieldComboBox.addItem("")
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

    def _font_size_delta(self, delta=None):
        delta = 0 if delta is None else int(delta)
        idx = self._font_index + delta
        idx = max(idx, 0)
        idx = min(idx, len(FONT_SIZES) - 1)
        self._font_index = idx
        font_size = FONT_SIZES[self._font_index]
        self.value_widget.setStyleSheet(STYLE_FSTR.format(font_size=font_size))

    def source(self, src):
        self._meter_source = src
        self.update()

    def update(self):
        if self._meter_value_source is not None:
            self._meter_value_source.on_update.disconnect(self.on_update)
            self._meter_value_source = None
        if self._meter_source is None:
            return
        value = self.fieldComboBox.currentText().lower()
        self._meter_value_source = self._meter_source.values[value]
        self._meter_value_source.on_update.connect(self.on_update)

    @QtCore.Slot(object, str)
    def on_update(self, values, units):
        idx = self.statisticComboBox.currentIndex()
        self.valueLabel.setText(values[idx])
        self.unitLabel.setText(f"<html>&nbsp;{units}&nbsp;</html>")

    @QtCore.Slot(int)
    def on_field_changed(self, index):
        self.update()

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.fieldLabel.setText(_translate("Form", "Field"))
        self.fieldComboBox.setItemText(0, _translate("Form", "Current"))
        self.fieldComboBox.setItemText(1, _translate("Form", "Voltage"))
        self.fieldComboBox.setItemText(2, _translate("Form", "Power"))
        self.fieldComboBox.setItemText(3, _translate("Form", "Energy"))
        self.statisticLabel.setText(_translate("Form", "Statistic"))
        self.statisticComboBox.setItemText(0, _translate("Form", "Mean"))
        self.statisticComboBox.setItemText(1, _translate("Form", "Standard Deviation"))
        self.statisticComboBox.setItemText(2, _translate("Form", "Minimum"))
        self.statisticComboBox.setItemText(3, _translate("Form", "Maximum"))
        self.statisticComboBox.setItemText(4, _translate("Form", "Peak-to-Peak"))
        self.valueLabel.setText(_translate("Form", "0.000"))
        self.unitLabel.setText(_translate("Form", " mA "))

