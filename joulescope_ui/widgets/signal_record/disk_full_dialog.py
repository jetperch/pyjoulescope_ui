# Copyright 2023 Jetperch LLC
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

from joulescope_ui import N_
from PySide6 import QtCore, QtWidgets


_MESSAGE = N_('The disk is full')


class DiskFullDialog(QtWidgets.QDialog):
    """Display disk full notification."""

    def __init__(self, pubsub, paths):
        paths_msg = '<br/>'.join(paths)
        html = f'<html><body><p>{_MESSAGE}</p><p>{paths_msg}</p></body></html>'
        parent = pubsub.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setObjectName('disk_monitor_dialog')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._label = QtWidgets.QLabel(html, self)
        self._label.setWordWrap(True)
        self._layout.addWidget(self._label)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

        self.resize(600, 400)
        self.setWindowTitle(_MESSAGE)
        self.finished.connect(self._on_finish)

        self.open()

    @QtCore.Slot()
    def _on_finish(self):
        self.close()
