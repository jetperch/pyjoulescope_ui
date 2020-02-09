# Copyright 2019 Jetperch LLC
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
Implement the application default preferences.
"""

from joulescope_ui.preferences import Preferences, BASE_PROFILE


def multimeter_profile_default(preferences: Preferences):
    is_active = (preferences.profile == 'Multimeter')
    if 'Multimeter' in preferences.profiles:
        preferences.profile_remove('Multimeter')
    preferences.profile_add('Multimeter', activate=is_active)
    preferences.set('Widgets/active', ['Multimeter:1'], profile='Multimeter')
    preferences.set('General/window_size', 'minimum', profile='Multimeter')
    preferences.set('General/window_location', 'center', profile='Multimeter')
    preferences.set('Device/setting/i_range', 'auto', profile='Multimeter')


def oscilloscope_profile_default(preferences: Preferences):
    is_active = (preferences.profile == 'Oscilloscope')
    if 'Oscilloscope' in preferences.profiles:
        preferences.profile_remove('Oscilloscope')
    preferences.profile_add('Oscilloscope', activate=is_active)
    preferences.set('Widgets/active', ['Control:1', 'Waveform Control:2', 'Waveform:3'], profile='Oscilloscope')
    preferences.set('General/window_size', '75%', profile='Oscilloscope')
    preferences.set('General/window_location', 'center', profile='Oscilloscope')
    preferences.set('Device/setting/i_range', 'auto', profile='Oscilloscope')


def defaults_profile_default(preferences: Preferences):
    preferences.restore_base_defaults()


PROFILES_RESET = {
    BASE_PROFILE: defaults_profile_default,
    'Multimeter': multimeter_profile_default,
    'Oscilloscope': oscilloscope_profile_default,
}


def restore(preferences: Preferences, profile):
    PROFILES_RESET[profile](preferences)


def defaults(preferences: Preferences):
    p = preferences
    profiles = p.profiles
    if 'Multimeter' not in profiles:
        multimeter_profile_default(p)
        p.profile = 'Multimeter'
    if 'Oscilloscope' not in profiles:
        oscilloscope_profile_default(p)
    if 'defaults' == p.profile:
        p.profile = 'Multimeter'
