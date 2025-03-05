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
from joulescope_ui.source_selector import SourceSelector
from joulescope_ui import N_, register, get_topic_name
from joulescope_ui.styles import styled_widget
from joulescope_ui.widget_tools import CallableAction, settings_action_create, context_menu_show
from pyjoulescope_driver import time64
import datetime


@register
@styled_widget(N_('Serial Console'))
class SerialConsoleWidget(QtWidgets.QWidget):

    CAPABILITIES = ['widget@']
    SETTINGS = {
        'source': {
            'dtype': 'str',
            'brief': N_('The signal sample stream source.'),
            'default': None,
        },
        'waveform_widget': {
            'dtype': 'str',
            'brief': N_('The target waveform widget.'),
            'default': '',
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self._subscription = None
        self.source_selector = SourceSelector(self, 'signal_stream')
        self.source_selector.source_changed.connect(self._on_source_changed)
        self.source_selector.resolved_changed.connect(self._on_resolved_changed)

        self.setObjectName('serial_console_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._table = QtWidgets.QTableWidget(rowCount=0, columnCount=2, parent=self)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setHorizontalHeaderLabels([N_('Time'), N_('Message')])
        self._table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        hdr = self._table.verticalHeader()
        hdr.setVisible(False)
        hdr.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._layout.addWidget(self._table)

    def on_pubsub_register(self):
        topic = f'{get_topic_name(self)}/settings/source'
        self.source_selector.on_pubsub_register(self.pubsub, topic)
        view = self.pubsub.query('registry/view/settings/active')
        self.pubsub.subscribe(f'{get_topic_name(view)}/children', self._on_view_update, ['retain', 'pub'])

    def _on_view_update(self, topic, value):
        if self.waveform_widget in value:
            return
        for obj in value:
            if obj.startswith('WaveformWidget:'):
                self.waveform_widget = obj
                return
        self.waveform_widget = ''

    def _connect(self):
        self.pubsub.unsubscribe(self._subscription)
        source = self.source_selector.resolved()
        if source is not None:
            topic = f'{get_topic_name(source)}/events/signals/S/!data'
            self._subscription = self.pubsub.subscribe(topic, self._on_data, ['pub'])
        self.repaint()

    def _on_data(self, pubsub, topic, value):
        self._add(value['time_str'], value['message'])

    @QtCore.Slot()
    def _on_source_changed(self, value):
        self.repaint()

    @QtCore.Slot()
    def _on_resolved_changed(self, value):
        self._connect()

    def _add(self, timestamp, message):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(timestamp)))
        self._table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(message)))

    @QtCore.Slot()
    def _on_cell_clicked(self, row, column):
        t_str = self._table.item(row, 0).text()
        t_datetime = datetime.datetime.fromisoformat(t_str)
        t_time64 = time64.as_time64(t_datetime)

        print(f'row={row} column={column} => {t_time64} : {self.waveform_widget}')

    def _context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        self.source_selector.submenu_factory(menu)
        settings_action_create(self, menu)
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self._table.mapToGlobal(pos))
