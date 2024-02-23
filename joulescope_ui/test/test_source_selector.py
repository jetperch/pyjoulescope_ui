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
Test joulescope_ui.source_selector
"""

import unittest
from joulescope_ui.source_selector import SourceSelector
from joulescope_ui import CAPABILITIES, Metadata
from joulescope_ui.pubsub import PubSub, PubSubProxy


_DEFAULT_TOPICS = [
    'registry/app/settings/defaults/statistics_stream_source',
    'registry/app/settings/defaults/signal_stream_source',
    'registry/app/settings/defaults/signal_buffer_source',
]

_LIST_TOPICS = [
    'registry_manager/capabilities/statistics_stream.source/list',
    'registry_manager/capabilities/signal_stream.source/list',
    'registry_manager/capabilities/signal_buffer.source/list',
]


class TestSourceSelector(unittest.TestCase):

    def setUp(self):
        self.topic = 'registry/test/settings/topic'
        p = PubSub(skip_core_undo=True)
        p.registry_initialize()
        for capability in CAPABILITIES:
            p.register_capability(capability.value)
        for topic in _DEFAULT_TOPICS:
            p.topic_add(topic, Metadata('obj', brief='default', default='default'))
        p.topic_add(self.topic, Metadata('obj', brief='topic', default='default'))
        self.pubsub = p
        self.p = PubSubProxy(p)
        self.s = None

    def factory(self, source_type):
        self.s = SourceSelector(None, source_type)
        self.s.on_pubsub_register(self.p, self.topic)

        self.source_changed_calls = []
        self.resolved_changed_calls = []
        self.sources_changed_calls = []

        self.s.source_changed.connect(lambda x: self.source_changed_calls.append(x))
        self.s.resolved_changed.connect(lambda x: self.resolved_changed_calls.append(x))
        self.s.sources_changed.connect(lambda x: self.sources_changed_calls.append(x))

    def tearDown(self):
        self.p.unsubscribe_all()

    def test_init(self):
        self.factory('statistics_stream')
        self.assertEqual('default', self.s.value)
        self.assertEqual(['default'], self.s.sources)

    def test_list(self):
        self.factory('statistics_stream')
        self.p.publish(_LIST_TOPICS[0], ['src1', 'src2'])
        self.assertEqual(['default', 'src1', 'src2'], self.s.sources)
        self.assertEqual([['default', 'src1', 'src2']], self.sources_changed_calls)

    def test_source(self):
        self.factory('statistics_stream')
        self.p.publish(_LIST_TOPICS[0], ['src1', 'src2'])
        self.p.publish(_DEFAULT_TOPICS[0], 'src2')
        self.assertEqual('default', self.s.value)
        self.assertEqual('src2', self.s.resolved())
        self.assertEqual(['src2'], self.resolved_changed_calls)

    def test_source_removed(self):
        self.factory('statistics_stream')
        self.p.publish(_LIST_TOPICS[0], ['src1', 'src2'])
        self.p.publish(_DEFAULT_TOPICS[0], 'src2')
        self.p.publish(self.topic, 'src1')
        self.assertEqual('src1', self.s.value)
        self.assertEqual(['src1'], self.source_changed_calls)
        self.assertEqual(['src2', 'src1'], self.resolved_changed_calls)

        self.source_changed_calls.clear()
        self.resolved_changed_calls.clear()
        self.p.publish(_LIST_TOPICS[0], ['src2'])
        self.assertEqual([], self.source_changed_calls)
        self.assertEqual([None], self.resolved_changed_calls)

        self.resolved_changed_calls.clear()
        self.p.publish(_LIST_TOPICS[0], ['src1', 'src2'])
        self.assertEqual([], self.source_changed_calls)
        self.assertEqual(['src1'], self.resolved_changed_calls)

    def test_set_nonpresent_source(self):
        self.factory('statistics_stream')
        self.p.publish(_LIST_TOPICS[0], ['src1', 'src2'])
        self.p.publish(self.topic, 'np')
        self.assertEqual([['default', 'src1', 'src2'], ['default', 'src1', 'src2', 'np']], self.sources_changed_calls)
        self.assertEqual('np', self.s.value)
        self.assertEqual(['np'], self.source_changed_calls)
        self.assertEqual([], self.resolved_changed_calls)

    def test_signal_buffer(self):
        self.factory('signal_buffer')
        self.p.topic_add('registry/src1/events/sources/!add', Metadata('str', 'source_add'))
        self.p.topic_add('registry/src1/events/sources/!remove', Metadata('str', 'source_remove'))
        self.p.topic_add('registry/src1/events/signals/!add', Metadata('str', 'signal_add'))
        self.p.topic_add('registry/src1/events/signals/!remove', Metadata('str', 'signal_remove'))

        def source_add(serial_number):
            source_id = f'JS220-{serial_number}'
            for signal_id in ['i', 'v']:
                signal = f'{source_id}.{signal_id}'
                self.p.topic_add(f'registry/src1/settings/signals/{signal}/name', Metadata('str', 'name', default='i'))
                self.p.topic_add(f'registry/src1/settings/signals/{signal}/meta', Metadata('obj', 'meta', default={
                    'vendor': 'Jetperch',
                    'model': 'JS220',
                    'version': '1.0.0',
                    'serial_number': serial_number,
                }))
                self.p.publish('registry/src1/events/signals/!add', signal)

        # signal buffers are different in that we care about the "sources" within the buffer
        for sn in ['000001', '123456', '112233']:
            source_add(sn)
        self.p.publish(_LIST_TOPICS[2], ['src1'])

        self.assertEqual([['default', 'src1.JS220-000001', 'src1.JS220-123456', 'src1.JS220-112233']],
                         self.sources_changed_calls)

        self.sources_changed_calls.clear()
        self.p.publish('registry/src1/events/signals/!remove', 'JS220-123456.i')
        self.p.publish('registry/src1/events/signals/!remove', 'JS220-123456.v')
        self.assertEqual([['default', 'src1.JS220-000001', 'src1.JS220-112233']],
                         self.sources_changed_calls)

        self.sources_changed_calls.clear()
        source_add('111111')
        self.assertEqual([['default', 'src1.JS220-000001', 'src1.JS220-112233', 'src1.JS220-111111']],
                         self.sources_changed_calls)
