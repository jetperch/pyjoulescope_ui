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
from joulescope_ui.locale import locale_get, locale_set, LOCALES
from joulescope_ui import pubsub_singleton, N_


_PROMPT = N_('Select a language')
_WARNING = N_('The application will automatically close when you change the locale.')


class LocaleDialog(QtWidgets.QDialog):
    """Display the language selection dialog."""

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setObjectName("language_dialog")
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._label = QtWidgets.QLabel(_PROMPT)
        self._layout.addWidget(self._label)

        self._codes = [x[0] for x in LOCALES]
        locale_now = locale_get()
        if locale_now is None:
            locale_now = 'en'
        self._locale = QtWidgets.QComboBox()
        for locale in LOCALES:
            self._locale.addItem(locale[-1])
            if locale[0] == locale_now:
                self._locale.setCurrentIndex(self._locale.count() - 1)
        self._layout.addWidget(self._locale)

        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._warning = QtWidgets.QLabel(_WARNING)
        self._layout.addWidget(self._warning)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

        self.resize(600, 400)
        self.setWindowTitle(_PROMPT)
        self.finished.connect(self._on_finish)
        self.open()

    @QtCore.Slot()
    def _on_finish(self, value):
        idx = self._locale.currentIndex()
        self.close()
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            locale = self._codes[idx]
            locale_set(locale)
            pubsub_singleton.publish('registry/ui/actions/!close', None)
