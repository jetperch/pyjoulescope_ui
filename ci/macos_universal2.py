#!/usr/bin/env python3

# Copyright 2023 Jetperch LLC
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

"""Patch all install packages to universal2 on macOS."""


import json
import os
import platform
from re import L
import subprocess
import sys


platform1 = 'macosx_12_0_x86_64'
platform2 = 'macosx_12_0_arm64'
platform_out = 'macos_12_0_universal2'


def _run_cmd(cmd):
    print(f'RUN {cmd}')
    rv = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8')
    if rv.returncode:
        raise RuntimeError(f'command failed {rv}:\n{cmd}\n{rv.stdout}\n{rv.stderr}')
    return rv


def _run_pip_download(cmd):
    rv = _run_cmd(cmd)
    for line in rv.stdout.split('\n'):
        if line.startswith('Saved '):
            filename = line.split(' ', 1)[1]
            return filename
    raise RuntimeError(f'Could not parse return filename:\n{rv.stdout}')


def is_universal2_file(path):
    rv = _run_cmd(f'lipo -info {path}')
    return not ('Non-fat' in rv.stdout)


def is_universal2(package):
    rv = _run_cmd(f'pip show -f {package}')
    header = True
    for line in rv.stdout.split('\n'):
        line = line.strip()
        if line.startswith('Location: '):
            location = line.split(' ', 1)[1]
        if header:
            if line == 'Files:':
                header = False
            continue
        if line.endswith('.so'):
            if not is_universal2_file(f'{location}/{line}'):
                return False
    return True


def run():
    if platform.system() != 'Darwin':
        print('skip - only applies to macOS')
        return 0
    if not is_universal2_file(sys.executable):
        print(f'WARNING: python executable is not universal2: {sys.executable}')
    _run_cmd('pip install -U delocate')
    os.system('rm *.whl')
    rv = _run_cmd('pip list --format json')
    packages = json.loads(rv.stdout)
    for package in packages:
        name = package['name']
        version = package['version']
        if not is_universal2(name):
            print(f'PATCH {name}')
            f1 = _run_pip_download(f'pip download --only-binary :all: --platform {platform1} {name}=={version}')
            f2 = _run_pip_download(f'pip download --only-binary :all: --platform {platform2} {name}=={version}')
            _run_cmd(f'delocate-fuse {f1} {f2} -w .')
            _run_cmd(f'pip install --force-reinstall -f . {f1}')
    return 0


if __name__ == '__main__':
    sys.exit(run())
