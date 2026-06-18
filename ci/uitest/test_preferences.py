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

"""Preferences persistence and "Clear config" behavior.

Maps to the "Preferences" rows of the test plan:
* App starts & accepts preferences from the previous release (config persists
  across a restart).
* File -> Clear config & Exit, then the app starts correctly from defaults.

Hardware-free.  Uses ``make_ui_session`` because it must control config-clear
across restarts (the default ``ui_session`` always clears on exit).
"""

import os

from uitest import discover

# A persisted, inert app setting to round-trip.  (Streaming-related settings
# like statistics_stream_enable are forced at startup when a device auto-opens,
# so they are NOT valid persistence probes.)  Config only persists on a clean
# exit, so the test asserts UiSession.exited_cleanly as well.
_PREF_TOPIC = 'registry/app/settings/device_update_check'


def test_preferences_persist_across_restart(make_ui_session):
    # Session 1: flip the preference, exit WITHOUT clearing -> config is saved.
    s1 = make_ui_session(config_clear_on_exit=False)
    original = bool(s1.query(_PREF_TOPIC))
    new_value = not original
    # Publishes are queued to the UI's pubsub thread, so confirm the change
    # landed (read-after-write) before relying on it / exiting.
    s1.publish_and_wait(_PREF_TOPIC, new_value)
    assert bool(s1.query(_PREF_TOPIC)) == new_value
    s1.stop()
    assert s1.exited_cleanly, 'UI was killed; config would not have been saved'

    # The config file should now exist on disk.
    config_path = discover.config_file_path()
    assert os.path.isfile(config_path), f'config not written to {config_path}'

    # Session 2: the preference survived the restart.
    s2 = make_ui_session(config_clear_on_exit=False)
    assert bool(s2.query(_PREF_TOPIC)) == new_value
    # Restore the original value so the test leaves no persistent side effect
    # (confirm it landed before the clean exit that writes the config).
    s2.publish_and_wait(_PREF_TOPIC, original)
    s2.stop()


def test_clear_config_resets_to_defaults(make_ui_session):
    config_path = discover.config_file_path()

    # Session 1: write a config, then exit WITH clear -> file removed.
    s1 = make_ui_session(config_clear_on_exit=False)
    s1.publish_and_wait(_PREF_TOPIC, not bool(s1.query(_PREF_TOPIC)))
    s1.stop()
    assert os.path.isfile(config_path)

    s2 = make_ui_session(config_clear_on_exit=True)
    s2.stop()
    assert not os.path.isfile(config_path), \
        f'Clear config did not remove {config_path}'

    # Session 3: the app starts cleanly from defaults after a clear.
    s3 = make_ui_session(config_clear_on_exit=True)
    assert s3.query('common/settings/paths/app')   # responsive => started OK
    s3.stop()
