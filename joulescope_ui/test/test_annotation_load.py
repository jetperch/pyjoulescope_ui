# Copyright 2023 Jetperch LLC
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
Test annotation load.
"""

import unittest
from unittest.mock import Mock
from joulescope_ui.jls_v2_annotations import load
import os


_MYPATH = os.path.dirname(os.path.abspath(__file__))
_ANNO1 = os.path.join(_MYPATH, 'anno1.anno.jls')


class TestAnnotationLoad(unittest.TestCase):

    def test_basic(self):
        pubsub = Mock()
        path = os.path.join(_ANNO1)
        thread = load(path, pubsub, 'registry/me/callbacks/!my_cbk')
        self.assertIsNotNone(thread)

        pubsub.publish.assert_has_calls([
            unittest.mock.call('registry/me/callbacks/!my_cbk', [
                {'annotation_type': 'y', 'plot_name': 'i', 'dtype': 'single', 'pos1': 0.009442977607250214, 'changed': True},
                {'annotation_type': 'y', 'plot_name': 'i', 'dtype': 'dual', 'pos1': 0.10405273735523224, 'pos2': 0.0934593677520752, 'changed': True},
                {'annotation_type': 'text', 'plot_name': 'i', 'text': 'Hello', 'text_show': True, 'shape': 0, 'x': 181706020277114630, 'y': 0.08213541656732559, 'y_mode': 'manual'},
                {'annotation_type': 'text', 'plot_name': 'i', 'text': 'End', 'text_show': True, 'shape': 3, 'x': 181706021440440961, 'y': None, 'y_mode': 'centered'},
                {'annotation_type': 'x', 'dtype': 'dual', 'pos1': 181706021444031554, 'pos2': 181706020837235312, 'changed': True, 'text_pos1': 'right', 'text_pos2': 'off'}
            ]),
            unittest.mock.call('registry/me/callbacks/!my_cbk', None),
        ])
        thread.join()
