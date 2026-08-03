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

"""
Test joulescope_ui.widgets.waveform.waveform_source_widget
"""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from joulescope_ui.widgets.waveform.waveform_source_widget import WaveformSourceWidget


class _PubSubStub:

    def __init__(self):
        self.published = []

    def query(self, topic, default=None):
        return default

    def publish(self, topic, value):
        self.published.append((topic, value))


class _Host(QtWidgets.QWidget):

    def __init__(self, pubsub):
        super().__init__()
        self.topic = 'registry/WaveformWidget:test'
        self.pubsub = pubsub


class TestWaveformSourceWidget(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance()
        if cls._app is None:
            cls._app = QtWidgets.QApplication([])

    def setUp(self):
        self.pubsub = _PubSubStub()
        self.host = _Host(self.pubsub)
        self.widget = WaveformSourceWidget(self.host)

    def tearDown(self):
        self.host.deleteLater()

    def test_is_needed_single_default(self):
        self.widget._on_subsources('subsources', ['s.dev1'])
        self.widget._on_trace_subsources('trace_subsources', ['default', None, None, None])
        self.widget._on_trace_priority('trace_priority', [0, None, None, None])
        self.assertFalse(self.widget._is_needed())

    def test_is_needed_single_selected_matches(self):
        self.widget._on_subsources('subsources', ['s.dev1'])
        self.widget._on_trace_subsources('trace_subsources', ['s.dev1', None, None, None])
        self.widget._on_trace_priority('trace_priority', [0, None, None, None])
        self.assertFalse(self.widget._is_needed())

    def test_is_needed_single_selected_differs(self):
        self.widget._on_subsources('subsources', ['s.dev1'])
        self.widget._on_trace_subsources('trace_subsources', ['s.dev2', None, None, None])
        self.widget._on_trace_priority('trace_priority', [0, None, None, None])
        self.assertTrue(self.widget._is_needed())

    def test_is_needed_no_subsources(self):
        self.widget._on_subsources('subsources', [])
        self.assertFalse(self.widget._is_needed())

    def test_is_needed_multiple_subsources(self):
        self.widget._on_subsources('subsources', ['s.dev1', 's.dev2'])
        self.assertTrue(self.widget._is_needed())

    def test_is_needed_multiple_traces(self):
        self.widget._on_subsources('subsources', ['s.dev1'])
        self.widget._on_trace_subsources('trace_subsources', ['default', 's.dev1', None, None])
        self.widget._on_trace_priority('trace_priority', [0, 1, None, None])
        self.assertTrue(self.widget._is_needed())

    def test_is_needed_must_not_mutate_selection(self):
        # Regression: `for self._trace_subsources[0] in [...]` assigned
        # 'default' into the retained list, silently discarding the user's
        # trace source selection on view switch.
        retained = ['s.dev2', None, None, None]
        self.widget._on_trace_subsources('trace_subsources', retained)
        self.widget._on_trace_priority('trace_priority', [0, None, None, None])
        self.widget._on_subsources('subsources', ['s.dev1'])  # calls _is_needed
        self.assertEqual(['s.dev2', None, None, None], retained)
        self.assertEqual(['s.dev2', None, None, None], self.widget._trace_subsources)

    def test_handlers_copy_pubsub_values(self):
        # The values passed to the subscribers are the pubsub retained
        # objects; the widget must never hold or mutate them directly.
        subsources = ['s.dev1']
        trace_subsources = ['default', None, None, None]
        trace_priority = [0, None, None, None]
        self.widget._on_subsources('subsources', subsources)
        self.widget._on_trace_subsources('trace_subsources', trace_subsources)
        self.widget._on_trace_priority('trace_priority', trace_priority)
        self.assertIsNot(self.widget._subsources, subsources)
        self.assertIsNot(self.widget._trace_subsources, trace_subsources)
        self.assertIsNot(self.widget._trace_priorities, trace_priority)

    def test_default_construction_is_needed(self):
        # trace_priorities regression: a trailing comma made the initial
        # value a 1-tuple, so _is_needed() misread the trace priorities
        # before the first trace_priority publish arrived.
        self.widget._on_subsources('subsources', ['s.dev1'])
        self.assertFalse(self.widget._is_needed())


if __name__ == '__main__':
    unittest.main()
