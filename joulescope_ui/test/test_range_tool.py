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
from joulescope_ui.time_map import TimeMap
import numpy as np
from unittest.mock import Mock


class PubSub:
    """Fake pubsub for range tool testing."""

    def __init__(self):
        self.x_range = [time64.HOUR, time64.HOUR + time64.SECOND * 5]
        self.signals = {
            'source1.dev1.i': {},
            'source1.dev1.v': {}
        }
        self.topics = {}
        self._subscribe = {}

        for signal_id in self.signals.keys():
            source, device, quantity = signal_id.split('.')
            self.topics[f'registry/{source}/settings/signals/{device}.{quantity}/name'] = signal_id
            self.topics[f'registry/{source}/settings/signals/{device}.{quantity}/meta'] = 'meta'
            self.topics[f'registry/{source}/settings/signals/{device}.{quantity}/range'] = self.x_range

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
            tm = TimeMap()
            tm.update(100_000_000, time64.YEAR, 1_000_000)
            if value['time_type'] == 'utc':
                utc_start = value['start']
                utc_end = value['end']
                length = value['length']
                sample_start = tm.time64_to_counter(utc_start)
                sample_end = tm.time64_to_counter(utc_end)
            elif value['time_type'] == 'samples':
                sample_start = value['start']
                sample_end = value['end']
                length = value['length']
                utc_start = tm.counter_to_time64(sample_start)
                utc_end = tm.counter_to_time64(sample_end)
            else:
                raise ValueError()
            rsp = {
                'version': 1,
                'rsp_id': value['rsp_id'],
                'info': {
                    'field': value['signal_id'].split('.')[-1],
                    'units': '',
                    'time_range_utc': {
                        'start': utc_start,
                        'end': utc_end,
                        'length': length,
                    },
                    'time_range_samples': {
                        'start': sample_start,
                        'end': sample_end,
                        'length': length,
                    },
                    'time_map': {
                        'offset_time': tm.time_offset,
                        'offset_counter': tm.counter_offset,
                        'counter_rate': tm.time_to_counter_scale * time64.SECOND,
                    },
                },
                'response_type': 'samples',
                'data_type': 'f32',
                'data': np.zeros(10, dtype=np.float32),
            }
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
