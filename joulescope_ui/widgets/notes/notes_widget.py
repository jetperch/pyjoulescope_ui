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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import N_, register
from joulescope_ui.styles import styled_widget


@register
@styled_widget(N_('Notes'))
class NotesWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']
    SETTINGS = {
        'value': {
            'dtype': 'str',
            'brief': N_('The notes value.'),
            'default': '<html><body></body></html>',
        },
    }

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('notes_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._edit = QtWidgets.QTextEdit(self)
        self._edit.textChanged.connect(self._on_text_changed)
        self._layout.addWidget(self._edit)

    @QtCore.Slot()
    def _on_text_changed(self):
        self.value = self._edit.toHtml()

    def on_pubsub_register(self):
        self._edit.setHtml(self.value)
