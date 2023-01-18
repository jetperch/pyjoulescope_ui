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
from joulescope_ui import get_unique_id, get_topic_name, Metadata
from joulescope_ui.capabilities import CAPABILITIES
from .js110 import Js110
from .js220 import Js220
import logging


class JsdrvWrapper:
    """Joulescope driver."""
    CAPABILITIES = [CAPABILITIES.DEVICE_FACTORY]
    EVENTS = {
        '!publish': Metadata('obj', 'Resync to UI publish thread')
    }

    def __init__(self):
        self._parent = None
        self._log = logging.getLogger(__name__)
        self.pubsub = None
        self._topic = None
        self.driver = None
        self.subscriptions: dict[str, list[callable]] = {}
        self.devices = {}
        self._on_driver_publish_fn = self._on_driver_publish
        self._on_event_publish_fn = self._on_event_publish

    def on_pubsub_register(self, pubsub):
        topic = get_topic_name(self)
        self._log.info('on_pubsub_register start %s', topic)
        pubsub.register(Js220)
        pubsub.register(Js110)
        self.pubsub = pubsub
        self._topic = topic
        self.driver = Driver()
        self.driver.log_level = 'INFO'
        self.pubsub.subscribe(f'{topic}/events/!publish', self._on_event_publish_fn, ['pub'])
        self.driver.subscribe('@', 'pub', self._on_driver_publish_fn)
        for d in self.driver.device_paths():
            self._log.info('on_pubsub_register add %s', d)
            self._on_driver_publish('@/!add', d)
        self._log.info('on_pubsub_register done %s', topic)

    def on_action_finalize(self):
        self._log.info('finalize')
        while len(self.devices):
            _, device = self.devices.popitem()
            device.finalize()
        d, self.driver = self.driver, None
        if d is not None:
            d.finalize()

    def _on_driver_publish(self, topic, value):
        """Callback from the pyjoulescope_driver pubsub instance.

        :param topic: The pyjoulescope_driver topic.
        :param topic: The pyjoulescope_driver value.

        Resynchronizes to _on_event_publish
        """
        t = f'{get_topic_name(self)}/events/!publish'
        self.pubsub.publish(t, (topic, value))

    def _on_event_publish(self, value):
        topic, value = value
        if topic[0] == '@':
            if topic == '@/!add':
                self._on_device_add(value)
            elif topic == '@/!remove':
                self._on_device_remove(value)

    def _on_device_add(self, value):
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
        self._log.info('_on_device_add %s', unique_id)
        d = cls(self, value)
        self.pubsub.register(d, unique_id)
        if d.name is None:
            d.name = unique_id
        self.devices[value] = d
        self.pubsub.publish(f'{get_topic_name(d)}/actions/!open', None)

    def _on_device_remove(self, value):
        d = self.devices.pop(value, None)
        if d is not None:
            self._log.info('_on_device_remove %s', get_unique_id(d))
            topic = get_topic_name(d)
            self.pubsub.publish(f'{topic}/actions/!close', None)
            self.pubsub.unregister(d)
