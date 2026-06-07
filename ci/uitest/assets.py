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

"""Fetch & cache large test-data fixtures on demand.

Some fixtures (e.g. the 78 MB ``js110_evk1_10s_0_7_0.jls`` v1 recording the
test plan opens) are too large to commit, so they are downloaded from
``download.joulescope.com`` on first use and cached under ``assets/`` (which
is git-ignored).  Each fixture is validated by its expected JLS major version
so a truncated or HTML-error download fails loudly instead of feeding the UI
garbage.
"""

import os
import logging

_log = logging.getLogger(__name__)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')

#: Canonical JLS **v1** recording referenced by the test plan's
#: "Open JLS v1 recording and export" section.
JLS_V1_EVK1 = 'js110_evk1_10s_0_7_0.jls'

# name -> (download URL, expected JLS major version)
_ASSETS = {
    JLS_V1_EVK1: (
        'https://download.joulescope.com/products/JS110/js110_evk1_10s_0_7_0.jls',
        1,
    ),
}


def asset_path(name):
    """Return the local cache path for ``name`` (no download)."""
    return os.path.join(ASSETS_DIR, name)


def get_asset(name, *, force=False, timeout=60.0):
    """Return a local path to fixture ``name``, downloading it if needed.

    :param force: Re-download even if a cached copy exists.
    :param timeout: Per-request timeout in seconds.
    :raises KeyError: If ``name`` is not a registered asset.
    :raises ValueError: If the downloaded file fails its JLS-version check.
    :return: The absolute path to the cached fixture.
    """
    if name not in _ASSETS:
        raise KeyError(f'unknown asset: {name!r}')
    url, expected_version = _ASSETS[name]
    path = asset_path(name)
    if not force and os.path.isfile(path) and os.path.getsize(path) > 0:
        _validate(path, expected_version)
        return path

    os.makedirs(ASSETS_DIR, exist_ok=True)
    _log.info('downloading asset %s from %s', name, url)
    tmp = path + '.part'
    import requests  # local import: keep module import cheap and dependency-soft
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(tmp, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
    _validate(tmp, expected_version)
    os.replace(tmp, path)
    return path


def _validate(path, expected_version):
    """Validate the cached file's JLS major version; raise on mismatch."""
    from uitest import verify  # local import avoids a hard import cycle
    found = verify.jls_version(path)
    if found != expected_version:
        raise ValueError(
            f'{path}: expected JLS v{expected_version}, found {found!r} '
            f'(corrupt or unexpected download?)')
