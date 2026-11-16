# Copyright 2026 Jetperch LLC
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

"""Test settings_reset."""

import unittest
from joulescope_ui.pubsub import PubSub
from joulescope_ui import CAPABILITIES
from joulescope_ui.styles.manager import style_settings
from joulescope_ui.settings_reset import RESET_TOPIC, reset, reset_values, base_topic, modified


_SETTINGS = {
    'gain': {'dtype': 'int', 'brief': 'gain', 'default': 1},
    'mode': {'dtype': 'str', 'brief': 'mode', 'default': 'a'},
    'state': {'dtype': 'int', 'brief': 'widget state', 'default': 0, 'flags': ['hide']},
    'info': {'dtype': 'str', 'brief': 'read only', 'default': 'x', 'flags': ['ro']},
    'live': {'dtype': 'int', 'brief': 'temporary', 'default': 0, 'flags': ['tmp']},
}


class Widget:
    CAPABILITIES = ['widget@']
    SETTINGS = {**_SETTINGS, **style_settings('Widget')}


class Device:
    CAPABILITIES = ['device@']
    SETTINGS = {
        **_SETTINGS,
        'name': {'dtype': 'str', 'brief': 'name', 'default': 'Device'},
        'signals/i/enable': {'dtype': 'bool', 'brief': 'i', 'default': True, 'flags': ['hide']},
        'signals/r/enable': {'dtype': 'bool', 'brief': 'r', 'default': False, 'flags': ['hide']},
    }

    def __init__(self):
        self.state_req = []

    def on_action_state_req(self, value):
        self.state_req.append(value)


class Plain:
    """An instance whose class is not editable in the Settings widget."""
    SETTINGS = dict(_SETTINGS)


class TestSettingsReset(unittest.TestCase):

    def setUp(self):
        self.p = PubSub()
        self.p.registry_initialize()
        for capability in CAPABILITIES:
            self.p.register_capability(capability.value)
        self.p.register_command(RESET_TOPIC, lambda pubsub, topic, value: reset(pubsub, value))
        for cls in [Widget, Device]:
            self.p.register(cls, cls.__name__)

    def tearDown(self):
        for cls in [Widget, Device, Plain]:
            if getattr(cls, 'unique_id', None) is not None:
                self.p.unregister(cls, delete=True)

    def _widget(self):
        w = Widget()
        self.p.register(w)
        return w

    def test_base_topic(self):
        w = self._widget()
        plain = Plain()
        self.p.register(plain, 'plain')
        self.assertEqual('registry/Widget', base_topic(self.p, w))
        self.assertIsNone(base_topic(self.p, 'Widget'))
        self.assertIsNone(base_topic(self.p, 'plain'))

    def test_instance_resets_to_class_values(self):
        self.p.publish('registry/Widget/settings/gain', 5)  # user edited defaults
        w = self._widget()
        self.p.publish(f'{w.topic}/settings/gain', 7)
        self.p.publish(f'{w.topic}/settings/mode', 'b')
        self.p.publish(RESET_TOPIC, {'target': w.unique_id})
        self.assertEqual(5, self.p.query(f'{w.topic}/settings/gain'))
        self.assertEqual('a', self.p.query(f'{w.topic}/settings/mode'))

    def test_class_resets_to_factory(self):
        self.p.publish('registry/Widget/settings/gain', 5)
        self.p.publish('registry/Widget/settings/colors', {'dark': {'c': '#112233ff'}})
        self.p.publish(RESET_TOPIC, {'target': 'Widget'})
        self.assertEqual(1, self.p.query('registry/Widget/settings/gain'))
        self.assertIsNone(self.p.query('registry/Widget/settings/colors'))

    def test_plain_instance_resets_to_factory(self):
        plain = Plain()
        self.p.register(plain, 'plain')
        self.p.publish('registry/plain/settings/gain', 3)
        self.p.publish(RESET_TOPIC, {'target': 'plain'})
        self.assertEqual(1, self.p.query('registry/plain/settings/gain'))

    def test_skips_name_hidden_ro_tmp(self):
        w = self._widget()
        t = f'{w.topic}/settings'
        self.p.publish(f'{t}/name', 'Mine')
        self.p.publish(f'{t}/state', 4)
        self.p.publish(f'{t}/live', 4)
        self.assertEqual([], reset_values(self.p, w))
        self.assertEqual('Mine', self.p.query(f'{t}/name'))

    def test_styles(self):
        w = self._widget()
        t = f'{w.topic}/settings'
        self.p.publish(f'{t}/colors', {'dark': {'c': '#112233ff'}, 'light': {'c': '#445566ff'}})
        self.p.publish(f'{t}/fonts', {'js1': {'f': '10pt Lato'}})
        self.p.publish(f'{t}/style_defines', {'d': '4px'})
        self.p.publish(RESET_TOPIC, {'target': w.unique_id, 'tabs': ['colors'],
                                     'schemes': {'colors': 'dark'}})
        self.assertEqual({'light': {'c': '#445566ff'}}, self.p.query(f'{t}/colors'))
        self.assertEqual({'js1': {'f': '10pt Lato'}}, self.p.query(f'{t}/fonts'))
        self.p.publish(RESET_TOPIC, {'target': w.unique_id, 'tabs': ['colors'],
                                     'schemes': {'colors': 'light'}})
        self.assertIsNone(self.p.query(f'{t}/colors'))
        self.p.publish(RESET_TOPIC, {'target': w.unique_id})
        self.assertIsNone(self.p.query(f'{t}/fonts'))
        self.assertIsNone(self.p.query(f'{t}/style_defines'))

    def test_one_tab(self):
        w = self._widget()
        t = f'{w.topic}/settings'
        self.p.publish(f'{t}/gain', 7)
        self.p.publish(f'{t}/colors', {'dark': {'c': '#112233ff'}})
        self.p.publish(RESET_TOPIC, {'target': w.unique_id, 'tabs': ['colors']})
        self.assertEqual(7, self.p.query(f'{t}/gain'))
        self.assertIsNone(self.p.query(f'{t}/colors'))

    def test_single_undo(self):
        w = self._widget()
        t = f'{w.topic}/settings'
        self.p.publish(f'{t}/gain', 7)
        self.p.publish(f'{t}/mode', 'b')
        self.p.publish(f'{t}/colors', {'dark': {'c': '#112233ff'}})
        n0 = len(self.p.undos)
        self.p.publish(RESET_TOPIC, {'target': w.unique_id})
        self.assertEqual(n0 + 1, len(self.p.undos))
        self.p.undo()
        self.assertEqual(7, self.p.query(f'{t}/gain'))
        self.assertEqual('b', self.p.query(f'{t}/mode'))
        self.assertEqual({'dark': {'c': '#112233ff'}}, self.p.query(f'{t}/colors'))
        self.p.redo()
        self.assertEqual(1, self.p.query(f'{t}/gain'))

    def test_nothing_to_reset_adds_no_undo(self):
        w = self._widget()
        n0 = len(self.p.undos)
        self.p.publish(RESET_TOPIC, {'target': w.unique_id})
        self.assertEqual(n0, len(self.p.undos))

    def test_device(self):
        d = Device()
        self.p.register(d)
        t = f'{d.topic}/settings'
        self.p.publish(f'{t}/gain', 7)
        self.p.publish(f'{t}/state', 3)  # hidden device configuration resets
        self.p.publish(f'{t}/signals/r/enable', True)
        self.p.publish(f'{t}/name', 'Bench')
        self.p.publish(RESET_TOPIC, {'target': d.unique_id})
        self.assertEqual([0], d.state_req)  # closed before the reset
        self.assertEqual(1, self.p.query(f'{t}/gain'))
        self.assertEqual(0, self.p.query(f'{t}/state'))
        self.assertTrue(self.p.query(f'{t}/signals/i/enable'))  # restored
        self.assertFalse(self.p.query(f'{t}/signals/r/enable'))
        self.assertEqual('Bench', self.p.query(f'{t}/name'))

    def test_one_setting(self):
        w = self._widget()
        t = f'{w.topic}/settings'
        self.p.publish(f'{t}/gain', 7)
        self.p.publish(f'{t}/mode', 'b')
        self.p.publish(RESET_TOPIC, {'target': w.unique_id, 'tabs': ['settings'], 'names': ['gain']})
        self.assertEqual(1, self.p.query(f'{t}/gain'))
        self.assertEqual('b', self.p.query(f'{t}/mode'))

    def test_one_color_and_define(self):
        w = self._widget()
        t = f'{w.topic}/settings'
        self.p.publish(f'{t}/colors', {'dark': {'a': '#112233ff', 'b': '#445566ff'},
                                       'light': {'a': '#778899ff'}})
        self.p.publish(f'{t}/style_defines', {'d': '4px', 'e': '5px'})
        self.p.publish(RESET_TOPIC, {'target': w.unique_id, 'tabs': ['colors'],
                                     'schemes': {'colors': 'dark'}, 'names': ['a']})
        self.assertEqual({'dark': {'b': '#445566ff'}, 'light': {'a': '#778899ff'}},
                         self.p.query(f'{t}/colors'))
        self.p.publish(RESET_TOPIC, {'target': w.unique_id, 'tabs': ['colors'],
                                     'schemes': {'colors': 'dark'}, 'names': ['b']})
        self.assertEqual({'light': {'a': '#778899ff'}}, self.p.query(f'{t}/colors'))
        self.p.publish(RESET_TOPIC, {'target': w.unique_id, 'tabs': ['style_defines'], 'names': ['d']})
        self.assertEqual({'e': '5px'}, self.p.query(f'{t}/style_defines'))

    def test_modified(self):
        self.p.publish('registry/Widget/settings/gain', 5)
        w = self._widget()
        t = f'{w.topic}/settings'
        self.assertEqual(set(), modified(self.p, w, 'settings'))  # equals the class
        self.p.publish(f'{t}/mode', 'b')
        self.p.publish(f'{t}/state', 4)  # hidden: not reset, so not modified
        self.assertEqual({'mode'}, modified(self.p, w, 'settings'))
        self.assertEqual({'gain'}, modified(self.p, 'Widget', 'settings'))  # vs factory
        self.p.publish(f'{t}/colors', {'dark': {'a': '#112233ff'}})
        self.assertEqual({'a'}, modified(self.p, w, 'colors', 'dark'))
        self.assertEqual(set(), modified(self.p, w, 'colors', 'light'))
        self.assertEqual(set(), modified(self.p, w, 'style_defines'))
