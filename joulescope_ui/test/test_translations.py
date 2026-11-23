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

"""
Check the translation catalogs for errors that break the UI.
"""

import gettext
import os
import re
import tempfile
import unittest
from unittest import mock
import polib
from joulescope_ui import locale

_LOCALE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'locale')
_PLACEHOLDER = re.compile(r'\{[^{}]*\}|%\([a-z_]+\)[sdfg]|%[sdfg]')
_TAG = re.compile(r'</?([a-zA-Z][a-zA-Z0-9]*)')
# Shown together in signal selectors, so each must translate to distinct text.
_SIGNAL_GROUPS = [
    ['Current', 'Voltage', 'Power'],
    ['current', 'voltage', 'power', 'charge', 'energy'],
]


def _catalogs():
    for locale in sorted(os.listdir(_LOCALE_PATH)):
        path = os.path.join(_LOCALE_PATH, locale, 'LC_MESSAGES', 'joulescope_ui.po')
        if os.path.isfile(path):
            yield locale, polib.pofile(path)


class TestTranslations(unittest.TestCase):

    def test_catalogs_found(self):
        self.assertGreater(len(list(_catalogs())), 0)

    def test_format(self):
        for locale, po in _catalogs():
            for e in po.translated_entries():
                with self.subTest(locale=locale, msgid=e.msgid):
                    self.assertEqual(sorted(_PLACEHOLDER.findall(e.msgid)),
                                     sorted(_PLACEHOLDER.findall(e.msgstr)), 'placeholders')
                    self.assertEqual(sorted(t.lower() for t in _TAG.findall(e.msgid)),
                                     sorted(t.lower() for t in _TAG.findall(e.msgstr)), 'tags')
                    self.assertEqual(e.msgid.count('\n'), e.msgstr.count('\n'), 'newlines')

    def test_signal_names_distinct(self):
        for locale, po in _catalogs():
            lookup = {e.msgid: e.msgstr for e in po.translated_entries() if not e.msgctxt}
            for group in _SIGNAL_GROUPS:
                with self.subTest(locale=locale, group=group):
                    names = [lookup.get(msgid, msgid) for msgid in group]
                    self.assertEqual(len(group), len({n.casefold() for n in names}), names)

    def test_context_entries_compile(self):
        with tempfile.TemporaryDirectory() as path:
            for locale_name, po in _catalogs():
                with self.subTest(locale=locale_name):
                    entries = [e for e in po.translated_entries() if e.msgctxt]
                    self.assertGreater(len(entries), 0)
                    mo_path = os.path.join(path, f'{locale_name}.mo')
                    po.save_as_mofile(mo_path)
                    with open(mo_path, 'rb') as f:
                        t = gettext.GNUTranslations(f)
                    for e in entries:
                        self.assertEqual(e.msgstr, t.pgettext(e.msgctxt, e.msgid))


class TestContextTranslate(unittest.TestCase):
    # Call through an alias so babel does not extract these test strings.

    def test_normalize_and_fallback(self):
        with mock.patch.object(locale, 'translate', gettext.NullTranslations()):
            translate = locale.C_
            self.assertEqual('Open', translate('state', '  Open\n'))

    def test_uses_context(self):
        t = mock.Mock()
        t.pgettext.return_value = 'Geöffnet'
        with mock.patch.object(locale, 'translate', t):
            translate = locale.C_
            self.assertEqual('Geöffnet', translate('state', 'Open'))
        t.pgettext.assert_called_once_with('state', 'Open')


class TestRightToLeft(unittest.TestCase):

    def _is_rtl(self, languages, translate):
        with mock.patch.object(locale, 'languages', languages), \
                mock.patch.object(locale, 'translate', translate):
            return locale.is_rtl()

    def test_rtl(self):
        catalog = mock.Mock(spec=gettext.GNUTranslations)
        self.assertTrue(self._is_rtl(['ar_SA', 'ar_SA'], catalog))
        self.assertTrue(self._is_rtl(['ar', 'ar'], catalog))
        self.assertFalse(self._is_rtl(['de_DE', 'de_DE'], catalog))

    def test_no_catalog_is_ltr(self):
        self.assertFalse(self._is_rtl(['ar', 'ar'], gettext.NullTranslations()))
