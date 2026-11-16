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

"""Test the Settings widget reset rows, see docs/plans/settings_reset.md."""

import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6 import QtWidgets
import joulescope_ui
from joulescope_ui import CAPABILITIES
from joulescope_ui.pubsub import PubSub
from joulescope_ui.styles import manager, styled_widget
from joulescope_ui.settings_reset import RESET_TOPIC, reset
from joulescope_ui.widgets.settings import settings_widget as sw


@styled_widget('Item')
class Item:
    CAPABILITIES = ['widget@']
    SETTINGS = {
        'gain': {'dtype': 'str', 'brief': 'gain', 'default': '1'},
    }


class TestSettingsWidgetReset(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.p = PubSub(app='joulescope_ui_settings_widget_test')
        self.p.registry_initialize()
        for capability in CAPABILITIES:
            self.p.register_capability(capability.value)
        self.p.register_command(RESET_TOPIC, lambda pubsub, topic, value: reset(pubsub, value))
        self.p.topic_add('registry/view/settings/active', dtype='str', brief='view', default='myview')
        self._singletons = joulescope_ui.pubsub_singleton, manager.pubsub_singleton
        joulescope_ui.pubsub_singleton = self.p
        manager.pubsub_singleton = self.p
        Item._style_cls = None
        self.p.register(Item, 'Item')
        self.item = Item()
        self.p.register(self.item)

    def tearDown(self):
        self.p.unregister(self.item, delete=True)
        self.p.unregister(Item, delete=True)
        joulescope_ui.pubsub_singleton, manager.pubsub_singleton = self._singletons

    def _editor(self, cls, obj):
        w = cls()
        w.pubsub = self.p
        w.object = obj
        return w

    @staticmethod
    def _bold(w):
        return {n for n, label in w._labels.items() if 'bold' in label.styleSheet()}

    def test_reset_text(self):
        self.assertEqual('Reset to defaults', sw._reset_text(self.p, self.item.unique_id))
        self.assertEqual('Reset to factory defaults', sw._reset_text(self.p, 'Item'))
        self.assertEqual('Reset Colors to defaults', sw._reset_text(self.p, self.item.unique_id, 'Colors'))
        self.assertEqual('Reset to factory default', sw._reset_text(self.p, 'Item', one=True))

    def test_settings_row(self):
        w = self._editor(sw.SettingsEditorWidget, self.item.unique_id)
        self.assertEqual(set(), self._bold(w))
        self.p.publish(f'{self.item.topic}/settings/gain', '2')
        self.assertEqual({'gain'}, self._bold(w))
        w._reset_name('gain')
        self.assertEqual('1', self.p.query(f'{self.item.topic}/settings/gain'))
        self.assertEqual(set(), self._bold(w))

    def test_color_rows(self):
        self.p.publish(f'{self.item.topic}/settings/colors', {'dark': {'a': '#112233ff'}})
        self.p.publish('registry/Item/settings/colors', {'dark': {'b': '#445566ff'}})
        w = self._editor(sw.ColorEditorWidget, self.item)
        self.assertEqual({'a', 'b'}, set(w._labels.keys()))
        self.assertEqual({'a'}, self._bold(w))  # b is inherited from the class
        w._reset_name('a')
        self.assertIsNone(self.p.query(f'{self.item.topic}/settings/colors'))
        self.assertEqual({'b'}, set(w._labels.keys()))  # rebuilt
        self.assertEqual(set(), self._bold(w))
        w = self._editor(sw.ColorEditorWidget, Item)
        self.assertEqual({'b'}, self._bold(w))  # vs factory
        self.assertEqual(1, len(w))
