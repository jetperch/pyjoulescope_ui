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


import logging


def all_except_empty(x):
    """Return True when all but False if empty.

    :param x: The iterable of items.

    The normal python implementation of "all" returns True on empty.
    For aggregation, we often want False on empty.
    """
    if len(x):
        return all(x)
    else:
        return False


class PubsubAggregator:
    """Create a new pubsub aggregator.

    :param pubsub: The pubsub instance.
    :param capability: The registry_manager/capabilities/{capability} to aggregate.
    :param subtopic: The subtopic to inspect for each added capability.
    :param fn: The callable(iterable) use to compute the aggregated topic value.
        The iterable contains the subtopic values.
        Common fn values are :func:`any` and :func:`all_except_empty`.
        Note that the iterable may be empty!
    :param aggregated_topic: The fully-qualified aggregated topic that
        this instance uses to publish the resulting value.

    This class implements a centralized event aggregation method that combines
    multiple topics into a single summarized topic.  This feature allows a simple
    way to implement "any" and "all" summary topics.
    """

    def __init__(self, pubsub, capability, subtopic, fn, aggregated_topic):
        self._value_prev = '__uninitialized__'
        self._log = logging.getLogger(f'{__name__}.{capability}.{subtopic}')
        self._pubsub = pubsub
        self._capability = capability
        self._subtopic = subtopic
        self._fn = fn
        self._aggregated_topic = aggregated_topic
        self._values = {}
        self._capability_list_topic = f'registry_manager/capabilities/{self._capability}/list'
        self._pubsub.subscribe(self._capability_list_topic, self._on_capability_list, ['pub', 'retain'])

    def close(self):
        self._pubsub.unsubscribe(self._capability_list_topic, self._on_capability_list)
        for c in self._values.keys():
            self._pubsub.unsubscribe(f'registry/{c}/{self._subtopic}', self._on_subtopic)
        self._values.clear()

    def _on_capability_list(self, topic, value):
        for c in value:
            if c in self._values:
                continue
            try:
                self._values[c] = self._pubsub.query(f'registry/{c}/{self._subtopic}')
                self._log.info('Adding %s to %s aggregator', c, self._aggregated_topic)
            except KeyError:
                continue
            self._pubsub.subscribe(f'registry/{c}/{self._subtopic}', self._on_subtopic, ['pub', 'retain'])
        for c in self._values.keys():
            if c not in value:
                self._log.info('Removing %s from %s aggregator', c, self._aggregated_topic)
                self._pubsub.unsubscribe(f'registry/{c}/{self._subtopic}', self._on_subtopic)
        self._publish()

    def _publish(self):
        x = self._values.values()
        value = self._fn(x)
        if value == self._value_prev:
            return  # deduplicate locally
        self._value_prev = value
        self._pubsub.publish(self._aggregated_topic, value)

    def _on_subtopic(self, topic, value):
        unique_id = topic.split('/')[1]
        if unique_id not in self._values:
            self._log.warning('unique_id %s not known', unique_id)
            return
        self._values[unique_id] = value
        self._publish()
