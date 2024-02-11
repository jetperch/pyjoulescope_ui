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
from joulescope_ui import N_, Metadata
from joulescope_ui.styles import styled_widget
import logging

_LOG_COLOR = {
    logging.CRITICAL: ((255, 255, 255), (255, 64, 64)),
    logging.ERROR:    ((255, 255, 255), (128, 0, 0)),
    logging.WARNING:  ((0, 0, 0), (255, 255, 0)),
    logging.INFO:     ((224, 224, 224), (32, 32, 32)),
    logging.DEBUG:    ((128, 128, 128), (32, 32, 32)),
}
_LOG_BRUSH = dict([(level, (QtGui.QBrush(QtGui.QColor(*fg)), QtGui.QBrush(QtGui.QColor(*bg))))
                   for level, (fg, bg) in _LOG_COLOR.items()])
_LOG_BRUSH_DEFAULT = _LOG_BRUSH[logging.INFO]
_TABLE_COLUMNS = [N_('Timestamp'), N_('Level'), N_('Source'), N_('Message')]


class QLogViewResyncEvent(QtCore.QEvent):
    """An event containing a request for python message processing."""
    EVENT_TYPE = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())
    _instances = []

    def __init__(self, record):
        self.record = record
        QtCore.QEvent.__init__(self, self.EVENT_TYPE)
        QLogViewResyncEvent._instances.append(self)

    def __str__(self):
        return 'QLogViewResyncEvent()'

    def __len__(self):
        return 0


class _Handler(logging.Handler):

    def __init__(self, parent):
        logging.Handler.__init__(self)
        self._parent = parent

    def emit(self, record):
        self._parent.on_log_record(record)


@styled_widget(N_('Log View'))
class LogViewWidget(QtWidgets.QWidget):
    """A developer widget to view the log messages."""

    CAPABILITIES = ['widget@']
    SETTINGS = {
        'test': {
            'dtype': 'bool',
            'brief': 'Enable tools to help develop and test this widget',
            'default': False,
        },
    }
    EVENTS = {
        'msg': Metadata('obj', 'Log message.', flags=['ro', 'skip_undo']),
    }

    def __init__(self, parent=None):
        self.EVENTS = {}
        self._log = logging.getLogger()
        self._handler = None
        self._events = []
        self._items_by_row = []
        super().__init__(parent=parent)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._demo_button = QtWidgets.QPushButton(N_('Demo'))
        self._demo_button.pressed.connect(self._on_demo)
        self._layout.addWidget(self._demo_button)

        self._model = QtGui.QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self._table = QtWidgets.QTableView(self)
        self._table.setObjectName('log_view_table')
        self._table.setModel(self._model)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self._layout.addWidget(self._table)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._table.scrollToBottom)

    def on_log_record(self, record):
        event = QLogViewResyncEvent(record)
        self._events.append(event)
        QtCore.QCoreApplication.postEvent(self, event)

    def event(self, event: QtCore.QEvent):
        if event.type() == QLogViewResyncEvent.EVENT_TYPE:
            event.accept()
            self._events.remove(event)
            record = event.record
            timestamp = QtGui.QStandardItem(record.asctime)
            level = QtGui.QStandardItem(record.levelname)
            source = QtGui.QStandardItem(f'{record.filename}:{record.lineno}')
            msg = QtGui.QStandardItem(record.message)
            row = [timestamp, level, source, msg]
            fg, bg = _LOG_BRUSH.get(record.levelno, _LOG_BRUSH_DEFAULT)
            for e in row:
                e.setData(fg, QtCore.Qt.ForegroundRole)
                e.setData(bg, QtCore.Qt.BackgroundRole)
                e.setEditable(False)
            self._items_by_row.append(row)
            self._model.appendRow(row)
            if self._table.rowViewportPosition(self._model.rowCount() - 1) <= self._table.height():
                self._timer.start(0)
            return True
        else:
            return super().event(event)

    def on_setting_test(self, value):
        self._demo_button.setVisible(value)

    def on_pubsub_register(self):
        self._handler = _Handler(self)
        self._handler.setLevel(logging.DEBUG)
        self._log.addHandler(self._handler)

    def on_pubsub_unregister(self):
        self._log.removeHandler(self._handler)
        self._handler = None

    def _on_demo(self):
        self._log.critical('critical')
        self._log.error('error')
        self._log.warning('warning')
        self._log.info('info')
        self._log.debug('debug')
