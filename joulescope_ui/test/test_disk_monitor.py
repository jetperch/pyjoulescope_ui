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
Test the disk monitor.
"""

import unittest
from unittest.mock import Mock
from joulescope_ui.pubsub import PubSub, Metadata
from joulescope_ui import disk_monitor, get_topic_name


class TestDiskMonitor(unittest.TestCase):

    def setUp(self) -> None:
        self.full = []
        self.disk_free = Mock()
        self.disk_free.return_value = 100_000_000_000
        self._disk_free_orig, disk_monitor.disk_free = disk_monitor.disk_free, self.disk_free
        self.pubsub = PubSub(app='test_disk_monitor')
        self.pubsub.registry_initialize()
        self.pubsub.topic_add(disk_monitor.TIMER_TOPIC, Metadata('none', 'event'))
        self.pubsub.register(disk_monitor.DiskMonitor)
        self.dm = disk_monitor.DiskMonitor()
        self.pubsub.register(self.dm, 'DiskMonitor:0')
        self.topic = get_topic_name(self.dm)
        self.pubsub.subscribe(f'{self.topic}/events/full', self._on_full)

    def tearDown(self):
        self.pubsub.unregister('DiskMonitor:0', delete=True)
        self.pubsub.unregister(disk_monitor.DiskMonitor, delete=True)
        disk_monitor.disk_free = self._disk_free_orig

    def _on_full(self, value):
        self.full.append(value)

    def check(self):
        self.pubsub.publish(disk_monitor.TIMER_TOPIC, None)

    def test_basic(self):
        self.pubsub.publish(f'{self.topic}/actions/!add', __file__)
        self.check()
        self.assertEqual([], self.full)
        self.disk_free.return_value = 1_000_000
        self.check()
        self.assertEqual([[__file__]], self.full)
        self.pubsub.publish(f'{self.topic}/actions/!remove', __file__)

    def test_remove(self):
        self.pubsub.publish(f'{self.topic}/actions/!add', __file__)
        self.pubsub.publish(f'{self.topic}/actions/!remove', __file__)
        self.disk_free.return_value = 1_000_000
        self.check()
        self.assertEqual([], self.full)
