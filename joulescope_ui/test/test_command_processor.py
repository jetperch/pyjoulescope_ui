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
from joulescope_ui.command_processor import CommandProcessor


class TestCommandProcessor(unittest.TestCase):

    def setUp(self):
        self.commands = []

    def execute_ignore(self, command, data):
        self.commands.append((command, data))
        return command, data

    def execute_undo(self, command, data):
        return command + '/undo', data + '/undo'

    def test_register_invoke_unregister(self):
        c = CommandProcessor(synchronous=True)
        c.register('my/command', self.execute_ignore)
        c.invoke('my/command', 'hello')
        self.assertEqual([('my/command', 'hello')], self.commands)
        c.unregister('my/command')

    def test_register_invalid(self):
        c = CommandProcessor()
        with self.assertRaises(ValueError):
            c.register(1, self.execute_ignore)
        with self.assertRaises(ValueError):
            c.register('hello/world', 2)

    def test_invoke_when_unregistered(self):
        with self.assertRaises(KeyError):
            CommandProcessor().invoke('hello', self.execute_ignore)

    def test_register_duplicate(self):
        c = CommandProcessor()
        c.register('my/command', self.execute_ignore)
        with self.assertRaises(KeyError):
            c.register('my/command', self.execute_ignore)

    def test_undo_redo(self):
        c = CommandProcessor(synchronous=True)
        c.register('my/command', self.execute_undo)
        c.register('my/command/undo', self.execute_ignore)
        self.assertEqual([], c.undos)
        self.assertEqual([], c.redos)
        c.invoke('my/command', 'hi')
        self.assertEqual(['my/command'], c.undos)
        c.invoke('undo')
        self.assertEqual([], c.undos)
        self.assertEqual([('my/command/undo', 'hi/undo')], self.commands)
        self.assertEqual(['my/command'], c.redos)

        self.commands = []
        c.invoke('redo')
        self.assertEqual(['my/command'], c.undos)
        self.assertEqual([], c.redos)

    def test_undo_when_empty(self):
        CommandProcessor(synchronous=True).invoke('undo')

    def test_redo_when_empty(self):
        CommandProcessor(synchronous=True).invoke('redo')
