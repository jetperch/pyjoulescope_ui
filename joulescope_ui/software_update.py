# Copyright 2019-2023 Jetperch LLC
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

"""Check for software updates"""

from PySide6 import QtWidgets, QtCore
import requests
import json
import threading
import platform
from joulescope_ui import __version__, N_, is_release, pubsub_singleton, register_decorator
from joulescope_ui.help_ui import load_style
from joulescope_ui.ui_util import show_in_folder
import logging
import hashlib
import os
import shutil
import subprocess
import sys


_log = logging.getLogger(__name__)
_URL_BASE = 'https://download.joulescope.com/joulescope_install/'
_URL_INDEX = _URL_BASE + 'index_v2.json'
_TIMEOUT = 30.0


_HEADER = """\
<html>
<head>
{style}
</head>
<body>
"""


_BODY = """\
<body>
<p>{description}</p>
<table>
<tr><td>{current_version_label}</td><td>{current_version}</td></tr>
<tr><td>{available_version_label}</td><td>{available_version}</td></tr>
<tr><td>{channel_label}</td><td>{channel}</td></tr>
</table>
</body>
</html>
"""


_PROMPT = """\
<body>
<p>We have detected that you are running the Joulescope UI
from a python package or source.</p>
<p>To update your python packages, issue the following command:</p>
</body>
</html>
"""


_TITLE = N_('Software update')


_SOFTWARE_UPDATE_TXT = {
    'description': N_('A software update is available:'),
    'current_version_label': N_('Current version'),
    'available_version_label': N_('Available version'),
    'channel_label': N_('Channel'),
}


def _validate_channel(channel):
    if channel is None:
        channel = 'stable'
    channel = str(channel).lower()
    if channel not in ['alpha', 'beta', 'stable']:
        raise ValueError(f'Unsupported update channel "{channel}"')
    return channel


def str_to_version(v):
    if isinstance(v, str):
        v = v.split('.')
    if len(v) != 3:
        raise ValueError('invalid version - needs [major, minor, patch]')
    return [int(x) for x in v]


def version_to_str(v):
    if isinstance(v, str):
        v = str_to_version(v)
    if len(v) != 3:
        raise ValueError('invalid version - needs [major, minor, patch]')
    return '.'.join(str(x) for x in v)


def current_version():
    return str_to_version(__version__)


def is_newer(version):
    if 'dev' in __version__:
        return False
    return str_to_version(version) > current_version()


def _platform_name():
    psys = platform.system()
    if psys == 'Windows':
        if platform.machine() == 'AMD64':
            return 'win10_x86_64'  # for both win10 and win11
    elif psys == 'Linux':
        # assume all Linux is the supported Ubuntu version for now
        return 'ubuntu_22_04_x86_64'
    elif psys == 'Darwin':
        release, _, machine = platform.mac_ver()
        # use "machine" to add arm64 support here
        release_major = int(release.split('.')[0])
        if release_major >= 12:
            if platform.machine() == 'arm64':
                return f'macos_{release_major}_0_arm64'
            else:
                return f'macos_{release_major}_0_x86_64'
        else:
            _log.warning(f'unsupported macOS version {release}')
            return None
    else:
        _log.warning(f'unsupported platform {psys}')
        return None


def fetch_info(channel=None):
    """Fetch the update information.

    :param channel: The software update channel which is one of
        ['alpha', 'beta', 'stable'].  None (default) is equivalent to 'stable'.
    :return: None on error or dict containing:
        * channel: The update channel.
        * current_version: The currently running version string.
        * available_version: The available version string.
        * download_url: The URL to download the available version.
        * sha256_url: The URL to download the SHA256 over the download contents.
        * changelog_url: The URL to download the changelog for the available version.
    """
    channel = _validate_channel(channel)
    platform_name = _platform_name()
    if platform_name is None:
        return None

    try:
        response = requests.get(_URL_INDEX, timeout=_TIMEOUT)
    except Exception:
        _log.warning('Could not connect to software download server')
        return None

    try:
        data = json.loads(response.text)
    except Exception:
        _log.warning('Could not parse software metadata')
        return None

    try:
        active = data.get('active', {}).get(channel, {})
        latest_version = active.get('version', [0, 0, 0])
        if not is_newer(latest_version):
            _log.info('software up to date: version=%s, latest=%s, channel=%s',
                      __version__,
                      version_to_str(latest_version),
                      channel)
            return None
        return {
            'channel': channel,
            'current_version': __version__,
            'available_version': version_to_str(latest_version),
            'download_url': _URL_BASE + active['releases'][platform_name],
            'changelog_url': _URL_BASE + active['changelog']
        }
    except Exception:
        _log.exception('Unexpected error checking available software')
        return None


def _download(url, path):
    os.makedirs(path, exist_ok=True)
    fname = url.split('/')[-1]
    path = os.path.join(path, fname)

    try:
        response = requests.get(url + '.sha256', timeout=_TIMEOUT)
    except Exception:
        _log.warning('Could not download %s', url)
        return None
    sha256_hex = response.text.split(' ')[0]

    def validate_hash():
        if os.path.isfile(path):
            m = hashlib.sha256()
            with open(path, 'rb') as f:
                m.update(f.read())
            return m.hexdigest() == sha256_hex
        return False

    if validate_hash():  # skip download if already downloaded
        return path
    try:
        response = requests.get(url, timeout=_TIMEOUT)
    except Exception:
        _log.warning('Could not download %s', url)
        return None

    path_tmp = path + '.tmp'
    with open(path_tmp, 'wb') as f:
        f.write(response.content)
    os.rename(path_tmp, path)
    if validate_hash():
        return path
    raise RuntimeError('Invalid sha256 hash')


def _run(callback, path, channel):
    try:
        info = fetch_info(channel)
        if info is not None:
            shutil.rmtree(path, ignore_errors=True)
            info['download_path'] = _download(info['download_url'], path)
        callback(info)
    except Exception:
        _log.exception('Software update check failed')
        _log.info('Software update check failed')


def check(callback, path, channel=None):
    """Check for software updates.

    :param callback: The function to call when the check is complete.
        * On no update needed, callback(None).
        * On timeout, callback('timeout')
        * On update available, callback(info).  The info dict contains keys:
          * channel: The update channel.
          * current_version: The currently running version string.
          * available_version: The available version string.
          * download_path: The path to the available version installer.
          * changelog_path: The path to the changelog for the available version.
    :param path: The path for storing the software updates.
    :param channel: The software update channel which is in:
        ['alpha', 'beta', 'stable'].  None (default) is equivalent to 'stable'.
    :return: The software update thread.
    """
    if __version__ == 'UNRELEASED':
        _log.info('Skip software update check: version is UNRELEASED')
        return None
    _log.info('Start software update check: path=%s, channel=%s', path, channel)
    channel = _validate_channel(channel)
    if _platform_name() is None:
        return None
    thread = threading.Thread(name='sw_update_check', target=_run, args=[callback, path, channel])
    thread.daemon = True
    thread.start()
    return thread


def apply(info):
    path = info['download_path']
    _log.info('software update apply: %s', path)
    if platform.system() == 'Windows':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([path, '/SILENT'], creationflags=flags)
    elif platform.system() == 'Darwin':
        subprocess.run(['hdiutil', 'attach', '-autoopen', path])
    else:
        show_in_folder(os.path.dirname(path))


@register_decorator('software_update')
class SoftwareUpdateDialog(QtWidgets.QDialog):
    """Display user-meaningful help information."""

    _clipboard = None

    def __init__(self, pubsub, info, done_action=None):
        _log.debug('create start')
        self._pubsub = pubsub
        self._info = info
        self._done_action = done_action
        style = load_style()
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setObjectName("software_update")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

        html = _HEADER.format(style=style) + \
            _BODY.format(**_SOFTWARE_UPDATE_TXT, **info)

        self._label = QtWidgets.QLabel(html, self)
        self._label.setWordWrap(True)
        self._label.setOpenExternalLinks(True)
        self._layout.addWidget(self._label)

        self._buttons = QtWidgets.QDialogButtonBox()
        if is_release:
            self._buttons = QtWidgets.QDialogButtonBox()
            self._update = self._buttons.addButton(N_('Update Now'), QtWidgets.QDialogButtonBox.YesRole)
            self._update.pressed.connect(self.accept)
            self._later = self._buttons.addButton(N_('Later'), QtWidgets.QDialogButtonBox.NoRole)
            self._later.pressed.connect(self.reject)
            self._layout.addWidget(self._buttons)
        else:
            html = _HEADER.format(style=style) + _PROMPT
            self._action_prompt = QtWidgets.QLabel(html, self)
            self._action_txt = f'{sys.orig_argv[0]} -m pip install -U --upgrade-strategy=eager joulescope_ui'
            self._action = QtWidgets.QLabel(self._action_txt, self)
            self._action_copy = QtWidgets.QPushButton(N_('Copy to clipboard'), self)
            self._action_copy.pressed.connect(self._on_action_copy)
            self._layout.addWidget(self._action_prompt)
            self._layout.addWidget(self._action)
            self._layout.addWidget(self._action_copy)

            self._ok = self._buttons.addButton(N_('OK'), QtWidgets.QDialogButtonBox.YesRole)
            self._ok.pressed.connect(self.accept)
            self._layout.addWidget(self._buttons)

        self.setWindowTitle(_TITLE)
        self.finished.connect(self._on_finish)

        _log.info('open')
        self.open()

    @QtCore.Slot()
    def _on_action_copy(self):
        SoftwareUpdateDialog._clipboard = self._action_txt
        QtWidgets.QApplication.clipboard().setText(self._action_txt)

    @QtCore.Slot(int)
    def _on_finish(self, value):
        if not is_release:
            _log.info('software update: not a release')
        elif value == QtWidgets.QDialog.DialogCode.Accepted:
            _log.info('software update: update now')
            self._pubsub.publish('registry/ui/actions/!close', {'software_update': self._info})
        else:
            _log.info('software update: later')
        if self._done_action is not None:
            self._pubsub.publish(*self._done_action, defer=True)
        self.close()

    @staticmethod
    def on_cls_action_show(pubsub, topic, value):
        info, done_action = value
        SoftwareUpdateDialog(pubsub, info, done_action)


if __name__ == '__main__':
    _run(lambda x: print(x), 'stable')
