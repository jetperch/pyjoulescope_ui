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
import shutil

from uitest import config_fixtures, discover

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

    # Session 2: the preference survived the restart.  Clear on exit so the
    # saved config does not leak into later tests' UI sessions.
    s2 = make_ui_session(config_clear_on_exit=True)
    assert bool(s2.query(_PREF_TOPIC)) == new_value
    s2.stop()
    assert not os.path.isfile(config_path), 'config left on disk'


def test_clear_config_resets_to_defaults(make_ui_session):
    """File -> Config -> Clear and exit removes the config; the UI starts from defaults."""
    config_path = discover.config_file_path()

    # Session 1: write a config, then clear it through the File menu.
    s1 = make_ui_session(config_clear_on_exit=False)
    default = bool(s1.query(_PREF_TOPIC))
    s1.publish_and_wait(_PREF_TOPIC, not default)
    s1.menubar_invoke('File/Config/Clear and exit')
    s1.wait_for_root('QMessageBox')
    s1.qt_action('click', text='Yes')
    assert s1.wait_exit() == 0
    assert not os.path.isfile(config_path), f'Clear and exit did not remove {config_path}'

    # Session 2: the app starts cleanly from defaults.
    s2 = make_ui_session(config_clear_on_exit=True)
    assert bool(s2.query(_PREF_TOPIC)) == default
    s2.stop()


def test_previous_release_config(make_ui_session):
    """The UI starts with a config saved by the previous release and keeps its preferences.

    The configs are release assets; see :mod:`uitest.config_fixtures`.
    """
    from joulescope_ui import __version__
    versions = config_fixtures.previous_versions(__version__, 1)
    assert versions, f'no release before {__version__}'
    version = versions[0]
    shutil.copyfile(config_fixtures.release_config(version), discover.config_file_path())
    session = make_ui_session(config_clear_on_exit=True)
    for topic, value in config_fixtures.PREFS.items():
        assert session.query(topic) == value, f'{version} config: {topic} was not kept'
    mm = config_fixtures.multimeter_id(session)
    assert session.query(f'registry/{mm}/settings/precision') == \
        config_fixtures.MULTIMETER_PRECISION, f'{version} config: Multimeter precision was not kept'
