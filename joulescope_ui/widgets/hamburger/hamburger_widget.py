# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtWidgets
from joulescope_ui import register, N_
from joulescope_ui.widget_tools import CallableSlotAdapter


_MENU_ITEMS = [
    ['getting_started', N_('Getting Started'), ['registry/help_html/actions/!show', 'getting_started']],
    ['changelog', N_('Changelog'), ['registry/help_html/actions/!show', 'changelog']],
    ['credits', N_('Credits'), ['registry/help_html/actions/!show', 'credits']],
    ['about', N_('About'), ['registry/help_html/actions/!show', 'about']],
]

@register
class HamburgerWidget(QtWidgets.QWidget):
    CAPABILITIES = []

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._widgets = []
        self.setObjectName('hamburger_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        for obj_name, user_name, action in _MENU_ITEMS:
            self._add_button(obj_name, user_name, action)

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

    def _add_button(self, obj_name, user_name, action):
        b = QtWidgets.QPushButton(self)
        b.setObjectName(obj_name)
        b.setText(user_name)
        self._layout.addWidget(b)
        adapter = CallableSlotAdapter(b, lambda: self.pubsub.publish(*action))
        b.clicked.connect(adapter.slot)
        self._widgets.append(b)
        return b
