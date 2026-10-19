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

"""Add a platform release key to already-published index_v2.json entries.

The deployed UI looks up ``active[channel]['releases'][_platform_name()]``,
where the platform name tracks the OS version (e.g. ``macos_27_0_arm64``).
When a new OS version ships, existing releases lack that key and the update
check fails.  This command aliases ``new_key`` to the installer already listed
under ``from_key`` for every ``active`` and ``versions`` entry that has
``from_key``, then re-renders ``index.html``.  No installer files are touched.

New releases get the key from ``ci/publish.py`` (``_MACOS_RELEASE_KEYS``).

Environment (S3 mode):
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    JOULESCOPE_DOWNLOAD_BUCKET   S3 bucket (e.g. "download-joulescope-com")

Usage:
    python ci/release_alias.py macos_27_0_arm64 macos_26_0_arm64 --os-ver macos_27 --dry-run
    python ci/release_alias.py macos_27_0_arm64 macos_26_0_arm64 --os-ver macos_27
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _publish_common as common  # noqa: E402


def _alias_entry(entry, new_key, from_key, os_ver):
    releases = entry.get('releases', {})
    if from_key not in releases or new_key in releases:
        return False
    installer = releases[from_key]
    releases[new_key] = installer
    if os_ver is not None:
        for pinfo in entry.get('platform', {}).values():
            ver = pinfo.get('os_ver')
            if pinfo.get('installer') == installer and ver is not None \
                    and os_ver not in ver:
                ver.append(os_ver)
    return True


def release_alias(backend, new_key, from_key, os_ver=None):
    """Alias ``new_key`` to ``from_key`` in all index entries.

    :return: The list of modified entry labels.
    """
    pub = common.Publisher(backend)
    changed = []

    def mutate(index):
        changed.clear()
        for name, entry in index.get('active', {}).items():
            if _alias_entry(entry, new_key, from_key, os_ver):
                changed.append(f'active.{name}')
        for entry in index.get('versions', []):
            if _alias_entry(entry, new_key, from_key, os_ver):
                changed.append(common.version_str(entry['version']))

    pub.update_index(mutate)
    return changed


def main():
    parser = argparse.ArgumentParser(
        description='Alias a new platform release key in index_v2.json.')
    parser.add_argument('new_key', help='New release key (e.g. macos_27_0_arm64).')
    parser.add_argument('from_key', help='Existing release key (e.g. macos_26_0_arm64).')
    parser.add_argument('--os-ver',
                        help='Also append to the matching platform os_ver list (e.g. macos_27).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Read the live index and print planned writes.')
    parser.add_argument('--local', metavar='DIR',
                        help='Operate on a local tree at DIR instead of S3.')
    args = parser.parse_args()

    backend = common.make_backend(local=args.local, dry_run=args.dry_run)
    changed = release_alias(backend, args.new_key, args.from_key, args.os_ver)
    print(f'aliased {args.new_key} -> {args.from_key} in {len(changed)} entries: '
          f'{", ".join(changed)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
