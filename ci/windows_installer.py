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
import platform
import subprocess
import sys


_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INNO_SETUP_PATH = "ISCC.exe"


def windows_release(suffix=None):
    """Create the Windows installer release.

    :param suffix: The optional filename suffix for this distribution.
    """
    suffix = '' if suffix is None else str(suffix)

    # The workflow signs the bundled binaries before this step, and the
    # installer after it, with jetperch/github_actions/windows_sign.
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
    arch = '_arm64' if platform.machine().upper() in ('ARM64', 'AARCH64') else ''
    installer_final = f'{installer_exe_base}{arch}{suffix}{installer_exe_ext}'
    os.rename(installer_exe, installer_final)
    return 0


_ALLOWED = \
    'abcdefghijklmnopqrstuvwxyz' + \
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ' + \
    '0123456789' + \
    '_-'


def str_to_filename(s: str, maxlen=None) -> str:
    """Convert a string to a safe filename.

    :param s: The string to convert to a filename.
    :param maxlen: The maximum length for the string.
    """
    if maxlen is None:
        maxlen = 255 - 16  # 255 FAT - room for extension

    s = ''.join(['_' if c not in _ALLOWED else c for c in s])
    s = s[:maxlen]
    return s


if __name__ == '__main__':
    if len(sys.argv) == 2:
        dist_suffix = str_to_filename(f'_{sys.argv[1]}')
    else:
        dist_suffix = None
    try:
        sys.exit(windows_release(dist_suffix))
    except Exception as ex:
        print(ex)
        sys.exit(1)
