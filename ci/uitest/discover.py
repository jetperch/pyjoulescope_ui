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

"""Locate the UI's TCP server credentials and enumerate connected devices.

This module is intentionally free of any ``joulescope_ui`` / PySide6 import so
that its path logic can be unit-tested without the UI installed.  The path
computation mirrors :meth:`joulescope_ui.pubsub.PubSub._paths_init` exactly --
if that ever changes, update :func:`app_dir` to match.
"""

import dataclasses
import json
import os
import sys


APP_NAME = 'joulescope'

# Device models the suite recognizes.  The UI registers a connected device as
# ``registry/<MODEL>-<serial>`` (e.g. ``JS220-002557``, ``JS320-8W2A``); the
# class-level registration is the bare ``JS220``/``JS320``/``JS110`` topic.
# Matching is case-insensitive so both forms (and ``Prefix:js320`` ids) resolve.
_MODELS = ('JS220', 'JS320', 'JS110')


def app_dir(app=APP_NAME, platform=None):
    """Return the UI base application directory for ``app``.

    Mirrors ``PubSub._paths_init``: the UI writes ``server.json`` here and
    keeps ``config/`` and ``log/`` subdirectories alongside it.

    :param app: The application name (default ``'joulescope'``).
    :param platform: Override ``sys.platform`` (for testing).  When None, the
        running platform is used.
    :return: The absolute base application directory path.
    """
    platform = sys.platform if platform is None else platform
    if 'win32' in platform:
        # PubSub uses FOLDERID_LocalAppData; %LOCALAPPDATA% is its env
        # equivalent and is always set on a normal Windows session.  The
        # harness always runs on the same machine as the UI, so this matches.
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        return os.path.join(base, app)
    elif 'darwin' in platform:
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', app)
    elif 'linux' in platform:
        return os.path.join(os.path.expanduser('~'), '.' + app)
    raise RuntimeError(f'unsupported platform: {platform}')


def server_json_path(app=APP_NAME, platform=None):
    """Return the path to the UI's ``server.json`` credentials file."""
    return os.path.join(app_dir(app, platform), 'server.json')


def config_dir(app=APP_NAME, platform=None):
    """Return the UI config directory (``<app_dir>/config``)."""
    return os.path.join(app_dir(app, platform), 'config')


def config_file_path(app=APP_NAME, platform=None):
    """Return the path to the UI's persisted config JSON."""
    return os.path.join(config_dir(app, platform), 'joulescope_ui_config.json')


def find_credentials(path=None, app=APP_NAME):
    """Load ``{'token', 'port'}`` from the UI's ``server.json``.

    :param path: Explicit ``server.json`` path; default uses
        :func:`server_json_path` for the running platform.
    :return: The credentials dict, or None if the file is absent/unreadable.
    """
    if path is None:
        path = server_json_path(app)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def model_for_unique_id(unique_id):
    """Map a device ``unique_id`` (e.g. ``'js220'``, ``'js320_1'``) to a model.

    :return: 'JS220' | 'JS320' | 'JS110', or None if not a known device.
    """
    if not unique_id:
        return None
    name = unique_id.split(':')[-1].upper()   # tolerate 'JsdrvDevice:js220' ids
    for model in _MODELS:
        if name.startswith(model):
            return model
    return None


@dataclasses.dataclass(frozen=True)
class Device:
    """A device discovered through the UI's pubsub registry."""

    unique_id: str
    model: str
    serial_number: str = ''

    @property
    def topic(self):
        """The device's pubsub registry base topic."""
        return f'registry/{self.unique_id}'


def _capability_list_topics():
    """Capability ``.../list`` topics that enumerate connected devices.

    Statistics + signal stream sources are exactly the JS110/JS220/JS320
    devices (see ``joulescope_ui/capabilities.py``).
    """
    return [
        'registry_manager/capabilities/statistics_stream.source/list',
        'registry_manager/capabilities/signal_stream.source/list',
    ]


def enumerate_devices(client):
    """Enumerate connected Joulescope devices via a connected ``Client``.

    :param client: An open :class:`joulescope_ui.tcp_client.Client`.
    :return: A list of unique :class:`Device`, deduplicated by ``unique_id``.
    """
    unique_ids = []
    for topic in _capability_list_topics():
        try:
            value = client.query(topic)
        except Exception:
            continue
        for uid in (value or []):
            if uid not in unique_ids:
                unique_ids.append(uid)

    devices = []
    for uid in unique_ids:
        model = model_for_unique_id(uid)
        if model is None:
            continue
        serial = ''
        try:
            info = client.query(f'registry/{uid}/settings/info')
            if isinstance(info, dict):
                serial = str(info.get('serial_number', '') or '')
        except Exception:
            pass
        devices.append(Device(unique_id=uid, model=model, serial_number=serial))
    return devices
