# Copyright 2022 Jetperch LLC
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

__all__ = ['N_']


# https://docs.python.org/3/library/gettext.html
# https://www.gnu.org/software/gettext/manual/gettext.html
# https://www.mattlayman.com/blog/2015/i18n/
# https://babel.pocoo.org/


PATH = os.path.dirname(os.path.abspath(__file__))
translate = gettext.translation('ui', PATH, fallback=True)
N_ = translate.gettext
