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
from joulescope_ui import CAPABILITIES


class MyClass:
    """Simple class to demonstrate registry.

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
            'default': 'param1_default',
        },
        'a/b/c/p1': {
            'dtype': 'str',
            'brief': 'My first hierarchical parameter',
            'default': 'p1 default',
        },
        'a/b/c/p2': {
            'dtype': 'str',
            'brief': 'My second hierarchical parameter',
            'default': 'p2 default',
        },
    }
    CALLS = []

    def __init__(self):
        """Constructor method."""
        self.name = 'unknown'
        self.param1 = 'unknown'
        self.calls = []

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
    def on_cls_callback_data(pubsub, topic, value):
        MyClass.CALLS.append(['cbk_data', value])

    @staticmethod
    def on_cls_setting_param1(value):
        MyClass.CALLS.append(['setting_param1', value])

    def on_action_view1(self, value):
        self.calls.append(['action_view1', value])

    def on_action_view2(self, value):
        self.calls.append(['action_view2', value])

    def on_action_signals__current__sample_req(self, value):
        self.calls.append(['i_sample_req', value])

    def on_callback_update(self, value):
        self.calls.append(['cbk_update', value])

    def on_setting_name(self, value):
        self.name = value

    def on_setting_param1(self, value):
        self.param1 = value

    def on_setting_a__b__c__p2(self, value):
        self.calls.append(['p2', value])


class MySubClass(MyClass):

    def __init__(self):
        super().__init__()

    @staticmethod
    def on_cls_action_show1(value):
        MyClass.CALLS.append(['sub_action_show1', value])

    def on_action_view1(self, value):
        self.calls.append(['sub_action_view1', value])

    def on_setting_param1(self, value):
        self.calls.append(['sub_param1', value])


class CapabilitiesClass:
    """Simple class to demonstrate registry.

    This is a more detailed message.
    """
    CAPABILITIES = [CAPABILITIES.STATISTIC_STREAM_SINK, 'widget@']


class TestRegistry(unittest.TestCase):

    def setUp(self):
        MyClass.CALLS.clear()
        self.p = PubSub()
        self.p.registry_initialize()
        self.calls = []

    def tearDown(self) -> None:
        if hasattr(MyClass, 'unique_id'):
            self.p.unregister(MyClass)

    def on_cbk(self, topic, value):
        self.calls.append([topic, value])

    def test_action1(self):
        self.p.register(MyClass)
        MyClass.CALLS.clear()
        self.assertEqual('MyClass', MyClass.unique_id)
        self.p.publish(f'registry/{MyClass.unique_id}/actions/!show1', 'hello world 1')
        self.assertEqual(MyClass.CALLS, [['action_show1', 'hello world 1']])

    def test_action2(self):
        self.p.register(MyClass)
        MyClass.CALLS.clear()
        self.p.publish(f'registry/{MyClass.unique_id}/actions/!show2', 'hello world 2')
        self.assertEqual(MyClass.CALLS, [['action_show2',
                                          f'registry/{MyClass.unique_id}/actions/!show2',
                                          'hello world 2']])

    def test_action3(self):
        self.p.register(MyClass)
        MyClass.CALLS.clear()
        self.p.publish(f'registry/{MyClass.unique_id}/actions/!show3', 'hello world 3')
        self.assertEqual(MyClass.CALLS, [['action_show3',
                                          self.p,
                                          f'registry/{MyClass.unique_id}/actions/!show3',
                                          'hello world 3']])

    def test_callback(self):
        self.p.register(MyClass)
        MyClass.CALLS.clear()
        self.p.publish(f'registry/{MyClass.unique_id}/callbacks/!data', 'hello world')
        self.assertEqual(MyClass.CALLS, [['cbk_data', 'hello world']])

    def test_capability(self):
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
        self.p.register(obj)
        unique_id = obj.unique_id
        self.p.publish(f'registry/{unique_id}/actions/!view1', 'hello world 1')
        self.p.publish(f'registry/{unique_id}/callbacks/!update', 'x')
        self.assertEqual(obj.calls, [['p2', 'p2 default'], ['action_view1', 'hello world 1'], ['cbk_update', 'x']])
        obj.calls.clear()
        self.p.publish(f'registry/{unique_id}/actions/signals/current/!sample_req', 'x')
        self.assertEqual(obj.calls, [['i_sample_req', 'x']])
        obj.calls.clear()
        self.p.publish(f'registry/{unique_id}/settings/a/b/c/p1', 'v1')
        self.assertEqual(obj.a__b__c__p1, 'v1')
        self.p.publish(f'registry/{unique_id}/settings/a/b/c/p2', 'v2')
        self.assertEqual(obj.calls, [['p2', 'v2']])

    def test_settings_with_explicit_function(self):
        # class
        self.p.register(MyClass, unique_id='myclass')
        self.assertEqual('myclass', MyClass.unique_id)
        param1_cls_topic = f'registry/{MyClass.unique_id}/settings/param1'
        self.assertEqual(MyClass.CALLS, [['setting_param1', 'param1_default']])
        MyClass.CALLS.clear()
        self.assertEqual('param1_default', self.p.query(param1_cls_topic))
        self.p.publish(param1_cls_topic, 'new_value')
        self.assertEqual(MyClass.CALLS, [['setting_param1', 'new_value']])
        MyClass.CALLS.clear()

        # instance
        obj = MyClass()
        topic = self.p.register(obj, unique_id='myclass_obj')
        param1_topic = f'{topic}/settings/param1'
        self.assertEqual('new_value', obj.param1)

    def test_capabilities(self):
        calls = []

        def on_capability(topic, value):
            calls.append([topic, value])

        for capability in CAPABILITIES:
            self.p.register_capability(capability.value)
        topics = [
            'registry_manager/capabilities/statistics_stream.sink/!add',
            'registry_manager/capabilities/widget.class/!add',
        ]
        for t in topics:
            self.p.subscribe(t, on_capability, ['pub'])

        self.p.register(CapabilitiesClass, unique_id='myclass')
        self.assertIn('registry_manager/capabilities/statistics_stream.sink', self.p)
        self.assertIn('registry_manager/capabilities/view.class', self.p)
        self.assertEqual([[topics[0], 'myclass'], [topics[1], 'myclass']], calls)


class TestRegistrySubclass(unittest.TestCase):

    def setUp(self):
        MyClass.CALLS.clear()
        self.p = PubSub()
        self.p.registry_initialize()
        self.calls = []

    def tearDown(self) -> None:
        if hasattr(MySubClass, 'unique_id'):
            self.p.unregister(MySubClass)

    def test_cls_action(self):
        self.p.register(MySubClass)
        MyClass.CALLS.clear()
        self.p.publish(f'registry/{MySubClass.unique_id}/actions/!show1', 'hello world 1')
        self.p.publish(f'registry/{MySubClass.unique_id}/actions/!show2', 'hello world 2')
        self.assertEqual(
            [
                ['sub_action_show1', 'hello world 1'],
                ['action_show2', f'registry/{MySubClass.unique_id}/actions/!show2', 'hello world 2']
            ],
            MyClass.CALLS
        )

    def test_obj_action(self):
        c = MySubClass()
        self.p.register(c)
        c.calls.clear()
        self.p.publish(f'registry/{c.unique_id}/actions/!view1', 'v1')
        self.p.publish(f'registry/{c.unique_id}/actions/!view2', 'v2')
        self.assertEqual([['sub_action_view1', 'v1'], ['action_view2', 'v2']], c.calls)


class SettingsClass:

    SETTINGS = {
        'name': {
            'dtype': 'str',
            'brief': 'The name of this instance',
            'default': 'SimpleClass',
        },
        'param1': {
            'dtype': 'str',
            'brief': 'My first simple parameter',
            'default': 'param1_default_in_settings',
        },
        'param2': {
            'dtype': 'str',
            'brief': 'My second parameter with existing getter/setter',
            'default': 'param2_default',
        },
        'param3': {
            'dtype': 'str',
            'brief': 'My third parameter with no defs',
            'default': 'param3_default',
        },
        'param4': {
            'dtype': 'str',
            'brief': 'My fourth parameter with function',
            'default': 'param4_default',
        },
    }

    def __init__(self):
        self.name = 'instance name'         # assignment ignored, but makes IDEs happy
        self.param1 = 'instance param1'     # assignment ignored, but makes IDEs happy
        self.param2_value = 'instance param2'    # assignment ignored, but makes IDEs happy
        self.param4_value = 'instance param4'
        # param3 not defined here, generated automatically

    @property
    def param2(self):
        return self.param2_value

    @param2.setter
    def param2(self, value):
        self.param2_value = value

    def on_setting_param4(self, value):
        self.param4_value = value


class TestRegistryClassSettings(unittest.TestCase):

    def test_settings(self):
        p = PubSub()
        calls = []
        p.registry_initialize()
        p.register(SettingsClass)

        for iteration in range(5):
            with self.subTest(iteration=iteration):
                if iteration >= 3:
                    p.unregister(SettingsClass, delete=(iteration == 4))
                    p.register(SettingsClass)

                # change class default topic
                param1_cls_topic = f'registry/{SettingsClass.unique_id}/settings/param1'
                p.publish(param1_cls_topic, 'param1_default')

                obj = SettingsClass()
                p.register(obj, 'obj')
                prefix = f'registry/{obj.unique_id}/settings'

                def on_value(topic, value):
                    calls.append([topic, value])

                if iteration in [0, 2]:
                    self.assertEqual('param1_default', obj.param1)
                    self.assertEqual('param2_default', obj.param2)
                    self.assertEqual('param2_default', obj.param2_value)
                    self.assertEqual('param3_default', obj.param3)
                    self.assertEqual('param4_default', obj.param4_value)
                else:
                    self.assertEqual('1', obj.param1)
                    self.assertEqual('2', obj.param2)
                    self.assertEqual('2', obj.param2_value)
                    self.assertEqual('3', obj.param3)
                    self.assertEqual('4', obj.param4_value)

                for i in range(1, 5):
                    self.assertEqual(getattr(obj, f'param{i}'), p.query(f'{prefix}/param{i}'))

                # instance
                p.subscribe(prefix, on_value, ['pub'])
                self.assertEqual([], calls)
                obj.param1 = 'p1'
                obj.param2 = 'p2'
                obj.param3 = 'p3'
                obj.param4 = 'p4'
                expect = [
                    [f'{prefix}/param1', 'p1'],
                    [f'{prefix}/param2', 'p2'],
                    [f'{prefix}/param3', 'p3'],
                    [f'{prefix}/param4', 'p4'],
                ]
                self.assertEqual(expect, calls)
                calls.clear()

                # Set from pubsub
                p.publish(f'{prefix}/param1', 'v1')
                p.publish(f'{prefix}/param2', 'v2')
                p.publish(f'{prefix}/param3', 'v3')
                p.publish(f'{prefix}/param4', 'v4')
                self.assertEqual('v1', obj.param1)
                self.assertEqual('v2', obj.param2_value)
                self.assertEqual('v3', obj.param3)
                self.assertEqual('v4', obj.param4_value)

                # Set from instance
                obj.param1 = '1'
                obj.param2 = '2'
                obj.param3 = '3'
                obj.param4 = '4'
                self.assertEqual('1', p.query(f'{prefix}/param1'))
                self.assertEqual('2', p.query(f'{prefix}/param2'))
                self.assertEqual('2', obj.param2_value)
                self.assertEqual('3', p.query(f'{prefix}/param3'))
                self.assertEqual('4', p.query(f'{prefix}/param4'))
                self.assertEqual('4', obj.param4_value)

                p.unregister(obj, delete=(iteration == 1))
                calls.clear()
                obj.param1 = 'no_pub'
                self.assertEqual([], calls)
                p.unsubscribe(prefix, on_value)


class DynamicCapabilities:
    CAPABILITIES = ['cls']

    def __init__(self):
        self.CAPABILITIES = ['obj']


class TestDynamicCapabilities(unittest.TestCase):

    def setUp(self):
        self.calls = []
        self.p = PubSub()
        self.p.registry_initialize()
        for cap in ['cls', 'obj', '1', '2', '3']:
            self.p.register_capability(cap)
            self.p.subscribe(f'registry_manager/capabilities/{cap}/list', self.on_cap_list, ['pub'])

    def tearDown(self) -> None:
        pass

    def on_cap_list(self, topic, value):
        self.calls.append((topic, value))

    def test_static(self):
        self.p.register(DynamicCapabilities)
        self.assertEqual([('registry_manager/capabilities/cls/list', ['DynamicCapabilities'])], self.calls)
        self.calls.clear()
        obj = DynamicCapabilities()

        self.p.register(obj, 'caps')
        self.assertEqual([('registry_manager/capabilities/obj/list', ['caps'])], self.calls)
        self.calls.clear()

        self.p.capabilities_append(obj, ['1', '2'])
        expect = [
            ('registry_manager/capabilities/1/list', ['caps']),
            ('registry_manager/capabilities/2/list', ['caps'])
        ]
        self.assertEqual(expect, self.calls)
        self.calls.clear()

        self.p.capabilities_remove(obj, ['1'])
        self.assertEqual([('registry_manager/capabilities/1/list', [])], self.calls)
        self.calls.clear()

        self.p.capabilities_append(obj, ['1'])
        self.assertEqual([('registry_manager/capabilities/1/list', ['caps'])], self.calls)
        self.calls.clear()


class TestPubsubMember(unittest.TestCase):

    def setUp(self):
        self.calls = []

    def tearDown(self) -> None:
        pass

    def _callback(self, value):
        self.calls.append(value)

    def test_unregister_unsub(self):
        p = PubSub()
        p.registry_initialize()
        topic = 'my/topic/one'
        p.topic_add(topic, dtype='str', brief='my topic', default='default')
        p.register(self)
        self.pubsub.subscribe(topic, self._callback)
        p.publish(topic, 'hello')
        self.assertEqual(['hello'], self.calls)
        self.calls.clear()
        p.unregister(self)
        p.publish(topic, 'world')
        self.assertEqual([], self.calls)
