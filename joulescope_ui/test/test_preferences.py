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
Test the preferences
"""

import unittest
import os
from joulescope_ui.preferences import Preferences, validate, options_conform
from joulescope_ui import paths


class TestPreferences(unittest.TestCase):

    def setUp(self):
        self.listener_calls = []
        self.app = f'joulescope_preferences_{os.getpid()}'
        self.paths = paths.paths_current(app=self.app)
        os.makedirs(self.paths['dirs']['config'])
        self.p = Preferences(app=self.app)

    def tearDown(self):
        paths.clear(app=self.app, delete_data=True)

    def test_get_set_get(self):
        with self.assertRaises(KeyError):
            self.p.get('hello')
        self.assertEqual('default', self.p.get('hello', default='default'))
        self.p.set('hello', 'world')
        self.assertEqual('world', self.p.get('hello'))
        self.assertEqual('world', self.p.get('hello', default='default'))

    def test_set_profile_missing(self):
        with self.assertRaises(KeyError):
            self.p.set('hello', 'world', profile='p1')

    def test_get_profile_missing(self):
        with self.assertRaises(KeyError):
            self.p.get('hello', profile='p1')

    def test_set_clear(self):
        self.p.set('hello', 'world')
        self.p.clear('hello')
        with self.assertRaises(KeyError):
            self.p.get('hello')

    def test_profile_add_remove(self):
        self.assertEqual('all', self.p.profile)
        self.assertEqual(['all'], self.p.profiles)
        self.p.profile_add('p1')
        self.assertEqual(['all', 'p1'], self.p.profiles)
        self.assertEqual('all', self.p.profile)
        self.p.profile = 'p1'
        self.assertEqual('p1', self.p.profile)
        self.p.profile_remove('p1')
        self.assertEqual('all', self.p.profile)
        self.assertEqual(['all'], self.p.profiles)

    def test_profile_override(self):
        self.p.set('hello', 'all_value')
        self.assertEqual('all_value', self.p.get('hello'))
        self.p.profile_add('p1', activate=True)
        self.assertEqual('all_value', self.p.get('hello'))
        self.assertFalse(self.p.is_in_profile('hello'))
        self.p.set('hello', 'p1_value')
        self.assertTrue(self.p.is_in_profile('hello'))
        self.assertEqual('p1_value', self.p.get('hello'))
        self.p.profile = 'all'
        self.assertEqual('all_value', self.p.get('hello'))

    def test_load_not_found(self):
        self.p.define(name='hello', default='world')
        self.assertEqual('world', self.p['hello'])
        self.p.load()
        self.assertEqual('world', self.p['hello'])

    def test_save_load_simple(self):
        self.p.set('hello', 'world')
        self.p.save()
        p = Preferences(app=self.app).load()
        self.assertEqual('world', p.get('hello'))

    def test_save_load_skip_starting_with_pound(self):
        self.p.set('hello/#there', 'world')
        self.assertIn('hello/#there', self.p)
        self.p.save()
        p = Preferences(app=self.app).load()
        self.assertNotIn('hello/#there', p)

    def test_save_load_bytes(self):
        self.p.set('hello', b'world')
        self.p.save()
        p = Preferences(app=self.app).load()
        self.assertEqual(b'world', p.get('hello'))

    def test_define_default_when_new(self):
        self.p.define(name='hello', default='world')
        self.assertEqual('world', self.p.get('hello'))

    def test_define_default_when_existing(self):
        self.p.set('hello', 'there')
        self.p.define(name='hello', default='world')
        self.assertEqual('there', self.p.get('hello'))

    def test_validate_str(self):
        self.assertEqual('there', validate('there', 'str'))
        with self.assertRaises(ValueError):
            validate(1, 'str')
        with self.assertRaises(ValueError):
            validate(1.0, 'str')
        with self.assertRaises(ValueError):
            validate([], 'str')
        with self.assertRaises(ValueError):
            validate({}, 'str')

    def test_validate_str_options_list(self):
        options = options_conform(['a', 'b', 'c'])
        self.assertEqual('a', validate('a', 'str', options=options))
        with self.assertRaises(ValueError):
            validate('A', 'str', options=options)

    def test_validate_str_options_map(self):
        options = options_conform({
            'a': {'brief': 'option a'},
            'b': {'brief': 'option b'},
            'c': {}})
        self.assertEqual('a', validate('a', 'str', options=options))
        with self.assertRaises(ValueError):
            validate('A', 'str', options=options)

    def test_validate_str_options_map_with_aliases(self):
        options = options_conform({'a': {'brief': 'option a', 'aliases': ['b', 'c']}})
        self.assertEqual('a', validate('a', 'str', options=options))
        self.assertEqual('a', validate('b', 'str', options=options))
        self.assertEqual('a', validate('c', 'str', options=options))
        with self.assertRaises(ValueError):
            validate('d', 'str', options=options)

    def test_validate_int(self):
        self.assertEqual(1, validate(1, 'int'))
        self.assertEqual(1, validate('1', 'int'))
        with self.assertRaises(ValueError):
            validate('world', 'int')

    def test_validate_float(self):
        self.assertEqual(1, validate(1, 'float'))
        self.assertEqual(1.1, validate(1.1, 'float'))
        self.assertEqual(1.1, validate('1.1', 'float'))
        with self.assertRaises(ValueError):
            validate('world', 'float')

    def test_validate_bool(self):
        self.assertEqual(True, validate(True, 'bool'))
        self.assertEqual(False, validate(False, 'bool'))
        self.assertEqual(False, validate(None, 'bool'))
        self.assertEqual(False, validate('off', 'bool'))
        self.assertEqual(False, validate('none', 'bool'))
        self.assertEqual(False, validate('None', 'bool'))
        self.assertEqual(False, validate('0', 'bool'))
        self.assertEqual(True, validate(1, 'bool'))
        self.assertEqual(True, validate('1.1', 'bool'))

    def test_validate_bytes(self):
        self.assertEqual(True, validate(b'12345', 'bytes'))

    def test_validate_dict(self):
        self.assertEqual({}, validate({}, 'dict'))
        with self.assertRaises(ValueError):
            validate('world', 'dict')

    def test_set_invalid_type(self):
        self.p.define(name='hello', dtype='str', default='world')
        with self.assertRaises(ValueError):
            self.p.set('hello', 1)

    def test_set_invalid_option(self):
        self.p.define(name='hello', dtype='str', options=['there', 'world'], default='world')
        self.p.set('hello', 'there')
        with self.assertRaises(ValueError):
            self.p.set('hello', 'you')

    def test_set_invalid_default(self):
        with self.assertRaises(ValueError):
            self.p.define(name='hello', dtype='str', options=['there', 'world'], default='bad')

    def test_definition_get(self):
        self.p.define(name='hello', dtype='str', default='world')
        d = self.p.definition_get(name='hello')

    def test_definitions_get(self):
        self.p.define(name='/', brief='top level', dtype='container')
        self.p.define(name='hello/', brief='holder', dtype='container')
        self.p.define(name='hello/world', brief='hello', dtype='str', default='world')
        d = self.p.definitions
        self.assertIn('children', d)

    def test_dict_style_access(self):
        p = self.p
        self.assertEqual(0, len(p))
        p.define(name='hello/a', dtype='str', default='a_default')
        p.define(name='hello/b', dtype='str', default='b_default')
        self.assertEqual(2, len(p))
        self.assertIn('hello/a', p)
        pairs = [(key, value) for key, value in p]
        self.assertEqual([('hello/a', 'a_default'), ('hello/b', 'b_default')], pairs)

        p.profile_add('p1', activate=True)
        p['hello/a'] = 'a_override'
        self.assertEqual('a_override', p['hello/a'])
        self.assertEqual('b_default', p['hello/b'])
        self.assertEqual(2, len(p))
        del p['hello/a']
        self.assertEqual(2, len(p))
        self.assertEqual('a_default', p['hello/a'])

    def test_items(self):
        p = self.p
        p.define(name='a', dtype='str', default='zz')
        p.define(name='a/0', dtype='str', default='0')
        p.define(name='a/1', dtype='str', default='1')
        p.define(name='b/2', dtype='str', default='2')
        p.profile_add('p1', activate=True)
        p['a/1'] = 'new'
        self.assertEqual([('a', 'zz'), ('a/0', '0'), ('a/1', 'new'), ('b/2', '2')], list(p.items()))
        self.assertEqual([('a', 'zz'), ('a/0', '0'), ('a/1', 'new')], list(p.items(prefix='a')))
        self.assertEqual([('a/0', '0'), ('a/1', 'new')], list(p.items(prefix='a/')))
        self.assertEqual([('b/2', '2')], list(p.items(prefix='b/')))
