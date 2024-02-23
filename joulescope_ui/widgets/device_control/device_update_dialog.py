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
from joulescope_ui import N_, CAPABILITIES, get_topic_name
from joulescope_ui.pubsub_proxy import PubSubProxy
from joulescope_ui.styles import styled_widget
from joulescope_ui.devices.device_update import is_device_update_available, is_js220_update_available
import logging


_COLUMNS = [
    N_('Update'),
    N_('Device'),
    N_('Version'),
    N_('Progress'),
]
_STATUS = {
    None: '',
    'scan': N_('Device scan in progress.'),
    'no_updates': N_('No updates available.'),
    'updates': '<html><body>' + N_("""\
        <p>Before starting updates, ensure that Joulescopes are plugged directly
        into a USB port on the host computer.</p>  
        <p>Do not use any USB hubs, docks or adapters.</p>""") + '</body></html>',
    'in_progress': N_('Device update is in progress.  Please wait.'),
    'complete': N_('Device update completed.'),
}
_SELECT_ALL = N_('Select all')
_SELECT_NONE = N_('Select none')
_CANCEL = N_('Cancel')
_OK = N_('OK')
_UPDATE = N_('Update')
_DEVICE_TOPIC = f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list'
_PROGRESS_TOPICS = [
    'registry/JS220_Updater/events/!progress',
]
_SCAN_DELAY_MS = 2000


@styled_widget(N_('Device Update'))
class DeviceUpdateDialog(QtWidgets.QDialog):
    """Device firmware/FPGA update control and status widget."""

    def __init__(self, parent, pubsub, done_action):
        self.pubsub = PubSubProxy(pubsub)
        self._done_action = done_action
        self._devices = {}
        self._log = logging.getLogger(__name__)
        self._devices_update_list = []
        self._devices_update_map = None
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.resize(600, 400)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._grid_widget = QtWidgets.QWidget(self)
        self._grid_layout = QtWidgets.QGridLayout(self._grid_widget)
        self._layout.addWidget(self._grid_widget)
        self._header = [QtWidgets.QLabel(column, self._grid_widget) for column in _COLUMNS]

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        self._status_set('scan')
        self._layout.addWidget(self._status)

        self._buttons = QtWidgets.QWidget(self)
        self._buttons_layout = QtWidgets.QHBoxLayout(self._buttons)
        self._select_all = QtWidgets.QPushButton(_SELECT_ALL, self)
        self._select_all.pressed.connect(self._on_select_all)
        self._select_none = QtWidgets.QPushButton(_SELECT_NONE, self)
        self._select_none.pressed.connect(self._on_select_none)
        self._select_all.setVisible(False)
        self._select_none.setVisible(False)
        self._cancel = QtWidgets.QPushButton(_CANCEL, self)
        self._cancel.pressed.connect(self.reject)
        self._ok = QtWidgets.QPushButton(_OK, self)
        self._ok.pressed.connect(self._on_ok)
        self._buttons_layout.addWidget(self._select_all)
        self._buttons_layout.addWidget(self._select_none)
        self._bspacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._buttons_layout.addItem(self._bspacer)
        self._buttons_layout.addWidget(self._cancel)
        self._buttons_layout.addWidget(self._ok)
        self._layout.addWidget(self._buttons)

        self.finished.connect(self._on_finish)
        self._clear()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.update_devices)
        self._timer.setSingleShot(True)
        self._timer.start(_SCAN_DELAY_MS)

        self.pubsub.subscribe(_DEVICE_TOPIC, self._on_device_list, ['pub', 'retain'])
        for topic in _PROGRESS_TOPICS:
            self.pubsub.subscribe(topic, self._on_progress, ['pub'])
        self.open()

    @QtCore.Slot()
    def _on_select_all(self):
        self._log.info('select all')
        for widgets in self._devices.values():
            widgets[0].setChecked(True)

    @QtCore.Slot()
    def _on_select_none(self):
        self._log.info('select none')
        for widgets in self._devices.values():
            widgets[0].setChecked(False)

    def _status_set(self, status):
        self._status.setText(_STATUS[status])

    @QtCore.Slot()
    def _on_ok(self):
        if self._ok.text() == _OK:
            self.accept()
            return
        self._devices_update_list = []
        self._devices_update_map = {}
        for row in range(1, self._grid_layout.rowCount()):
            checkbox = self._grid_layout.itemAtPosition(row, 0).widget()
            if checkbox.isChecked():
                name = self._grid_layout.itemAtPosition(row, 1).widget().text()
                self._devices_update_map[name] = {
                    'name': name,
                    'status': 'ready',
                    'order': len(self._devices_update_list),
                    'progress': self._grid_layout.itemAtPosition(row, 3).widget(),
                }
                self._devices_update_list.append(name)
        self._ok.setVisible(False)
        self._cancel.setVisible(False)
        self._status_set('in_progress')
        self._update_next()

    def _update_next(self, completed=None):
        if completed is not None:
            device = self._devices_update_map[completed]
            device['status'] = 'done'
            device['progress'].setValue(1000)
        if not len(self._devices_update_list):
            self._devices_update_map = None
            self._timer.start(_SCAN_DELAY_MS)
            self._status_set('complete')
            return
        device_name = self._devices_update_list.pop(0)
        self._log.info('Device update %s', device_name)
        device = self._devices_update_map[device_name]
        device['status'] = 'in_progress'
        self.pubsub.publish(f'{get_topic_name(device_name)}/actions/!device_update', None)

    def _on_progress(self, value):
        progress = value['progress']
        device_name = value['device_id']
        progress_value = int(1000 * progress)
        self._devices_update_map[device_name]['progress'].setValue(progress_value)
        if progress >= 1.0:
            self._update_next(device_name)

    def _clear(self):
        # Remove all widgets from grid
        while self._grid_layout.count():
            self._grid_layout.takeAt(0)
        for column, widget in enumerate(self._header):
            self._grid_layout.addWidget(widget, 0, column, 1, 1)

    @QtCore.Slot()
    def update_devices(self):
        if self._devices_update_map is not None:
            return  # skip refresh while updating devices
        self._log.info('update devices')
        self._ok.setVisible(True)
        self._cancel.setVisible(True)
        self._clear()
        device_list = self.pubsub.query(_DEVICE_TOPIC)

        # Delete removed devices
        value_set = set(device_list)
        removed = [d for d in self._devices.keys() if d not in value_set]
        for device in removed:
            widgets = self._devices.pop(device)
            for widget in widgets[:-1]:
                widget.deleteLater()

        # Create added devices
        added = [d for d in device_list if d not in self._devices]
        for device in added:
            details = {}
            checkbox = QtWidgets.QCheckBox(self._grid_widget)
            name = QtWidgets.QLabel(device, self._grid_widget)
            if device.startswith('JS220-'):
                details = self.pubsub.query(f'{get_topic_name(device)}/settings/update_available', default={})
                checkbox.setChecked(is_js220_update_available(details))
            version = QtWidgets.QLabel(self._grid_widget)
            version.setWordWrap(True)
            progress = QtWidgets.QProgressBar(self._grid_widget)
            progress.setRange(0, 1000)
            progress.setValue(0)
            self._devices[device] = [checkbox, name, version, progress, details]

        for row, (device, widgets) in enumerate(sorted(self._devices.items())):
            available = False
            checkbox, name, version, progress, details = widgets
            info = self.pubsub.query(f'{get_topic_name(device)}/settings/info', default={})
            if info['model'] == 'JS220':
                details = self.pubsub.query(f'{get_topic_name(device)}/settings/update_available', default={})
                version_str = '<br/>'.join([f'{key}:{v[0]}→{v[1]}' for key, v in details.items()])
                version_str = f'<html><body>{version_str}</body></html>'
                available = is_js220_update_available(details)
            elif info['model'] == 'JS110':
                version_str = ', '.join([f'{key}={v}' for key, v in info['version'].items()])
            else:
                version_str = 'unsupported'
            version.setText(version_str)

            for column, widget in enumerate(widgets[:-1]):
                self._grid_layout.addWidget(widget, row + 1, column, 1, 1)
                widget.setEnabled(available)
            checkbox.setVisible(available)

        if is_device_update_available():
            self._cancel.setVisible(True)
            self._ok.setText(_UPDATE)
            self._select_all.setVisible(True)
            self._select_none.setVisible(True)
            self._status_set('updates')
        else:
            self._cancel.setVisible(False)
            self._select_all.setVisible(False)
            self._select_none.setVisible(False)
            self._ok.setText(_OK)
            self._status_set('no_updates')

    def _is_unchanged(self, devices):
        self._log.info(f'devices:\n{sorted(devices)}\n{sorted(self._devices.keys())}')
        if len(devices) != len(self._devices):
            return False
        return sorted(devices) == sorted(self._devices.keys())

    def _on_device_list(self, value):
        if self._devices_update_map is not None:
            return  # skip refresh while updating devices
        if self._is_unchanged(value):
            return
        self._clear()
        self._timer.start(_SCAN_DELAY_MS)
        self._status_set('scan')

    @QtCore.Slot()
    def _on_finish(self):
        self._log.info('finish')
        self.pubsub.unsubscribe_all()
        if self._done_action is not None:
            self.pubsub.publish(*self._done_action)
        self.close()

    @staticmethod
    def on_show(pubsub, topic, value):
        info, done_action = value
        DeviceUpdateDialog(pubsub, info, done_action)
