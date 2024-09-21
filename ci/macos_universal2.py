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

platform0 = 'macosx_12_0_x86_universal2'
platform1 = 'macosx_12_0_x86_64'
platform2 = 'macosx_12_0_arm64'


def _run_cmd(cmd):
    print(f'RUN {cmd}')
    rv = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8')
    print(rv.stdout)
    if bool(rv.stderr):
        print(f'STDERR:\n{rv.stderr}')
    if rv.returncode:
        print(f'RUN FAILED {rv}')
        rv.check_returncode()
    return rv


def _run_pip_download(cmd):
    rv = _run_cmd(cmd)
    for line in rv.stdout.split('\n'):
        if line.startswith('Saved '):
            filename = line.split(' ', 1)[1]
            return filename
    print(f'PIP_DOWNLOAD could not parse return filename')
    raise RuntimeError(f'PIP_DOWNLOAD could not parse return filename')


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

    # delocate 0.12.0 removed delocate-fuse, now delocate-merge
    _run_cmd('pip install -U "delocate>=0.12.0,<1" --report pip_install_delocate.json')
    with open('pip_install_delocate.json', 'rt') as f:
        delocate_report = json.load(f)
    os.remove('pip_install_delocate.json')
    delocate_packages = [x['metadata']['name'] for x in delocate_report['install']]
    print(f'delocate_packages: {" ".join(delocate_packages)}')

    os.system('rm *.whl')
    rv = _run_cmd('pip list --format json')
    packages = json.loads(rv.stdout)
    for package in packages:
        name = package['name']
        version = package['version']
        if name in delocate_packages:
            print(f'SKIP {name} in delocate_packages')
        elif not is_universal2(name):
            try:
                print(f'DOWNLOAD {name} universal2 if available')
                f3 = _run_pip_download(f'pip download --only-binary :all: --platform {platform0} {name}=={version}')
            except Exception:
                f3 = None
            if f3 is None or '-none-any' in f3:
                print(f'PATCH {name}')
                f1 = _run_pip_download(f'pip download --only-binary :all: --platform {platform1} {name}=={version}')
                f2 = _run_pip_download(f'pip download --only-binary :all: --platform {platform2} {name}=={version}')
                if 'x86_64' not in f1 or 'arm64' not in f2:
                    raise RuntimeError('Could not find matching files')
                _run_cmd(f'delocate-merge {f1} {f2} -w .')
                f3 = f2.replace('arm64', 'universal2')
            _run_cmd(f'pip install --force-reinstall -f . {f3}')
        else:
            print(f'SKIP {name} already universal2')

    _run_cmd(f'pip uninstall -y {" ".join(delocate_packages)}')
    return 0


if __name__ == '__main__':
    sys.exit(run())
