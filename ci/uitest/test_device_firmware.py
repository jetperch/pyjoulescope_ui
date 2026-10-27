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

"""Bring attached device firmware up to date through the UI.

When a JS220 or JS320 runs firmware older than the firmware bundled with the
UI, the UI opens its Device Update dialog at startup.  That window-modal dialog
would block every later test, so this test runs first (``firmware`` marker,
see ``conftest.py``) and performs the update through the dialog.  When all
firmware is current, it does nothing.  JS110 has no UI firmware update.

See docs/plans/expand_test_coverage_202610.md, Stage 0.
"""

import time

import pytest

from uitest import discover
from uitest.conftest import FIRMWARE_STALE
from uitest.harness import DEVICE_UPDATE_DIALOG

pytestmark = [pytest.mark.device, pytest.mark.firmware]

_UPDATABLE = ('JS220', 'JS320')
_DEVICE_TIMEOUT = 30.0      # seconds for devices to open and report versions
_DIALOG_TIMEOUT = 60.0      # seconds for the startup dialog to appear
_UPDATE_TIMEOUT = 900.0     # seconds for all updates (JS320 includes the FPGA)
_REOPEN_TIMEOUT = 120.0     # seconds for an updated device to reopen

# DeviceUpdateDialog status strings (untranslated; the suite runs in English).
_STATUS_DONE = ('Device update completed.', 'No updates available.')


def _is_stale(update_available):
    from joulescope_ui.devices.device_update import is_update_available
    return is_update_available(update_available)


def _update_available(session, unique_id):
    return session.query(f'registry/{unique_id}/settings/update_available')


def _versions(session, models):
    """Wait for each attached updatable device to report ``update_available``.

    :return: ``{unique_id: update_available}``.  The value stays None for a
        device that never reports (a driver without embedded firmware).
    """
    deadline = time.monotonic() + _DEVICE_TIMEOUT
    while True:
        devices = [d for d in session.devices() if d.model in models]
        versions = {d.unique_id: _update_available(session, d.unique_id) for d in devices}
        found = {d.model for d in devices}
        if (found >= set(models) and all(v is not None for v in versions.values())) \
                or time.monotonic() >= deadline:
            return versions
        session.wait(0.5)


def _text(session, name):
    rsp = session.qt_action('get_property', path=name, property='text')
    return rsp.get('value') if rsp.get('ok') else None


def _wait_text(session, name, values, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = _text(session, name)
        if text in values:
            return text
        session.wait(1.0)
    pytest.fail(f'{name} never showed {values} (last: {_text(session, name)!r})')


def test_device_firmware(ui_session, request):
    expected = discover.advertised_models()
    if expected == ():
        pytest.skip(f'{discover.ENV_DEVICES} is empty; no device tests')
    models = [m for m in (expected or _UPDATABLE) if m in _UPDATABLE]
    if not models:
        pytest.skip('no attached model supports a UI firmware update')

    versions = _versions(ui_session, models)
    stale = {uid: v for uid, v in versions.items() if _is_stale(v)}
    if not stale:
        return  # firmware current: nothing to do
    stash = request.config.stash[FIRMWARE_STALE]
    stash.update(stale)

    ui_session.wait_for_root(DEVICE_UPDATE_DIALOG, timeout=_DIALOG_TIMEOUT)
    _wait_text(ui_session, 'device_update_ok', ['Update'], timeout=_DEVICE_TIMEOUT)
    ui_session.qt_action('click', path='device_update_ok')   # every stale device is checked
    _wait_text(ui_session, 'device_update_status', _STATUS_DONE, timeout=_UPDATE_TIMEOUT)

    for unique_id in stale:
        ui_session.wait_for(f'registry/{unique_id}/settings/update_available',
                            lambda v: v is not None and not _is_stale(v),
                            timeout=_REOPEN_TIMEOUT)
        stash.pop(unique_id)

    # Close the dialog once its rescan finds nothing left to update.
    _wait_text(ui_session, 'device_update_status', [_STATUS_DONE[1]], timeout=_DEVICE_TIMEOUT)
    ui_session.qt_action('click', path='device_update_ok')
    ui_session.wait(0.5)
    assert ui_session.qt_inspect(max_depth=0).get('objectName') != DEVICE_UPDATE_DIALOG
