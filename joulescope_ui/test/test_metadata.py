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
Test the metadata implementation
"""

import unittest
from joulescope_ui.metadata import Metadata


class TestMetadata(unittest.TestCase):

    def test_str_basic(self):
        m = Metadata('str', 'My string')
        self.assertEqual('hello world', m.validate('hello world'))
        m.validate(None)  # None is a valid value
        with self.assertRaises(ValueError):
            m.validate(1)
        with self.assertRaises(ValueError):
            m.validate(1.0)
        with self.assertRaises(ValueError):
            m.validate(b'Hello world')

    def test_str_options(self):
        m = Metadata('str', brief='My str', options=[['one', 1], ['two', 2]])
        self.assertEqual('one', m.validate('one'))
        self.assertEqual('one', m.validate(1))
        self.assertEqual('two', m.validate(2))
        with self.assertRaises(ValueError):
            m.validate('three')

    def test_bytes(self):
        m = Metadata('bytes', brief='My bytes')
        self.assertEqual(b'hello', m.validate(b'hello'))
        with self.assertRaises(ValueError):
            m.validate('hello')

    def test_float(self):
        m = Metadata('float', brief='My float')
        self.assertEqual(1.5, m.validate(1.5))
        self.assertEqual(1.5, m.validate('1.5'))
        self.assertEqual(1.0, m.validate(1))
        with self.assertRaises(ValueError):
            m.validate('hello')

    def test_int(self):
        m = Metadata('int', brief='my int')
        self.assertEqual(2, m.validate(2))
        self.assertEqual(2, m.validate('2'))
        self.assertEqual(1, m.validate(1.25))
        with self.assertRaises(ValueError):
            m.validate('hello')

    def test_unsigned_int_bounds(self):
        for b in [8, 16, 32, 64]:
            m = Metadata(f'u{b}', brief='my int')
            b_max = 2 ** b
            self.assertEqual(0, m.validate(0))
            self.assertEqual(b_max - 1, m.validate(b_max - 1))
            with self.assertRaises(ValueError):
                m.validate(-1)
            with self.assertRaises(ValueError):
                m.validate(b_max)

    def test_signed_int_bounds(self):
        for b in [8, 16, 32, 64]:
            m = Metadata(f'i{b}', brief='my int')
            b_min, b_max = -2 ** (b - 1), 2 ** (b - 1)
            self.assertEqual(b_min, m.validate(b_min))
            self.assertEqual(b_max - 1, m.validate(b_max - 1))
            with self.assertRaises(ValueError):
                m.validate(b_min - 1)
            with self.assertRaises(ValueError):
                m.validate(b_max)

    def test_int_range2(self):
        m = Metadata(f'i32', brief='my int', range=[10, 20])
        self.assertEqual(10, m.validate(10))
        self.assertEqual(20, m.validate(20))
        with self.assertRaises(ValueError):
            m.validate(9)
        with self.assertRaises(ValueError):
            m.validate(21)

    def test_int_range3(self):
        m = Metadata(f'i32', brief='my int', range=[10, 20, 5])
        self.assertEqual(10, m.validate(10))
        self.assertEqual(15, m.validate(15))
        self.assertEqual(20, m.validate(20))
        with self.assertRaises(ValueError):
            m.validate(11)
        with self.assertRaises(ValueError):
            m.validate(9)
        with self.assertRaises(ValueError):
            m.validate(21)

    def test_int_range_options(self):
        m = Metadata(f'i32', brief='my int', range=[10, 20, 5],
                     options=[[10, 'ten', 'yes'], [15, '15', 'ok'], [20, 'twenty', 'no']])
        self.assertEqual(10, m.validate(10))
        self.assertEqual(15, m.validate(15))
        self.assertEqual(20, m.validate(20))
        self.assertEqual(10, m.validate('ten'))
        self.assertEqual(15, m.validate('15'))
        self.assertEqual(20, m.validate('twenty'))
        self.assertEqual(10, m.validate('yes'))
        self.assertEqual(15, m.validate('ok'))
        self.assertEqual(20, m.validate('no'))
        with self.assertRaises(ValueError):
            m.validate('YES')

    def test_bool(self):
        m = Metadata('bool', brief='My bool')
        self.assertTrue(m.validate(True))
        self.assertTrue(m.validate('on'))
        self.assertTrue(m.validate('ON'))
        self.assertTrue(m.validate('True'))
        self.assertTrue(m.validate('enable'))
        self.assertFalse(m.validate(False))
        self.assertFalse(m.validate(None))
        self.assertFalse(m.validate('off'))
        self.assertFalse(m.validate('OFF'))
        self.assertFalse(m.validate('False'))
        self.assertFalse(m.validate('disable'))
        with self.assertRaises(ValueError):
            m.validate('hello world')

    def test_font(self):
        m = Metadata('font', brief='My font')
        fnt = "Lato,48,-1,5,87,0,0,0,0,0,Black"
        self.assertEqual(fnt, m.validate(fnt))

    def test_color(self):
        m = Metadata('color', brief='My color')
        self.assertEqual('#ff123456', m.validate('#123456'))

    def test_none(self):
        m = Metadata('none', brief='My none')
        self.assertEqual(None, m.validate(None))
        with self.assertRaises(ValueError):
            m.validate(True)

    def test_node(self):
        m = Metadata('node', brief='My node')
        self.assertEqual(None, m.validate(None))
        with self.assertRaises(ValueError):
            m.validate(True)

    def test_default(self):
        m = Metadata('int', brief='My int', default=42)
        self.assertEqual(42, m.default)

    def test_unique_strings(self):
        m = Metadata('unique_strings',
                     brief='My unique strings list',
                     default=['a', 'b'],
                     options=[
                         ['a', 'alpha'],
                         ['b', 'beta', 'butter'],
                         ['c', 'charlie'],
                     ])
        self.assertEqual(['a', 'b'], m.default)
        self.assertEqual(['a', 'c'], m.validate(['alpha', 'charlie']))
        self.assertEqual(['b'], m.validate(['butter']))
        with self.assertRaises(ValueError):
            m.validate(['d'])
        with self.assertRaises(ValueError):
            m.validate(['beta', 'butter'])

    def test_to_map(self):
        m = Metadata(
            'int',
            brief='My int',
            detail='My detail description.',
            default=42,
            options=[[1, 'one'], [42, 'answer']],
            range=[0, 100],
            format='%d',
            flags=['hide'],
        )
        k = m.to_map()
        self.assertEqual(m.dtype, k['dtype'])
        for key in ['dtype', 'brief', 'detail', 'default', 'options', 'range', 'format', 'flags']:
            self.assertIn(key, k)

    def test_from_meta(self):
        m1 = Metadata('int', brief='My int', default=42)
        m2 = Metadata(m1)
