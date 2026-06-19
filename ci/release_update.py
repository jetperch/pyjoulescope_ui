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

"""Promote an already-published Joulescope UI release to a maturity channel.

``ci/publish.py`` always publishes to the ``alpha`` channel.  Once a release has
been validated, promote it to ``beta`` or ``stable`` (or re-point ``alpha``)
with this command.  It rewrites only ``joulescope_install/index_v2.json``
(setting ``active[maturity]`` to the existing ``versions`` entry) and
re-renders ``index.html``.  No installer files are uploaded — they were placed
by the earlier ``publish.py`` run.

This is the automated replacement for the legacy ``js220_mfg publish ui
<version> <maturity> --active-only`` step, intended to be run by a developer
locally (or wired to a workflow_dispatch).

Environment (S3 mode):
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    JOULESCOPE_DOWNLOAD_BUCKET   S3 bucket (e.g. "download-joulescope-com")

Usage:
    python ci/release_update.py 1.5.1 stable
    python ci/release_update.py 1.5.1 beta --dry-run
    python ci/release_update.py 1.5.1 beta --local DIR
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _publish_common as common  # noqa: E402


def release_update(backend, version, maturity):
    v = common.version_tuple(version)
    if maturity not in common.RELEASE_NAMES:
        raise ValueError(f'maturity must be one of {common.RELEASE_NAMES}')
    pub = common.Publisher(backend)

    def mutate(index):
        versions = index.get('versions', [])
        match = next((x for x in versions if x.get('version') == v), None)
        if match is None:
            raise RuntimeError(
                f'version {common.version_str(v)} not found in index_v2.json; '
                f'publish it before promoting')
        index.setdefault('active', {})[maturity] = match

    pub.update_index(mutate)
    return v


def main():
    parser = argparse.ArgumentParser(
        description='Promote a published Joulescope UI release to a channel.')
    parser.add_argument('version', help='Version as major.minor.patch (e.g. 1.5.1).')
    parser.add_argument('maturity', choices=common.RELEASE_NAMES,
                        help='Target maturity channel.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Read the live index and print planned writes.')
    parser.add_argument('--local', metavar='DIR',
                        help='Operate on a local tree at DIR instead of S3.')
    args = parser.parse_args()

    backend = common.make_backend(local=args.local, dry_run=args.dry_run)
    v = release_update(backend, args.version, args.maturity)
    print(f'promoted {common.version_str(v)} to {args.maturity}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
