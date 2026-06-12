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
Test the PubSub implementation
"""

import unittest
from joulescope_ui.pubsub import PubSub, _paths_encode, _paths_decode
from joulescope_ui.metadata import Metadata
import io
import json
import logging
import os
import threading


TOPIC1 = 'my/topic/one'


class TestPubSub(unittest.TestCase):

    def setUp(self):
        self.pub = []

    def _on_publish1(self, value):
        self.pub.append([value])

    def _on_publish2(self, topic, value):
        self.pub.append([topic, value])

    def _on_publish3(self, pubsub, topic, value):
        self.pub.append([pubsub, topic, value])

    def test_basic(self):
        p = PubSub()
        self.assertFalse(TOPIC1 in p)
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        self.assertTrue(TOPIC1 in p)
        self.assertEqual('hello', p.query(TOPIC1))
        self.assertEqual('my topic', p.metadata(TOPIC1).brief)
        self.assertEqual(0, len(self.pub))
        p.subscribe(TOPIC1, self._on_publish2, flags=['pub', 'retain'])
        self.assertEqual(1, len(self.pub))
        self.assertEqual([TOPIC1, 'hello'], self.pub.pop())
        self.assertEqual(0, len(self.pub))
        p.publish(TOPIC1, 'world')
        self.assertEqual(1, len(self.pub))
        self.assertEqual([TOPIC1, 'world'], self.pub.pop())

    def test_basic_dedup(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='default')
        p.subscribe(TOPIC1, self._on_publish1, flags=['pub'])
        p.publish(TOPIC1, 'hello')
        p.publish(TOPIC1, 'hello')
        p.publish(TOPIC1, 'world')
        self.assertEqual([['hello'], ['world']], self.pub)

    def test_basic1(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.subscribe(TOPIC1, self._on_publish1, flags=['pub', 'retain'])
        self.assertEqual(['hello'], self.pub.pop())

    def test_bound_methods(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        m1 = self._on_publish1  # bound method
        m2 = self._on_publish1  # different bound method reference
        self.assertTrue(m1 is not m2)
        self.assertTrue(m1 == m2)
        p.subscribe(TOPIC1, m1, flags=['pub'])
        p.unsubscribe(TOPIC1, m2)
        p.publish(TOPIC1, 'pub_value')
        self.assertFalse(self.pub)

    def test_basic3(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.subscribe(TOPIC1, self._on_publish3, flags=['pub', 'retain'])
        self.assertEqual([p, TOPIC1, 'hello'], self.pub.pop())

    def test_topic_add_variations(self):
        meta = Metadata('obj', 'my topic')
        p = PubSub()
        p.topic_add('t/1', dtype='obj', brief='my topic')
        p.topic_add('t/2', 'obj', brief='my topic')
        p.topic_add('t/3', 'obj', 'my topic')
        p.topic_add('t/4', meta)
        p.topic_add('t/5', meta=meta)
        p.topic_add('t/6', meta=json.dumps(meta.to_map()))

    def test_topic_add_duplicate(self):
        p = PubSub()
        p.topic_add('t/1', dtype='obj', brief='my topic')
        p.topic_add('t/1', dtype='obj', brief='my topic', exists_ok=True)
        with self.assertRaises(ValueError):
            p.topic_add('t/1', dtype='obj', brief='my topic', exists_ok=False)

    def test_no_retain(self):
        p = PubSub()
        p.topic_add('my/topic/!one', dtype='str', brief='my topic', default='hello')
        self.assertEqual(None, p.query('my/topic/!one'))
        p.subscribe('my/topic/!one', self._on_publish2, flags=['pub', 'retain'])
        self.assertEqual(0, len(self.pub))

    def test_subscribe_node(self):
        p = PubSub()
        p.topic_add('my/topic', dtype='node', brief='node')
        p.topic_add('my/topic/sub', dtype='str', brief='my topic', default='hello')
        p.subscribe('my/topic', self._on_publish2)
        p.publish('my/topic/sub', 'world')
        self.assertEqual(1, len(self.pub))

    def test_publish_invalid_topic(self):
        p = PubSub()
        p.subscribe(TOPIC1, self._on_publish2, flags=['pub', 'retain'])
        p.publish(TOPIC1, 'world')
        self.assertEqual(0, len(self.pub))

    def test_unsubscribe(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.subscribe(TOPIC1, self._on_publish2, flags=['pub'])
        p.unsubscribe(TOPIC1, self._on_publish2, flags=['pub'])
        p.publish(TOPIC1, 'world')
        self.assertEqual(0, len(self.pub))

    def test_unsubscribe_by_obj(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        obj = p.subscribe(TOPIC1, self._on_publish2, flags=['pub'])
        p.unsubscribe(obj)
        p.publish(TOPIC1, 'world')
        self.assertEqual(0, len(self.pub))

    def test_unsubscribe_all(self):
        p = PubSub()
        p.topic_add('my/topic', dtype='node', brief='node')
        p.topic_add('my/topic/sub', dtype='str', brief='my topic', default='hello')
        p.subscribe('my/topic', self._on_publish2)
        p.subscribe('my/topic/sub', self._on_publish2)
        p.unsubscribe_all(self._on_publish2)
        p.publish('my/topic/sub', 'world')

    def test_undo_redo(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.publish(TOPIC1, 'world')
        self.assertEqual('world', p.query(TOPIC1))
        p.undo()
        self.assertEqual('hello', p.query(TOPIC1))
        p.redo()
        self.assertEqual('world', p.query(TOPIC1))

    def test_proxy_unsubscribe_removes_empty_topic(self):
        from joulescope_ui.pubsub import PubSubProxy
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='t', default='hello')
        proxy = PubSubProxy(p)
        proxy.subscribe(TOPIC1, self._on_publish2, ['pub'])
        self.assertIn(TOPIC1, proxy._subscribers)
        proxy.unsubscribe(TOPIC1, self._on_publish2)
        self.assertNotIn(TOPIC1, proxy._subscribers)  # no empty-list accumulation

    def test_proxy_unsubscribe_with_flags(self):
        # The proxy must accept the same flags argument as subscribe / PubSub.
        from joulescope_ui.pubsub import PubSubProxy
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='t', default='hello')
        proxy = PubSubProxy(p)
        proxy.subscribe(TOPIC1, self._on_publish2, ['pub', 'retain'])
        proxy.unsubscribe(TOPIC1, self._on_publish2, ['pub', 'retain'])  # must not raise
        self.assertNotIn(TOPIC1, proxy._subscribers)
        self.pub.clear()
        p.publish(TOPIC1, 'world')
        self.assertEqual(0, len(self.pub))

    def test_undo_history_is_bounded(self):
        from joulescope_ui.pubsub import UNDO_REDO_COUNT_MAX
        p = PubSub()
        p.topic_add(TOPIC1, dtype='int', brief='my topic', default=0)
        # distinct topics so coalescing does not merge the entries
        for i in range(1, UNDO_REDO_COUNT_MAX + 50):
            t = f'base/n{i}'
            p.topic_add(t, dtype='int', brief='n', default=0)
            p.publish(t, i)
        self.assertEqual(UNDO_REDO_COUNT_MAX, len(p.undos))

    def test_new_publish_clears_redo(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='int', brief='my topic', default=0)
        p.topic_add('base/two', dtype='int', brief='two', default=0)
        p.publish(TOPIC1, 1)
        p.undo()
        self.assertEqual(1, len(p.redos))
        p.publish('base/two', 2)  # a new action invalidates the redo stack
        self.assertEqual(0, len(p.redos))
        p.redo()  # nothing to redo
        self.assertEqual(0, p.query(TOPIC1))
        self.assertEqual(2, p.query('base/two'))

    def test_topic_remove(self):
        p = PubSub()
        with self.assertRaises(KeyError):
            p.query(TOPIC1)
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        self.assertEqual('hello', p.query(TOPIC1))
        p.topic_remove(TOPIC1)
        with self.assertRaises(KeyError):
            p.query(TOPIC1)

    def test_enumerate(self):
        p = PubSub()
        p.topic_add('base/one', dtype='str', brief='one', default='a')
        p.topic_add('base/two', dtype='str', brief='one', default='b')
        p.topic_add('base/three', dtype='str', brief='one', default='c')
        p.topic_add('base/three/a', dtype='str', brief='one', default='1')
        p.topic_add('base/three/b', dtype='str', brief='one', default='2')
        p.topic_add('base/three/c', dtype='str', brief='one', default='3')
        self.assertEqual(['one', 'two', 'three'], p.enumerate('base'))
        self.assertEqual(['base/one', 'base/two', 'base/three'], p.enumerate('base', absolute=True))
        self.assertEqual(['one', 'two', 'three', 'three/a', 'three/b', 'three/c'], p.enumerate('base', traverse=True))
        self.assertEqual('base/one', p.enumerate('base', absolute=True, traverse=True)[0])

    def test_subscribe_undo(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.subscribe(TOPIC1, self._on_publish2, flags=['pub'])
        p.undo()
        p.publish(TOPIC1, 'world')
        self.assertEqual(0, len(self.pub))
        p.subscribe(TOPIC1, self._on_publish2, flags=['pub'])
        p.undo()
        p.redo()
        p.publish(TOPIC1, 'there')
        self.assertEqual(1, len(self.pub))

    def test_unsubscribe_undo(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.subscribe(TOPIC1, self._on_publish2, flags=['pub'])
        p.unsubscribe(TOPIC1, self._on_publish2, flags=['pub'])
        p.undo()
        p.publish(TOPIC1, 'world')
        self.assertEqual(1, len(self.pub))

    def test_undo_topic_add_and_remove(self):
        p = PubSub()
        p.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        p.undo()
        with self.assertRaises(KeyError):
            p.query(TOPIC1)
        p.redo()
        self.assertEqual('hello', p.query(TOPIC1))
        p.topic_remove(TOPIC1)
        with self.assertRaises(KeyError):
            p.query(TOPIC1)
        p.undo()
        self.assertEqual('hello', p.query(TOPIC1))
        p.redo()
        with self.assertRaises(KeyError):
            p.query(TOPIC1)

    def test_save(self):
        topic = 'registry/value/settings/my_topic'
        p1 = PubSub()
        p1.topic_add('registry_manager/next_unique_id', dtype='int', brief='next_unique_id', default=1)
        p1.topic_add(topic, dtype='str', brief='my topic', default='hello')
        f = io.StringIO()
        p1.save(f)
        s = f.getvalue()

        p2 = PubSub()
        p2.registry_initialize()
        f = io.StringIO(s)
        p2.load(f)
        self.assertEqual('hello', p2.query(topic))

    def _config_obj(self, version):
        topic = 'registry/value/settings/my_topic'
        p1 = PubSub()
        p1.topic_add('registry_manager/next_unique_id', dtype='int', brief='', default=1)
        p1.topic_add(topic, dtype='str', brief='my topic', default='hello')
        f = io.StringIO()
        p1.save(f)
        obj = json.loads(f.getvalue())
        obj['version'] = version
        return topic, obj

    def test_load_old_version_migrates(self):
        topic, obj = self._config_obj(1)  # simulate a pre-path-substitution config
        p2 = PubSub()
        p2.registry_initialize()
        self.assertTrue(p2.load(io.StringIO(json.dumps(obj))))
        self.assertEqual('hello', p2.query(topic))

    def test_load_newer_version_best_effort(self):
        topic, obj = self._config_obj(9999)  # from a hypothetical future build
        p2 = PubSub()
        p2.registry_initialize()
        # best-effort load rather than discarding every setting
        self.assertTrue(p2.load(io.StringIO(json.dumps(obj))))
        self.assertEqual('hello', p2.query(topic))

    def test_load_invalid_version_rejected(self):
        p2 = PubSub()
        p2.registry_initialize()
        obj = {'type': 'joulescope_ui_config', 'version': 'bad'}
        self.assertFalse(p2.load(io.StringIO(json.dumps(obj))))

    def test_paths_encode_decode_roundtrip(self):
        home = os.path.join(os.sep + 'users', 'alice')
        documents = os.path.join(home, 'Documents')
        subs = [
            (os.path.join(home, 'AppData', 'Local', 'joulescope'), '{jsui:path:app}'),
            (os.path.join(documents, 'joulescope'), '{jsui:path:data}'),
            (documents, '{jsui:path:documents}'),
            (home, '{jsui:path:home}'),
        ]
        obj = {
            'app': os.path.join(home, 'AppData', 'Local', 'joulescope'),
            'data': os.path.join(documents, 'joulescope'),
            'nested': {'value': os.path.join(documents, 'joulescope', 'sub', 'file.jls')},
            'mru_files': [
                os.path.join(documents, 'joulescope', 'a.jls'),
                os.path.join(home, 'Desktop', 'b.jls'),
            ],
            'other': 42,
        }
        enc = _paths_encode(obj, subs)
        # most-specific prefix wins
        self.assertEqual('{jsui:path:app}', enc['app'])
        self.assertEqual('{jsui:path:data}', enc['data'])
        self.assertEqual('{jsui:path:data}' + os.sep + os.path.join('sub', 'file.jls'),
                         enc['nested']['value'])
        self.assertEqual('{jsui:path:data}' + os.sep + 'a.jls', enc['mru_files'][0])
        self.assertEqual('{jsui:path:home}' + os.sep + os.path.join('Desktop', 'b.jls'),
                         enc['mru_files'][1])
        self.assertEqual(42, enc['other'])
        # round-trip restores the original
        self.assertEqual(obj, _paths_decode(enc, subs))

    def test_paths_decode_to_different_machine(self):
        enc = {'app': '{jsui:path:app}', 'file': '{jsui:path:data}\\sub\\x.jls'}
        bob_home = os.path.join(os.sep + 'users', 'bob')
        subs = [
            (os.path.join(bob_home, 'AppData', 'Local', 'joulescope'), '{jsui:path:app}'),
            (os.path.join(bob_home, 'Documents', 'joulescope'), '{jsui:path:data}'),
        ]
        dec = _paths_decode(enc, subs)
        self.assertEqual(os.path.join(bob_home, 'AppData', 'Local', 'joulescope'), dec['app'])
        # windows-style separators in the remainder are normalized to os.sep
        self.assertEqual(os.path.join(bob_home, 'Documents', 'joulescope', 'sub', 'x.jls'),
                         dec['file'])

    def test_paths_decode_passthrough(self):
        subs = [(os.path.join(os.sep + 'users', 'alice'), '{jsui:path:home}')]
        self.assertEqual('hello world', _paths_decode('hello world', subs))
        self.assertEqual('{timestamp}.jls', _paths_decode('{timestamp}.jls', subs))

    def test_save_tokenizes_home(self):
        p1 = PubSub()
        p1.registry_initialize()
        home = p1._base_paths()['home']
        f = io.StringIO()
        p1.save(f)
        s = f.getvalue()
        self.assertIn('{jsui:path:', s)
        self.assertNotIn(home, s)

    def _on_notify(self):
        self.pub.append('notify')

    def test_notify_fn_on_main_thread(self):
        p1 = PubSub()
        p1.notify_fn = self._on_notify
        p1.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        self.assertEqual([], self.pub)

    def test_notify_fn_threaded(self):
        p1 = PubSub()
        p1.notify_fn = self._on_notify
        p1.topic_add(TOPIC1, dtype='str', brief='my topic', default='hello')
        def run():
            p1.publish(TOPIC1, 'world')

        t = threading.Thread(target=run)
        t.start()
        t.join()
        self.assertEqual(['notify'], self.pub)
        self.assertEqual('hello', p1.query(TOPIC1))
        p1.process()
        self.assertEqual('world', p1.query(TOPIC1))

    def test_bool_toggle(self):
        p1 = PubSub()
        p1.topic_add(TOPIC1, dtype='bool', brief='my topic', default=False)
        p1.process()
        self.assertEqual(False, p1.query(TOPIC1))

        p1.publish(TOPIC1, '!')
        p1.process()
        self.assertEqual(True, p1.query(TOPIC1))

        p1.publish(TOPIC1, '__toggle__')
        p1.process()
        self.assertEqual(False, p1.query(TOPIC1))

    # todo complicated undo with stack usage
    # todo profiles
    # todo settings
