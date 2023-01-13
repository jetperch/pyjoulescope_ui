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

from PySide6 import QtCore, QtGui, QtWidgets
import logging
from joulescope_ui import N_, register, tooltip_format, pubsub_singleton
from joulescope_ui.styles import styled_widget


class Js220CtrlWidget(QtWidgets.QWidget):

    def __init__(self, parent, unique_id):
        self._parent = parent
        self._unique_id = unique_id
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._top_widget = QtWidgets.QWidget(self)
        self._top_layout = QtWidgets.QHBoxLayout()
        self._top_layout.setContentsMargins(0, 0, 0, 0)


        self._device_label = QtWidgets.QLabel(unique_id)

        self._top_layout.addWidget(self._device_label)
        self._top_widget.setLayout(self._top_layout)
        self._layout.addWidget(self._top_widget)

        self._main = QtWidgets.QWidget(self)
        self._layout.addWidget(self._main)

        self.setLayout(self._layout)

