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
from joulescope_ui import N_
from joulescope_ui.styles import styled_widget


_TOPIC_TABLE_COLUMNS = [N_('Count'), N_('Topic')]
_VALUE_TABLE_COLUMNS = [N_('Topic'), N_('Value')]


@styled_widget(N_('Publish Spy'))
class PublishSpyWidget(QtWidgets.QWidget):
    """A developer widget to spy on PubSub publish events."""

    CAPABILITIES = ['widget@']
    SETTINGS = {
    }

    def __init__(self, parent=None):
        self._timer = None
        self._data_display = {}
        self._data_capture = {}
        self._items = []
        super().__init__(parent=parent)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._top = QtWidgets.QWidget(self)
        self._top_layout = QtWidgets.QHBoxLayout(self._top)
        self._capture = QtWidgets.QPushButton(N_('Capture'))
        self._capture.setCheckable(True)
        self._capture.toggled.connect(self._on_capture_toggled)
        self._top_layout.addWidget(self._capture)
        self._mode_combobox = QtWidgets.QComboBox()
        self._mode_combobox.addItem(N_('Topics'))
        self._mode_combobox.addItem(N_('Values'))
        self._top_layout.addWidget(self._mode_combobox)
        self._top_spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._top_layout.addItem(self._top_spacer)
        self._pps = QtWidgets.QLabel()
        self._top_layout.addWidget(self._pps)
        self._layout.addWidget(self._top)

        self._model = QtGui.QStandardItemModel(self)
        self._table = QtWidgets.QTableView(self)
        self._table.setObjectName('publish_spy_table')
        self._table.setModel(self._model)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self._layout.addWidget(self._table)

    @property
    def _enabled(self):
        return self._capture.isChecked()

    def _on_capture_toggled(self, checked):
        if self._enabled:
            self._start()
        else:
            self._stop()

    def _on_value(self, topic, value):
        if not self._enabled:
            return
        if isinstance(self._data_capture, dict):
            if topic not in self._data_capture:
                self._data_capture[topic] = []
            self._data_capture[topic].append(str(value))
        else:
            self._data_capture.append((topic, str(value)))

    def _on_topics(self):
        self._model.setHorizontalHeaderLabels(_TOPIC_TABLE_COLUMNS)
        z = [(len(value), key) for key, value in self._data_display.items()]
        count = sum([x for x, _ in z])
        self._pps.setText(f'<html>{len(z)} unique per second<br/>{count} total per second</html>')
        z = sorted(z, reverse=True)

        for count, topic in sorted(z, reverse=True):
            row = [QtGui.QStandardItem(str(count)), QtGui.QStandardItem(topic)]
            for e in row:
                e.setEditable(False)
            self._items.append(row)
            self._model.appendRow(row)

    def _on_values(self):
        self._model.setHorizontalHeaderLabels(_VALUE_TABLE_COLUMNS)
        self._pps.setText(f'<html>{len(self._data_display)} total per second</html>')
        for topic, value in self._data_display:
            row = [QtGui.QStandardItem(topic), QtGui.QStandardItem(value)]
            for e in row:
                e.setEditable(False)
            self._items.append(row)
            self._model.appendRow(row)

    @QtCore.Slot()
    def _on_timer(self):
        if not self._enabled:
            return
        self._model.clear()
        self._items = []
        self._data_display, self._data_capture = self._data_capture, None
        if isinstance(self._data_display, dict):
            self._on_topics()
        else:
            self._on_values()
        if 0 == self._mode_combobox.currentIndex():
            self._data_capture = {}
        else:
            self._data_capture = []

    def _start(self):
        self._stop()
        self._data_capture = {}
        self._timer = QtCore.QTimer(self)
        self._timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(1000)
        self.pubsub.subscribe('', self._on_value, ['pub'])

    def _stop(self):
        self.pubsub.unsubscribe('', self._on_value)
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def on_pubsub_register(self):
        self._capture.setChecked(True)

    def on_pubsub_unregister(self):
        self._capture.setChecked(False)
