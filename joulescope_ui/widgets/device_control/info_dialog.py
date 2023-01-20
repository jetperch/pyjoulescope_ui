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


from PySide6 import QtWidgets
from joulescope_ui import pubsub_singleton
import logging


class InfoDialog(QtWidgets.QDialog):

    dialogs = []

    def __init__(self, info):
        self._log = logging.getLogger(__name__)
        self._log.debug('create start')
        self._widgets = []
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setObjectName("device_info_dialog")

        self._layout = QtWidgets.QGridLayout()
        self.setLayout(self._layout)

        row = 0

        for outer_key, outer_value in info.items():
            w = QtWidgets.QLabel(outer_key, self)
            self._layout.addWidget(w, row, 0, 1, 3)
            self._widgets.append(w)

            row += 1
            for key, value in outer_value.items():
                w = QtWidgets.QLabel(key, self)
                self._layout.addWidget(w, row, 1, 1, 1)
                self._widgets.append(w)
                w = QtWidgets.QLabel(value, self)
                self._layout.addWidget(w, row, 2, 1, 1)
                self._widgets.append(w)
                row += 1

        self.resize(self.sizeHint())
        self.setWindowTitle('Device Information')
        self.finished.connect(self._on_finish)

        self._log.info('open')
        self.open()
        InfoDialog.dialogs.append(self)

    def _on_finish(self):
        self.close()
        self._log.info('finish')
        InfoDialog.dialogs.remove(self)
