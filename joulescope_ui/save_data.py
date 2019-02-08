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

"""Display and update application preferences"""

from joulescope_ui.save_data_dialog import Ui_Form
from PySide2 import QtWidgets, QtGui
import os
import logging


log = logging.getLogger(__name__)


class SaveDataDialog(QtWidgets.QDialog):

    def __init__(self, path):
        QtWidgets.QDialog.__init__(self)
        self._path = path
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.saveButton.pressed.connect(self.accept)
        self.ui.cancelButton.pressed.connect(self.reject)
        self.ui.filenameLineEdit.textChanged.connect(self.on_filename_text_edit)
        self.ui.filenameSelectButton.pressed.connect(self.on_filename_select_button)

    def on_filename_select_button(self):
        filename, select_mask = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Joulescope Data', self._path, 'Joulescope Data (*.csv)')
        log.info('save filename selected: %s', filename)
        filename = str(filename)
        self.ui.filenameLineEdit.setText(filename)
        self.ui.saveButton.setEnabled(True)

    def on_filename_text_edit(self, text):
        self.ui.saveButton.setEnabled(True)

    def _field_flags(self):
        d = {}
        for name, widget in self._fields:
            d[name] = widget.isChecked()
        return d

    def exec_(self):
        if QtWidgets.QDialog.exec_(self) == 1:
            return {
                'filename': str(self.ui.filenameLineEdit.text()),
                'contents': str(self.ui.contentsComboBox.currentText()),
            }
        else:
            return None
