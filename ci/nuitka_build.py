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

import platform
import os
import shutil
import subprocess
import sys


_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INNO_SETUP_PATH = "ISCC.exe"


def is_windows():
    return platform.system() == 'Windows'


def azure_sign(path):
    # https://melatonin.dev/blog/how-to-code-sign-windows-installers-with-an-ev-cert-on-github-actions/
    AZURE_KEY_VAULT_URI = os.getenv('AZURE_KEY_VAULT_URI')
    if AZURE_KEY_VAULT_URI is None:
        return
    print(f'signing {path}')
    rc = subprocess.run(['AzureSignTool', 'sign',
                    '-kvu', os.getenv('AZURE_KEY_VAULT_URI'),
                    '-kvi', os.getenv('AZURE_CLIENT_ID'),
                    '-kvt', os.getenv('AZURE_TENANT_ID'),
                    '-kvs', os.getenv('AZURE_CLIENT_SECRET'),
                    '-kvc', os.getenv('AZURE_CERT_NAME'),
                    '-tr', 'http://timestamp.digicert.com',
                    '-v', path,
                    ])
    rc.check_returncode()


def sign(path):
    if is_windows():
        azure_sign(path)


def nuitka():
    # https://nuitka.net/index.html
    print('Run Nuitka')
    rc = subprocess.run(
        [
            sys.executable,
            '-m',
            'nuitka',
            '--standalone',
            '--assume-yes-for-downloads',
            '--plugin-enable=pyside6',
            '--python-flag=-m',
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
            '--output-filename=joulescope',
            'joulescope_ui',
        ],
        cwd=_PATH,
    )
    rc.check_returncode()

    path = os.path.join(_PATH, 'dist')
    os.makedirs(path, exist_ok=True)
    path = os.path.join(path, 'joulescope')
    shutil.move(os.path.join(_PATH, 'joulescope_ui.dist'), path)

    return path


def windows_release(path):
    # sign the executable
    sign(os.path.join(path, 'joulescope.exe'))

    print('Create Inno Setup installer')
    rc = subprocess.run(
        [
            _INNO_SETUP_PATH,
            os.path.join(_PATH, 'joulescope.iss')
        ],
        cwd=_PATH
    )
    rc.check_returncode()

    # sign the installer
    installer_path = os.path.join(_PATH, 'dist_installer')
    installer_exe = os.path.join(installer_path, os.listdir(installer_path)[0])
    installer_exe_base, installer_exe_ext = os.path.splitext(installer_exe)
    installer_final = f'{installer_exe_base}_nuitka{installer_exe_ext}'
    os.rename(installer_exe, installer_final)
    sign(installer_final)
    return 0


if __name__ == '__main__':
    rv = 0
    try:
        dist_path = nuitka()
        if is_windows():
            windows_release(dist_path)
    except Exception as ex:
        print(ex)
        rv = 1
    sys.exit(rv)
