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

"""Publish a Joulescope UI release to download.joulescope.com (alpha channel).

Invoked by .github/workflows/packaging.yml on a tag push, after the installer
artifacts have been downloaded into ``dist_installer/``.  For the running
version it:

1. Selects the Windows (x86_64 + arm64), macOS, and Ubuntu installers plus the
   changelog from ``dist_installer/`` (preferring the Nuitka Windows build).
2. Uploads each to ``joulescope_install/{major}/{minor}/{patch}/`` along with a
   ``{filename}.sha256`` sidecar.
3. Read-modify-writes ``joulescope_install/index_v2.json`` so ``active.alpha``
   and the head of ``versions`` point at this release, then re-renders
   ``index.html``.

This *only ever* publishes to the ``alpha`` channel.  Promotion to ``beta`` /
``stable`` is a separate step: ``ci/release_update.py {version} {maturity}``.

The existing ``joulescope_install/`` file layout and ``index_v2.json`` schema
are preserved so already-deployed Joulescope UIs keep auto-updating.

Environment (S3 mode):
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    JOULESCOPE_DOWNLOAD_BUCKET   S3 bucket (e.g. "download.joulescope.com")

Usage (run from the repository root):
    python ci/publish.py                 # publish to S3
    python ci/publish.py --dry-run       # read live index, print planned writes
    python ci/publish.py --local DIR     # write the full tree to DIR, no AWS
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _publish_common as common  # noqa: E402


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_VERSION_PY = os.path.join(_REPO, 'joulescope_ui', 'version.py')
_DIST_INSTALLER = os.path.join(_REPO, 'dist_installer')
_CHANGELOG = 'CHANGELOG.md'

# macOS/Ubuntu release-key sets mirror the most recent published release so the
# consumer's _platform_name() keys all resolve.
_MACOS_OS_VER = ['macos_13', 'macos_14', 'macos_15', 'macos_26']
_MACOS_RELEASE_KEYS = [
    'macos_26_0_arm64', 'macos_26_0_x86_64',
    'macos_15_0_arm64', 'macos_15_0_x86_64',
    'macos_14_0_arm64', 'macos_14_0_x86_64',
    'macos_13_0_arm64', 'macos_13_0_x86_64',
]
_UBUNTU_OS_VER = ['ubuntu_24_04']
_UBUNTU_RELEASE_KEYS = ['ubuntu_24_04_x86_64', 'ubuntu_22_04_x86_64']


def read_version(path=_VERSION_PY):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    m = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)[\'"]', text)
    if not m:
        raise RuntimeError(f'__version__ not found in {path}')
    return m.group(1)


def _content_type(name):
    if name.endswith('.tar.gz'):
        return 'application/gzip'
    if name.endswith('.md'):
        return 'text/markdown; charset=utf-8'
    if name.endswith('.json'):
        return 'application/json'
    if name.endswith('.sha256'):
        return 'text/plain; charset=utf-8'
    return 'application/octet-stream'  # .exe, .dmg


def _pick_exe(files, arm64):
    """Return the best Windows installer for the requested arch, or None.

    Prefers the Nuitka build, then PyInstaller, then any .exe.  ``arm64``
    selects names containing 'arm64'; otherwise names without it.
    """
    cands = [f for f in files
             if f.endswith('.exe') and (('arm64' in f) == bool(arm64))]
    if not cands:
        return None
    for suffix in ('_nuitka.exe', '_pyinstaller.exe'):
        for f in cands:
            if f.endswith(suffix):
                return f
    return cands[0]


def _pick_one(files, suffix, what):
    cands = [f for f in files if f.endswith(suffix)]
    if not cands:
        raise RuntimeError(f'no {what} ({suffix}) found in dist_installer')
    if len(cands) > 1:
        raise RuntimeError(f'multiple {what} found: {sorted(cands)}')
    return cands[0]


def select_installers(dist_dir):
    """Map source files in ``dist_dir`` to canonical published filenames.

    Returns a list of ``(source_path, target_name)`` for the release files
    (Windows x86_64, optional Windows arm64, macOS, Ubuntu, changelog).
    """
    files = os.listdir(dist_dir)
    version = read_version()
    v = common.version_tuple(version)
    vfs = common.version_filename_part(version)

    win_x86 = _pick_exe(files, arm64=False)
    if win_x86 is None:
        raise RuntimeError('no x86_64 Windows installer (.exe) in dist_installer')
    win_arm = _pick_exe(files, arm64=True)
    dmg = _pick_one(files, '.dmg', 'macOS installer')
    tar = _pick_one(files, '.tar.gz', 'Ubuntu installer')
    if _CHANGELOG not in files:
        raise RuntimeError(f'{_CHANGELOG} not found in dist_installer')

    mapping = [
        (os.path.join(dist_dir, win_x86), f'joulescope_setup_{vfs}.exe'),
    ]
    if win_arm is not None:
        mapping.append(
            (os.path.join(dist_dir, win_arm), f'joulescope_setup_arm64_{vfs}.exe'))
    mapping += [
        (os.path.join(dist_dir, dmg), f'joulescope_{vfs}.dmg'),
        (os.path.join(dist_dir, tar), f'joulescope_{vfs}.tar.gz'),
        (os.path.join(dist_dir, _CHANGELOG), _CHANGELOG),
    ]
    return v, mapping


def build_summary(v, names, prefix=''):
    """Build the index_v2.json release entry.

    ``names`` maps role -> filename.  ``prefix`` is prepended to every path
    ('' for the per-release index.json; '{m}/{n}/{p}/' for index_v2.json).
    """
    win = prefix + names['windows']
    dmg = prefix + names['macos']
    tar = prefix + names['ubuntu']

    platform = {
        'windows': {
            'os': ['win10', 'win11'],
            'arch': ['x86_64'],
            'installer': win,
        },
    }
    releases = {
        'win11_x86_64': win,
        'win10_x86_64': win,
    }
    if 'windows_arm64' in names:
        arm = prefix + names['windows_arm64']
        platform['windows_arm64'] = {
            'os': ['win11'],
            'arch': ['arm64'],
            'installer': arm,
        }
        releases['win11_arm64'] = arm
        releases['win10_arm64'] = arm

    platform['macos'] = {
        'os_ver': list(_MACOS_OS_VER),
        'arch': ['x86_64', 'arm64'],
        'installer': dmg,
    }
    platform['ubuntu'] = {
        'os_ver': list(_UBUNTU_OS_VER),
        'arch': ['x86_64'],
        'installer': tar,
    }
    for key in _MACOS_RELEASE_KEYS:
        releases[key] = dmg
    for key in _UBUNTU_RELEASE_KEYS:
        releases[key] = tar

    return {
        'version': list(v),
        'platform': platform,
        'releases': releases,
        'changelog': prefix + names[_CHANGELOG],
    }


def publish(backend, dist_dir=_DIST_INSTALLER):
    v, mapping = select_installers(dist_dir)
    vdir = '/'.join(str(x) for x in v)
    pub = common.Publisher(backend)

    # role names for build_summary
    names = {_CHANGELOG: _CHANGELOG}
    for src, target in mapping:
        if target.endswith('.dmg'):
            names['macos'] = target
        elif target.endswith('.tar.gz'):
            names['ubuntu'] = target
        elif target.endswith('.exe'):
            names['windows_arm64' if 'arm64' in target else 'windows'] = target

    # per-release index.json carries bare filenames (legacy parity)
    local_summary = build_summary(v, names, prefix='')
    index_json_bytes = common.dumps_index(local_summary).encode('utf-8')

    # Upload every release file + a {name}.sha256 sidecar.
    uploads = []  # (target_name, content_type, body_bytes)
    for src, target in mapping:
        with open(src, 'rb') as f:
            uploads.append((target, _content_type(target), f.read()))
    uploads.append(('index.json', 'application/json', index_json_bytes))

    for target, ct, body in uploads:
        key = f'{common.PREFIX}/{vdir}/{target}'
        pub.put_bytes(key, body, ct)
        sidecar = common.sha256_sidecar(common.sha256_bytes(body), target)
        pub.put_bytes(f'{key}.sha256', sidecar.encode('utf-8'),
                      'text/plain; charset=utf-8')

    # index_v2.json paths are relative to joulescope_install/.
    summary = build_summary(v, names, prefix=f'{vdir}/')

    def mutate(index):
        index.setdefault('active', {})['alpha'] = summary
        versions = index.setdefault('versions', [])
        index['versions'] = [summary] + [x for x in versions
                                         if x.get('version') != list(v)]

    pub.update_index(mutate)
    return v


def main():
    parser = argparse.ArgumentParser(
        description='Publish a Joulescope UI release to the alpha channel.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Read the live index and print planned writes.')
    parser.add_argument('--local', metavar='DIR',
                        help='Write the full tree to DIR instead of S3.')
    parser.add_argument('--dist', default=_DIST_INSTALLER,
                        help='Installer source directory (default: dist_installer).')
    args = parser.parse_args()

    backend = common.make_backend(local=args.local, dry_run=args.dry_run)
    v = publish(backend, dist_dir=args.dist)
    print(f'published {common.version_str(v)} to alpha')
    return 0


if __name__ == '__main__':
    sys.exit(main())
