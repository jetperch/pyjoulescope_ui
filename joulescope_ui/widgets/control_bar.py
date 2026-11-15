# Copyright 2026 Jetperch LLC
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

"""A widget control bar of buttons and comboboxes bound to settings.

Each control publishes its setting through the parent widget's
setting_publish(name, value).  The widget calls :meth:`ControlBar.value_set`
from its on_setting_* handlers, so the controls always mirror the settings.
"""

from PySide6 import QtCore, QtWidgets


class ControlBar(QtWidgets.QWidget):
    """The control bar base.

    :param parent: The parent widget, which implements setting_publish.
    :param prefix: The object name prefix for the bar and its controls.
    :param tooltips: The map of control name to tooltip.
    """

    def __init__(self, parent, prefix, tooltips):
        self._parent = parent
        self._prefix = prefix
        self._tooltips = tooltips
        self._combos = {}
        self._toggles = {}
        super().__init__(parent)
        self.setObjectName(f'{prefix}_control')
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self._layout = layout

    def button_add(self, name, text, on_click):
        """Add a push button that calls on_click()."""
        b = QtWidgets.QPushButton(text, self)
        b.setObjectName(f'{self._prefix}_{name}')
        b.setToolTip(self._tooltips.get(name, ''))
        b.clicked.connect(lambda checked=False: on_click())
        self._layout.addWidget(b)
        return b

    def toggle_add(self, name, text):
        """Add a checkable button bound to the bool setting name."""
        b = QtWidgets.QPushButton(text, self)
        b.setObjectName(f'{self._prefix}_{name}')
        b.setCheckable(True)
        b.setToolTip(self._tooltips.get(name, ''))
        b.toggled.connect(lambda checked: self._parent.setting_publish(name, bool(checked)))
        self._layout.addWidget(b)
        self._toggles[name] = b
        return b

    def combo_add(self, name, options=None):
        """Add a combobox.

        :param name: The control name.
        :param options: The list of (value, label) for a combobox bound to
            setting name, or None for a combobox the caller connects.
        """
        combo = QtWidgets.QComboBox(self)
        combo.setObjectName(f'{self._prefix}_{name}')
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setToolTip(self._tooltips.get(name, ''))
        self._layout.addWidget(combo)
        self._combos[name] = combo
        if options is not None:
            for value, label in options:
                combo.addItem(label, value)
            combo.activated.connect(self._factory(name))
        return combo

    def _factory(self, name):
        def fn(index):
            self._parent.setting_publish(name, self._combos[name].itemData(index))
        return fn

    @staticmethod
    def _select(combo, value):
        idx = combo.findData(value)
        if idx >= 0:
            with QtCore.QSignalBlocker(combo):
                combo.setCurrentIndex(idx)

    def value_set(self, name, value):
        """Update a control to match its setting."""
        if name in self._toggles:
            b = self._toggles[name]
            with QtCore.QSignalBlocker(b):
                b.setChecked(bool(value))
        elif name in self._combos:
            self._select(self._combos[name], value)

    def items_set(self, name, items, value):
        """Replace a combobox's items.

        :param name: The combobox name.
        :param items: The list of (value, label).
        :param value: The selected value.
        """
        combo = self._combos[name]
        with QtCore.QSignalBlocker(combo):
            combo.clear()
            for v, label in items:
                combo.addItem(label, v)
        self._select(combo, value)

    def labels_set(self, name, labels):
        """Update the item labels, keeping values.

        :param name: The combobox name.
        :param labels: The map of value to label.
        """
        combo = self._combos[name]
        for idx in range(combo.count()):
            label = labels.get(combo.itemData(idx))
            if label is not None:
                combo.setItemText(idx, label)
        combo.updateGeometry()  # the size hint changed, but the layout does not know
