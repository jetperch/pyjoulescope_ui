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

import os
import shutil
import unittest
from joulescope_ui.pubsub import PubSub
from joulescope_ui.styles import manager


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
