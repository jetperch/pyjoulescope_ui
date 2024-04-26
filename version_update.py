#!/usr/bin/env python3
# Copyright 2021-2024 Jetperch LLC
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
Update the project version.

Use the most recently CHANGELOG as the definitive version for:
- CHANGELOG.md
- joulescope_ui/version.py
- joulescope_ui/locale/joulescope_ui.pot
- joulescope.iss
"""

import os
import re

MYPATH = os.path.dirname(os.path.abspath(__file__))


def _str(version, sep=None):
    sep = '.' if sep is None else sep
    return sep.join([str(x) for x in version])


def _changelog_version():
    path = os.path.join(MYPATH, 'CHANGELOG.md')
    with open(path, 'rt') as f:
        for line in f:
            if line.startswith('## '):
                version = line.split(' ')[1]
                return [int(x) for x in version.split('.')]


def _py_version(version):
    path = os.path.join(MYPATH, 'joulescope_ui', 'version.py')
    path_tmp = path + '.tmp'
    with open(path, 'rt') as rd:
        with open(path_tmp, 'wt') as wr:
            for line in rd:
                if line.startswith('__version__'):
                    line = f'__version__ = "{_str(version)}"\n'
                wr.write(line)
    os.replace(path_tmp, path)


def _locale_version(version):
    path = os.path.join(MYPATH, 'joulescope_ui', 'locale', 'joulescope_ui.pot')
    path_tmp = path + '.tmp'
    with open(path, 'rt') as rd:
        with open(path_tmp, 'wt') as wr:
            for line in rd:
                if line.strip().startswith('"Project-Id-Version:'):
                    parts = line.split(' ')
                    p_end = parts[-1].split('\\')[-1]
                    parts[-1] = f'{_str(version)}\\{p_end}'
                    line = ' '.join(parts)
                wr.write(line)
    os.replace(path_tmp, path)


def _iss_version(version):
    path = os.path.join(MYPATH, 'joulescope.iss')
    path_tmp = path + '.tmp'
    with open(path, 'rt') as rd:
        with open(path_tmp, 'wt') as wr:
            for line in rd:
                if line.startswith('#define MyAppVersion '):
                    line = f'#define MyAppVersion "{_str(version)}"\n'
                elif line.startswith('#define MyAppVersionUnderscores '):
                    line = f'#define MyAppVersionUnderscores "{_str(version, "_")}"\n'
                wr.write(line)
    os.replace(path_tmp, path)


def run():
    version = _changelog_version()
    print(f'Version = {_str(version)}')
    _py_version(version)
    _locale_version(version)
    _iss_version(version)
    return 0


if __name__ == '__main__':
    run()
