# Copyright 2023 Jetperch LLC
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

from .locale import N_
from joulescope_ui import pubsub_singleton, CAPABILITIES, get_topic_name
import logging


class App:
    """Singleton application instance for global settings.

    These settings are persistent and do not depend upon the selected view.
    However, they are dependent upon the selected profile / session.
    For profile-invariant global settings, use "common/settings" subtopics.
    """

    SETTINGS = {
        'name': {
            'dtype': 'str',
            'brief': N_('The name for this widget.'),
            'default': N_('app'),
        },
        'device_active': {
            'dtype': 'str',
            'brief': N_('The unique_id for the primary active device.'),
            'default': None,
        },
        'device_default': {
            'dtype': 'str',
            'brief': N_('The unique_id for the default device used on the next restart.'),
            'default': None,
        },
    }

    def __init__(self):
        self._on_devices_fn = self._on_devices
        self._devices: dict[str] = []
        self._device_default: str = None
        self._device_active: str = None
        self._log = logging.getLogger(__name__)

    def register(self):
        pubsub_singleton.register(self, 'app')
        pubsub_singleton.subscribe(f'registry_manager/capabilities/{CAPABILITIES.DEVICE_OBJECT}/list',
                                   self._on_devices_fn, ['pub', 'retain'])
        return self

    def on_setting_device_active(self, value):
        if hasattr(self, 'unique_id'):
            self._log.info('Set active device: %s', value)
            self._device_active = value

    def on_setting_device_default(self, value):
        self._device_default = value

    def _on_devices(self, value):
        self._devices = list(value)
        topic = get_topic_name(self.unique_id)
        if not len(value):
            pubsub_singleton.publish(f'{topic}/settings/device_active', None)
            return
        if self._device_default is not None and self._device_default in value:
            pubsub_singleton.publish(f'{topic}/settings/device_active', self._device_default)
        else:
            device = value[0]
            pubsub_singleton.publish(f'{topic}/settings/device_active', device)
            pubsub_singleton.publish(f'{topic}/settings/device_default', device)
