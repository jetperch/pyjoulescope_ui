# Copyright 2022-2023 Jetperch LLC
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
from joulescope_ui import get_unique_id, get_topic_name, Metadata, N_
from joulescope_ui.capabilities import CAPABILITIES
from .jsdrv_stream_buffer import JsdrvStreamBuffer
from .js110 import Js110
from .js220 import Js220
from .js220_updater import Js220Updater
import logging


class JsdrvWrapper:
    """The singleton Joulescope driver wrapper.

    Provide access to Joulescope devices including the JS220 and JS110.
    This class wraps a pyjoulescope_driver.Driver instance and relays
    messages between the UI's pubsub instance and the jsdrv pubsub
    instance.
    """
    CAPABILITIES = []
    EVENTS = {
        '!publish': Metadata('obj', 'Resync to UI publish thread',
                             flags=['ro', 'hide', 'tmp', 'skip_undo']),
    }
    SETTINGS = {
        'log_level': {
            'dtype': 'str',
            'brief': N_('The pyjoulescope_driver log level.'),
            'options': [
                ['off', 'off'],
                ['emergency', 'emergency'],
                ['alert', 'alert'],
                ['critical', 'critical'],
                ['warning', 'warning'],
                ['notice', 'notice'],
                ['info', 'info'],
                ['debug1', 'debug1'],
                ['debug2', 'debug2'],
                ['debug3', 'debug3'],
                ['debug3', 'all'],
            ],
            'default': 'info',
        },
        'device_ids': {
            'dtype': 'obj',  # list of unique_id
            'brief': 'The connected jsdrv devices',
            'default': None,
            'flags': ['hide', 'tmp', 'noinit', 'skip_undo']
        }
    }

    def __init__(self):
        self.CAPABILITIES = [CAPABILITIES.DEVICE_FACTORY]
        self._log = logging.getLogger(__name__)
        self.driver = None
        self.devices = {}
        self._ui_subscriptions = []
        self._driver_subscriptions = []
        self._stream_buffers = {}

    def on_pubsub_register(self, pubsub):
        topic = get_topic_name(self)
        self._log.info('on_pubsub_register start %s', topic)
        self.devices = {}
        self.device_ids = []
        self.driver = Driver()
        self._ui_subscribe(f'{topic}/settings/log_level', self._on_log_level, ['retain', 'pub'])
        self._ui_subscribe(f'{topic}/events/!publish', self._on_event_publish, ['pub'])
        self.driver.subscribe('@', 'pub', self._on_driver_publish)
        for d in self.driver.device_paths():
            self._log.info('on_pubsub_register add %s', d)
            self._on_driver_publish('@/!add', d)
        self._log.info('on_pubsub_register done %s', topic)

    def on_pubsub_unregister(self):
        for d in list(self.devices.keys()):
            self._on_device_remove(d)

    def on_action_mem__add(self, value):
        self._log.info('mem add %s', value)
        mem_id = int(value)
        if mem_id <= 0 or mem_id >= 16:
            raise ValueError(f'Invalid mem_id {value}')
        b = JsdrvStreamBuffer(self, mem_id)
        self._stream_buffers[mem_id] = b
        unique_id = f'JsdrvStreamBuffer:{mem_id:03d}'
        self.pubsub.register(b, unique_id=unique_id)

    def on_action_mem_remove(self, value):
        self._log.info('mem remove %s', value)
        mem_id = int(value)
        if mem_id <= 0 or mem_id >= 16:
            raise ValueError(f'Invalid mem_id {value}')
        if mem_id not in self._stream_buffers:
            return
        b = self._stream_buffers.pop(mem_id)
        self.pubsub.unregister(b)

    def clear(self):
        while len(self._ui_subscriptions):
            topic, fn, flags = self._ui_subscribe.pop()
            self.pubsub.unsubscribe(topic, fn, flags)
        while len(self._driver_subscriptions):
            topic, fn, flags = self._driver_subscriptions.pop()
            self.driver.unsubscribe(topic, fn)

    def _ui_subscribe(self, topic: str, update_fn: callable, flags=None):
        self._ui_subscriptions.append((topic, update_fn, flags))
        self.pubsub.subscribe(topic, update_fn, flags)

    def _driver_subscribe(self, topic: str, flags, fn, timeout=None):
        self._driver_subscriptions.append((topic, fn))
        self.driver.subscribe(topic, flags, fn, timeout)

    def _on_log_level(self, value):
        self.driver.log_level = value

    def on_action_finalize(self):
        self._log.info('finalize')
        while len(self.devices):
            _, device = self.devices.popitem()
            device.finalize()
            self.pubsub.unregister(device)
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
        _, model, serial_number = value.split('/')
        unique_id = f'{model.upper()}-{serial_number}'
        if value in self.devices:
            return
        if '/js220/' in value:
            cls = Js220
        elif '/js110/' in value:
            cls = Js110
        elif '/&js220/' in value:
            unique_id = unique_id[1:] + '-UPDATER'
            cls = Js220Updater
        else:
            self._log.info('Unsupported device: %s', value)
            return
        self._log.info('_on_device_add %s', unique_id)
        d = cls(self, value)
        self.pubsub.register(d, unique_id)
        self.devices[value] = d
        self.device_ids = sorted([d.unique_id for d in self.devices.values()])

    def _on_device_remove(self, value):
        d = self.devices.pop(value, None)
        if d is not None:
            self._log.info('_on_device_remove %s', get_unique_id(d))
            topic = get_topic_name(d)
            self.pubsub.publish(f'{topic}/actions/!finalize', None)
            self.pubsub.unregister(d)
            self.device_ids = sorted([d.unique_id for d in self.devices.values()])
