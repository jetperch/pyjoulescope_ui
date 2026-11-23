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

import os
import re
import unittest
import polib

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
            lookup = {e.msgid: e.msgstr for e in po.translated_entries()}
            for group in _SIGNAL_GROUPS:
                with self.subTest(locale=locale, group=group):
                    names = [lookup.get(msgid, msgid) for msgid in group]
                    self.assertEqual(len(group), len({n.casefold() for n in names}), names)
