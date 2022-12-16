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


class Device:
    """Joulescope driver."""
    CAPABILITIES = [CAPABILITIES.DEVICE,
                    CAPABILITIES.SIGNAL_SOURCE, CAPABILITIES.SIGNAL_STREAMING,
                    CAPABILITIES.STATISTICS_SOURCE]
    EVENTS = {
        '!statistics_data': Metadata('obj', 'Periodic statistics data'),
    }

    def __init__(self, driver, device_path):
        self._pubsub = driver.pubsub
        self._driver = driver.driver
        while device_path.endswith('/'):
            device_path = device_path[:-1]
        self._log = logging.getLogger(__name__ + '.' + device_path.replace('/', '.'))
        self._path = device_path

    def _driver_topic_make(self, topic):
        if topic[0] != '/':
            topic = '/' + topic
        return self._path + topic

    def _driver_publish(self, topic, value, timeout=None):
        return self._driver.publish(self._driver_topic_make(topic), value, timeout)

    def _driver_query(self, topic, timeout=None):
        return self._driver.query(self._driver_topic_make(topic), timeout)

    def _driver_subscribe(self, topic, flags, fn, timeout=None):
        return self._driver.subscribe(self._driver_topic_make(topic), flags, fn, timeout)

    def _driver_unsubscribe(self, topic, fn, timeout=None):
        return self._driver.unsubscribe(self._driver_topic_make(topic), fn, timeout)

    def _driver_unsubscribe_all(self, fn, timeout=None):
        return self._driver.unsubscribe(fn, timeout)

    def _ui_topic_make(self, topic):
        if topic[0] != '/':
            topic = '/' + topic
        return self.topic + topic

    def _ui_publish(self, topic: str, value, timeout=None):
        return self._pubsub.publish(self._ui_topic_make(topic), value, timeout)

    def _ui_query(self, topic):
        return self._pubsub.query(self._ui_topic_make(topic))

    def _ui_subscribe(self, topic: str, update_fn: callable, flags=None, timeout=None):
        return self._pubsub.subscribe(self._ui_topic_make(topic), update_fn, flags, timeout)

    def _ui_unsubscribe(self, topic, update_fn: callable, flags=None, timeout=None):
        return self._pubsub.unsubscribe(self._ui_topic_make(topic), update_fn, flags, timeout)

    def _ui_unsubscribe_all(self, update_fn: callable, timeout=None):
        return self._pubsub.unsubscribe_all(update_fn, timeout)