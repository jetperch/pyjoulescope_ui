# Copyright 2022 Jetperch LLC
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

from PySide6 import QtWidgets, QtCore
from joulescope_ui import register, N_
from joulescope_ui.widget_tools import settings_action_create, context_menu_show
from joulescope_ui.styles import styled_widget


@register
@styled_widget(N_('Example'))
class ExampleWidget(QtWidgets.QWidget):
    """A simple example widget."""

    CAPABILITIES = ['widget@']

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._menu = None
        self._layout = QtWidgets.QVBoxLayout(self)

        self._label1 = QtWidgets.QLabel()
        self._label1.setObjectName('label1')
        self._label1.setText('Label 1')
        self._layout.addWidget(self._label1)

        self._label2 = QtWidgets.QLabel()
        self._label2.setObjectName('label2')
        self._label2.setText('Label 2')
        self._layout.addWidget(self._label2)

        self._label3 = QtWidgets.QLabel()
        self._label3.setObjectName('label3')
        self._label3.setText('Label 3')
        self._layout.addWidget(self._label3)

        self.mousePressEvent = self._on_mousePressEvent

    def _on_mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton:
            pass
        elif event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            settings_action_create(self, menu)
            context_menu_show(menu, event)
