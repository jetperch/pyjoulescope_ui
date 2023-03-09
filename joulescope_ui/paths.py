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
    'save_path': {
        'dtype': 'str',
        'brief': N_('Save path'),
        'detail': N_('The path for saving files.'),
        'flags': ['ro', 'hidden'],
        'default': None,
    },
    'load_path': {
        'dtype': 'str',
        'brief': N_('Load path'),
        'detail': N_('The path for loading files.'),
        'flags': ['ro', 'hidden'],
        'default': None,
    },
    'fixed_save_path': {
        'dtype': 'str',
        'brief': N_('Save path'),
        'detail': N_('The fixed path for saving files.'),
        'default': None,
    },
    'fixed_load_path': {
        'dtype': 'str',
        'brief': N_('Load path'),
        'detail': N_('The fixed path used for loading files.'),
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
    'load_path_method': {
        'dtype': 'int',
        'brief': N_('The load path method'),
        'detail': N_("""\
        Select the method to compute the load path.
        
        The load path can use a fixed value, the most recently used
        load path, or the most recently used path.
        """),
        'options': [
            [0, N_('fixed')],
            [1, N_('Most recent load path')],
            [2, N_('Most recently used path')],
        ],
        'default': 2,
    },
    'save_path_method': {
        'dtype': 'int',
        'brief': N_('The save path method'),
        'detail': N_(""""""),
        'options': [
            [0, N_('fixed')],
            [1, N_('Most recent load path')],
            [2, N_('Most recently used path')],
        ],
        'default': 2,
    },
    'mru_files': {
        'dtype': 'obj',
        'brief': N_('Most recent file list'),
        'flags': ['ro', 'hidden'],
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
        for key in ['fixed_save_path', 'fixed_load_path',
                    'most_recent_save_path', 'most_recent_load_path',
                    'most_recent_path']:
            self.SETTINGS[key]['default'] = default

    def register(self):
        pubsub_singleton.register(self, 'paths')
        self._update()
        return self

    def on_action_mru(self, value):
        topic = f'{get_topic_name(self)}/settings/mru_files'
        mru_files = pubsub_singleton.query(topic)
        mru_files = [value] + mru_files[:(self.mru_count - 1)]
        pubsub_singleton.publish(topic, mru_files)

    def _update(self):
        if not hasattr(self, 'unique_id'):
            return
        topic = get_topic_name(self)
        path = [
            pubsub_singleton.query(f'{topic}/settings/fixed_load_path'),
            pubsub_singleton.query(f'{topic}/settings/most_recent_load_path'),
            pubsub_singleton.query(f'{topic}/settings/most_recent_path'),
        ]
        idx = pubsub_singleton.query(f'{topic}/settings/load_path_method')
        pubsub_singleton.publish(f'{topic}/settings/load_path', path[idx])

        path = [
            pubsub_singleton.query(f'{topic}/settings/fixed_save_path'),
            pubsub_singleton.query(f'{topic}/settings/most_recent_save_path'),
            pubsub_singleton.query(f'{topic}/settings/most_recent_path'),
        ]
        idx = pubsub_singleton.query(f'{topic}/settings/save_path_method')
        pubsub_singleton.publish(f'{topic}/settings/save_path', path[idx])

    def on_setting_fixed_save_path(self, value):
        self._update()

    def on_setting_fixed_load_path(self, value):
        self._update()

    def on_setting_most_recent_save_path(self, value):
        self._update()

    def on_setting_most_recent_load_path(self, value):
        self._update()

    def on_setting_load_path_method(self, value):
        self._update()

    def on_setting_save_path_method(self, value):
        self._update()

    def on_setting_mru_count(self, value):
        if hasattr(self, 'unique_id'):
            topic = f'{get_topic_name(self)}/settings/mru_files'
            mru_files = pubsub_singleton.query(topic)
            mru_files = list(mru_files[:value])
            pubsub_singleton.publish(topic, mru_files)
