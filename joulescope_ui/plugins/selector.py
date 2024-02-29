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


from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui import N_, register
from joulescope_ui.widget_tools import CallableSlotAdapter, settings_action_create, context_menu_show
from joulescope_ui.ui_util import comboBoxConfig
from joulescope_ui.styles import styled_widget


_HEADER = """<html><body>
<p>⚠ POTENTIALLY UNSAFE ⚠</p>
<p>Active plugins have full access to run arbitrary code on this computer.
Make sure you trust a plugin before activating it.</p>  
</body></html>
"""


@register
@styled_widget(N_('Plugins'))
class PluginSelectorWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        header = QtWidgets.QLabel(_HEADER)
        header.setWordWrap(True)
        self._layout.addWidget(header)

        grid_scroll = QtWidgets.QScrollArea()
        grid_scroll.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        grid_scroll.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._layout.addWidget(grid_scroll)

        grid_widget = QtWidgets.QWidget()
        grid_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._grid = QtWidgets.QGridLayout(grid_widget)
        grid_scroll.setWidget(grid_widget)

        self._grid.addWidget(QtWidgets.QLabel(N_('Name'), self), 0, 0, 1, 1)
        self._grid.addWidget(QtWidgets.QLabel(N_('Version'), self), 0, 1, 1, 1)
        self._grid.addWidget(QtWidgets.QLabel(N_('Active'), self), 0, 2, 1, 1)
        spacer = QtWidgets.QSpacerItem(0, 0,  QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addSpacerItem(spacer)

        self._monitor = MonitorWidget()
        self._monitor.changed.connect(self._on_monitor_changed)
        self._layout.addWidget(self._monitor)

    def on_pubsub_register(self):
        self.pubsub.subscribe('registry/plugins/settings/available', self._update, ['pub', 'retain'])
        self.pubsub.subscribe('registry/plugins/settings/active', self._update, ['pub', 'retain'])
        self._update_monitor_options()

    def _update_monitor_options(self):
        values = self.pubsub.query('registry/plugins/settings/active')
        value = self.pubsub.query('registry/plugins/settings/monitor')
        self._monitor.update(values, value)

    def _update(self, value):
        plugins = self.pubsub.query('registry/plugins/settings/available')
        for row in range(1, self._grid.rowCount()):
            for column in range(0, self._grid.columnCount()):
                w = self._grid.itemAtPosition(row, column).widget()
                self._grid.removeWidget(w)
                w.deleteLater()

        def on_checkbox_toggled_factory(plugin_name):
            def fn(checked):
                if checked:
                    self.pubsub.publish('registry/plugins/actions/!load', plugin_name)
                else:
                    self.pubsub.publish('registry/plugins/actions/!unload', plugin_name)
            return fn

        for idx, name in enumerate(sorted(plugins.keys())):
            row = idx + 1
            info = plugins[name]
            self._grid.addWidget(QtWidgets.QLabel(name), row, 0, 1, 1)
            self._grid.addWidget(QtWidgets.QLabel(info['version']), row, 1, 1, 1)
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(info['state'] == 'loaded')
            adapter = CallableSlotAdapter(checkbox, on_checkbox_toggled_factory(name))
            checkbox.toggled.connect(adapter.slot)
            self._grid.addWidget(checkbox, row, 2, 1, 1)

        self._update_monitor_options()

    def _on_monitor_changed(self, txt):
        self.pubsub.publish('registry/plugins/settings/monitor', txt)

    def mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            settings_action_create(self, menu)
            context_menu_show(menu, event)


class MonitorWidget(QtWidgets.QWidget):

    changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        self._enable = QtWidgets.QCheckBox()
        self._enable.toggled.connect(self._on_enable)
        layout.addWidget(self._enable)
        layout.addWidget(QtWidgets.QLabel(N_('Monitor')))
        self._options = QtWidgets.QComboBox()
        self._options.currentTextChanged.connect(self._on_option)
        layout.addWidget(self._options)

    def _on_enable(self, checked):
        self._options.setEnabled(checked)
        if checked and self._options.count():
            txt = self._options.currentText()
        else:
            txt = ''
        self._on_option(txt)

    def _on_option(self, txt):
        self.changed.emit(txt)

    def update(self, values, value):
        if value in values:
            comboBoxConfig(self._options, values, value)
            self._enable.setChecked(True)
        else:
            comboBoxConfig(self._options, values)
            if not value:
                self._enable.setChecked(False)
