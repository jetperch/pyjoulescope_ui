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


from joulescope_ui import N_
from PySide6 import QtCore, QtWidgets


class UniqueStringsWidget(QtWidgets.QWidget):

    changed = QtCore.Signal(object)  # the list of selected values

    def __init__(self, parent, options=None):
        """A widget for selecting an ordered list of strings.

        :param parent: The parent QObject or None.
        :param options: The list of values option lists given as:
            [[value, user-meaningful-value {, alternate-value1 ...}], ...]
            If the values are not constrained, provide None.
        """
        self._value = []
        self._options = options
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setObjectName('UniqueStringsWidget')

        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setObjectName('UniqueStringsWidgetLayout')
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._option_to_str = {}
        self._str_to_option = {}

        if self._options is None:
            self._line_edit = QtWidgets.QLineEdit(self)
            self._line_edit.textChanged.connect(self._on_line_edit)
            self._layout.addWidget(self._line_edit, 0, 0, 1, 1)
        else:
            self._available_label = QtWidgets.QLabel(N_('Available'), self)
            self._available = _DraggableListWidget(self)
            for option in self._options:
                s = option[0] if len(option) == 1 else option[1]
                self._option_to_str[option[0]] = s
                for z in option:
                    self._str_to_option[z] = option[0]
                self._available.addItem(s)
            self._selected_label = QtWidgets.QLabel(N_('Selected'), self)
            self._selected = _DraggableListWidget(self)

            self._available.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            self._selected.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            self._layout.addWidget(self._available_label, 0, 0, 1, 1)
            self._layout.addWidget(self._selected_label, 0, 1, 1, 1)
            self._layout.addWidget(self._available, 1, 0, 1, 1)
            self._layout.addWidget(self._selected, 1, 1, 1, 1)

            self._selected.changed.connect(self._on_changed)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = [self._option_to_str[z] for z in v]
        if self._options is None:
            block_state = self._line_edit.blockSignals(True)
            self._line_edit.setText(','.join(self._value))
            self._line_edit.blockSignals(block_state)
        else:
            block_state_available = self._available.blockSignals(True)
            block_state_selected = self._selected.blockSignals(True)
            selected = dict([(self._selected.item(idx).text(), None) for idx in range(self._selected.count())])
            available = [self._available.item(idx).text() for idx in range(self._available.count())]
            self._selected.clear()
            try:
                for z in self._value:
                    self._selected.addItem(z)
                    if z in selected:
                        selected.pop(z)
                    else:
                        idx = available.index(z)
                        available.pop(idx)
                        self._available.takeItem(idx)
                for z in selected.keys():
                    self._available.addItem(z)
            except Exception:
                self._rebuild()
            self._available.blockSignals(block_state_available)
            self._selected.blockSignals(block_state_selected)

    def _rebuild(self):
        self._selected.clear()
        self._available.clear()
        values = [self._option_to_str[option[0]] for option in self._options]
        for v in self._value:
            self._selected.addItem(v)
            try:
                values.remove(v)
            except KeyError:
                pass
        for v in values:
            self._available.addItem(v)

    @QtCore.Slot(str)
    def _on_line_edit(self, txt):
        self._value = txt.split(',')
        self.changed.emit(self._value)

    @QtCore.Slot()
    def _on_changed(self):
        self._value = [self._str_to_option[self._selected.item(idx).text()] for idx in range(self._selected.count())]
        self.changed.emit(self._value)


class _DraggableListWidget(QtWidgets.QListWidget):
    changed = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setDragDropMode(QtWidgets.QListWidget.DragDrop)

    def dropEvent(self, event):
        source = event.source()
        if isinstance(source, _DraggableListWidget):
            event.setDropAction(QtCore.Qt.MoveAction)
            super().dropEvent(event)
            if source != self:
                source.takeItem(source.currentRow())
                source.changed.emit()
            self.changed.emit()
