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

"""
Test joulescope_ui.widgets.device_control.device_update_dialog.

ci/uitest/test_device_firmware.py drives this dialog by object name and status
text, so these tests pin both.
"""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from joulescope_ui import pubsub_singleton
from joulescope_ui.devices.device_update import DEVICE_LIST_TOPIC
from joulescope_ui.widgets.device_control.device_update_dialog import DeviceUpdateDialog

_DEVICE = 'JS220-000001'
_TOPIC = f'registry/{_DEVICE}/settings'
_CHECK_TOPIC = 'registry/app/settings/device_update_check'


class TestDeviceUpdateDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance()
        if cls._app is None:
            cls._app = QtWidgets.QApplication([])

    def setUp(self):
        self.pubsub = pubsub_singleton
        self.pubsub.topic_add(f'{_TOPIC}/info', dtype='obj', brief='info',
                              default={'model': 'JS220'})
        self.pubsub.topic_add(f'{_TOPIC}/update_available', dtype='obj', brief='fw',
                              default=None)
        self.pubsub.publish(DEVICE_LIST_TOPIC, [_DEVICE])
        self._check_added = _CHECK_TOPIC not in self.pubsub
        if self._check_added:
            self.pubsub.topic_add(_CHECK_TOPIC, dtype='bool', brief='check', default=True)
        self.dialog = None

    def tearDown(self):
        if self.dialog is not None:
            self.dialog.done(0)
            self.dialog.deleteLater()
        self.pubsub.publish(DEVICE_LIST_TOPIC, [])
        self.pubsub.topic_remove(f'registry/{_DEVICE}')
        if self._check_added:
            self.pubsub.topic_remove(_CHECK_TOPIC)

    def _dialog(self, update_available):
        self.pubsub.publish(f'{_TOPIC}/update_available', update_available)
        self.dialog = DeviceUpdateDialog(None, self.pubsub, None)
        self.dialog.update_devices()
        return self.dialog

    def _text(self, name):
        return self.dialog.findChild(QtWidgets.QWidget, name).text()

    def test_object_names(self):
        d = self._dialog(None)
        self.assertEqual('device_update_dialog', d.objectName())
        for name in ['device_update_ok', 'device_update_cancel', 'device_update_status']:
            self.assertIsNotNone(d.findChild(QtWidgets.QWidget, name), name)

    def test_update_available_none(self):
        # A driver without embedded firmware reports None; this used to raise.
        self._dialog(None)
        self.assertEqual('No updates available.', self._text('device_update_status'))

    def test_update_available(self):
        self._dialog({'fw': ['1.2.0', '1.2.1'], 'fpga': ['1.2.1', '1.2.1']})
        self.assertEqual('Update', self._text('device_update_ok'))

    def test_no_update(self):
        self._dialog({'fw': ['1.2.1', '1.2.1'], 'fpga': ['1.2.1', '1.2.1']})
        self.assertEqual('OK', self._text('device_update_ok'))
        self.assertEqual('No updates available.', self._text('device_update_status'))

    def test_update_complete_status(self):
        self._dialog({'fw': ['1.2.0', '1.2.1'], 'fpga': ['1.2.1', '1.2.1']})
        self.dialog.findChild(QtWidgets.QWidget, 'device_update_ok').click()
        self.dialog._on_progress({'device_id': _DEVICE, 'progress': 1.0})
        self.assertEqual('Device update completed.', self._text('device_update_status'))


if __name__ == '__main__':
    unittest.main()
