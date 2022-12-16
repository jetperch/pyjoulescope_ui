# Copyright 2022 Jetperch LLC
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


from pyjoulescope_driver import Driver
from joulescope_ui.capabilities import CAPABILITIES
from .js110 import Js110
from .js220 import Js220
import atexit
import logging


class JsdrvWrapper:
    """Joulescope driver."""
    CAPABILITIES = [CAPABILITIES.DEVICE_FACTORY]

    def __init__(self):
        self._parent = None
        self._log = logging.getLogger(__name__)
        self.pubsub = None
        self._topic = None
        self.driver = None
        self.devices = {}
        self._on_device_add_fn = self._on_device_add
        self._on_device_remove_fn = self._on_device_remove
        self._finalize_fn = self._finalize

    def on_pubsub_register(self, pubsub, topic):
        self._log.info('on_pubsub_register start %s', topic)
        pubsub.register(Js220)
        pubsub.register(Js110)
        self.pubsub = pubsub
        self._topic = topic
        self.driver = Driver()
        self.driver.log_level = 'INFO'
        atexit.register(self._finalize_fn)
        self.driver.subscribe('@/!add', 'pub', self._on_device_add_fn)
        self.driver.subscribe('@/!remove', 'pub', self._on_device_remove_fn)
        for d in self.driver.device_paths():
            self._on_device_add('@/!add', d)
        self._log.info('on_pubsub_register done %s', topic)

    def on_pubsub_unregister(self):
        atexit.unregister(self._finalize_fn)
        self._finalize()

    def __del__(self):
        self._finalize()

    def _finalize(self):
        while len(self.devices):
            _, device = self.devices.popitem()
            device.close()
        d, self.driver = self.driver, None
        if d is not None:
            d.finalize()

    def _on_device_add(self, topic, value):
        if value in self.devices:
            return
        if 'js220' in value:
            cls = Js220
        elif 'js110' in value:
            pass  # cls = DeviceJs110
        else:
            self._log.info('Unsupported device: %s', value)
            return
        _, model, serial_number = value.split('/')
        unique_id = f'{model.upper()}-{serial_number}'
        d = cls(self, value)
        topic = self.pubsub.register(d, unique_id)
        self.devices[value] = d
        d.open()

    def _on_device_remove(self, topic, value):
        d = self.devices.pop(value, None)
        if d is not None:
            d.close()
