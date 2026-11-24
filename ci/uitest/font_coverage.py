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

"""Check that this computer's fonts can show every translated character.

The UI font (Lato) covers Latin text.  Other scripts rely on Qt's font
fallback, which needs an installed font for that writing system.  Missing
glyphs show as boxes.  Run on each platform::

    python ci/uitest/font_coverage.py [--json out.json]

The exit code is 1 when any character has no font.  See
docs/plans/translation_display_audit.md, stage 5.
"""

import argparse
import json
import os
import sys
import unicodedata

_CI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_CI)
_LOCALE_PATH = os.path.join(_ROOT, 'joulescope_ui', 'locale')
UI_FONT = 'Lato'

# Qt writing system names to check per locale, beyond Latin.
WRITING_SYSTEMS = {
    'ar': ['Arabic'],
    'el': ['Greek'],
    'ja': ['Japanese'],
    'ko': ['Korean'],
    'zh': ['SimplifiedChinese'],
}


def catalog_chars(po_path):
    """Return the set of displayable characters in a catalog's translations.

    Whitespace, control, and format characters are excluded, since they
    have no glyph.
    """
    import polib
    chars = set()
    for entry in polib.pofile(po_path):
        if entry.obsolete:
            continue
        for ch in entry.msgstr:
            if ch.isspace() or unicodedata.category(ch)[0] in ('C', 'Z'):
                continue
            chars.add(ch)
    return chars


def check(locales=None):
    """Check font coverage for each locale.

    :return: {locale: {'chars', 'ui_font_missing', 'fonts', 'missing'}}.
    """
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from PySide6 import QtGui, QtWidgets
    from joulescope_ui.resources import load_fonts, load_resources
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    resources = load_resources()  # noqa: F841 keep the resource data alive
    load_fonts()
    ui_font = QtGui.QRawFont.fromFont(QtGui.QFont(UI_FONT))
    if ui_font.familyName() != UI_FONT:
        raise RuntimeError(f'{UI_FONT} did not load; found {ui_font.familyName()!r}')
    db = QtGui.QFontDatabase
    results = {}
    for locale in locales or sorted(os.listdir(_LOCALE_PATH)):
        po_path = os.path.join(_LOCALE_PATH, locale, 'LC_MESSAGES', 'joulescope_ui.po')
        if not os.path.isfile(po_path):
            continue
        chars = catalog_chars(po_path)
        ui_missing = sorted(ch for ch in chars if not ui_font.supportsCharacter(ord(ch)))
        families = []
        for name in WRITING_SYSTEMS.get(locale, []) + ['Latin']:
            ws = getattr(db.WritingSystem, name)
            families.extend(f for f in db.families(ws) if f not in families)
        missing = []
        used = []
        raw = {}
        for ch in ui_missing:
            for family in families:
                font = raw.get(family)
                if font is None:
                    font = raw[family] = QtGui.QRawFont.fromFont(QtGui.QFont(family))
                if font.familyName() == family and font.supportsCharacter(ord(ch)):
                    if family not in used:
                        used.append(family)
                    break
            else:
                missing.append(ch)
        results[locale] = {'chars': len(chars), 'ui_font_missing': len(ui_missing),
                           'fonts': used, 'missing': missing}
    del app
    return results


def run(argv=None):
    p = argparse.ArgumentParser(description='Check translated text font coverage.')
    p.add_argument('--lang', action='append', help='Locale (repeat).  Default: all.')
    p.add_argument('--json', help='Write the results to this file.')
    args = p.parse_args(argv)
    results = check(args.lang)
    rc = 0
    for locale, r in results.items():
        status = 'ok' if not r['missing'] else 'MISSING ' + ''.join(r['missing'])
        print(f'{locale}: {r["chars"]} characters, {r["ui_font_missing"]} not in {UI_FONT}, '
              f'fallback {r["fonts"][:3]}: {status}')
        rc |= bool(r['missing'])
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    return int(rc)


if __name__ == '__main__':
    sys.exit(run())
