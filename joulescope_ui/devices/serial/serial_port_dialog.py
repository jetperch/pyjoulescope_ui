# Copyright 2026 Jetperch LLC
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

"""Dialog for managing external serial port connections."""

from joulescope_ui import N_, pubsub_singleton, get_topic_name
from PySide6 import QtCore, QtWidgets
import serial.tools.list_ports
import logging


_BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
_DEFAULT_BAUD = 115200

_log = logging.getLogger(__name__)

_MANAGER_TOPIC = 'registry/ext_serial'


class ExternalSerialPortDialog(QtWidgets.QDialog):
    """Dialog for configuring external serial port connections."""

    def __init__(self, parent=None):
        ui_parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=ui_parent)
        self.setObjectName('external_serial_port_dialog')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(N_('External Serial Ports'))

        self._layout = QtWidgets.QVBoxLayout(self)

        # --- Port list table ---
        self._table = QtWidgets.QTableWidget(0, 5, self)
        self._table.setHorizontalHeaderLabels([
            N_('Port'), N_('Name'), N_('Baud Rate'), N_('Status'), N_(''),
        ])
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self._layout.addWidget(self._table)

        # --- Add port section ---
        add_group = QtWidgets.QGroupBox(N_('Add Port'), self)
        add_layout = QtWidgets.QHBoxLayout(add_group)

        self._port_combo = QtWidgets.QComboBox(self)
        self._port_combo.setMinimumWidth(150)
        self._port_combo.setEditable(True)
        add_layout.addWidget(QtWidgets.QLabel(N_('Port:'), self))
        add_layout.addWidget(self._port_combo)

        self._refresh_btn = QtWidgets.QPushButton(N_('Refresh'), self)
        self._refresh_btn.clicked.connect(self._refresh_ports)
        add_layout.addWidget(self._refresh_btn)

        self._name_edit = QtWidgets.QLineEdit(self)
        self._name_edit.setPlaceholderText(N_('Friendly name'))
        add_layout.addWidget(QtWidgets.QLabel(N_('Name:'), self))
        add_layout.addWidget(self._name_edit)

        self._baud_combo = QtWidgets.QComboBox(self)
        self._baud_combo.setEditable(True)
        for baud in _BAUD_RATES:
            self._baud_combo.addItem(str(baud), baud)
        self._baud_combo.setCurrentText(str(_DEFAULT_BAUD))
        add_layout.addWidget(QtWidgets.QLabel(N_('Baud:'), self))
        add_layout.addWidget(self._baud_combo)

        self._auto_open_check = QtWidgets.QCheckBox(N_('Auto-open'), self)
        add_layout.addWidget(self._auto_open_check)

        self._add_btn = QtWidgets.QPushButton(N_('Add'), self)
        self._add_btn.clicked.connect(self._on_add)
        add_layout.addWidget(self._add_btn)

        self._layout.addWidget(add_group)

        # --- Close button ---
        self._close_btn = QtWidgets.QPushButton(N_('Close'), self)
        self._close_btn.clicked.connect(self.accept)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self._close_btn)
        self._layout.addLayout(btn_layout)

        self.resize(700, 400)
        self.finished.connect(self._on_finish)

        self._port_combo.currentIndexChanged.connect(self._on_port_selected)
        self._refresh_ports()
        self._refresh_table()
        self.open()

    def _refresh_ports(self):
        self._port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in sorted(ports, key=lambda x: x.device):
            label = f'{p.device} - {p.description}' if p.description and p.description != 'n/a' else p.device
            self._port_combo.addItem(label, p.device)

    def _on_port_selected(self, index):
        if index < 0:
            return
        ports = serial.tools.list_ports.comports()
        device = self._port_combo.currentData()
        for p in ports:
            if p.device == device:
                desc = p.description if p.description and p.description != 'n/a' else ''
                if desc:
                    self._name_edit.setText(desc)
                break

    def _refresh_table(self):
        try:
            manager = pubsub_singleton.query(f'{_MANAGER_TOPIC}/instance')
        except KeyError:
            return
        ports = pubsub_singleton.query(f'{_MANAGER_TOPIC}/settings/ports') or []
        self._table.setRowCount(0)
        for cfg in ports:
            self._add_table_row(cfg, manager.is_port_open(cfg['port']))

    def _add_table_row(self, cfg, is_open):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(cfg['port']))
        self._table.setItem(row, 1, QtWidgets.QTableWidgetItem(cfg.get('name', '')))
        self._table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(cfg.get('baud_rate', _DEFAULT_BAUD))))
        status = N_('Open') if is_open else N_('Closed')
        self._table.setItem(row, 3, QtWidgets.QTableWidgetItem(status))

        # Button cell with Open/Close and Remove
        btn_widget = QtWidgets.QWidget()
        btn_layout = QtWidgets.QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(2, 2, 2, 2)

        port = cfg['port']
        if is_open:
            close_btn = QtWidgets.QPushButton(N_('Close'), self)
            close_btn.clicked.connect(lambda checked=False, p=port: self._on_close_port(p))
            btn_layout.addWidget(close_btn)
        else:
            open_btn = QtWidgets.QPushButton(N_('Open'), self)
            open_btn.clicked.connect(lambda checked=False, p=port: self._on_open_port(p))
            btn_layout.addWidget(open_btn)

        remove_btn = QtWidgets.QPushButton(N_('Remove'), self)
        remove_btn.clicked.connect(lambda checked=False, p=port: self._on_remove_port(p))
        btn_layout.addWidget(remove_btn)

        self._table.setCellWidget(row, 4, btn_widget)

    def _on_add(self):
        port = self._port_combo.currentData()
        if port is None:
            port = self._port_combo.currentText().strip()
        if not port:
            return
        name = self._name_edit.text().strip() or port
        baud_rate = self._baud_combo.currentData()
        if baud_rate is None:
            try:
                baud_rate = int(self._baud_combo.currentText().strip())
            except ValueError:
                QtWidgets.QMessageBox.warning(self, N_('Error'), N_('Invalid baud rate'))
                return
        auto_open = self._auto_open_check.isChecked()

        cfg = {
            'port': port,
            'baud_rate': baud_rate,
            'name': name,
            'auto_open': auto_open,
        }
        topic = f'{_MANAGER_TOPIC}/actions/!port_add'
        pubsub_singleton.publish(topic, cfg)
        pubsub_singleton.process()
        self._refresh_table()

    def _on_open_port(self, port):
        try:
            topic = f'{_MANAGER_TOPIC}/actions/!port_open'
            pubsub_singleton.publish(topic, port)
            pubsub_singleton.process()
        except Exception as ex:
            _log.warning('Failed to open port %s: %s', port, ex)
            QtWidgets.QMessageBox.warning(self, N_('Error'), str(ex))
        self._refresh_table()

    def _on_close_port(self, port):
        topic = f'{_MANAGER_TOPIC}/actions/!port_close'
        pubsub_singleton.publish(topic, port)
        pubsub_singleton.process()
        self._refresh_table()

    def _on_remove_port(self, port):
        topic = f'{_MANAGER_TOPIC}/actions/!port_remove'
        pubsub_singleton.publish(topic, port)
        pubsub_singleton.process()
        self._refresh_table()

    @QtCore.Slot()
    def _on_finish(self):
        self.close()
