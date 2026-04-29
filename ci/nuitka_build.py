# Copyright 2023-2026 Jetperch LLC
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

import argparse
import os
import shutil
import subprocess
import sys
import PySide6


_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Nuitka only includes OpenGL software lib for QML or "all", so include manually
_PYSIDE6_PATH = os.path.dirname(PySide6.__file__)
_OPENGL32SW = os.path.join(_PYSIDE6_PATH, 'opengl32sw.dll').replace(r'\\', '/')
_OPENGL32DLL = os.path.basename(_OPENGL32SW)


def parser_config():
    """Capture streaming samples to a JLS v2 file."""
    p = argparse.ArgumentParser(
        description='Joulescope Windows build using Nuitka',
    )
    p.add_argument('--debug',
                   action='store_true',
                   help='Debug the Nuitka build.')
    return p


def _changelog_version():
    path = os.path.join(_PATH, 'CHANGELOG.md')
    with open(path, 'rt') as f:
        for line in f:
            if line.startswith('## '):
                version = line.split(' ')[1]
                return version.strip()


def nuitka():
    args = parser_config().parse_args()

    dist_path = os.path.join(_PATH, 'dist')
    dst_path = os.path.join(dist_path, 'joulescope')
    if os.path.isdir(dst_path):
        shutil.rmtree(dst_path)

    version = _changelog_version()
    print(f'Release Joulescope UI {version} using Nuitka')

    # https://nuitka.net/index.html
    cmd = [
        sys.executable,
        '-m',
        'nuitka',
        '--standalone',
        '--company-name=Jetperch LLC',
        '--product-name=Joulescope UI',
        '--file-version=' + version,
        '--product-version=' + version,
        '--file-description=Joulescope UI',
        '--copyright=2026 Jetperch LLC',
        '--assume-yes-for-downloads',
        '--plugin-enable=pyside6',
        '--python-flag=-m',
        '--python-flag=no_docstrings',
        '--python-flag=isolated',
        '--msvc=latest',  # for Windows
        '--windows-icon-from-ico=joulescope_ui/resources/icon.ico',
        '--include-module=ctypes.util',
        '--include-module=joulescope.v0.driver',
        '--include-module=joulescope.v0.decimators',
        '--include-module=joulescope.v0.filter_fir',
        '--include-module=joulescope.units',
        '--include-module=PySide6.QtOpenGL',   # added 2025-12-02 for Qt 6.10.1
        #'--include-windows-runtime-dlls=yes',
        '--nofollow-import-to=*.test',
        '--include-package-data=joulescope_ui',
        '--include-package-data=pyjoulescope_driver',
        '--include-data-files=CHANGELOG.md=CHANGELOG.md',
        '--include-data-files=CREDITS.html=CREDITS.html',
        '--include-data-files=LICENSE.txt=LICENSE.txt',
        '--include-data-files=README.md=README.md',
        '--report=nuitka_report.xml',
        '--output-filename=joulescope',
    ]

    if os.path.isfile(_OPENGL32SW):
        # include OpenGL software renderer (for Intel UHD)
        cmd.append(f'--include-data-file={_OPENGL32SW}={_OPENGL32DLL}')
    if False:  # nuitka debug
        cmd.append('--debug')
        cmd.append('--no-debug-immortal-assumptions')
    elif args.debug:  # Joulescope UI build debug
        cmd.append('--windows-console-mode=force')
        #'--embed-debug-qt-resources',
    else:
        cmd.append('--windows-console-mode=disable')

    cmd.append('joulescope_ui')

    rc = subprocess.run(cmd, cwd=_PATH)
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
