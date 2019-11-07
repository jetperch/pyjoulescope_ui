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
from joulescope_ui.command_processor import CommandProcessor, Preferences
from joulescope_ui import paths
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
        return command, data

    def execute_undo(self, command, data):
        return command + '/undo', data + '/undo'

    def test_register_invoke_unregister(self):
        self.c.register('!my/command', self.execute_ignore)
        self.c.invoke('!my/command', 'hello')
        self.assertEqual([('!my/command', 'hello')], self.commands)
        self.c.unregister('!my/command')

    def test_register_invalid(self):
        with self.assertRaises(ValueError):
            self.c.register(1, self.execute_ignore)
        with self.assertRaises(ValueError):
            self.c.register('!hello/world', 2)

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

    def test_undo_when_empty(self):
        self.c.invoke('!undo')

    def test_redo_when_empty(self):
        self.c.invoke('!redo')

    def test_publish_subscribe(self):
        self.c.define('hello', default='world')
        self.c.subscribe('hello', self.execute_ignore)
        self.c.publish('hello', 'there')
        self.assertEqual([('hello', 'there')], self.commands)

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

    def test_publish_same_topic_undo(self):
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
        self.c.invoke('!preferences/profile/switch', 'p1')
        self.c.publish('a/0', 'update')
        self.assert_commands([('a/0', 'update')])
        self.c.invoke('!preferences/profile/switch', 'all')
        self.assert_commands([('a/0', '0')])
        self.c.invoke('!preferences/profile/switch', 'p1')
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
