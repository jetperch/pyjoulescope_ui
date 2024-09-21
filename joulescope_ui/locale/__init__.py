# Copyright 2024 Jetperch LLC
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

import ctypes
import gettext
import os
import re
import sys


__all__ = ['N_', 'locale_get', 'locale_set', 'LOCALES']
_APP = 'joulescope'
_LOCALE_MAX_LENGTH = 256
_LOCALE_VARS = [
    'LANGUAGE_joulescope_ui', 'LANGUAGE_joulescope',
    'LANG_JOULESCOPE_UI', 'LANG_JOULESCOPE',
    'LANG_joulescope_ui', 'LANG_joulescope',
    'LANG',
]
_WHITESPACE_REGEX = re.compile(r'\s+')
LOCALES = [
    # [code, English name, native name]
    ['ar', 'Arabic', 'العربية'],
    ['de', 'German', 'Deutsch'],
    ['el', 'Greek', 'ελληνικά'],
    ['en', 'English (US)', 'English'],
    ['es', 'Spanish', 'español'],
    ['fr', 'French', 'français'],
    ['it', 'Italian', 'italiano'],
    ['ja', 'Japanese', '日本語'],
    ['ko', 'Korean', '한국어'],
    ['zh', 'Chinese (simplified)', '中文'],
]


def override_filename():
    if 'win32' in sys.platform:
        from win32com.shell import shell, shellcon
        appdata_path = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
        app_path = os.path.join(appdata_path, _APP)
    elif 'darwin' in sys.platform:
        app_path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', _APP)
    elif 'linux' in sys.platform:
        app_path = os.path.join(os.path.expanduser('~'), '.' + _APP)
    else:
        raise RuntimeError('unsupported platform')
    return os.path.join(app_path, 'language.txt')


def locale_set(lang):
    """Set the language using the language code.

    The application requires a restart after setting this code.
    """
    with open(override_filename(), 'wt') as f:
        f.write(lang)


def windows_locale():
    try:
        s = ctypes.create_unicode_buffer(_LOCALE_MAX_LENGTH)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(s, _LOCALE_MAX_LENGTH):
            return s.value
    except Exception:
        pass
    print('Could not detect Windows locale')
    return None


def env_locale():
    path = override_filename()
    if os.path.isfile(path):
        with open(path, 'rt') as f:
            return f.read()
    for v in _LOCALE_VARS:
        if v in os.environ:
            return os.environ[v].split('.')[0]
    return None


def locale_to_languages(locale_str):
    if locale_str is None:
        locale_str = 'en-US'
    locale_str = locale_str.split('.')[0]
    lang = locale_str.split('-')[0]
    return [locale_str, lang]


_locale_str = env_locale()
if _locale_str is None and sys.platform.startswith('win'):
    _locale_str = windows_locale()
languages = locale_to_languages(_locale_str)
# print(f'languages={languages}')
PATH = os.path.dirname(os.path.abspath(__file__))
translate = gettext.translation('joulescope_ui', PATH, languages=languages, fallback=True)


def N_(txt: str) -> str:
    """Normalize and translate text using the active locale."""
    txt = txt.strip()
    txt = _WHITESPACE_REGEX.sub(' ', txt)
    return translate.gettext(txt)


def locale_get():
    return _locale_str
