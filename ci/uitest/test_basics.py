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

"""Basics: the executable starts and Help -> About shows the correct versions.

Maps to the "Basics" rows of the JS220/JS110 test-plan tabs.  Hardware-free, so
these run on every platform (including CI runners under offscreen Qt).
"""

import joulescope_ui
from pyjoulescope_driver import __version__ as jsdrv_version
from pyjls import __version__ as jls_version

from uitest import qt


def test_executable_starts(ui_session):
    """The UI launched, the control socket answered, and a top-level window exists."""
    title = ui_session.qt_action('get_property', property='windowTitle')
    assert title.get('ok') is True
    assert 'Joulescope' in str(title.get('value', ''))


def test_about_shows_versions(ui_session):
    """Help -> About displays the UI, driver and JLS versions."""
    ui_session.publish('registry/help_html/actions/!show', 'about')
    ui_session.wait(0.6)
    tree = ui_session.qt_inspect(max_depth=40)
    missing = qt.all_texts_present(
        tree, [joulescope_ui.__version__, jsdrv_version, jls_version])
    assert not missing, f'About dialog missing version strings: {missing}'
