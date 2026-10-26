#!/usr/bin/env python3
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

"""Generate .github/ISSUE_TEMPLATE/*.yml from ci/issue_forms.yaml.

Usage (normally invoked by version_update.py):
    python ci/issue_forms.py [--check]
"""

import argparse
import os
import sys
import yaml

_CI = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_CI)
SOURCE = os.path.join(_CI, 'issue_forms.yaml')
OUT_DIR = os.path.join(_ROOT, '.github', 'ISSUE_TEMPLATE')
HEADER = '# Generated from ci/issue_forms.yaml by ci/issue_forms.py. DO NOT EDIT.\n'


class _Dumper(yaml.SafeDumper):
    """Indent block sequences and never emit anchors."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def ignore_aliases(self, data):
        return True


def _str_representer(dumper, data):
    style = '|' if '\n' in data else None
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style=style)


_Dumper.add_representer(str, _str_representer)


def _read_version():
    path = os.path.join(_ROOT, 'joulescope_ui', 'version.py')
    with open(path, 'rt') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip('"\'')
    raise ValueError('__version__ not found')


def _substitute(obj, version):
    if isinstance(obj, str):
        return obj.replace('{version}', version)
    if isinstance(obj, list):
        return [_substitute(x, version) for x in obj]
    if isinstance(obj, dict):
        return {k: _substitute(v, version) for k, v in obj.items()}
    return obj


def render(version, source=None):
    """Render the issue forms.

    :param version: The UI version string, such as "1.7.4".
    :param source: The source YAML path.  None uses ci/issue_forms.yaml.
    :return: The map of filename to file contents.
    """
    with open(source or SOURCE, 'rt', encoding='utf-8') as f:
        src = yaml.safe_load(f)
    result = {}
    for name, form in src['forms'].items():
        form = _substitute(form, version)
        body = yaml.dump(form, Dumper=_Dumper, sort_keys=False,
                         allow_unicode=True, width=1000)
        result[f'{name}.yml'] = HEADER + body
    return result


def generate(version=None, check=False):
    """Write (or check) the issue forms.

    :param version: The UI version string.  None reads joulescope_ui/version.py.
    :param check: When True, do not write and only report stale files.
    :return: The list of stale (check) or written filenames.
    """
    version = version or _read_version()
    changed = []
    for fname, contents in render(version).items():
        path = os.path.join(OUT_DIR, fname)
        try:
            with open(path, 'rt', encoding='utf-8') as f:
                existing = f.read()
        except FileNotFoundError:
            existing = None
        if existing == contents:
            continue
        changed.append(fname)
        if not check:
            with open(path, 'wt', encoding='utf-8', newline='\n') as f:
                f.write(contents)
    return changed


def run():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true',
                        help='Exit 1 if any generated form is stale.')
    args = parser.parse_args()
    changed = generate(check=args.check)
    for fname in changed:
        print(f'{"stale" if args.check else "updated"}: {fname}')
    return 1 if (args.check and changed) else 0


if __name__ == '__main__':
    sys.exit(run())
