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

"""Configs saved by earlier UI releases, for the upgrade test.

Each release's GitHub Release carries a ``joulescope_ui_config.json`` saved by
that release with :data:`PREFS` set.  The packaging workflow generates it
(``build_sdist``) and attaches it (``publish``).
``test_preferences.test_previous_release_config`` downloads the previous
release's config and checks that :data:`PREFS` survive.

To generate one by hand, run from ``pyjoulescope_ui/`` with the release's UI
source (default: this checkout)::

    python ci/uitest/config_fixtures.py --source ../ui_release --out dist_config

Generating a config runs the UI, so it backs up and restores this machine's
own UI config.
"""

import argparse
import json
import os
import shutil
import sys

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uitest import assets, discover  # noqa: E402

#: The release asset name.
RELEASE_ASSET = 'joulescope_ui_config.json'
_RELEASE_URL = 'https://github.com/jetperch/pyjoulescope_ui/releases/download/v{version}/' + RELEASE_ASSET

#: Non-default preferences the configs store, as ``{topic: value}``.
PREFS = {
    'registry/app/settings/units': 'Xh',
    'registry/view/settings/active': 'view:oscilloscope',
}

#: The Multimeter widget's precision, a widget-instance setting.
MULTIMETER_PRECISION = 4


def multimeter_id(session):
    ids = [i for i in session.enumerate('registry') if i.startswith('MultimeterWidget:')]
    assert ids, 'no Multimeter widget'
    return ids[0]


def previous_versions(version, count, index=None):
    """Return the ``count`` latest published versions before ``version``.

    :param version: The UI version string, such as ``'1.7.5'``.
    :param index: The parsed ``index_v2.json``; default fetches it.
    :return: Version strings, newest first.
    """
    from uitest import installer
    if index is None:
        index = installer.fetch_index()
    current = [int(x) for x in version.split('.')[:3]]
    published = sorted({tuple(v['version']) for v in index.get('versions', [])}, reverse=True)
    return ['.'.join(str(x) for x in v) for v in published if list(v) < current][:count]


def release_config(version, *, timeout=60.0):
    """Return a local path to the config saved by release ``version``.

    Downloads the release asset on first use and caches it under ``assets/``.

    :raises FileNotFoundError: If the release has no config asset.
    :raises ValueError: If the download is not a UI config.
    """
    path = assets.asset_path(f'joulescope_ui_config_{version}.json')
    if not os.path.isfile(path):
        import requests
        url = _RELEASE_URL.format(version=version)
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            raise FileNotFoundError(
                f'release v{version} has no {RELEASE_ASSET} asset; attach one with '
                f'"config_fixtures.py --source <v{version} checkout>" and gh release upload')
        resp.raise_for_status()
        if resp.json().get('type') != 'joulescope_ui_config':
            raise ValueError(f'{url} is not a joulescope_ui_config')
        os.makedirs(assets.ASSETS_DIR, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(resp.content)
    return path


def _source_version(source):
    scope = {}
    with open(os.path.join(source, 'joulescope_ui', 'version.py'), 'rt') as f:
        exec(f.read(), scope)
    return scope['__version__']


def generate(source, out_dir):
    """Run the UI from ``source``, store :data:`PREFS`, and save its config.

    :param source: The UI source directory (holding ``joulescope_ui/``).
    :param out_dir: The directory for :data:`RELEASE_ASSET`.
    :return: The saved config path.
    """
    from uitest.harness import UiSession
    config = discover.config_file_path()
    backup = config + '.config_fixtures_backup'
    if os.path.isfile(config):
        shutil.copyfile(config, backup)
    try:
        if os.path.isfile(config):
            os.remove(config)
        session = UiSession(offscreen=True, config_clear_on_exit=False,
                            cwd=os.path.abspath(source))
        session.start()
        try:
            for topic, value in PREFS.items():
                session.publish_and_wait(topic, value)
            session.publish_and_wait(f'registry/{multimeter_id(session)}/settings/precision',
                                     MULTIMETER_PRECISION)
        finally:
            session.stop()
        if not session.exited_cleanly:
            raise RuntimeError('UI did not exit cleanly; config not saved')
        with open(config, 'rt', encoding='utf-8') as f:
            if json.load(f).get('type') != 'joulescope_ui_config':
                raise RuntimeError(f'{config} is not a joulescope_ui_config')
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, RELEASE_ASSET)
        shutil.copyfile(config, path)
        return path
    finally:
        if os.path.isfile(backup):
            shutil.move(backup, config)
        elif os.path.isfile(config):
            os.remove(config)


def main():
    parser = argparse.ArgumentParser(description='Save a UI release config for the upgrade test.')
    parser.add_argument('--source', default='.',
                        help='The UI source directory of the release (default: this checkout).')
    parser.add_argument('--out', default='dist_config',
                        help=f'The output directory for {RELEASE_ASSET}.')
    args = parser.parse_args()
    print(f'UI {_source_version(args.source)}: {generate(args.source, args.out)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
