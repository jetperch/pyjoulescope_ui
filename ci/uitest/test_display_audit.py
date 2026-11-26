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

"""Pseudo-locale display check: no hardcoded English, no truncated text.

Runs the hardware-free screens of :mod:`uitest.display_audit` in the ``qps``
pseudo-locale.  Stage 8 of docs/plans/translation_display_audit.md.
"""

import os
import pytest
from uitest import display_audit, pseudo_locale


def test_pseudo_locale_screens(tmp_path):
    pytest.importorskip('PySide6')
    # The packaging sdist job runs this check.  The farm bench venvs lack polib.
    pytest.importorskip('polib')
    locale_path = str(tmp_path / '_locale')
    pseudo_locale.generate(pseudo_locale.pot_path(), locale_path)
    results = display_audit.run_locale(
        pseudo_locale.LOCALE, str(tmp_path), ['views', 'widgets', 'dialogs'], [(1280, 720)],
        locale_path, executable=os.environ.get('JS_UITEST_EXECUTABLE'))
    assert len(results) > 30
    errors = [(r['screen'], r['error']) for r in results if r.get('error')]
    english = [(r['screen'], t) for r in results for t in r.get('untranslated', [])]
    tooltips = [(r['screen'], t) for r in results for t in r.get('untranslated_tooltips', [])]
    truncated = [(r['screen'], t['text']) for r in results for t in r.get('truncated', [])]
    blank = [(r['screen'], b) for r in results for b in r.get('blank', [])]
    assert not errors, errors
    assert not english, english
    assert not tooltips, tooltips
    assert not truncated, truncated
    assert not blank, blank
