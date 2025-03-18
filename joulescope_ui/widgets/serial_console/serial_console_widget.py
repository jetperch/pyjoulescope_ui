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

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui.source_selector import SourceSelector
from joulescope_ui import N_, register, get_topic_name
from joulescope_ui.styles import styled_widget
from joulescope_ui.widget_tools import CallableAction, settings_action_create, context_menu_show
from pyjoulescope_driver import time64
import datetime


def _str_to_time64(t_str):
    t_datetime = datetime.datetime.fromisoformat(t_str)
    t_time64 = time64.as_time64(t_datetime)
    return t_time64


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
        },
        'plot_index': {
            'dtype': 'int',
            'brief': 'Plot index',
            'default': -1,
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._enable = False
        self._clipboard = None

        self._subscription = None
        self._waveform_extent_subscription = None
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
        self._table.itemSelectionChanged.connect(self._on_selection)
        #self._table.cellClicked.connect(self._on_cell_clicked)
        self._layout.addWidget(self._table)

    def on_pubsub_register(self):
        topic = f'{get_topic_name(self)}/settings/source'
        self.source_selector.on_pubsub_register(self.pubsub, topic)
        self.pubsub.subscribe('registry/app/settings/signal_stream_enable',
                              self._on_global_signal_stream_enable, ['retain', 'pub'])
        view = self.pubsub.query('registry/view/settings/active')
        self.pubsub.subscribe(f'{get_topic_name(view)}/children', self._on_view_update, ['retain', 'pub'])

    def _on_global_signal_stream_enable(self, topic, value):
        self._enable = bool(value)
        if self._enable:
            for idx in range(self._table.rowCount(), -1, -1):
                self._table.removeRow(idx)

    def _waveform_subscribe(self):
        topic = f'{get_topic_name(self.waveform_widget)}/settings/x_extent'
        self._waveform_extent_subscription = self.pubsub.subscribe(topic, self._on_waveform_extent, ['retain', 'pub'])

    def _on_view_update(self, topic, value):
        if self.waveform_widget in value:
            if self._waveform_extent_subscription is None:
                self._waveform_subscribe()
            return
        self.pubsub.unsubscribe(self._waveform_extent_subscription)
        self._waveform_extent_subscription = None
        for obj in value:
            if obj.startswith('WaveformWidget:'):
                self.waveform_widget = obj
                self._waveform_subscribe()
                return
        self.waveform_widget = ''

    def _on_waveform_extent(self, topic, value):
        x0, _ = value
        while self._table.rowCount() and self._row_time64(0) < x0:
            self._table.removeRow(0)

    def _connect(self):
        self.pubsub.unsubscribe(self._subscription)
        source = self.source_selector.resolved()
        if source is not None:
            topic = f'{get_topic_name(source)}/events/signals/S/!data'
            self._subscription = self.pubsub.subscribe(topic, self._on_data, ['pub'])
        self.repaint()

    def _on_data(self, pubsub, topic, value):
        if self._enable:
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
        if self.plot_index >= 0:
            t_time64 = _str_to_time64(timestamp)
            topic = f'{get_topic_name(self.waveform_widget)}/actions/!text_annotation'
            a = {
                'plot_index': self.plot_index,
                'x': t_time64,
                'y': 0,
                'y_mode': 'centered',
                'shape': 0,
                'text': message,
                'text_show': True,
            }
            self.pubsub.publish(topic, ['add', a])

    def _row_time64(self, row_idx):
        t_str = self._table.item(row_idx, 0).text()
        return _str_to_time64(t_str)

    @QtCore.Slot()
    def _on_selection(self):
        t_time64 = []
        for item in self._table.selectedItems():
            if item.column() == 0:
                t_time64.append(self._row_time64(item.row()))
        t_time64.sort()
        topic = f'{get_topic_name(self.waveform_widget)}/actions/!x_markers'
        if len(t_time64) == 0:
            self.pubsub.publish(topic, ['show_single', 'serial_console', None])
        elif len(t_time64) == 1:
            self.pubsub.publish(topic, ['show_single', 'serial_console', t_time64[0]])
        else:
            self.pubsub.publish(topic, ['show_dual', 'serial_console', t_time64[0], t_time64[-1]])

    def _action_copy_selection_to_clipboard(self, time_mode=None):
        items = []
        for item in self._table.selectedItems():
            row_idx = item.row()
            if item.column() == 0:
                items.append([
                    row_idx,
                    item.text(),
                    self._table.item(row_idx, 1).text()
                ])
        items.sort()
        if time_mode in [True, 'on', None]:
            parts = [f'{x[1]} {x[2]}' for x in items]
        else:
            parts = [x[2] for x in items]
        self._clipboard = '\n'.join(parts)
        QtWidgets.QApplication.clipboard().setText(self._clipboard)

    def _action_annotate_signal(self, idx):
        self.plot_index = idx

    def _context_menu(self, pos):
        menu = QtWidgets.QMenu(self)

        copy_menu = menu.addMenu(N_('Copy'))
        copy_group = QtGui.QActionGroup(copy_menu)
        CallableAction(copy_group, N_('Entry'), lambda: self._action_copy_selection_to_clipboard(time_mode=True))
        CallableAction(copy_group, N_('Text only'), lambda: self._action_copy_selection_to_clipboard(time_mode=False))

        annotate_menu = menu.addMenu(N_('Annotate Waveform'))
        annotate_signal_group = QtGui.QActionGroup(annotate_menu)

        def construct_annotate_signal(plot_idx, name):
            CallableAction(annotate_signal_group, name, lambda: self._action_annotate_signal(plot_idx),
                           checkable=True, checked=(self.plot_index == plot_idx))

        construct_annotate_signal(-1, N_('off'))
        waveform_state = self.pubsub.query(f'{get_topic_name(self.waveform_widget)}/settings/state')
        for plot in waveform_state['plots']:
            if plot['enabled']:
                construct_annotate_signal(plot['index'], plot['quantity'])

        self.source_selector.submenu_factory(menu)
        settings_action_create(self, menu)
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self._table.mapToGlobal(pos))
