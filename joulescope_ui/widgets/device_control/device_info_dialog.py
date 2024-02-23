# 2023 Jetperch LLC
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
import logging


class DeviceInfoDialog(QtWidgets.QDialog):

    def __init__(self, info, pubsub):
        self._log = logging.getLogger(__name__)
        self._log.debug('create start')
        self._widgets = []
        parent = pubsub.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setObjectName("device_info_dialog")
        self.setWindowTitle('Device Information')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self._layout = QtWidgets.QVBoxLayout(self)

        w = QtWidgets.QWidget(self)
        w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._widgets.append(w)
        self._layout.addWidget(w)
        self._grid = QtWidgets.QGridLayout(w)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(3)

        row = 0

        for key, value in info.items():
            if isinstance(value, dict):
                w = QtWidgets.QLabel(key, self)
                self._grid.addWidget(w, row, 0, 1, 3)
                self._widgets.append(w)
                row += 1
                for inner_key, inner_value in value.items():
                    w = QtWidgets.QLabel(inner_key, self)
                    self._grid.addWidget(w, row, 1, 1, 1)
                    self._widgets.append(w)
                    w = QtWidgets.QLabel(inner_value, self)
                    self._grid.addWidget(w, row, 2, 1, 1)
                    self._widgets.append(w)
                    row += 1
            else:
                w = QtWidgets.QLabel(key, self)
                self._grid.addWidget(w, row, 0, 1, 2)
                self._widgets.append(w)
                w = QtWidgets.QLabel(value, self)
                self._grid.addWidget(w, row, 2, 1, 2)
                self._widgets.append(w)
                row += 1

        self._spacer = QtWidgets.QSpacerItem(1, 1,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

        self.finished.connect(self._on_finish)

        self.resize(self.sizeHint())
        self._log.info('open')
        self.open()

    @QtCore.Slot()
    def _on_finish(self):
        self._log.info('finish')
        self.close()
