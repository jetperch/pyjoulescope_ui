# Copyright 2024 Jetperch LLC
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
Test the plugin manager
"""

import unittest
import joulescope_ui
from joulescope_ui.plugins.manager import PluginManager
from joulescope_ui.pubsub import PubSub
import os


_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')


class TestPluginManager(unittest.TestCase):

    def setUp(self):
        self.pubsub = PubSub()
        joulescope_ui.pubsub_singleton, self._pubsub_singleton = self.pubsub, joulescope_ui.pubsub_singleton
        self.pubsub.registry_initialize()
        self.m = PluginManager(paths=[_PATH])
        self.pubsub.register(self.m, 'plugins')

    def tearDown(self):
        self.m.on_action_unload('p1')
        self.m.on_action_unload('p2')
        joulescope_ui.pubsub_singleton = self._pubsub_singleton
        self.pubsub.unregister(PluginManager, delete=True)

    def test_load_unload_load(self):
        self.assertEqual([], sorted(self.m.active))
        self.assertEqual(['p1', 'p2'], sorted(self.m.available))
        self.m.on_action_load('p1')
        self.assertEqual(['p1'], sorted(self.m.active))
        self.assertIn('registry/P1', self.pubsub)
        self.assertEqual(1, self.pubsub.query('registry/P1/settings/counter'))

        # Manually unload then reload
        self.m.on_action_unload('p1')
        self.assertEqual([], sorted(self.m.active))
        self.m.on_action_load('p1')
        self.assertEqual(['p1'], sorted(self.m.active))
        self.assertEqual(2, self.pubsub.query('registry/P1/settings/counter'))

        # Just reload
        self.m.on_action_load('p1')
        self.assertEqual(['p1'], sorted(self.m.active))
        self.assertEqual(3, self.pubsub.query('registry/P1/settings/counter'))
