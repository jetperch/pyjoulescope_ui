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


class App:
    """Singleton application instance for global settings.

    These settings are persistent and do not depend upon the selected view.
    However, they are dependent upon the selected profile / session.
    For profile-invariant global settings, use "common/settings" subtopics.
    """

    SETTINGS = {
        'name': {
            'dtype': 'str',
            'brief': N_('The name for this widget.'),
            'default': N_('app'),
        },
        'statistics_stream_enable': {
            'dtype': 'bool',
            'brief': N_('Statistics display control.'),
            'default': True,
        },
        'statistics_stream_record': {
            'dtype': 'bool',
            'brief': N_('Statistics record control.'),
            'default': False,
        },
        'signal_stream_enable': {
            'dtype': 'bool',
            'brief': N_('Signal stream enable control.'),
            'default': True,
        },
        'signal_stream_record': {
            'dtype': 'bool',
            'brief': N_('Signal stream record control.'),
            'default': False,
        },
        'defaults/statistics_stream_source': {
            'dtype': 'str',
            'brief': N_('The default unique_id for the default statistics streaming source.'),
            'default': None,
        },
        'defaults/signal_stream_source': {
            'dtype': 'str',
            'brief': N_('The unique_id for the default signal streaming source.'),
            'default': None,
        },
        'defaults/signal_buffer_source': {
            'dtype': 'str',
            'brief': N_('The unique_id for the default signal buffer source.'),
            'default': None,
        },
    }

    def __init__(self):
        self._log = logging.getLogger(__name__)
        self._cbks = []

    def _construct_capability_callback(self, capability):
        def cbk(value):
            self._on_capability_list(capability, value)
        return cbk

    def register(self):
        pubsub_singleton.register(self, 'app')
        for capability in _DEFAULT_CAPABILITIES.keys():
            fn = self._construct_capability_callback(capability)
            self._cbks.append([capability, fn])
            pubsub_singleton.subscribe(f'registry_manager/capabilities/{capability}/list',
                                       fn, ['pub', 'retain'])
        return self

    def _on_capability_list(self, capability, value):
        base_topic = get_topic_name(self.unique_id)
        subtopic = _DEFAULT_CAPABILITIES[capability]
        topic = f'{base_topic}/settings/{subtopic}'
        default = pubsub_singleton.query(topic)
        if not len(value):
            # no sources found, clear default
            pubsub_singleton.publish(topic, None)
        elif default is not None and default in value:
            # default found in list, keep
            pass
        else:
            # default not in list, use first item in list
            pubsub_singleton.publish(topic, value[0])
