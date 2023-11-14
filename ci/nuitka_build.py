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

import os
import shutil
import subprocess
import sys


_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _changelog_version():
    path = os.path.join(_PATH, 'CHANGELOG.md')
    with open(path, 'rt') as f:
        for line in f:
            if line.startswith('## '):
                version = line.split(' ')[1]
                return version


def nuitka():
    dist_path = os.path.join(_PATH, 'dist')
    dst_path = os.path.join(dist_path, 'joulescope')
    if os.path.isdir(dst_path):
        shutil.rmtree(dst_path)

    version = _changelog_version()
    print(f'Release Joulescope UI {version} using Nuitka')

    # https://nuitka.net/index.html
    rc = subprocess.run(
        [
            sys.executable,
            '-m',
            'nuitka',
            '--standalone',
            '--company-name=Jetperch LLC',
            '--product-name=Joulescope UI',
            '--file-version=' + version,
            '--product-version=' + version,
            '--file-description=Joulescope UI',
            '--copyright=2023 Jetperch LLC',
            '--assume-yes-for-downloads',
            '--plugin-enable=pyside6',
            '--python-flag=-m',
            '--python-flag=no_docstrings',
            '--python-flag=isolated',
            '--msvc=latest',  # for Windows
            '--include-module=ctypes.util',
            '--include-module=joulescope.v0.driver',
            '--include-module=joulescope.v0.decimators',
            '--include-module=joulescope.v0.filter_fir',
            '--include-module=joulescope.units',
            '--nofollow-import-to=*.test',
            '--include-package-data=joulescope_ui',
            '--include-package-data=pyjoulescope_driver',
            '--include-data-files=CHANGELOG.md=CHANGELOG.md',
            '--include-data-files=CREDITS.html=CREDITS.html',
            '--include-data-files=LICENSE.txt=LICENSE.txt',
            '--include-data-files=README.md=README.md',
            '--windows-icon-from-ico=joulescope_ui/resources/icon.ico',
            '--disable-console',
            #'--force-stdout-spec=%HOME%/joulescope_%TIME%_%PID%.out.txt',
            #'--force-stderr-spec=%HOME%/joulescope_%TIME%_%PID%.err.txt',
            '--report=nuitka_report.xml',
            '--output-filename=joulescope',
            'joulescope_ui',
        ],
        cwd=_PATH,
    )
    rc.check_returncode()

    os.makedirs(dist_path, exist_ok=True)
    shutil.move(os.path.join(_PATH, 'joulescope_ui.dist'), dst_path)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(nuitka())
    except Exception as ex:
        print(ex)
        sys.exit(1)
