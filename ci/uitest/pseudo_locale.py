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

"""Generate the ``qps`` pseudo-locale for the display audit.

Each string becomes ``⟦ÀççéñŧéðΓ·····⟧``: accented, about 40 % longer, and
bracketed, while placeholders, markup, entities, URLs, and line breaks stay
intact.  Text shown without the brackets never went through ``N_()``, and
clipped brackets show truncation.  See
docs/plans/translation_display_audit.md.

The catalog is generated at run time from the POT and is never committed.
Point the UI at it with ``JOULESCOPE_UI_LOCALE_PATH``.
"""

import math
import os
import re

LOCALE = 'qps'
OPEN = '⟦'
CLOSE = '⟧'
PAD = '·'
EXPANSION = 0.4

_PROTECT = re.compile(
    r'\{[^{}]*\}'                     # str.format placeholders
    r'|%\([a-z_]+\)[sdfg]|%[sdfg%]'    # printf placeholders
    r'|<[^<>]+>'                       # markup
    r'|&[a-zA-Z]+;|&#\d+;'             # entities
    r'|https?://\S+'                   # URLs
    r'|\n')
_ACCENTS = str.maketrans(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
    'àƀçđéƒĝĥíĵķľɱñóþǫŕšŧúṽŵẋýžÀƁÇĐÉƑĜĤÍĴĶĽṀÑÓÞǪŔŠŦÚṼŴẊÝŽ')


def pseudo(text):
    """Return the pseudo-localized text.

    :param text: The English source text (msgid).
    :return: The bracketed, accented, expanded text.
    """
    if not text:
        return text
    parts = []
    pos = 0
    for m in _PROTECT.finditer(text):
        parts.append(text[pos:m.start()].translate(_ACCENTS))
        parts.append(m.group(0))
        pos = m.end()
    parts.append(text[pos:].translate(_ACCENTS))
    visible = len(_PROTECT.sub('', text))
    pad = PAD * max(1, math.ceil(visible * EXPANSION))
    return OPEN + ''.join(parts) + pad + CLOSE


def pot_path():
    """Find the catalog template of the joulescope_ui under test.

    :return: The joulescope_ui.pot path.

    The farm's suite bundle holds no source tree, so look in the package that
    ``python -m joulescope_ui`` runs, without importing it.
    """
    import importlib.util
    spec = importlib.util.find_spec('joulescope_ui')
    return os.path.join(spec.submodule_search_locations[0], 'locale', 'joulescope_ui.pot')


def generate(pot_path, out_path):
    """Write the compiled pseudo-locale catalog.

    :param pot_path: The joulescope_ui.pot path.
    :param out_path: The locale directory to create.  The catalog is written
        to ``<out_path>/qps/LC_MESSAGES/joulescope_ui.mo``.
    :return: The .mo file path.
    """
    import polib  # not in the bench venvs, which hold only the UI and pytest
    pot = polib.pofile(pot_path)
    po = polib.POFile()
    po.metadata = {
        'Content-Type': 'text/plain; charset=utf-8',
        'Language': LOCALE,
        'Plural-Forms': 'nplurals=2; plural=(n != 1);',
    }
    for entry in pot:
        if entry.obsolete:
            continue
        po.append(polib.POEntry(msgctxt=entry.msgctxt, msgid=entry.msgid, msgstr=pseudo(entry.msgid)))
    path = os.path.join(out_path, LOCALE, 'LC_MESSAGES')
    os.makedirs(path, exist_ok=True)
    mo_path = os.path.join(path, 'joulescope_ui.mo')
    po.save_as_mofile(mo_path)
    return mo_path


def is_marked(text):
    """Check if all letters in displayed text came through the pseudo-locale.

    :param text: Displayed text.
    :return: True if the text has no ASCII words outside the brackets.
    """
    outside = re.sub(re.escape(OPEN) + r'.*?(' + re.escape(CLOSE) + r'|$)', ' ', text, flags=re.S)
    return re.search(r'[A-Za-z]{3,}', outside) is None
