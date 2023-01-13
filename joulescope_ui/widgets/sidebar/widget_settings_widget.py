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


@register
class WidgetSettingsWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout()
        self._label = QtWidgets.QLabel()
        self._label.setWordWrap(True)
        self._label.setText('<html><body><p>WidgetSettingsWidget</p><p>Lorem ipsum dolor sit amet, consectetuer adipiscing elit.</p></body></html>')
        self._layout.addWidget(self._label)
        self.setLayout(self._layout)
