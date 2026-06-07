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

"""Resolve, download and silently install a published Joulescope UI build.

A HIL bench runs the *installed* release (not ``pip install -e .``), so the
release_test workflow uses this module to pull the just-published installer for
the bench's ``(platform, arch)`` from ``index_v2.json``, verify its SHA-256, and
install it unattended.

The index schema mirrors :func:`ci.publish.build_summary`: each
``active[channel].platform[<key>]`` carries an ``installer`` path *relative to*
``joulescope_install/``, with a ``{installer}.sha256`` sidecar.

This module is Qt-free and does not import ``joulescope_ui`` (whose
``software_update`` consumer pulls in PySide6), so the resolver is unit-testable
without a display.

NOTE: the URL/index/sha256 resolution here overlaps with the Qt-coupled
``joulescope_ui/software_update.py``.  See
``docs/plans/dedup_software_update_resolver.md`` for the plan to factor the pure
resolver out of ``software_update`` so both import one copy.
"""

import hashlib
import logging
import os
import platform as _platform
import subprocess
import sys

_log = logging.getLogger(__name__)

#: Base URL the deployed UI and this resolver share (== software_update._URL_BASE).
URL_BASE = 'https://download.joulescope.com/joulescope_install/'
INDEX_URL = URL_BASE + 'index_v2.json'

CHANNELS = ('alpha', 'beta', 'stable')


def platform_key(system=None, machine=None):
    """Return the ``index_v2.json`` platform key for this machine.

    :param system: Override ``platform.system()`` (for testing).
    :param machine: Override ``platform.machine()`` (for testing).
    :return: 'windows' | 'windows_arm64' | 'macos' | 'ubuntu'.
    :raises RuntimeError: For an unsupported platform.
    """
    system = (system or _platform.system()).lower()
    machine = (machine or _platform.machine()).lower()
    is_arm = machine in ('arm64', 'aarch64')
    if system.startswith('win') or system == 'windows':
        return 'windows_arm64' if is_arm else 'windows'
    if system == 'darwin':
        return 'macos'           # universal2 build serves both arches
    if system == 'linux':
        return 'ubuntu'
    raise RuntimeError(f'unsupported platform: system={system!r} machine={machine!r}')


def installer_relpath(index, channel, key):
    """Return the installer path (relative to ``joulescope_install/``).

    :param index: The parsed ``index_v2.json`` dict.
    :param channel: 'alpha' | 'beta' | 'stable'.
    :param key: A platform key from :func:`platform_key`.
    :raises KeyError: If the channel/platform entry is missing.
    :return: The relative installer path string.
    """
    if channel not in CHANNELS:
        raise KeyError(f'unknown channel: {channel!r}')
    active = index.get('active', {})
    release = active.get(channel)
    if release is None:
        raise KeyError(f'channel {channel!r} has no active release')
    pinfo = release.get('platform', {}).get(key)
    if pinfo is None or 'installer' not in pinfo:
        raise KeyError(f'no installer for platform {key!r} in channel {channel!r}')
    return pinfo['installer']


def installer_urls(index, channel, key):
    """Return ``(installer_url, sha256_url)`` for the channel/platform."""
    rel = installer_relpath(index, channel, key)
    url = URL_BASE + rel
    return url, url + '.sha256'


def parse_sha256_sidecar(text):
    """Extract the hex digest from a ``{file}.sha256`` sidecar body.

    Sidecar format is ``"{hex} ./{filename}"`` (see
    :func:`ci._publish_common.sha256_sidecar`).
    """
    token = text.strip().split()[0]
    if len(token) != 64 or any(c not in '0123456789abcdefABCDEF' for c in token):
        raise ValueError(f'invalid sha256 sidecar: {text!r}')
    return token.lower()


def fetch_index(url=INDEX_URL, timeout=30.0):
    """Fetch and parse ``index_v2.json``."""
    import requests
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def download_installer(channel, dest_dir, *, index=None, key=None, timeout=120.0):
    """Download + SHA-256-verify the installer for ``channel`` on this platform.

    :param channel: 'alpha' | 'beta' | 'stable'.
    :param dest_dir: Directory to download into (created if needed).
    :param index: Pre-fetched index dict; default fetches :data:`INDEX_URL`.
    :param key: Platform key; default auto-detects via :func:`platform_key`.
    :raises ValueError: On a SHA-256 mismatch.
    :return: Path to the verified installer file.
    """
    import requests
    if index is None:
        index = fetch_index()
    if key is None:
        key = platform_key()
    url, sha_url = installer_urls(index, channel, key)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(url))

    _log.info('download installer %s', url)
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        h = hashlib.sha256()
        with open(dest, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
                    h.update(chunk)
    actual = h.hexdigest()

    expected = parse_sha256_sidecar(requests.get(sha_url, timeout=timeout).text)
    if actual != expected:
        raise ValueError(f'{dest}: sha256 mismatch (got {actual}, expected {expected})')
    _log.info('installer verified: %s', dest)
    return dest


def install(installer_path, *, system=None):
    """Silently install ``installer_path`` on the current platform.

    Runs on the HIL bench; not exercised by the offscreen unit tests.

    :return: For macOS/Ubuntu, the directory the app was installed/extracted to;
        for Windows, None (Inno Setup installs to its configured location).
    """
    system = (system or _platform.system()).lower()
    if system == 'windows':
        # Inno Setup unattended switches.
        subprocess.run([installer_path, '/VERYSILENT', '/SUPPRESSMSGBOXES',
                        '/NORESTART'], check=True)
        return None
    if system == 'darwin':
        return _install_macos_dmg(installer_path)
    if system == 'linux':
        return _extract_tar_gz(installer_path)
    raise RuntimeError(f'unsupported platform: {system!r}')


def _install_macos_dmg(dmg_path, apps_dir='/Applications'):
    """Mount a .dmg, copy the .app to ``apps_dir``, clear quarantine."""
    import plistlib
    import shutil
    out = subprocess.run(['hdiutil', 'attach', '-nobrowse', '-plist', dmg_path],
                         check=True, capture_output=True)
    plist = plistlib.loads(out.stdout)
    mount_point = None
    for entity in plist.get('system-entities', []):
        if entity.get('mount-point'):
            mount_point = entity['mount-point']
            break
    if mount_point is None:
        raise RuntimeError('could not determine .dmg mount point')
    try:
        app = next(n for n in os.listdir(mount_point) if n.endswith('.app'))
        dst = os.path.join(apps_dir, app)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(mount_point, app), dst)
        subprocess.run(['xattr', '-dr', 'com.apple.quarantine', dst], check=False)
        return dst
    finally:
        subprocess.run(['hdiutil', 'detach', mount_point], check=False)


def _extract_tar_gz(tar_path, dest_dir=None):
    """Extract a Ubuntu .tar.gz build and return the extraction directory."""
    import tarfile
    if dest_dir is None:
        dest_dir = os.path.join(os.path.dirname(tar_path), 'joulescope_app')
    os.makedirs(dest_dir, exist_ok=True)
    with tarfile.open(tar_path, 'r:gz') as tf:
        tf.extractall(dest_dir)   # trusted, self-published artifact
    return dest_dir


def locate_executable(install_dir=None, *, system=None):
    """Best-effort path to the installed ``joulescope`` executable.

    :param install_dir: Where :func:`install` placed the app (macOS/Ubuntu).
    :param system: Override platform (for testing).
    :return: The executable path, or None if it could not be located.
    """
    system = (system or _platform.system()).lower()
    if system == 'windows':
        for base in (os.environ.get('LOCALAPPDATA', ''), os.environ.get('ProgramFiles', '')):
            if not base:
                continue
            cand = os.path.join(base, 'Joulescope', 'joulescope.exe')
            if os.path.isfile(cand):
                return cand
        return None
    if system == 'darwin':
        if install_dir:
            name = os.path.splitext(os.path.basename(install_dir))[0]
            cand = os.path.join(install_dir, 'Contents', 'MacOS', name)
            if os.path.isfile(cand):
                return cand
        return None
    if system == 'linux':
        if install_dir:
            for root, _dirs, files in os.walk(install_dir):
                if 'joulescope' in files:
                    cand = os.path.join(root, 'joulescope')
                    if os.access(cand, os.X_OK):
                        return cand
        return None
    raise RuntimeError(f'unsupported platform: {system!r}')


def launch_command(executable=None):
    """Return the argv to launch the UI with the TCP server enabled.

    Falls back to the dev module invocation when no installed executable is
    given (``python -m joulescope_ui ui --tcp-server``).
    """
    if executable:
        return [executable, '--tcp-server']
    return [sys.executable, '-m', 'joulescope_ui', 'ui', '--tcp-server']
