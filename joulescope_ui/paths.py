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

from .locale import N_
from joulescope_ui import pubsub_singleton, CAPABILITIES, get_topic_name
import logging
import os


_DEFAULT_CAPABILITIES = {
    CAPABILITIES.STATISTIC_STREAM_SOURCE: 'defaults/statistics_stream_source',
    CAPABILITIES.SIGNAL_STREAM_SOURCE: 'defaults/signal_stream_source',
    CAPABILITIES.SIGNAL_BUFFER_SOURCE: 'defaults/signal_buffer_source',
}

SETTINGS = {
    'name': {
        'dtype': 'str',
        'brief': N_('The name for this widget.'),
        'default': N_('Paths'),
    },
    'path': {
        'dtype': 'str',
        'brief': N_('Default path'),
        'detail': N_('The default path for loading and saving files.'),
        'flags': ['ro', 'hide'],
        'default': None,
    },
    'fixed_path': {
        'dtype': 'str',
        'brief': N_('Fixed default path'),
        'detail': N_('The fixed default path for loading and saving files.'),
        'default': None,
    },
    'most_recent_save_path': {
        'dtype': 'str',
        'brief': N_('Most recent save path'),
        'flags': ['ro'],
        'default': None,
    },
    'most_recent_load_path': {
        'dtype': 'str',
        'brief': N_('Most recent load path'),
        'flags': ['ro'],
        'default': None,
    },
    'most_recent_path': {
        'dtype': 'str',
        'brief': N_('Most recent path'),
        'flags': ['ro'],
        'default': None,
    },
    'path_method': {
        'dtype': 'int',
        'brief': N_('The default path method'),
        'detail': N_(""""""),
        'options': [
            [0, N_('Fixed')],
            [1, N_('Most recent save path')],
            [2, N_('Most recent load path')],
            [3, N_('Most recently used path')],
        ],
        'default': 3,
    },
    'mru_files': {
        'dtype': 'obj',
        'brief': N_('Most recent file list'),
        'flags': ['ro', 'hide'],
        'default': [],
    },
    'mru_count': {
        'dtype': 'int',
        'brief': N_('Most recently used length'),
        'options': [
            [5, '5'],
            [10, '10'],
            [25, '25'],
        ],
        'default': 10,
    },
}


class Paths:
    """Singleton paths instance for global path settings."""

    def __init__(self):
        self._log = logging.getLogger(__name__)
        self._cbks = []
        self.SETTINGS = SETTINGS
        default = pubsub_singleton.query('common/settings/paths/data')
        for key in ['fixed_path',
                    'most_recent_save_path', 'most_recent_load_path',
                    'most_recent_path']:
            self.SETTINGS[key]['default'] = default

    def register(self):
        pubsub_singleton.register(self, 'paths')
        self._update()
        return self

    def _update_mru(self, value):
        value = os.path.abspath(value)
        topic = f'{get_topic_name(self)}/settings/mru_files'
        mru_files = pubsub_singleton.query(topic)
        mru_files = [f for f in mru_files if f != value]
        mru_files = [value] + mru_files[:(self.mru_count - 1)]
        pubsub_singleton.publish(topic, mru_files)
        return os.path.dirname(value)

    def on_action_mru_save(self, value):
        self._log.info('mru_save %s', value)
        path = self._update_mru(value)
        pubsub_singleton.publish(f'{get_topic_name(self)}/settings/most_recent_save_path', path)
        pubsub_singleton.publish(f'{get_topic_name(self)}/settings/most_recent_path', path)

    def on_action_mru_load(self, value):
        self._log.info('mru_load %s', value)
        path = self._update_mru(value)
        pubsub_singleton.publish(f'{get_topic_name(self)}/settings/most_recent_load_path', path)
        pubsub_singleton.publish(f'{get_topic_name(self)}/settings/most_recent_path', path)

    def _update(self):
        if not hasattr(self, 'unique_id'):
            return
        topic = get_topic_name(self)
        paths = [
            pubsub_singleton.query(f'{topic}/settings/fixed_path'),
            pubsub_singleton.query(f'{topic}/settings/most_recent_save_path'),
            pubsub_singleton.query(f'{topic}/settings/most_recent_load_path'),
            pubsub_singleton.query(f'{topic}/settings/most_recent_path'),
        ]
        idx = pubsub_singleton.query(f'{topic}/settings/path_method')
        path = paths[idx]
        pubsub_singleton.publish(f'{topic}/settings/path', path)
        self._log.info('path %s', path)

    def on_setting_fixed_path(self, value):
        self._update()

    def on_setting_most_recent_save_path(self, value):
        self._update()

    def on_setting_most_recent_load_path(self, value):
        self._update()

    def on_setting_most_recent_path(self, value):
        self._update()

    def on_setting_path_method(self, value):
        self._update()

    def on_setting_mru_count(self, value):
        if hasattr(self, 'unique_id'):
            topic = f'{get_topic_name(self)}/settings/mru_files'
            mru_files = pubsub_singleton.query(topic)
            mru_files = list(mru_files[:value])
            pubsub_singleton.publish(topic, mru_files)
