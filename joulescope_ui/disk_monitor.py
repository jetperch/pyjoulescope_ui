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


from joulescope_ui import N_, Metadata, get_topic_name
import logging
import shutil


TIMER_TOPIC = 'registry/ui/events/blink_slow'
_FREE_THRESHOLD = 500_000_000


def disk_free(path):
    return shutil.disk_usage(path).free


class DiskMonitor:
    SETTINGS = {
        'free_threshold': {
            'dtype': 'int',
            'brief': 'The free threshold for declaring fullness',
            'default': _FREE_THRESHOLD,
        },
    }

    EVENTS = {
        'full': Metadata(dtype='obj',
                         brief='Disk is more full than threshold',
                         detail='The list of paths that indicate full',
                         flags=['ro', 'skip_undo']),
    }

    def __init__(self):
        self._log = logging.getLogger(__name__)
        self._paths = []

    def on_pubsub_register(self):
        self.pubsub.subscribe(TIMER_TOPIC, self._on_timer, ['pub'])

    def _on_timer(self):
        free_list = []
        for path in self._paths:
            free = disk_free(path)
            if free <= self.free_threshold:
                self._log.info('full: %s < %s: %s', free, self.free_threshold, path)
                free_list.append(path)
        if len(free_list):
            self._paths = [p for p in self._paths if p not in free_list]
            topic = get_topic_name(self)
            self.pubsub.publish(f'{topic}/events/full', free_list)

    def on_action_add(self, value):
        if isinstance(value, str):
            self._log.info('add %s', value)
            self._paths.append(value)

    def on_action_remove(self, value):
        if isinstance(value, str):
            try:
                self._paths.remove(value)
            except ValueError:
                self._log.info('remove but not present: %s', value)
