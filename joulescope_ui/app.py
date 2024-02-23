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
        'brief': N_('The name for this application.'),
        'default': N_('app'),
    },
    'mode': {
        'dtype': 'str',
        'brief': 'The application mode for this invocation',
        'default': 'uninitialized',
        'options': [
            ['uninitialized'],  # default, changed at app start
            ['normal'],         # "normal" behavior
            ['file_viewer'],    # file viewer, for ".jls" file association.
        ],
        'flags': ['ro', 'hide', 'tmp', 'noinit', 'skip_undo'],
    },
    'target_power': {
        'dtype': 'bool',
        'brief': N_('Target power'),
        'detail': N_("""\
            Toggle the power to all connected targets.
            
            This feature forces all connected instruments to disable
            current flow.  You can use this feature to perform a
            power cycle reset for the connected target devices.
                 
            The JS220 disconnects the current terminals.
            
            The JS110 disconnects the current from IN+ to OUT+.
            The system setup must prevent excessive backwards current."""),
        'default': True,
    },
    'fuse_engaged': {
        'dtype': 'bool',
        'brief': N_('Fuse engaged indicator'),
        'detail': N_("""\
            This indicator becomes active when at least one connected
            instrument has an engaged fuse.  Instruments with 
            engaged fuses prevent current flow until cleared.  
            
            Press to clear."""),
        'default': False,
    },
    'statistics_stream_enable': {
        'dtype': 'bool',
        'brief': N_('Statistics display'),
        'detail': N_("""\
            Click to toggle live streaming statistics.
            
            When enabled, the widgets will display the statistics data
            as it arrives from the connected instruments.
            
            When disabled, hold the existing values.  New statistics data
            is processed, but widgets displaying statistics information
            do not update."""),
        'default': True,
        'flags': ['skip_undo'],
    },
    'statistics_stream_record': {
        'dtype': 'bool',
        'brief': N_('Statistics recording'),
        'detail': N_("""\
            Click to control streaming statistics data recording.
            
            Click once to start a recording to a CSV file.
            Click again to stop the recording.
            
            By default, Joulescopes provide statistics data at 2 Hz.
            Each device allows you to change this setting to the desired rate."""),
        'default': False,
        'flags': ['skip_undo'],
    },
    'signal_stream_enable': {
        'dtype': 'bool',
        'brief': N_('Signal sample streaming'),
        'detail': N_("""\
            Click to toggle sample data streaming.
            
            When enabled, stream sample data from all open sample sources
            and configure all sample widgets for acquisition mode.
            
            When disabled, stop sample streaming and configure
            all sample widgets for buffer mode.  
            """),
        'default': True,
        'flags': ['skip_undo'],
    },
    'signal_stream_record': {
        'dtype': 'bool',
        'brief': N_('Signal sample recording'),
        'detail': N_("""\
            Click to control signal sample recording.
            
            Click once to start a recording to a JLS file.
            Click again to stop the recording.
            
            The recording will capture data from all enabled 
            sample sources and signals at their configured sample rates.
            To reduce the file size, you can disable sources, 
            disable signals, and/or reduce the sample rates.
        """),
        'default': False,
        'flags': ['skip_undo'],
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
    'software_update_check': {
        'dtype': 'bool',
        'brief': N_('Check for software updates.'),
        'default': True,
    },
    'software_update_channel': {
        'dtype': 'str',
        'brief': N_('The software update channel.'),
        'default': 'stable',
        'options': [
            ['alpha', N_('alpha')],
            ['beta', N_('beta')],
            ['stable', N_('stable')],
        ]
    },
    'device_update_check': {
        'dtype': 'bool',
        'brief': N_('Check for device firmware updates.'),
        'default': True,
    },
    'units': {
        'dtype': 'str',
        'brief': N_('The units to display.'),
        'options': [
            ['SI', N_('International System of Units (SI)')],
            ['Xh', N_('Customary units (Ah and Wh)')],
        ],
        'default': 'SI',
    },
    'opengl': {
        'dtype': 'str',
        'brief': N_('Select the OpenGL rendering method.'),
        'detail': N_("""\
            This application uses OpenGL to accelerate graphics rendering.
            OpenGL has multiple options for rendering, which varies between
            platforms.  By default, this application uses "desktop" rendering.
            If OpenGL is not well-supported by your graphics drivers, 
            you can select "software" rendering.
            
            Selecting "ANGLE" may break copy as image and save as image.
            
            UI restart required for change to take effect. 
        """),
        'options': [
            ['desktop', N_('desktop')],
            ['angle', 'ANGLE'],
            ['software', N_('software')],
            ['dynamic', N_('Autodetect')],
            ['unspec', N_('Not specified')],
        ],
        'default': 'desktop',
    },
    'intel_graphics_prompt': {
        'dtype': 'bool',
        'brief': N_('Prompt to switch from Intel graphics to software renderer.'),
        'default': True,
        'flags': ['skip_undo'],
    },
}


_SETTINGS_VALUES_AT_START = {
    'statistics_stream_enable': True,
    'statistics_stream_record': False,
    'signal_stream_enable': True,
    'signal_stream_record': False,
}


class App:
    """Singleton application instance for global settings.

    These settings are persistent and do not depend upon the selected view.
    However, they are dependent upon the selected profile / session.
    For profile-invariant global settings, use "common/settings" subtopics.
    """

    SETTINGS = SETTINGS

    def __init__(self):
        self._log = logging.getLogger(__name__)
        self._cbks = []

    def _construct_capability_callback(self, capability):
        def cbk(value):
            self._on_capability_list(capability, value)
        return cbk

    def register(self, mode=None):
        p = pubsub_singleton
        topic = get_topic_name('app')
        if p.query(f'{topic}/settings/statistics_stream_enable', default=None) is not None:
            for key, value in _SETTINGS_VALUES_AT_START.items():
                p.publish(f'{topic}/settings/{key}', value)
        p.register(self, 'app')
        for capability in _DEFAULT_CAPABILITIES.keys():
            fn = self._construct_capability_callback(capability)
            self._cbks.append([capability, fn])
            self.pubsub.subscribe(f'registry_manager/capabilities/{capability}/list',
                                  fn, ['pub', 'retain'])
        if mode is not None:
            p.publish(f'{topic}/settings/mode', mode)
        return self

    def _on_capability_list(self, capability, value):
        self._log.info('Capability %s: %s', capability, value)
        base_topic = get_topic_name(self.unique_id)
        subtopic = _DEFAULT_CAPABILITIES[capability]
        topic = f'{base_topic}/settings/{subtopic}'
        default = pubsub_singleton.query(topic)
        if not len(value):
            value = None
        elif default is not None and default in value:
            # default found in list, keep
            return
        else:
            # default not in list, use first item in list
            value = value[0]
        if capability != CAPABILITIES.SIGNAL_BUFFER_SOURCE:
            pubsub_singleton.publish(topic, value)
        if capability == CAPABILITIES.SIGNAL_STREAM_SOURCE:
            pubsub_singleton.publish('registry/app/settings/defaults/signal_buffer_source',
                                     f'JsdrvStreamBuffer:001.{value}')

    def on_action_fuse_clear_all(self):
        pass
