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


# pip install babel polib deepl

from babel.messages.frontend import CommandLineInterface
import argparse
import deepl
import polib
import os
import re
import subprocess
import sys


LOCALES = [
    'ar',       # Arabic
    'de',       # German
    'el',       # Greek
    # 'en',     # English
    'es',       # Spanish
    'fr',       # French
    'ja',       # Japanese
    'ko',       # Korean
    # 'pt-BR',    # Portuguese (Brazil)
    'zh',       # Chinese (simplified)
]
_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_PATH = os.path.join(_PATH, 'joulescope_ui', 'locale')
POT_FILE = os.path.join(LOCALE_PATH, 'joulescope_ui.pot')
_whitespace = r'\s+'


with open(os.path.join(_PATH, 'joulescope_ui', 'version.py'), 'rt') as f:
    __version__ = f.readline().split('=')[1].strip()[1:-1]


def parser_config():
    """Capture streaming samples to a JLS v2 file."""
    p = argparse.ArgumentParser(
        description='Joulescope UI translation support',
    )
    p.add_argument('--preserve-create-date',
                   action='store_true',
                   help='Preserve the POT file creation date.')
    p.add_argument('--error-if-changed',
                   action='store_true',
                   help='Return an error if the POT or PO files change.')
    p.add_argument('--compile-only',
                   action='store_true',
                   help='Compile PO to MO only.')
    return p


def run_babel(preserve_create_date=False):
    os.chdir(os.path.join(_PATH, 'joulescope_ui'))
    if bool(preserve_create_date) and os.path.isfile(POT_FILE):
        metadata = polib.pofile(POT_FILE).metadata
    else:
        metadata = None
    babel_args = [
        sys.argv[0],
        'extract',
        '--no-default-keywords',
        '--keywords=N_',
        '--copyright-holder=Jetperch LLC',
        f'--version={__version__}',
        f"--input-dirs=.",
        f"--output-file={POT_FILE}",
    ]
    rv = CommandLineInterface().run(babel_args)
    if rv not in [None, 0]:
        raise RuntimeError(f'BABEL failed with {rv}')
    if metadata is not None:
        pofile = polib.pofile(POT_FILE)
        pofile.metadata['POT-Creation-Date'] = metadata['POT-Creation-Date']
        pofile.save(POT_FILE)


def _msgid_process(txt):
    txt = txt.strip()
    txt = re.sub(_whitespace, ' ', txt)
    return txt


def run_pot_patch():
    print('Update POT msgid entries')
    pofile = polib.pofile(POT_FILE)
    for entry in pofile:
        entry.msgid = _msgid_process(entry.msgid)
    pofile.save(POT_FILE)
    return 0


def run_po_update():
    data = {}
    for locale in LOCALES:
        path = os.path.join(LOCALE_PATH, locale, 'LC_MESSAGES')
        os.makedirs(path, exist_ok=True)
        outputfile = os.path.join(path, 'joulescope_ui.po')
        if not os.path.isfile(outputfile):
            print(f'create {locale}')
            babel_args = [
                sys.argv[0],
                'init',
                '-i', POT_FILE,
                '-o', outputfile,
                '-l', locale,
            ]
        else:
            print(f'update {locale}')
            babel_args = [
                sys.argv[0],
                'update',
                '-i', POT_FILE,
                '-o', outputfile,
                '-l', locale,
                '--previous',
            ]
        rv = CommandLineInterface().run(babel_args)
        if rv not in [None, 0]:
            raise RuntimeError(f'BABEL failed with {rv}')
        data[locale] = outputfile
    return data


def _text_patch(s):
    return s


def _text_unpatch(s):
    return s


def run_deepl(data):
    translator = deepl.Translator(os.getenv('DEEPL_AUTH'))
    for locale, path in data.items():
        pofile = polib.pofile(path)
        entries = pofile.untranslated_entries()
        text = [_text_patch(e.msgid) for e in entries]
        if len(text):
            print(f'{locale}: Translating {len(text)} entries')
            result = translator.translate_text(text, target_lang=locale, tag_handling='html')
            for r, entry in zip(result, entries):
                entry.msgstr = _text_unpatch(r.text)
        pofile.save(path)


def is_git_changed():
    rv = subprocess.run(['git', 'diff', '--ignore-all-space', '--exit-code'])
    return rv.returncode != 0


def run_compile():
    for locale in os.listdir(LOCALE_PATH):
        path_in = os.path.join(LOCALE_PATH, locale, 'LC_MESSAGES', 'joulescope_ui.po')
        if not os.path.isfile(path_in):
            continue
        pass
        path_out = path_in.replace('.po', '.mo')
        print(f'compile {locale}')
        babel_args = [
            sys.argv[0],
            'compile',
            '-i', path_in,
            '-o', path_out,
            '-l', locale,
            '--statistics',
        ]
        rv = CommandLineInterface().run(babel_args)
        if rv not in [None, 0]:
            raise RuntimeError(f'BABEL failed with {rv}')


def run():
    args = parser_config().parse_args()
    if not args.compile_only:
        run_babel(preserve_create_date=args.preserve_create_date)
        run_pot_patch()
        data = run_po_update()
        run_deepl(data)
    if args.error_if_changed and is_git_changed():
        print('ERROR: POT and/or PO file(s) changed')
        return 1
    run_compile()
    return 0


if __name__ == '__main__':
    sys.exit(run())
