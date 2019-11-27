# Copyright 2019 Jetperch LLC
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
Test the command processor
"""

import unittest
from joulescope_ui.command_processor import CommandProcessor, Preferences, BASE_PROFILE
from joulescope_ui import paths
import weakref
import os


class TestCommandProcessor(unittest.TestCase):

    def setUp(self):
        self.app = f'joulescope_cmdp_{os.getpid()}'
        self.paths = paths.paths_current(app=self.app)
        os.makedirs(self.paths['dirs']['config'])
        self.c = CommandProcessor(synchronous=True, app=self.app)
        self.commands = []

    def tearDown(self):
        paths.clear(app=self.app, delete_data=True)

    def execute_ignore(self, command, data):
        self.commands.append((command, data))
        return command, str(data) + '-undo'

    def execute_undo(self, command, data):
        return command + '/undo', data + '/undo'

    def execute_undo_and_record(self, command, data):
        self.commands.append((command, data))
        return command + '/undo', data + '/undo'

    def test_register_invoke_unregister(self):
        for command in ['!my/command', 'my/command!']:
            with self.subTest(command=command):
                self.commands = []
                self.c.register(command, self.execute_ignore)
                self.c.invoke(command, 'hello')
                self.assertEqual([(command, 'hello')], self.commands)
                self.c.unregister(command)

    def test_register_invalid(self):
        with self.assertRaises(ValueError):
            self.c.register(1, self.execute_ignore)
        with self.assertRaises(ValueError):
            self.c.register('!hello/world', 2)

    def test_register_invalid_name(self):
        for topic in ['my/name', 'my/_name', 'my/#name']:
            with self.subTest(topic=topic):
                with self.assertRaises(ValueError):
                    self.c.register(topic, self.execute_ignore)

    def test_invoke_when_unregistered(self):
        with self.assertRaises(KeyError):
            self.c.invoke('!hello', self.execute_ignore)

    def test_register_duplicate(self):
        self.c.register('!my/command', self.execute_ignore)
        with self.assertRaises(KeyError):
            self.c.register('!my/command', self.execute_ignore)

    def test_undo_redo(self):
        c = self.c
        c.register('!my/command', self.execute_undo)
        c.register('!my/command/undo', self.execute_ignore)
        self.assertEqual([], c.undos)
        self.assertEqual([], c.redos)
        c.invoke('!my/command', 'hi')
        self.assertEqual(['!my/command'], c.undos)
        c.invoke('!undo')
        self.assertEqual([], c.undos)
        self.assertEqual([('!my/command/undo', 'hi/undo')], self.commands)
        self.assertEqual(['!my/command'], c.redos)

        self.commands = []
        c.invoke('!redo')
        self.assertEqual(['!my/command'], c.undos)
        self.assertEqual([], c.redos)

    def test_undo_redo_rewrite(self):
        def fn(topic, value):
            self.commands.append((topic, value))
            return ('!c1', value + 'a'), ('!c2', 'v2')
        c = self.c
        c.register('!c1', self.execute_ignore)
        c.register('!c2', self.execute_ignore)
        c.register('!c0', fn)
        c.invoke('!c0', 'v1')
        c.invoke('!undo')
        c.invoke('!redo')
        self.assertEqual([('!c0', 'v1'), ('!c2', 'v2'), ('!c1', 'v1a')], self.commands)

    def test_undo_then_command_erases_redo(self):
        c = self.c
        c.register('!my/command', self.execute_undo_and_record)
        c.register('!my/command/undo', self.execute_ignore)
        c.invoke('!my/command', '1')
        c.invoke('!undo')
        c.invoke('!my/command', '2')
        c.invoke('!redo')
        self.assertEqual([('!my/command', '1'), ('!my/command/undo', '1/undo'), ('!my/command', '2')], self.commands)

    def test_undo_when_empty(self):
        self.c.invoke('!undo')

    def test_redo_when_empty(self):
        self.c.invoke('!redo')

    def test_command_group_undo_redo(self):
        c = self.c
        cmds = [('!my/cmd', '1'), ('!my/cmd', '2'), ('!my/cmd', '3')]
        c.register('!my/cmd', self.execute_ignore)
        c.invoke('!my/cmd', '1')
        c.invoke('!command_group/start', None)
        c.invoke('!my/cmd', '2')
        c.invoke('!my/cmd', '3')
        c.invoke('!command_group/end', None)
        self.assert_commands(cmds)
        c.invoke('!undo')
        self.assert_commands([('!my/cmd', '3-undo'), ('!my/cmd', '2-undo')])
        c.invoke('!undo')
        self.assert_commands([('!my/cmd', '1-undo')])
        c.invoke('!redo')
        c.invoke('!redo')
        self.assert_commands(cmds)

    def test_command_group_nested(self):
        c = self.c
        cmds = [('!my/cmd', '1'), ('!my/cmd', '2'), ('!my/cmd', '3'), ('!my/cmd', '4')]
        c.register('!my/cmd', self.execute_ignore)
        c.invoke('!my/cmd', '1')
        c.invoke('!command_group/start', None)
        c.invoke('!my/cmd', '2')
        c.invoke('!command_group/start', None)
        c.invoke('!my/cmd', '3')
        c.invoke('!command_group/end', None)
        c.invoke('!my/cmd', '4')
        c.invoke('!command_group/end', None)
        self.assert_commands(cmds)
        c.invoke('!undo')
        self.assert_commands([(topic, value + '-undo') for topic, value in cmds[-1:0:-1]])
        c.invoke('!redo')
        self.assert_commands(cmds[1:])

    def test_publish_subscribe(self):
        self.c.define('hello', default='world')
        self.c.subscribe('hello', self.execute_ignore)
        self.c.publish('hello', 'there')
        self.assertEqual([('hello', 'there')], self.commands)

    def test_subscribe_to_missing(self):
        self.c.subscribe('hello', self.execute_ignore)
        self.c.subscribe('hello', self.execute_ignore, update_now=True)
        self.assertEqual([], self.commands)

    def test_unsubscribe(self):
        self.c.define('hello', default='world')
        self.c.subscribe('hello', self.execute_ignore)
        self.c.unsubscribe('hello', self.execute_ignore)
        self.c.publish('hello', 'there')
        self.assertEqual([], self.commands)

    def test_unsubscribe_when_not_subscribed(self):
        self.c.unsubscribe('hello', self.execute_ignore)

    def define_group(self, preferences=None):
        if preferences is None:
            c = self.c
        else:
            c = preferences
        c.define('a', default='zz')
        c.define('a/0', default='0')
        c.define('a/1', default='1')
        c.define('b/0', default='x')
        c.define('b/1', default='y')

    def test_publish_subscribe_group(self):
        self.define_group()
        self.c.subscribe('a/', self.execute_ignore)
        self.c.publish('a/0', 'update')
        self.assertEqual([('a/0', 'update')], self.commands)

    def test_subscribe_update_now(self):
        self.c.define('hello', default='world')
        self.c.subscribe('hello', self.execute_ignore, update_now=True)
        self.assertEqual([('hello', 'world')], self.commands)

    def test_subscribe_update_now_with_command(self):
        self.c.register('!hello', self.execute_undo)
        self.c.subscribe('!hello', self.execute_ignore, update_now=True)
        self.assertEqual([], self.commands)

    def test_subscribe_update_group(self):
        self.define_group()
        self.c.subscribe('a/', self.execute_ignore, update_now=True)
        self.assertEqual([('a/0', '0'), ('a/1', '1')], self.commands)

    def test_publish_undo(self):
        self.c.define('hello', default='world')
        self.c.subscribe('hello', self.execute_ignore)
        self.c.publish('hello', '1')
        self.c.invoke('!undo')
        self.assert_commands([('hello', '1'), ('hello', 'world')])
        self.assertEqual('world', self.c.preferences['hello'])

    def test_publish_same_topic_undo_with_coalesce(self):
        self.c.define('hello', default='world')
        self.c.subscribe('hello', self.execute_ignore)
        self.c.publish('hello', '1')
        self.c.publish('hello', '2')
        self.assertEqual(1, len(self.c.undos))
        self.c.invoke('!undo')
        self.assertEqual('world', self.c.preferences['hello'])
        self.assert_commands([('hello', '1'), ('hello', '2'), ('hello', 'world')])

    def assert_commands(self, expected):
        self.assertEqual(expected, self.commands)
        self.commands.clear()

    def test_preferences_profile(self):
        self.define_group()
        self.c.subscribe('a/0', self.execute_ignore)
        self.c.invoke('!preferences/profile/add', 'p1')
        self.c.invoke('!preferences/profile/set', 'p1')
        self.c.publish('a/0', 'update')
        self.assert_commands([('a/0', 'update')])
        self.c.invoke('!preferences/profile/set', BASE_PROFILE)
        self.assert_commands([('a/0', '0')])
        self.c.invoke('!preferences/profile/set', 'p1')
        self.assert_commands([('a/0', 'update')])

    def test_preferences_restore(self):
        self.define_group()
        p = Preferences()
        self.define_group(p)
        p['a/0'] = 'override'
        self.c.subscribe('a/0', self.execute_ignore)
        self.c.invoke('!preferences/restore', p.state_export())
        self.assert_commands([('a/0', 'override')])
        self.c.invoke('!undo')
        self.assert_commands([('a/0', '0')])

    def test_preferences_load(self):
        self.define_group()
        self.c.subscribe('a/0', self.execute_ignore)

        p = Preferences(app=self.app)
        self.define_group(p)
        p['a/0'] = 'av0'
        p['b/0'] = 'bv0'
        p.save()
        self.c.invoke('!preferences/load')
        self.assert_commands([('a/0', 'av0')])
        self.c.invoke('!undo')
        self.assert_commands([('a/0', '0')])

    def test_preferences_save(self):
        self.define_group()
        self.c.invoke('!preferences/save')
        p = Preferences(app=self.app).load()
        self.assertEqual('0', p['a/0'])

    def test_preference_get_without_set_or_define(self):
        with self.assertRaises(KeyError):
            self.c['a/0']

    def test_preference_set_undo(self):
        self.c.publish('a', 'hello')
        self.c.invoke('!undo')
        with self.assertRaises(KeyError):
            self.c['a']

    def test_data_model(self):
        self.c['a'] = 'hello'
        self.assertEqual('hello', self.c['a'])
        del self.c['a']
        with self.assertRaises(KeyError):
            self.c['a']

    def test_profiles(self):
        self.c.preferences.define('a', default='default')
        self.c.subscribe('a', self.execute_ignore)
        self.c['a'] = 'world'
        self.c.invoke('!preferences/profile/add', 'p')
        self.c.invoke('!preferences/preference/set', ('a', 'value', 'p'))
        self.c.invoke('!preferences/preference/set', ('a', 'override', BASE_PROFILE))
        self.assertEqual('value', self.c.preferences.get('a', profile='p'))
        self.assertEqual('override', self.c.preferences.get('a', profile=BASE_PROFILE))
        self.assert_commands([('a', 'world'), ('a', 'override')])
        self.c.invoke('!preferences/profile/set', 'p')
        self.assert_commands([('a', 'value')])
        self.c.invoke('!undo')
        self.assert_commands([('a', 'override')])
        self.c.invoke('!undo')
        self.assert_commands([('a', 'world')])
        self.c.invoke('!undo')
        self.c.invoke('!undo')
        self.c.invoke('!undo')
        self.assert_commands([('a', 'default')])

    def test_weakref_support(self):
        calls = []
        fn = lambda topic, value: calls.append(value)
        self.c.preferences.define('a', default='default')
        self.c.subscribe('a', weakref.ref(fn))
        self.c['a'] = '1'
        self.assertEqual(['1'], calls)
        del fn
        self.c['a'] = '2'
        self.assertEqual(['1'], calls)

    def test_contains(self):
        self.assertFalse('hello' in self.c)
        self.c['hello'] = 'world'
        self.assertTrue('hello' in self.c)

