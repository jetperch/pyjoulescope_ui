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
Test the paths
"""

import unittest
from joulescope_ui.pubsub import PubSub


TOPIC1 = 'my/topic/one'


class TestPubSub(unittest.TestCase):

    def setUp(self):
        self.pub = []
        self._on_publish_fn = self._on_publish

    def _on_publish(self, topic, value):
        self.pub.append([topic, value])

    def test_basic(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        self.assertEqual('hello', p.query(TOPIC1))
        self.assertEqual('my topic', p.metadata(TOPIC1).brief)
        self.assertEqual(0, len(self.pub))
        p.subscribe(TOPIC1, self._on_publish_fn, flags=['pub', 'retain'])
        self.assertEqual(1, len(self.pub))
        self.assertEqual([TOPIC1, 'hello'], self.pub.pop())
        self.assertEqual(0, len(self.pub))
        p.publish(TOPIC1, 'world')
        self.assertEqual(1, len(self.pub))
        self.assertEqual([TOPIC1, 'world'], self.pub.pop())

    def test_no_retain(self):
        p = PubSub()
        p.topic_add('my/topic/!one', dtype='str', brief='my topic', default='hello')
        self.assertEqual(None, p.query('my/topic/!one'))
        p.subscribe('my/topic/!one', self._on_publish_fn, flags=['pub', 'retain'])
        self.assertEqual(0, len(self.pub))

    def test_subscribe_node(self):
        p = PubSub()
        p.topic_add('my/topic', dtype='node', brief='node')
        p.topic_add('my/topic/sub', dtype='str', brief='my topic', default='hello')
        p.subscribe('my/topic', self._on_publish_fn)
        p.publish('my/topic/sub', 'world')
        self.assertEqual(1, len(self.pub))

    def test_publish_invalid_topic(self):
        p = PubSub()
        p.subscribe(TOPIC1, self._on_publish_fn, flags=['pub', 'retain'])
        p.publish(TOPIC1, 'world')
        self.assertEqual(0, len(self.pub))

    def test_unsubscribe(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.subscribe(TOPIC1, self._on_publish_fn, flags=['pub'])
        p.unsubscribe(TOPIC1, self._on_publish_fn, flags=['pub'])
        p.publish(TOPIC1, 'world')
        self.assertEqual(0, len(self.pub))

    def test_subscribe_all(self):
        p = PubSub()
        p.topic_add('my/topic', dtype='node', brief='node')
        p.topic_add('my/topic/sub', dtype='str', brief='my topic', default='hello')
        p.subscribe('my/topic', self._on_publish_fn)
        p.subscribe('my/topic/sub', self._on_publish_fn)
        p.unsubscribe_all(self._on_publish_fn)
        p.publish('my/topic/sub', 'world')
        self.assertEqual(0, len(self.pub))

    def test_undo_redo(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.publish(TOPIC1, 'world')
        self.assertEqual('world', p.query(TOPIC1))
        p.undo()
        self.assertEqual('hello', p.query(TOPIC1))
        p.redo()
        self.assertEqual('world', p.query(TOPIC1))
