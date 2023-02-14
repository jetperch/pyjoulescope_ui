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
import copy

from pyjoulescope_driver import Driver
from joulescope_ui import get_unique_id, get_topic_name, Metadata, N_
from joulescope_ui.capabilities import CAPABILITIES
from .js110 import Js110
from .js220 import Js220
import logging
import time


_MEM_RESPONSE_TOPIC = '_/mem/!rsp'
_MEM_CLEANUP_PERIOD_S = 1.0   # process memory cleanup with this period (seconds)
_MEM_EXPIRE_INTERVAL_S = 2.0  # expire entries older than this duration (seconds)


class JsdrvWrapper:
    """Joulescope driver."""
    CAPABILITIES = [CAPABILITIES.DEVICE_FACTORY]
    EVENTS = {
        '!publish': Metadata('obj', 'Resync to UI publish thread')
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
            'default': 'notice',
        },
    }

    def __init__(self):
        self._parent = None
        self._log = logging.getLogger(__name__)
        self.pubsub = None
        self._topic = None
        self.driver = None
        self.devices = {}
        self._ui_subscriptions = []
        self._driver_subscriptions = []
        self._mem = {}
        self._mem_signals_free = list(range(1, 256))
        self._mem_req_fwd = {}  # (pubsub_rsp_topic, pubsub_rsp_id): device_rsp_id
        self._mem_req_bwd = {}  # device_rsp_id: (pubsub_rsp_topic, pubsub_rsp_id)
        self._mem_req_time = {}  # device_rsp_id: time_last_used
        self._mem_collect_time = time.time()

    def on_pubsub_register(self, pubsub):
        topic = get_topic_name(self)
        self._log.info('on_pubsub_register start %s', topic)
        pubsub.register(Js220)
        pubsub.register(Js110)
        self.pubsub = pubsub
        self._topic = topic
        self.driver = Driver()
        self._ui_subscribe(f'{topic}/settings/log_level', self._on_log_level, ['retain', 'pub'])
        self._ui_subscribe(f'{topic}/events/!publish', self._on_event_publish, ['pub'])
        self.driver.subscribe('@', 'pub', self._on_driver_publish)
        self.driver.publish('m/@/!add', 1)  # one and only memory buffer
        self.driver.subscribe(_MEM_RESPONSE_TOPIC, 'pub', self._on_mem_response)
        for d in self.driver.device_paths():
            self._log.info('on_pubsub_register add %s', d)
            self._on_driver_publish('@/!add', d)
        self._log.info('on_pubsub_register done %s', topic)

    def on_setting_mem__size(self, value):
        self.driver.publish('m/001/g/size', int(value))

    def on_setting_mem__hold(self, value):
        value = int(value)
        self.driver.publish('m/001/g/hold', value)

    def on_setting_mem__mode(self, value):
        self.driver.publish('m/001/g/mode', int(value))

    def on_action_mem__signal__add(self, value):
        data_topic = value
        signal_id = self._mem_signals_free.pop(0)
        self._mem[data_topic] = signal_id
        self.driver.publish('m/001/a/!add', signal_id)
        self.driver.publish(f'm/001/s/{signal_id:03d}/topic', data_topic)

    def on_action_mem__signal__remove(self, value):
        data_topic = value
        signal_id = self._mem.pop(data_topic)
        self.driver.publish('m/001/a/!remove', signal_id)
        self._mem_signals_free.append(0, signal_id)

    def _on_mem_response(self, topic, value):
        # will be called from device's pubsub thread
        value = copy.deepcopy(value)
        device_req_id = value['rsp_id']
        try:
            req = self._mem_req_bwd[device_req_id]
            value['rsp_topic'] = req[0]
            value['rsp_id'] = req[1]
            self.pubsub.publish(value['rsp_topic'], value)
        except KeyError:
            self._log.info('Unknown response: req_id=%s', device_req_id)

    def on_action_mem__signal__request(self, value):
        """Request data from the memory buffer.

        :param value: The dict defining the request with keys:
            * signal: The source data topic for the signal.
            * time_type: 'utc' or 'samples'
            * rsp_topic: The arbitrary response topic
            * rsp_id: The optional and arbitrary response id.
            * start: The starting time (UTC or samples)
            * end: The ending time (UTC or samples)
            * length: The number of requested entries evenly spread from start to end.
        """
        value = copy.deepcopy(value)
        data_topic = value['signal']
        if data_topic not in self._mem:
            return  # todo handle
        signal_id = self._mem[data_topic]
        pubsub_req = (value['rsp_topic'], value['rsp_id'])
        if pubsub_req in self._mem_req_fwd:
            device_req_id = self._mem_req_fwd[pubsub_req]
        else:
            # create and add new entry
            device_req_id = id(pubsub_req)
            self._mem_req_fwd[pubsub_req] = device_req_id
            self._mem_req_bwd[device_req_id] = pubsub_req
        t_now = time.time()
        self._mem_req_time[device_req_id] = t_now  # update last used time
        value['rsp_topic'] = _MEM_RESPONSE_TOPIC
        value['rsp_id'] = device_req_id
        self.driver.publish(f'm/001/s/{signal_id:03d}/!req', value)
        self._mem_collect(t_now)

    def _mem_collect(self, t_now):
        if t_now - self._mem_collect_time < _MEM_CLEANUP_PERIOD_S:
            return
        for device_req_id, t_last in list(self._mem_req_time.items()):
            if (t_now - t_last) > _MEM_EXPIRE_INTERVAL_S:
                pubsub_req = self._mem_req_bwd.pop(device_req_id)
                del self._mem_req_fwd.pop[pubsub_req]
                del self._mem_req_time[device_req_id]
        self._mem_collect_time = t_now

    def clear(self):
        while len(self._ui_subscriptions):
            topic, fn, flags = self._ui_subscribe.pop()
            self.pubsub.unsubscribe(topic, fn, flags)
        while len(self._driver_subscriptions):
            topic, fn, flags = self._driver_subscriptions.pop()
            self.driver.unsubscribe(topic, fn)

    def _ui_subscribe(self, topic: str, update_fn: callable, flags=None, timeout=None):
        self._ui_subscriptions.append((topic, update_fn, flags))
        self.pubsub.subscribe(topic, update_fn, flags, timeout)

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
        if 'js220' in value:
            cls = Js220
        elif 'js110' in value:
            pass  # cls = DeviceJs110
        else:
            self._log.info('Unsupported device: %s', value)
            return
        self._log.info('_on_device_add %s', unique_id)
        d = cls(self, value, unique_id)
        self.pubsub.register(d, unique_id)
        if d.name is None:
            d.name = unique_id
        self.devices[value] = d

    def _on_device_remove(self, value):
        d = self.devices.pop(value, None)
        if d is not None:
            self._log.info('_on_device_remove %s', get_unique_id(d))
            topic = get_topic_name(d)
            self.pubsub.publish(f'{topic}/actions/!finalize', None)
            self.pubsub.unregister(d)
