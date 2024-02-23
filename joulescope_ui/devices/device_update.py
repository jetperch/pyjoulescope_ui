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

from joulescope_ui import pubsub_singleton, get_topic_name, CAPABILITIES
from PySide6 import QtCore


DEVICE_LIST_TOPIC = f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list'
_TIMER_DELAY_MS = 2000


def is_js220_update_available(update_available):
    if update_available is None or not len(update_available):
        return False
    for key, (v_now, v_available) in update_available.items():
        v_now = [int(x) for x in v_now.split('.')]
        v_available = [int(x) for x in v_available.split('.')]
        if v_now < v_available:
            return True
    return False


def is_device_update_available():
    if not pubsub_singleton.query('registry/app/settings/device_update_check'):
        return False
    device_list = pubsub_singleton.query(DEVICE_LIST_TOPIC)
    for device in device_list:
        info = pubsub_singleton.query(f'{get_topic_name(device)}/settings/info', default={})
        if info['model'] == 'JS220':
            update_info = pubsub_singleton.query(f'{get_topic_name(device)}/settings/update_available', default=None)
            if is_js220_update_available(update_info):
                return True
        else:
            pass  # device does not support firmware updates
    return False


class DeviceUpdate(QtCore.QObject):
    """Wait until device list is stable for 2 seconds.

    :param parent: The parent QObject.
    :param pubsub: The pubsub instance.
    """

    enabled = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject, pubsub):
        self.pubsub = pubsub
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

    def enable(self):
        self.pubsub.subscribe(DEVICE_LIST_TOPIC, self._on_device_list, ['pub', 'retain'])
        self._timer.start(_TIMER_DELAY_MS)

    @QtCore.Slot()
    def _on_timer(self):
        self.pubsub.unsubscribe(DEVICE_LIST_TOPIC, self._on_device_list)
        self._timer.stop()
        self.enabled.emit()

    def _on_device_list(self):
        self._timer.start(_TIMER_DELAY_MS)

    def is_available(self):
        return is_device_update_available()
