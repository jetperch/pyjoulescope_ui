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

"""Offline feedback loop for ci/publish.py + ci/release_update.py.

Exercises the entire publish pipeline with no AWS and no network: it publishes
fabricated installers to a LocalBackend, promotes the release, and then feeds
the generated index_v2.json back through the real
joulescope_ui.software_update consumer (including the .sha256 download + hash
validation) for every platform key.  This is the end-to-end guarantee that
deployed Joulescope UIs will keep updating.

Run from the repository root:
    pytest ci/test_publish.py
"""

import json
import os
import sys

import pytest

_CI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _CI)

import _publish_common as common  # noqa: E402
import publish  # noqa: E402
import release_update  # noqa: E402


VERSION = publish.read_version()
V = common.version_tuple(VERSION)
VFS = common.version_filename_part(VERSION)
VDIR = '/'.join(str(x) for x in V)


def _make_dist(tmp_path):
    """Create a fake dist_installer/ with uniquely-keyed dummy artifacts."""
    dist = tmp_path / 'dist_installer'
    dist.mkdir()
    files = {
        f'joulescope_setup_{VFS}_nuitka.exe': b'WIN_X86_NUITKA',
        f'joulescope_setup_{VFS}_pyinstaller.exe': b'WIN_X86_PYINSTALLER',
        f'joulescope_setup_arm64_{VFS}_nuitka.exe': b'WIN_ARM_NUITKA',
        f'joulescope_setup_arm64_{VFS}_pyinstaller.exe': b'WIN_ARM_PYINSTALLER',
        f'joulescope_{VFS}.dmg': b'MACOS_DMG',
        f'joulescope_{VFS}.tar.gz': b'UBUNTU_TARGZ',
        'CHANGELOG.md': b'# changelog\n',
    }
    for name, data in files.items():
        (dist / name).write_bytes(data)
    return str(dist), files


def _read_index(root):
    path = os.path.join(root, *common.INDEX_KEY.split('/'))
    with open(path, 'rb') as f:
        return json.load(f)


def test_publish_layout_and_schema(tmp_path):
    dist, _ = _make_dist(tmp_path)
    root = str(tmp_path / 'store')
    publish.publish(common.LocalBackend(root), dist_dir=dist)

    base = os.path.join(root, 'joulescope_install', *VDIR.split('/'))
    exe = os.path.join(base, f'joulescope_setup_{VFS}.exe')
    arm = os.path.join(base, f'joulescope_setup_arm64_{VFS}.exe')

    # Canonical names exist, the Nuitka build won, PyInstaller was dropped.
    assert open(exe, 'rb').read() == b'WIN_X86_NUITKA'
    assert open(arm, 'rb').read() == b'WIN_ARM_NUITKA'
    assert os.path.isfile(os.path.join(base, f'joulescope_{VFS}.dmg'))
    assert os.path.isfile(os.path.join(base, f'joulescope_{VFS}.tar.gz'))
    assert not any('pyinstaller' in n for n in os.listdir(base))

    # Every release file has a correctly-formatted .sha256 sidecar.
    sidecar = open(exe + '.sha256').read()
    assert sidecar == common.sha256_sidecar(
        common.sha256_bytes(b'WIN_X86_NUITKA'), f'joulescope_setup_{VFS}.exe')

    index = _read_index(root)
    alpha = index['active']['alpha']
    assert alpha['version'] == V
    assert index['versions'][0]['version'] == V
    rel = alpha['releases']
    for key in ['win10_x86_64', 'win11_x86_64', 'win10_arm64', 'win11_arm64',
                'macos_26_0_arm64', 'macos_15_0_x86_64', 'ubuntu_24_04_x86_64']:
        assert rel[key].startswith(VDIR + '/'), key
    assert rel['win10_x86_64'] == f'{VDIR}/joulescope_setup_{VFS}.exe'
    assert rel['win11_arm64'] == f'{VDIR}/joulescope_setup_arm64_{VFS}.exe'

    html = open(os.path.join(root, *common.INDEX_HTML_KEY.split('/'))).read()
    assert 'Windows (ARM64)' in html
    assert 'index_v1.html' in html


def test_publish_is_idempotent_and_preserves_history(tmp_path):
    dist, _ = _make_dist(tmp_path)
    root = str(tmp_path / 'store')
    backend = common.LocalBackend(root)

    # Seed a prior, older release so we can confirm history is preserved.
    older = {'version': [0, 0, 1], 'platform': {}, 'releases': {},
             'changelog': '0/0/1/CHANGELOG.md'}
    backend.put(common.INDEX_KEY,
                common.dumps_index({'active': {}, 'versions': [older]}).encode(),
                common.CONTENT_TYPE_JSON)

    publish.publish(backend, dist_dir=dist)
    publish.publish(backend, dist_dir=dist)  # republish same version

    index = _read_index(root)
    matching = [x for x in index['versions'] if x['version'] == V]
    assert len(matching) == 1                      # no duplicate
    assert [0, 0, 1] in [x['version'] for x in index['versions']]  # history kept


def test_release_update_promotes_without_touching_files(tmp_path):
    dist, _ = _make_dist(tmp_path)
    root = str(tmp_path / 'store')
    backend = common.LocalBackend(root)
    publish.publish(backend, dist_dir=dist)

    base = os.path.join(root, 'joulescope_install', *VDIR.split('/'))
    before = {n: open(os.path.join(base, n), 'rb').read()
              for n in os.listdir(base)}
    versions_before = _read_index(root)['versions']

    release_update.release_update(backend, VERSION, 'stable')

    index = _read_index(root)
    assert index['active']['stable']['version'] == V
    assert index['versions'] == versions_before    # history untouched
    after = {n: open(os.path.join(base, n), 'rb').read()
             for n in os.listdir(base)}
    assert after == before                          # release files untouched


def test_release_update_missing_version_raises(tmp_path):
    dist, _ = _make_dist(tmp_path)
    root = str(tmp_path / 'store')
    backend = common.LocalBackend(root)
    publish.publish(backend, dist_dir=dist)
    with pytest.raises(RuntimeError):
        release_update.release_update(backend, '99.99.99', 'stable')


def test_consumer_round_trip(tmp_path, monkeypatch):
    """The real software_update consumer resolves and downloads each platform."""
    pytest.importorskip('requests')
    pytest.importorskip('PySide6')
    from joulescope_ui import software_update as su

    dist, _ = _make_dist(tmp_path)
    root = str(tmp_path / 'store')
    backend = common.LocalBackend(root)
    publish.publish(backend, dist_dir=dist)
    index = _read_index(root)
    releases = index['active']['alpha']['releases']

    base = su._URL_BASE

    class FakeResponse:
        def __init__(self, data):
            self.content = data
            self.text = data.decode('utf-8', errors='replace')

    def fake_get(url, timeout=None):
        assert url.startswith(base), url
        rel = url[len(base):]
        body, _ = backend.get(f'{common.PREFIX}/{rel}')
        if body is None:
            raise FileNotFoundError(url)
        return FakeResponse(body)

    monkeypatch.setattr(su, 'requests', type('R', (), {'get': staticmethod(fake_get)}))
    # Pretend we are running an older version so an update is "available".
    monkeypatch.setattr(su, 'current_version', lambda: [0, 0, 0])

    for platform_key, rel_path in releases.items():
        monkeypatch.setattr(su, '_platform_name', lambda k=platform_key: k)
        info = su.fetch_info('alpha')
        assert info is not None, platform_key
        assert info['download_url'] == base + rel_path
        assert info['changelog_url'].endswith('/CHANGELOG.md')

        # End-to-end download + .sha256 hash validation must succeed.
        dl_dir = str(tmp_path / 'dl' / platform_key)
        path = su._download(info['download_url'], dl_dir)
        assert path is not None and os.path.isfile(path)
