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


# pip install babel polib

from babel.messages.frontend import CommandLineInterface
import polib
import os
import re
import sys


_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PO_FILE = os.path.join(_PATH, 'joulescope_ui', 'locale', 'joulescope_ui.pot')
_whitespace = r'\s+'


with open(os.path.join(_PATH, 'joulescope_ui', 'version.py'), 'rt') as f:
    __version__ = f.readline().split('=')[1].strip()[1:-1]


def run_babel():
    os.chdir(os.path.join(_PATH, 'joulescope_ui'))
    babel_args = [
        sys.argv[0],
        'extract',
        '--no-default-keywords',
        '--keywords=N_',
        '--copyright-holder=Jetperch LLC',
        f'--version={__version__}',
        f"--input-dirs=.",
        f"--output-file={_PO_FILE}",
    ]
    rv = CommandLineInterface().run(babel_args)
    if rv not in [None, 0]:
        raise RuntimeError(f'BABEL failed with {rv}')


def _msgid_process(txt):
    txt = txt.strip()
    txt = re.sub(_whitespace, ' ', txt)
    return txt


def run_po_patch():
    print('Update POT msgid entries')
    pofile = polib.pofile(_PO_FILE)
    for entry in pofile:
        entry.msgid = _msgid_process(entry.msgid)
    pofile.save(_PO_FILE)
    return 0


if __name__ == '__main__':
    run_babel()
    run_po_patch()
