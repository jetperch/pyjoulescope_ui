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
import atexit
import logging


class DriverWrapper:

    def __init__(self, pubsub):
        self._pubsub = pubsub
        self._log = logging.getLogger(__name__)
        self._log.info('initialize start')
        self.driver = Driver()
        self.driver.log_level = 'INFO'
        self._finalize_fn = self.finalize
        self._on_device_add_fn = self._on_device_add
        self._on_device_remove_fn = self._on_device_remove
        atexit.register(self._finalize_fn)
        self.driver.subscribe('@/!add', 'pub', self._on_device_add_fn)
        self.driver.subscribe('@/!remove', 'pub', self._on_device_remove_fn)
        self._log.info('initialize done')

    def __del__(self):
        self.finalize()

    def finalize(self):
        if self.driver is not None:
            self._log.info('finalize start')
            atexit.unregister(self._finalize_fn)
            d, self.driver = self.driver, None
            d.finalize()
            self._log.info('finalize done')

    def _on_device_add(self, topic, value):
        if value in self.devices:
            return
        if 'js220' in value:
            pass
        elif 'js110' in value:
            pass
        else:
            self._log.info('Unsupported device: %s', value)
            return

    def _on_device_remove(self, topic, value):
        d = self.devices.pop(value, None)
        if d is not None:
            d.close()
