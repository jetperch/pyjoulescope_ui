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
import tempfile


_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INNO_SETUP_PATH = "ISCC.exe"

# Extensions for portable-executable (PE) files that carry signable code.
# Modern Windows (SmartScreen reputation, Smart App Control, WDAC/AppLocker)
# inspects the signatures of the DLLs/PYDs an application loads, not just the
# top-level launcher.  Every one of these must be signed or it is flagged as
# being of "unknown origin".
_SIGNABLE_EXTENSIONS = ('.exe', '.dll', '.pyd')


def _find_signable_files(path):
    """Recursively collect all signable PE files under a directory.

    :param path: The root directory to search.
    :return: The sorted list of absolute file paths to sign.
    """
    files = []
    for root, _, names in os.walk(path):
        for name in names:
            if name.lower().endswith(_SIGNABLE_EXTENSIONS):
                files.append(os.path.join(root, name))
    return sorted(files)


def azure_sign(paths):
    """Code sign one or more files using AzureSignTool.

    :param paths: A single path string or a list of path strings to sign.

    All files are signed in a single AzureSignTool invocation via an input
    file list, which avoids both command-line length limits and a separate
    Azure Key Vault + timestamp round-trip per file.
    """
    # https://melatonin.dev/blog/how-to-code-sign-windows-installers-with-an-ev-cert-on-github-actions/
    if isinstance(paths, str):
        paths = [paths]
    paths = [p for p in paths if p]
    if not paths:
        return
    AZURE_KEY_VAULT_URI = os.getenv('AZURE_KEY_VAULT_URI')
    if AZURE_KEY_VAULT_URI is None:
        print('sign SKIP : set AZURE_* environment variables to sign.')
        return

    cmd = [
        'AzureSignTool', 'sign',
        '-kvu', os.getenv('AZURE_KEY_VAULT_URI'),
        '-kvi', os.getenv('AZURE_CLIENT_ID'),
        '-kvt', os.getenv('AZURE_TENANT_ID'),
        '-kvs', os.getenv('AZURE_CLIENT_SECRET'),
        '-kvc', os.getenv('AZURE_CERT_NAME'),
        '-tr', 'http://timestamp.digicert.com',
        '-td', 'sha256',
        '-fd', 'sha256',
        '-s',  # skip files that are already signed
        '-v',
    ]

    list_path = None
    try:
        if len(paths) == 1:
            print(f'signing {paths[0]}')
            cmd.append(paths[0])
        else:
            print(f'signing {len(paths)} files')
            fd, list_path = tempfile.mkstemp(suffix='.txt', text=True)
            with os.fdopen(fd, 'wt', encoding='utf-8') as f:
                f.write('\n'.join(paths))
            # -mdop limits concurrent Key Vault calls to avoid throttling.
            cmd += ['-mdop', '4', '-ifl', list_path]
        rc = subprocess.run(cmd)
        rc.check_returncode()
    finally:
        if list_path is not None:
            os.remove(list_path)


def windows_release(path, suffix=None):
    """Create the Windows installer release.

    :param path: The path to the installer source binaries.
    :param suffix: The optional filename suffix for this distribution.
    """
    suffix = '' if suffix is None else str(suffix)

    # Sign every bundled executable, DLL, and PYD before packaging so that
    # Windows does not flag the loaded binaries as being of unknown origin.
    azure_sign(_find_signable_files(path))

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
    azure_sign(installer_final)
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
        sys.exit(windows_release(os.path.join(_PATH, 'dist', 'joulescope'), dist_suffix))
    except Exception as ex:
        print(ex)
        sys.exit(1)
