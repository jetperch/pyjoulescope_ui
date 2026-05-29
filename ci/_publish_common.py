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

"""Shared helpers for publishing the Joulescope UI to download.joulescope.com.

Both ``ci/publish.py`` (publish a new release to the alpha channel) and
``ci/release_update.py`` (promote an existing release to a maturity channel)
read-modify-write the same ``joulescope_install/index_v2.json`` object and
re-render ``joulescope_install/index.html`` from it.  This module holds the
schema constants, the JSON/HTML rendering, the hashing helpers, and the storage
backends so that the on-disk format lives in exactly one place.

The ``index_v2.json`` schema and the ``index.html`` layout intentionally
reproduce the output of the legacy ``js220_mfg publish ui`` tool so that
already-deployed Joulescope UIs (which poll ``index_v2.json`` and download
installers by the listed relative paths) keep updating without interruption.

Storage is abstracted behind a backend so the identical pipeline can run
against S3 in CI (``S3Backend``), the local filesystem in tests
(``LocalBackend``), or a read-only preview (``DryRunBackend``).
"""

import hashlib
import json
import os
import re


# The URL/key prefix.  The consumer (joulescope_ui/software_update.py) fetches
# https://download.joulescope.com/joulescope_install/index_v2.json and resolves
# installer paths relative to .../joulescope_install/, so every relative path we
# store in the index is relative to this prefix.
PREFIX = 'joulescope_install'
INDEX_KEY = f'{PREFIX}/index_v2.json'
INDEX_HTML_KEY = f'{PREFIX}/index.html'
BUCKET_ENV = 'JOULESCOPE_DOWNLOAD_BUCKET'

RELEASE_NAMES = ['alpha', 'beta', 'stable']

# Ordered platform -> human label.  Drives the index.html table columns.
# 'windows_arm64' is new (Windows on ARM); historical version entries omit it
# and render an empty cell.
PLATFORM_TO_USER_STR = {
    'windows': 'Windows',
    'windows_arm64': 'Windows (ARM64)',
    'macos': 'macOS',
    'ubuntu': 'Ubuntu',
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en-US">
<head>
<meta name="robots" content="noindex">
<title>{title}</title>
</head>
<body>
<h1>{title}</h1>

<style>
table {{
  table-layout: fixed;
  border-collapse: collapse;
}}
td, th {{
  border: 1px solid black;
  text-align: center;
  padding-left: 10px;
  padding-right: 10px;
}}
</style>

{body}

<p><a href="index_v1.html">Older versions</a></p>

</body>
</html>
"""

HTML_TITLE = 'Joulescope Application Software'
CONTENT_TYPE_JSON = 'application/json'
CONTENT_TYPE_HTML = 'text/html; charset=utf-8'


class ConflictError(Exception):
    """The index object changed between read and write (ETag mismatch)."""


def version_tuple(version):
    """Convert a version to a ``[major, minor, patch]`` list of ints.

    Accepts a ``"major.minor.patch"`` string or an iterable of three values.
    """
    if isinstance(version, str):
        parts = version.split('.')
    else:
        parts = list(version)
    if len(parts) != 3:
        raise ValueError(f'expected major.minor.patch, got {version!r}')
    return [int(p) for p in parts]


def version_str(version):
    return '.'.join(str(x) for x in version_tuple(version))


def version_filename_part(version):
    return '_'.join(str(x) for x in version_tuple(version))


_RE_DUMP = re.compile(r'\[[^\[\]\{\}]+\]')
_RE_REPLACE = re.compile(r'\s*\n\s*')


def _collapse(matchobj):
    return _RE_REPLACE.sub(' ', matchobj.group(0))


def dumps_index(index):
    """Serialize the index dict, collapsing scalar arrays onto one line.

    Reproduces the legacy formatting (``[ 1, 4, 1 ]``, ``[ "win10", "win11" ]``)
    so diffs against the deployed index_v2.json stay minimal.
    """
    s = json.dumps(index, indent=2)
    return _RE_DUMP.sub(_collapse, s)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_sidecar(sha256_hex, filename):
    """The body of a ``{filename}.sha256`` file.

    Format ``"{hex} ./{filename}"`` matches what the deployed UI parses in
    ``software_update._download`` (it splits on the first space).
    """
    return f'{sha256_hex} ./{filename}'


def _html_table(rows):
    out = ['<table>']
    for idx, row in enumerate(rows):
        tag_start, tag_end = ('<th>', '</th>') if idx == 0 else ('<td>', '</td>')
        out += ['  <tr>\n']
        for col in row:
            out += [f'    {tag_start}{col}{tag_end}\n']
        out += ['  </tr>\n']
    out += ['</table>']
    return ''.join(out)


def render_index_html(index):
    """Render index.html from the index dict (active table + version history).

    Unlike the legacy tool this does not stat the filesystem to decide whether
    to render a link: every entry present in ``index['versions']`` was
    published, so its files exist.  Platform lookups are guarded so historical
    entries that predate a platform key (e.g. ``windows_arm64``) render an
    empty cell.
    """
    active = index.get('active', {})
    versions = index.get('versions', [])

    # Active-by-channel table.
    rows = [['Platform'] + RELEASE_NAMES]
    for platform, platform_usr in PLATFORM_TO_USER_STR.items():
        row = [platform_usr]
        for release_name in RELEASE_NAMES:
            release = active.get(release_name)
            pinfo = None if release is None else release.get('platform', {}).get(platform)
            if pinfo is None:
                row.append('')
            else:
                v = version_str(release['version'])
                row.append(f'<a href="{pinfo["installer"]}">{v}</a>')
        rows.append(row)
    active_table = _html_table(rows)

    # Version-history table.
    rows = [['Version'] + list(PLATFORM_TO_USER_STR.values())]
    for version in versions:
        v = version_str(version['version'])
        changelog = version.get('changelog', '')
        row = [f'<a href={changelog}>{v}</a>']
        for platform in PLATFORM_TO_USER_STR.keys():
            pinfo = version.get('platform', {}).get(platform)
            if pinfo is None:
                row.append('')
            else:
                row.append(f'<a href="{pinfo["installer"]}">{v}</a>')
        rows.append(row)
    version_table = _html_table(rows)

    body = f'<p>{active_table}</p>\n<p>{version_table}</p>\n'
    return HTML_TEMPLATE.format(title=HTML_TITLE, body=body)


class StorageBackend:
    """Abstract get/put over a key namespace with optimistic concurrency."""

    def get(self, key):
        """Return ``(body_bytes, etag)`` or ``(None, None)`` if absent."""
        raise NotImplementedError

    def put(self, key, body, content_type, if_match=None):
        """Write ``body`` (bytes) at ``key``.

        When ``if_match`` is provided, raise :class:`ConflictError` if the
        current object's etag differs (or the object now exists when
        ``if_match`` was for a missing object).
        """
        raise NotImplementedError


class S3Backend(StorageBackend):
    def __init__(self, bucket, s3_client=None):
        self.bucket = bucket
        self._s3 = s3_client

    @property
    def s3(self):
        if self._s3 is None:
            import boto3
            self._s3 = boto3.client('s3')
        return self._s3

    def get(self, key):
        from botocore.exceptions import ClientError
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            if code in ('NoSuchKey', '404'):
                return None, None
            raise
        return resp['Body'].read(), resp['ETag']

    def put(self, key, body, content_type, if_match=None):
        from botocore.exceptions import ClientError
        kwargs = dict(Bucket=self.bucket, Key=key, Body=body,
                      ContentType=content_type)
        if if_match is not None:
            kwargs['IfMatch'] = if_match
        try:
            self.s3.put_object(**kwargs)
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            if code in ('PreconditionFailed', '412'):
                raise ConflictError(key) from e
            raise
        print(f'put s3://{self.bucket}/{key} ({len(body)} bytes)')


class LocalBackend(StorageBackend):
    """Filesystem backend mirroring the bucket layout under ``root``.

    The etag is the content sha256 so the conflict-retry path is still
    exercised.  No AWS, no network.
    """

    def __init__(self, root):
        self.root = os.path.abspath(root)

    def _path(self, key):
        return os.path.join(self.root, *key.split('/'))

    def get(self, key):
        path = self._path(key)
        if not os.path.isfile(path):
            return None, None
        with open(path, 'rb') as f:
            body = f.read()
        return body, sha256_bytes(body)

    def put(self, key, body, content_type, if_match=None):
        path = self._path(key)
        if if_match is not None:
            _, etag = self.get(key)
            if etag != if_match:
                raise ConflictError(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(body)
        os.replace(tmp, path)
        print(f'put {path} ({len(body)} bytes)')


class DryRunBackend(StorageBackend):
    """Reads pass through to ``inner``; writes only print."""

    def __init__(self, inner):
        self.inner = inner

    def get(self, key):
        return self.inner.get(key)

    def put(self, key, body, content_type, if_match=None):
        print(f'[dry-run] put {key} ({len(body)} bytes, {content_type})')


class Publisher:
    """Upload files and read-modify-write index_v2.json / index.html."""

    def __init__(self, backend):
        self.backend = backend

    def put_bytes(self, key, body, content_type):
        self.backend.put(key, body, content_type)

    def put_file(self, local_path, key, content_type):
        with open(local_path, 'rb') as f:
            body = f.read()
        self.backend.put(key, body, content_type)

    def get_index(self):
        body, etag = self.backend.get(INDEX_KEY)
        if not body:
            return {'active': {}, 'versions': []}, etag
        return json.loads(body), etag

    def update_index(self, mutate, max_attempts=2):
        """Read index_v2.json, apply ``mutate(index)``, write it + index.html.

        ``mutate`` mutates the dict in place.  The write is guarded by the
        read etag and retried once on conflict.  Returns the committed index.
        """
        for attempt in range(max_attempts):
            index, etag = self.get_index()
            mutate(index)
            json_body = dumps_index(index).encode('utf-8')
            try:
                self.backend.put(INDEX_KEY, json_body, CONTENT_TYPE_JSON,
                                 if_match=etag)
            except ConflictError:
                if attempt + 1 >= max_attempts:
                    raise
                print('index_v2.json changed, retrying')
                continue
            html_body = render_index_html(index).encode('utf-8')
            self.backend.put(INDEX_HTML_KEY, html_body, CONTENT_TYPE_HTML)
            return index
        raise ConflictError(INDEX_KEY)  # pragma: no cover


def make_backend(local=None, dry_run=False):
    """Build the backend from CLI options.

    ``local`` -> filesystem under that dir; ``dry_run`` -> read-only preview
    over S3; otherwise S3 (bucket from the ``JOULESCOPE_DOWNLOAD_BUCKET`` env).
    """
    if local is not None:
        return LocalBackend(local)
    bucket = os.environ.get(BUCKET_ENV)
    if dry_run:
        return DryRunBackend(S3Backend(bucket or '<bucket>'))
    if not bucket:
        raise RuntimeError(f'{BUCKET_ENV} not set')
    return S3Backend(bucket)
