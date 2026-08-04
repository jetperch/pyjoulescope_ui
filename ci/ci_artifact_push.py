#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
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

"""Push a built artifact to the joulescope_ci coordinator from CI.

A single, dependency-free (stdlib only) client that both **Gitea** and
**GitHub** Actions use to upload a build artifact. It signs the request with an
HMAC over a versioned canonical string (matching ``joulescope_ci/ingest.py``),
so the coordinator -- and, for GitHub, the ``api_jetperch_com`` gateway it goes
through -- can authenticate and verify it.

Point ``--url`` at the right endpoint:

* Gitea (on the LAN with the coordinator): ``http://<coordinator>:8080/builds``
* GitHub (cloud): ``https://api.jetperch.com/github/build`` (the gateway
  re-verifies and forwards to the coordinator)

The token is read from an environment variable (never the command line). Example
(GitHub Actions step)::

    python ci_artifact_push.py \\
        --url https://api.jetperch.com/github/build \\
        --source github --token-env JCI_BUILD_TOKEN \\
        --repo "${GITHUB_REPOSITORY##*/}" --ref "$GITHUB_REF" \\
        --commit "$GITHUB_SHA" --run-id "$GITHUB_RUN_ID" \\
        --build-kind dev --artifact-type python_wheel \\
        --artifact dist/pyjoulescope_driver-*.whl

Pull-request refs are refused (the coordinator rejects them too); gate the
workflow step so it does not run on ``pull_request`` events.
"""

import argparse
import hashlib
import hmac
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

SIG_VERSION = 'v1'
_PR_MARKERS = ('refs/pull/', 'refs/merge')


def canonical_string(source, repo, ref, commit, build_kind, artifact_type,
                     sha256, timestamp, nonce):
    """Exact string the coordinator HMAC-verifies (see ingest.canonical_string)."""
    return '\n'.join([SIG_VERSION, source, repo, ref, commit, build_kind,
                      artifact_type, sha256, str(timestamp), nonce])


def sign(token, message):
    mac = hmac.new(token.encode('utf-8'), message.encode('utf-8'),
                   hashlib.sha256).hexdigest()
    return 'sha256=' + mac


def build_headers(token, *, source, repo, ref, commit, run_id, build_kind,
                  artifact_type, body, name, timestamp, nonce,
                  tool_os='', tool_arch=''):
    sha = hashlib.sha256(body).hexdigest()
    ts = str(int(timestamp))
    msg = canonical_string(source, repo, ref, commit, build_kind,
                           artifact_type, sha, ts, nonce)
    extra = {}
    if tool_os:
        extra['X-JCI-Os'] = tool_os
    if tool_arch:
        extra['X-JCI-Arch'] = tool_arch
    return {
        **extra,
        'Content-Type': 'application/octet-stream',
        'X-JCI-Source': source,
        'X-JCI-Repo': repo,
        'X-JCI-Ref': ref,
        'X-JCI-Commit': commit,
        'X-JCI-Run-Id': run_id,
        'X-JCI-Build-Kind': build_kind,
        'X-JCI-Artifact-Type': artifact_type,
        'X-JCI-Sha256': sha,
        'X-JCI-Timestamp': ts,
        'X-JCI-Nonce': nonce,
        'X-JCI-Artifact-Name': name,
        'X-JCI-Signature': sign(token, msg),
    }


def _parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', required=True,
                   help='coordinator /builds (Gitea) or gateway URL (GitHub)')
    p.add_argument('--source', required=True, choices=['gitea', 'github'])
    p.add_argument('--repo', required=True, help='short repo name (e.g. js320)')
    p.add_argument('--ref', required=True, help='refs/heads/... or refs/tags/...')
    p.add_argument('--commit', required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--build-kind', default='dev', choices=['dev', 'release'])
    p.add_argument('--artifact-type', default='firmware',
                   choices=['firmware', 'python_wheel', 'tool', 'ui'])
    p.add_argument('--os', default='', dest='tool_os',
                   help='tool pushes: target bench os (linux/windows/macos)')
    p.add_argument('--arch', default='', dest='tool_arch',
                   help='tool pushes: target bench arch (x86_64/arm64)')
    p.add_argument('--artifact', required=True, help='path to the artifact file')
    p.add_argument('--name', default='', help='artifact name (default: basename)')
    p.add_argument('--token-env', default='JCI_BUILD_TOKEN',
                   help='env var holding the HMAC token (default JCI_BUILD_TOKEN)')
    p.add_argument('--timeout', type=float, default=60.0)
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if any(m in args.ref for m in _PR_MARKERS):
        print(f'refusing to push for a pull-request ref: {args.ref}',
              file=sys.stderr)
        return 2

    token = os.environ.get(args.token_env)
    if not token:
        print(f'token env var {args.token_env} is empty/unset', file=sys.stderr)
        return 2

    with open(args.artifact, 'rb') as f:
        body = f.read()
    name = args.name or os.path.basename(args.artifact)

    headers = build_headers(
        token, source=args.source, repo=args.repo, ref=args.ref,
        commit=args.commit, run_id=args.run_id, build_kind=args.build_kind,
        artifact_type=args.artifact_type, body=body, name=name,
        timestamp=time.time(), nonce=secrets.token_hex(16),
        tool_os=args.tool_os, tool_arch=args.tool_arch)

    req = urllib.request.Request(args.url, data=body, headers=headers,
                                 method='POST')
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            payload = resp.read().decode('utf-8', 'replace')
            print(f'{resp.status} {payload}')
            return 0
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode('utf-8', 'replace')
        print(f'push rejected: HTTP {ex.code} {detail}', file=sys.stderr)
        return 1
    except urllib.error.URLError as ex:
        print(f'push failed: {ex}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
