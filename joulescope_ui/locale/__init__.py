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

import gettext
import os
import re

__all__ = ['N_', 'gettext_locale_get']


if 'LANGUAGE_joulescope_ui' in os.environ:
    os.environ['LANGUAGE'] = os.environ['LANGUAGE_joulescope_ui']
elif 'LANGUAGE_joulescope' in os.environ:
    os.environ['LANGUAGE'] = os.environ['LANGUAGE_joulescope']


_whitespace = r'\s+'
PATH = os.path.dirname(os.path.abspath(__file__))
translate = gettext.translation('joulescope_ui', PATH, fallback=True)


def N_(txt):
    txt = txt.strip()
    txt = re.sub(_whitespace, ' ', txt)
    return translate.gettext(txt)


def gettext_locale_get():
    path = gettext.find('joulescope_ui', PATH)
    if path is None:
        return 'en'
    return path.split('\\')[-3]
