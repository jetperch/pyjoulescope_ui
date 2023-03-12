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

"""
Test the range tool implementation
"""

import unittest
from joulescope_ui.range_tool import RangeTool
from joulescope_ui import time64
from unittest.mock import Mock


class PubSub:
    """Fake pubsub for range tool testing."""

    def __init__(self):
        self.x_range = [time64.HOUR, time64.HOUR + time64.SECOND * 5]
        self.signals = {
            ('source1', 'dev1.i'): {},
            ('source1', 'dev1.v'): {}
        }
        self.topics = {}
        self._subscribe = {}

        for source_id, signal_id in self.signals.keys():
            self.topics[f'registry/{source_id}/settings/signals/{signal_id}/name'] = signal_id
            self.topics[f'registry/{source_id}/settings/signals/{signal_id}/meta'] = 'meta'
            self.topics[f'registry/{source_id}/settings/signals/{signal_id}/range'] = self.x_range

    def range_tool_init_value(self):
        return {
            'x_range': self.x_range,
            'signals': list(self.signals.keys()),
        }

    def subscribe(self, topic, callback, flags=None):
        if topic in self._subscribe:
            self._subscribe[topic].append(callback)
        else:
            self._subscribe[topic] = [callback]

    def query(self, topic, **kwargs):
        if 'default' in kwargs:
            return self.topics.get(topic, kwargs['default'])
        return self.topics[topic]

    def publish(self, topic, value):
        if topic.endswith('!request'):
            # todo construct response
            rsp = value
            for cbk in self._subscribe.get(value['rsp_topic'], []):
                cbk(rsp)


class TestRangeTool(unittest.TestCase):

    def construct(self, disconnected=None):
        pubsub = PubSub()
        rt = RangeTool(pubsub.range_tool_init_value())
        rt.pubsub = pubsub
        rt.rsp_topic = 'registry/rt1/callbacks/!data'
        if not disconnected:
            pubsub.subscribe(rt.rsp_topic, rt.push)
        signals = list(pubsub.signals.keys())
        return rt, pubsub, signals

    def test_basic(self):
        rt, pubsub, signals = self.construct()
        self.assertEqual('meta', rt.signal_query(signals[0], 'meta'))
        rsp = rt.request(signals[0], 'utc', *pubsub.x_range, 1)
        # todo check rsp

    def test_timeout(self):
        rt, pubsub, signals = self.construct(disconnected=True)
        with self.assertRaises(TimeoutError):
            rt.request(signals[0], 'utc', *pubsub.x_range, 1, timeout=0.05)

    def test_ignore_mismatched_rsp_id(self):
        rt, pubsub, signals = self.construct()
        rt.push({'rsp_id': '_mismatch_'})
        rsp = rt.request(signals[0], 'utc', *pubsub.x_range, 1)
        # todo check rsp
