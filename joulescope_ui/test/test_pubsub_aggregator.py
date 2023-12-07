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

"""
Test the registry
"""

import unittest
from joulescope_ui.pubsub import PubSub
from joulescope_ui.pubsub_aggregator import PubsubAggregator, all_except_empty
from joulescope_ui import CAPABILITIES, N_, Metadata


class MyDevice:
    """Simple class to demonstrate registry.

    This is a more detailed message.
    """

    CAPABILITIES = ['device@']

    def __init__(self):
        self.SETTINGS = {
            'name': {
                'dtype': 'str',
                'brief': N_('Device name'),
                'detail': N_("""\
                    The Joulescope UI automatically populates the device name
                    with the device type and serial number.
                
                    This setting allows you to change the default, if you wish, to better
                    reflect how you are using your JS220.  This setting is
                    most useful when you are instrumenting a system using 
                    multiple Joulescopes."""),
                'default': None,
            },
            'info': {
                'dtype': 'obj',
                'brief': N_('Device information'),
                'default': None,
                'flags': ['ro', 'hide', 'skip_undo'],
            },
            'state': {
                'dtype': 'int',
                'brief': N_('Device state indicator'),
                'options': [
                    [0, 'closed'],
                    [1, 'opening'],
                    [2, 'open'],
                    [3, 'closing'],
                ],
                'default': 0,
                'flags': ['ro', 'hide', 'skip_undo'],
            },
    }


TOPIC = 'registry/!result'  # no dedup


class TestPubsubAggregator(unittest.TestCase):

    def setUp(self):
        self.calls = []
        self.p = PubSub()
        self.p.registry_initialize()
        self.p.topic_add(TOPIC, Metadata('bool', 'result topic'))
        self.p.subscribe(TOPIC, self._on_value, ['pub'])
        self.p.register_capability('device.class')
        self.p.register_capability('device.object')
        self.p.register(MyDevice)
        self.p.register(PubsubAggregator)

    def tearDown(self) -> None:
        self.p.unregister(PubsubAggregator)
        self.p.unregister(MyDevice)

    def _on_value(self, x):
        self.calls.append(x)

    def test_action1(self):
        a = PubsubAggregator(self.p, 'device.object', 'settings/state', any, TOPIC)
        self.p.register(a, unique_id='a')
        self.assertEqual([False], self.calls)

        d1 = MyDevice()
        self.p.register(d1, unique_id='d1')
        self.assertEqual([False], self.calls)

        self.calls.clear()
        self.p.publish('registry/d1/settings/state', 1)
        self.assertEqual([True], self.calls)

    def test_add_initial_true(self):
        a = PubsubAggregator(self.p, 'device.object', 'settings/state', any, TOPIC)
        self.p.register(a, unique_id='a')
        self.assertEqual([False], self.calls)

        d1 = MyDevice()
        d1.SETTINGS['state']['default'] = 1
        self.p.register(d1, unique_id='d1')
        self.assertEqual([False, True], self.calls)

        self.calls.clear()
        self.p.publish('registry/d1/settings/state', 0)
        self.assertEqual([False], self.calls)

    def test_aggregate_any(self):
        a = PubsubAggregator(self.p, 'device.object', 'settings/state', any, TOPIC)
        self.p.register(a, unique_id='a')
        self.assertEqual([False], self.calls)

        # Create 5 devices
        d = {}
        for idx in range(5):
            self.calls.clear()
            d[idx] = MyDevice()
            self.p.register(d[idx], unique_id=f'd{idx}')
            self.assertEqual([], self.calls)

        # setting first sets aggregated topic, remainder have no effect
        for idx in range(5):
            self.calls.clear()
            d[idx].state = 1
            self.assertEqual([True] if idx == 0 else [], self.calls)

        # clearing last then triggers update
        for idx in range(5):
            self.calls.clear()
            d[idx].state = 0
            self.assertEqual([] if idx < 4 else [False], self.calls)

    def test_aggregate_all(self):
        a = PubsubAggregator(self.p, 'device.object', 'settings/state', all_except_empty, TOPIC)
        self.p.register(a, unique_id='a')
        self.assertEqual([False], self.calls)

        # Create 5 devices
        d = {}
        for idx in range(5):
            self.calls.clear()
            d[idx] = MyDevice()
            self.p.register(d[idx], unique_id=f'd{idx}')
            self.assertEqual([], self.calls)

        # setting all sets aggregated topic, remainder have no effect
        for idx in range(5):
            self.calls.clear()
            d[idx].state = 1
            self.assertEqual([True] if idx == 4 else [], self.calls)

        # clearing first then triggers update
        for idx in range(5):
            self.calls.clear()
            d[idx].state = 0
            self.assertEqual([] if idx > 0 else [False], self.calls)
