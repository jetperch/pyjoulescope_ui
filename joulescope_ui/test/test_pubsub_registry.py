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


class MyClass:
    """Simple class to demonstrate registry.

    :param arg1: Info about arg1.

    This is a more detailed message.
    """
    CAPABILITIES = []
    SETTINGS = {
        'name': {
            'dtype': 'str',
            'brief': 'The name of this instance',
            'default': 'MyClass',
        },
        'param1': {
            'dtype': 'str',
            'brief': 'My first parameter',
            'default': 'my default',
        },
    }
    CALLS = []

    def __init__(self):
        """Constructor method."""
        self.name = 'unknown'
        self.param1 = 'unknown'

    @staticmethod
    def on_cls_action_show1(value):
        MyClass.CALLS.append(['action_show1', value])

    @staticmethod
    def on_cls_action_show2(topic, value):
        MyClass.CALLS.append(['action_show2', topic, value])

    @staticmethod
    def on_cls_action_show3(pubsub, topic, value):
        MyClass.CALLS.append(['action_show3', pubsub, topic, value])

    @staticmethod
    def on_cls_cbk_data(pubsub, topic, value):
        MyClass.CALLS.append(['cbk_data', value])

    def on_action_view1(self, value):
        self.CALLS.append(['action_view1', value])

    def on_cbk_update(self, value):
        self.CALLS.append(['cbk_update', value])

    def on_setting_name(self, value):
        self.name = value

    def on_setting_param1(self, value):
        self.param1 = value


class MyClass1:

    def __init__(self):
        self.param1 = 'value'  # only self.param1, no MyClass1.param1
        self._name = 'hi'

    @property
    def name(self):
        # MyClass1.name.getter
        return self._name

    @name.setter
    def name(self, value):
        # MyClass1.name.setter
        self._name = value


class TestRegistry(unittest.TestCase):

    def setUp(self):
        MyClass.CALLS.clear()
        self.p = PubSub()
        self.p.registry_initialize()
        self.calls = []

    def on_cbk(self, topic, value):
        self.calls.append([topic, value])

    def test_action1(self):
        topic = self.p.register_class(MyClass)
        self.assertEqual('registry/test_pubsub_registry.MyClass', topic)
        self.p.publish(f'{topic}/actions/!show1', 'hello world 1')
        self.assertEqual(MyClass.CALLS, [['action_show1', 'hello world 1']])

    def test_action2(self):
        topic = self.p.register_class(MyClass)
        self.p.publish(f'{topic}/actions/!show2', 'hello world 2')
        self.assertEqual(MyClass.CALLS, [['action_show2',
                                          'registry/test_pubsub_registry.MyClass/actions/!show2',
                                          'hello world 2']])

    def test_action3(self):
        topic = self.p.register_class(MyClass)
        self.p.publish(f'{topic}/actions/!show3', 'hello world 3')
        self.assertEqual(MyClass.CALLS, [['action_show3',
                                          self.p,
                                          'registry/test_pubsub_registry.MyClass/actions/!show3',
                                          'hello world 3']])

    def test_callback(self):
        topic = self.p.register_class(MyClass)
        self.p.publish(f'{topic}/callbacks/!data', 'hello world')
        self.assertEqual(MyClass.CALLS, [['cbk_data', 'hello world']])

    def test_capabilitiy(self):
        with self.assertRaises(KeyError):
            self.p.query('registry_manager/capabilities/widget/list')
        self.p.subscribe('registry_manager/actions/capability/!add', self.on_cbk)
        self.p.register_capability('widget')
        self.assertEqual([['registry_manager/actions/capability/!add', 'widget']], self.calls)
        self.p.publish('registry_manager/capabilities/widget/!add', 'my.cls')
        self.assertEqual(['my.cls'], self.p.query('registry_manager/capabilities/widget/list'))
        self.p.publish('registry_manager/capabilities/widget/!remove', 'my.cls')
        self.assertEqual([], self.p.query('registry_manager/capabilities/widget/list'))
        self.p.unregister_capability('widget')
        with self.assertRaises(KeyError):
            self.p.query('registry_manager/capabilities/widget/list')

    def test_register_instance(self):
        obj = MyClass()
        print(obj.__doc__)
        topic = self.p.register_instance(obj)
        self.p.publish(f'{topic}/actions/!view1', 'hello world 1')
        self.p.publish(f'{topic}/callbacks/!update', 'x')
        self.assertEqual(MyClass.CALLS, [['action_view1', 'hello world 1'], ['cbk_update', 'x']])

    def test_monkeypatch(self):
        c = MyClass1()
        c.name = MyClass1.name

        def patch(self, value):
            self._name = f'patch_{value}'

        print(type(MyClass1.name))
        v = MyClass1.name.setter(patch)
        print(dir(v))
        print(type(v))
        print(str(v))
        MyClass1.name = v
        c.name = 'hi'
        self.assertEqual('patch_hi', c.name)
