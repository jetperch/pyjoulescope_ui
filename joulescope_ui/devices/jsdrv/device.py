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

from joulescope_ui.capabilities import CAPABILITIES
from joulescope_ui.metadata import Metadata
import logging


CAPABILITIES_CLASS = [CAPABILITIES.DEVICE_CLASS]
CAPABILITIES_OBJECT = [
    CAPABILITIES.DEVICE_OBJECT,
]


CAPABILITIES_OBJECT_OPEN = [
    # dynamically added when the open opens, removed on close
    CAPABILITIES.SOURCE,
    CAPABILITIES.STATISTIC_STREAM_SOURCE,
    CAPABILITIES.SIGNAL_STREAM_SOURCE,
]


class Device:
    """Joulescope driver."""
    CAPABILITIES = CAPABILITIES_CLASS
    EVENTS = {}

    def __init__(self, wrapper, device_path):
        self.CAPABILITIES = CAPABILITIES_OBJECT
        self._wrapper = wrapper  #: JsdrvWrapper
        while device_path.endswith('/'):
            device_path = device_path[:-1]
        self._log = logging.getLogger(__name__ + '.' + device_path.replace('/', '.'))
        self._path = device_path
        self._driver_subscriptions = []
        self._ui_subscriptions = []

    def __str__(self):
        return f'Device({self._path})'

    @property
    def device_path(self):
        return self._path

    def finalize(self):
        while len(self._driver_subscriptions):
            t, v = self._driver_subscriptions.pop()
            self._driver.unsubscribe(self._driver_topic_make(t), v)
        while len(self._ui_subscriptions):
            t, v, f = self._ui_subscriptions.pop()
            self._pubsub.unsubscribe(t, v, flags=[f])

    @property
    def _driver(self):
        return self._wrapper.driver

    @property
    def _pubsub(self):
        return self._wrapper.pubsub

    def _driver_topic_make(self, topic):
        if topic[0] != '/':
            topic = '/' + topic
        return self._path + topic

    def _driver_publish(self, topic, value, timeout=None):
        return self._driver.publish(self._driver_topic_make(topic), value, timeout)

    def _driver_query(self, topic, timeout=None):
        return self._driver.query(self._driver_topic_make(topic), timeout)

    def _driver_subscribe(self, topic, flags, fn, timeout=None):
        rv = self._driver.subscribe(self._driver_topic_make(topic), flags, fn, timeout)
        if rv == 0:
            self._driver_subscriptions.append((topic, fn))

    def _driver_unsubscribe(self, topic, fn, timeout=None):
        s, self._driver_subscriptions = self._driver_subscriptions, []
        for t, f in s:
            if t == topic and f == fn:  # "==" works for bound methods
                self._driver.unsubscribe(self._driver_topic_make(t), f, timeout)
            else:
                self._driver_subscriptions.append((t, f))

    def _driver_unsubscribe_all(self, fn, timeout=None):
        s, self._driver_subscriptions = self._driver_subscriptions, []
        for t, f in s:
            if f == fn:  # "==" works for bound methods
                self._driver.unsubscribe(f, timeout)
            else:
                self._driver_subscriptions.append((t, f))

    def _ui_topic_make(self, topic):
        if topic[0] != '/':
            topic = '/' + topic
        return self.topic + topic

    def _ui_publish(self, topic: str, value):
        return self._pubsub.publish(self._ui_topic_make(topic), value)

    def _ui_query(self, topic):
        return self._pubsub.query(self._ui_topic_make(topic))

    def _ui_subscribe(self, topic: str, update_fn: callable, flags=None, absolute_topic=False):
        if not bool(absolute_topic):
            topic = self._ui_topic_make(topic)
        flags = ['pub'] if flags is None else flags
        for flag in flags:
            self._ui_subscriptions.append((topic, update_fn, flag))
        return self._pubsub.subscribe(topic, update_fn, flags)

    def _ui_unsubscribe(self, topic, update_fn: callable, flags=None):
        topic = self._ui_topic_make(topic)
        flags = ['pub'] if flags is None else flags
        s, self._ui_subscriptions = self._ui_subscriptions, []
        for s_topic, s_update_fn, s_flag in s:
            if s_topic == topic and s_update_fn == update_fn and s_flag in flags:  # "==" works for bound methods
                pass
            else:
                self._ui_subscriptions.append((s_topic, s_update_fn, s_flag))
        return self._pubsub.unsubscribe(topic, update_fn, flags)

    def _ui_unsubscribe_all(self, update_fn: callable):
        s, self._ui_subscriptions = self._ui_subscriptions, []
        for s_topic, s_update_fn, s_flag in s:
            if s_update_fn == update_fn:  # "==" works for bound methods
                pass
            else:
                self._ui_subscriptions.append((s_topic, s_update_fn, s_flag))
        return self._pubsub.unsubscribe_all(update_fn)
