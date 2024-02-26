# Copyright 2024 Jetperch LLC
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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_


class SafeModeDialog(QtWidgets.QDialog):
    """The safe mode operation selection dialog."""

    def __init__(self, parent=None):
        self._result = None
        super().__init__(parent=parent)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self.setObjectName("safe_mode_dialog")
        self._layout = QtWidgets.QVBoxLayout(self)

        self._options = QtWidgets.QLabel(N_('Options'), self)
        self._layout.addWidget(self._options)

        self._config_load = QtWidgets.QCheckBox(N_('Load configuration on start'), self)
        self._layout.addWidget(self._config_load)
        self._config_save = QtWidgets.QCheckBox(N_('Save configuration on exit'), self)
        self._layout.addWidget(self._config_save)
        self._config_clear = QtWidgets.QCheckBox(N_('Clear configuration on exit'), self)
        self._layout.addWidget(self._config_clear)

        self._action = QtWidgets.QLabel(N_('Action'))
        self._layout.addWidget(self._action)
        self._action_normal = QtWidgets.QRadioButton(N_('Normal'), self)
        self._layout.addWidget(self._action_normal)
        self._action_report_issue = QtWidgets.QRadioButton(N_('Report issue'), self)
        self._layout.addWidget(self._action_report_issue)
        self._action_close = QtWidgets.QRadioButton(N_('Close'), self)
        self._layout.addWidget(self._action_close)

        self._action_group = QtWidgets.QButtonGroup(self)
        self._action_group.setExclusive(True)
        self._action_group.addButton(self._action_normal)
        self._action_group.addButton(self._action_report_issue)
        self._action_group.addButton(self._action_close)
        self._action_normal.setChecked(True)

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

        self.resize(600, 400)
        self.setWindowTitle(N_('Safe Mode Configuration'))
        self.finished.connect(self._on_finish)

        self.open()

    @QtCore.Slot()
    def _on_finish(self):
        if self._action_close.isChecked():
            action = 'close'
        elif self._action_report_issue.isChecked():
            action = 'report_issue'
        else:
            action = 'normal'
        self._result = {
            'configuration_load': self._config_load.isChecked(),
            'configuration_save': self._config_save.isChecked(),
            'configuration_clear': self._config_clear.isChecked(),
            'action': action,
        }
        self.close()

    def config(self):
        return self._result


def safe_mode_dialog():
    dialog = SafeModeDialog()
    dialog.exec()
    config = dialog.config()
    return config
