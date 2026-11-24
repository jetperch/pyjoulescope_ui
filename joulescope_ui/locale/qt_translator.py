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

"""Translate Qt's own text, which uses ``tr()`` instead of gettext.

Qt dialogs and the Advanced Docking System (ADS) translate through
QTranslator.  This module installs Qt's ``qtbase`` translation for the
active language, when Qt ships one, and a translator that answers from
this application's gettext catalog.  See
docs/plans/translation_display_audit.md.
"""

import logging
from PySide6 import QtCore, QtGui
from . import C_, N_, translate, languages

_log = logging.getLogger(__name__)

# The ADS tr() strings, listed so that babel extracts them into the catalog.
# ADS lookups try the "ads" message context first, for words whose docking
# meaning differs: "Pin" hides a panel at a window edge.
ADS_CONTEXT = 'ads'
ADS_STRINGS = [
    N_('Close'), N_('Close Tab'), N_('Close Active Tab'), N_('Close Group'),
    N_('Close Other Groups'), N_('Close Others'), N_('Detach'), N_('Detach Group'),
    N_('List All Tabs'), N_('Minimize'), C_('ads', 'Pin'), N_('Pin Group'), N_('Pin Group To...'),
    N_('Pin To...'), N_('Pin Active Tab (Press Ctrl to Pin Group)'), N_('Unpin (Dock)'),
    N_('Show View'), N_('Top'), N_('Bottom'), N_('Left'), N_('Right'),
]


UI_FONT_FAMILY = 'Lato'

# Preferred fallback fonts for text that the UI font does not cover, listed for
# Windows, macOS, then Linux.  Han characters differ between Chinese, Japanese,
# and Korean, so each locale names its own regional font.  Without this list,
# Qt picks a fallback by system order, such as Japanese glyphs for Chinese.
FONT_FALLBACKS = {
    'ar': ['Segoe UI', 'Geeza Pro', 'Noto Sans Arabic', 'Noto Naskh Arabic', 'DejaVu Sans'],
    'el': ['Segoe UI', 'Helvetica Neue', 'Noto Sans', 'DejaVu Sans'],
    'ja': ['Yu Gothic UI', 'Meiryo UI', 'Hiragino Sans', 'Noto Sans CJK JP', 'Noto Sans JP'],
    'ko': ['Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans CJK KR', 'Noto Sans KR'],
    'zh': ['Microsoft YaHei UI', 'PingFang SC', 'Noto Sans CJK SC', 'Noto Sans SC',
           'WenQuanYi Micro Hei'],
}
_FONT_FALLBACK_DEFAULT = ['Segoe UI', 'Segoe UI Symbol', 'Helvetica Neue', 'Noto Sans', 'DejaVu Sans']


def font_fallbacks(lang=None):
    """Return the fallback font families for a language code."""
    if lang is None:
        lang = languages[0]
    lang = lang.replace('-', '_').split('_')[0].lower()
    return FONT_FALLBACKS.get(lang, []) + _FONT_FALLBACK_DEFAULT


def install_font_fallbacks():
    """Register the fallback fonts for the UI font family and active language."""
    QtGui.QFont.insertSubstitutions(UI_FONT_FAMILY, font_fallbacks())


class GettextTranslator(QtCore.QTranslator):
    """Answer Qt tr() lookups from the gettext catalog."""

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self._catalog = catalog

    def isEmpty(self):
        return False

    def translate(self, context, source_text, disambiguation=None, n=-1):
        # None becomes a null QString, which tells Qt to try the next translator
        # or use the source text.  An empty string would blank the text.
        if not source_text:
            return None
        if context and context.startswith('ads::'):
            text = self._catalog.pgettext(ADS_CONTEXT, source_text)
            if text != source_text:
                return text
        text = self._catalog.gettext(source_text)
        return None if text == source_text else text


def install(app):
    """Install the Qt translators and font fallbacks for the active language.

    :param app: The QApplication.
    :return: The list of installed translators.
    """
    install_font_fallbacks()
    installed = []
    ours = GettextTranslator(translate, app)
    app.installTranslator(ours)
    installed.append(ours)
    qt_locale = QtCore.QLocale(languages[0].replace('-', '_'))
    path = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
    qtbase = QtCore.QTranslator(app)
    if qt_locale.language() != QtCore.QLocale.Language.English and \
            qtbase.load(qt_locale, 'qtbase', '_', path):
        app.installTranslator(qtbase)  # installed last, so Qt asks it first
        installed.append(qtbase)
    else:
        _log.info('no qtbase translation for %s in %s', qt_locale.name(), path)
    return installed
