# Copyright 2019-2022 Jetperch LLC
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
Test the style manager
"""

import io
import os
import shutil
import unittest
import joulescope_ui
from joulescope_ui.pubsub import PubSub
from joulescope_ui.styles import manager


_A = '#112233ff'
_B = '#445566ff'
_C = '#778899ff'


@manager.styled_widget('Styled')
class Styled:
    """A styled widget stand-in: no Qt, no style files."""

    def __init__(self):
        self.style_change_count = 0

    def on_style_change(self):
        self.style_change_count += 1


@manager.styled_widget('StyledView')
class StyledView:
    """A view stand-in that parents the Styled instances."""
    SETTINGS = {
        'color_scheme': {'dtype': 'str', 'brief': 'color scheme', 'default': 'dark'},
    }


class Ui:

    def __init__(self, pubsub):
        pubsub.topic_add('common/settings/profile/active', dtype='str', brief='Active profile name', default='basic')
        pubsub.topic_add('registry/view/settings/active', dtype='str', brief='Active view name', default='myview')
        pubsub.topic_add('registry/ui/settings/theme', dtype='str', brief='Active theme', default='js1')
        pubsub.topic_add('registry/ui/settings/color_scheme', dtype='str', brief='Color scheme name', default='dark')
        pubsub.topic_add('registry/ui/settings/colors', dtype='obj', brief='Active color scheme', default={})


class TestStyleManager(unittest.TestCase):

    def setUp(self):
        self.pubsub = PubSub(app='joulescope_ui_style_test')
        manager.pubsub_singleton, self._pubsub_singleton_orig = self.pubsub, manager.pubsub_singleton
        self.ui = Ui(self.pubsub)
        self.app_path = self.pubsub.query('common/settings/paths/app')
        self.styles_path = self.pubsub.query('common/settings/paths/styles')
        self.mgr = manager.StyleManager()

    def tearDown(self):
        manager.pubsub_singleton = self._pubsub_singleton_orig
        shutil.rmtree(self.app_path, ignore_errors=True)

    def test_basic(self):
        # self.mgr.render()
        # self.assertTrue(os.path.isdir(os.path.join(self.styles_path, 'basic')))
        pass  # todo


class TestClassStyleDefaults(unittest.TestCase):
    """Class (widget default) colors, fonts and defines apply to instances."""

    def setUp(self):
        self.pubsub = PubSub(app='joulescope_ui_style_cls_test')
        self.pubsub.registry_initialize()
        self._singletons = joulescope_ui.pubsub_singleton, manager.pubsub_singleton
        joulescope_ui.pubsub_singleton = self.pubsub
        manager.pubsub_singleton = self.pubsub
        self.app_path = self.pubsub.query('common/settings/paths/app')
        self.pubsub.topic_add('common/settings/profile/active', dtype='str', brief='profile', default='basic')
        self.pubsub.topic_add('registry/view/settings/active', dtype='str', brief='view', default='myview')
        self.mgr = manager.StyleManager()
        self.mgr.pubsub = self.pubsub
        self.mgr.enable = True
        self.pubsub.topic_add(manager.RENDER_TOPIC, dtype='obj', brief='render')
        self.pubsub.subscribe(manager.RENDER_TOPIC, self.mgr.on_action_render, ['pub'])
        Styled._style_cls = None
        self.pubsub.register(Styled, 'Styled')
        self.pubsub.register(StyledView, 'StyledView')
        self.view = StyledView()
        self.pubsub.register(self.view, 'myview')
        self.pubsub.publish(manager.RENDER_TOPIC, self.view)
        self.cls_topic = 'registry/Styled/settings'

    def tearDown(self):
        self.pubsub.unregister(self.view, delete=True)
        self.pubsub.unregister(StyledView, delete=True)
        self.pubsub.unregister(Styled, delete=True)
        joulescope_ui.pubsub_singleton, manager.pubsub_singleton = self._singletons
        shutil.rmtree(self.app_path, ignore_errors=True)

    def _instance(self):
        obj = Styled()
        self.pubsub.register(obj, parent='myview')
        self.pubsub.publish(manager.RENDER_TOPIC, obj)
        return obj

    def test_new_instance_has_no_overrides(self):
        self.pubsub.publish(f'{self.cls_topic}/colors', {'dark': {'a': _A}})
        obj = self._instance()
        self.assertIsNone(obj.colors)
        self.assertIsNone(obj.fonts)
        self.assertIsNone(obj.style_defines)
        self.assertEqual(_A, obj.style_obj['vars']['a'])

    def test_class_change_renders_existing_instances(self):
        obj = self._instance()
        count = obj.style_change_count
        self.pubsub.publish(f'{self.cls_topic}/colors', {'dark': {'a': _A}})
        self.assertEqual(_A, obj.style_obj['vars']['a'])
        self.assertGreater(obj.style_change_count, count)
        self.pubsub.publish(f'{self.cls_topic}/colors', {'dark': {'a': _B}})
        self.assertEqual(_B, obj.style_obj['vars']['a'])

    def test_class_change_skips_instances_outside_view(self):
        obj = Styled()
        self.pubsub.register(obj)  # no parent: not in the active view
        self.pubsub.publish(f'{self.cls_topic}/colors', {'dark': {'a': _A}})
        self.assertIsNone(obj.style_obj)

    def test_instance_override_wins(self):
        obj = self._instance()
        self.pubsub.publish(f'{obj.topic}/settings/colors', {'dark': {'a': _C}})
        self.pubsub.publish(f'{self.cls_topic}/colors', {'dark': {'a': _A, 'b': _B}})
        self.assertEqual(_C, obj.style_obj['vars']['a'])
        self.assertEqual(_B, obj.style_obj['vars']['b'])

    def test_fonts_and_defines(self):
        obj = self._instance()
        self.pubsub.publish(f'{self.cls_topic}/fonts', {'js1': {'f': '10pt Lato'}})
        self.pubsub.publish(f'{self.cls_topic}/style_defines', {'d': '4px'})
        self.assertEqual('10pt Lato', obj.style_obj['vars']['f'])
        self.assertEqual('4px', obj.style_obj['vars']['d'])

    def test_color_schemes_independent(self):
        obj = self._instance()
        self.pubsub.publish(f'{self.cls_topic}/colors', {'dark': {'a': _A}, 'light': {'a': _B}})
        self.assertEqual(_A, obj.style_obj['vars']['a'])
        self.pubsub.publish('registry/myview/settings/color_scheme', 'light')
        self.pubsub.publish(manager.RENDER_TOPIC, obj)
        self.assertEqual(_B, obj.style_obj['vars']['a'])

    def test_style_cls_ensure(self):
        self.assertIsNone(Styled._style_cls)
        style_cls = manager.style_cls_ensure(Styled)
        self.assertIs(style_cls, Styled._style_cls)
        self.assertIn('dark', style_cls['load']['colors'])
        self.assertIs(style_cls, manager.style_cls_ensure(Styled))

    def test_save_load(self):
        colors = {'dark': {'a': _A}}
        self.pubsub.publish(f'{self.cls_topic}/colors', colors)
        f = io.StringIO()
        self.pubsub.save(f)
        self.pubsub.publish(f'{self.cls_topic}/colors', None)
        f.seek(0)
        self.assertTrue(self.pubsub.load(f))
        self.assertEqual(colors, self.pubsub.query(f'{self.cls_topic}/colors'))
