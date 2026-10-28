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

"""Pytest fixtures for the automated UI release tests.

Markers
-------
* ``device`` -- requires a connected Joulescope; parametrized per model.  With
  ``JS_UITEST_DEVICES`` set, the listed models are expected (absent = FAIL);
  unset, every known model is a candidate and absent models skip
  (see :func:`uitest.discover.advertised_models`).
* ``slow``   -- long-running (e.g. the 1 h / 10 h captures); excluded from the
  release gate, scheduled separately.
* ``firmware`` -- brings device firmware up to date; always runs first
  (see ``test_device_firmware.py``).

Run the hardware-free subset anywhere with::

    pytest ci/uitest -m "not device"
"""

import os
from pathlib import Path
import re
import sys
import time

import pytest

from uitest import discover, fsutil
from uitest.harness import UiSession


_ARTIFACTS_DIR = os.environ.get('JS_UITEST_ARTIFACTS',
                                os.path.join(os.getcwd(), 'uitest_artifacts'))

#: Devices whose firmware the ``firmware`` test left out of date.  Their
#: startup Device Update dialog would block every later UI session.
FIRMWARE_STALE = pytest.StashKey[dict]()


def pytest_configure(config):
    config.addinivalue_line('markers', 'device: requires a connected Joulescope device')
    config.addinivalue_line('markers', 'slow: long-running test (hours); not in the release gate')
    config.addinivalue_line('markers', 'waveform_data(factory): rendered_waveform data factory')
    config.addinivalue_line('markers', 'waveform_path(factory): rendered_waveform file to open')
    config.addinivalue_line('markers', 'firmware: updates device firmware; runs first')
    config.stash[FIRMWARE_STALE] = {}


def pytest_collection_modifyitems(config, items):
    # Update firmware before anything else (stable sort keeps the rest in order).
    items.sort(key=lambda item: item.get_closest_marker('firmware') is None)


def _require_firmware_current(request):
    stale = request.config.stash[FIRMWARE_STALE]
    if stale:
        pytest.fail(f'device firmware out of date (see test_device_firmware): {stale}')


def pytest_generate_tests(metafunc):
    """Parametrize ``device`` tests over the expected or candidate models.

    ``JS_UITEST_DEVICES`` set: parametrize over exactly those models -- the
    :func:`device` fixture FAILS when one is absent.  Unset (auto-detect):
    parametrize over every known model as a candidate -- absent models skip
    at runtime, since detection needs a running UI session.
    """
    if 'device_model' not in metafunc.fixturenames:
        return
    models = discover.advertised_models()
    if models is None:
        models = list(discover._MODELS)
    if not models:
        metafunc.parametrize(
            'device_model',
            [pytest.param(None, marks=pytest.mark.skip(
                reason=f'{discover.ENV_DEVICES} is empty; no device tests'))],
        )
    else:
        metafunc.parametrize('device_model', list(models),
                             ids=[m.lower() for m in models])


def _offscreen_default():
    # Headless by default; set JS_UITEST_DISPLAY=1 on a bench with a real display.
    return not os.environ.get('JS_UITEST_DISPLAY')


def _require_ui_stack():
    """Skip the test when PySide6 / joulescope_ui are unavailable."""
    try:
        import joulescope_ui  # noqa: F401  (presence check only)
        import PySide6        # noqa: F401
    except ImportError as e:
        pytest.skip(f'UI stack unavailable: {e}')


# Do not wait for vblank (Mesa, NVIDIA).  A blanked screen on an unattended
# bench stops frame presentation, so each OpenGL swap stalls the UI.
_NO_VSYNC_ENV = {'vblank_mode': '0', '__GL_SYNC_TO_VBLANK': '0'}


# The installed release under test: None until installed, or the exception.
_release = {}


def _release_executable():
    """Install the published build of this UI version once, for a release build.

    ``JS_UITEST_BUILD_KIND=release`` (the HIL farm sets it for a release tag)
    tests the published installer instead of the pip-installed sdist.  arm64
    Linux has no installer (Flatpak only), so it keeps testing the sdist.

    :return: The installed executable, or None to run the sdist.
    """
    if os.environ.get('JS_UITEST_BUILD_KIND') != 'release':
        return None
    from uitest import installer
    try:
        key = installer.platform_key()
    except RuntimeError:
        return None
    if 'value' not in _release:
        import tempfile
        from joulescope_ui import __version__
        try:
            # The farm pushes a release right after publish; allow for a
            # cached download index.
            _release['value'] = installer.install_release(
                __version__, os.path.join(tempfile.gettempdir(), 'uitest_release', key),
                wait=600.0)
        except Exception as ex:
            _release['value'] = ex
    value = _release['value']
    if isinstance(value, Exception):
        pytest.fail(f'could not install the published UI: {value}')
    return value


def pytest_terminal_summary(terminalreporter):
    """Report which UI the sessions tested: an installed build or the sdist."""
    executable = os.environ.get('JS_UITEST_EXECUTABLE') or _release.get('value')
    if isinstance(executable, Exception):
        text = f'published build failed to install: {executable}'
    elif executable:
        text = f'installed build {executable}'
    else:
        text = 'python -m joulescope_ui (sdist)'
    terminalreporter.write_line(f'UI under test: {text}')


def _new_session(**kwargs):
    kwargs.setdefault('offscreen', _offscreen_default())
    if not kwargs['offscreen'] and sys.platform.startswith('linux'):
        kwargs['env'] = {**_NO_VSYNC_ENV, **(kwargs.get('env') or {})}
    executable = os.environ.get('JS_UITEST_EXECUTABLE') or _release_executable()
    return UiSession(executable=executable, **kwargs)


@pytest.fixture
def ui_session(request):
    """A started :class:`UiSession`, torn down (and config-cleared) after the test.

    Skips when the UI stack (PySide6 / joulescope_ui) is unavailable so the
    suite still collects on a bare developer machine.
    """
    _require_ui_stack()
    _require_firmware_current(request)
    session = _new_session()
    session.start()
    request.node._ui_session = session     # for screenshot-on-failure
    try:
        yield session
    finally:
        request.node._ui_session = None
        session.stop()


@pytest.fixture
def make_ui_session(request):
    """Factory for tests that manage their own UI lifecycle (e.g. restart).

    Returns ``factory(**UiSession_kwargs) -> started UiSession``.  All created
    sessions are stopped at teardown; the most recent is used for
    screenshot-on-failure.
    """
    _require_ui_stack()
    _require_firmware_current(request)
    sessions = []

    def factory(**kwargs):
        session = _new_session(**kwargs)
        session.start()
        sessions.append(session)
        request.node._ui_session = session
        return session

    try:
        yield factory
    finally:
        request.node._ui_session = None
        for session in reversed(sessions):
            try:
                session.stop()
            except Exception:
                pass


# Auto-detect mode: models that already failed a full detection poll this
# session.  A relaunched UI enumerates the same USB bus, so an absent model
# stays absent -- skip immediately instead of re-paying the timeout.
_absent_models = set()


def _resolve_device(session, device_model):
    """Return the connected :class:`discover.Device` for ``device_model``.

    Polls briefly because USB enumeration completes asynchronously after the UI
    launches.  When ``JS_UITEST_DEVICES`` lists the model, absence after the
    timeout FAILS -- a missing expected device is a real fault on the bench.
    In auto-detect mode (variable unset) an absent model skips instead.
    """
    if device_model is None:
        pytest.skip(f'{discover.ENV_DEVICES} is empty; no device tests')
    expected = discover.advertised_models()
    if expected is not None and device_model not in expected:
        # The expectation changed between collection and this test, so this
        # model was never promised for the bench: skip rather than fail.
        expected = None
    if expected is None and device_model in _absent_models:
        pytest.skip(f'{device_model} not detected')
    timeout = float(os.environ.get('JS_UITEST_DEVICE_TIMEOUT', '10'))
    deadline = time.monotonic() + timeout
    while True:
        found = [d for d in session.devices() if d.model == device_model]
        if found:
            return found[0]
        if time.monotonic() >= deadline:
            if expected is None:
                _absent_models.add(device_model)
                pytest.skip(
                    f'{device_model} not detected (waited {timeout:g}s)')
            pytest.fail(
                f'{discover.ENV_DEVICES} lists {device_model} but no such '
                f'device is connected (waited {timeout:g}s)')
        session.wait(0.5)


@pytest.fixture
def all_devices(ui_session):
    """Every expected device, or with ``JS_UITEST_DEVICES`` unset, every
    device detected within the device timeout."""
    expected = discover.advertised_models()
    if expected == ():
        pytest.skip(f'{discover.ENV_DEVICES} is empty; no device tests')
    if expected is not None:
        return [_resolve_device(ui_session, model) for model in expected]
    deadline = time.monotonic() + float(os.environ.get('JS_UITEST_DEVICE_TIMEOUT', '10'))
    while time.monotonic() < deadline:
        ui_session.wait(0.5)
    devices = ui_session.devices()
    if not devices:
        pytest.skip('no device detected')
    return devices


@pytest.fixture
def device(ui_session, device_model):
    """The connected :class:`discover.Device` for the parametrized model."""
    return _resolve_device(ui_session, device_model)


def _has_display():
    if sys.platform in ('win32', 'darwin'):
        return True  # an interactive session always has a display
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def _rendered_env():
    """UI environment for rendered sessions.

    On Wayland, run the UI on XWayland: synthetic clicks cannot open popup
    menus on native Wayland, which needs a real input-event serial.
    """
    if (sys.platform.startswith('linux') and os.environ.get('WAYLAND_DISPLAY')
            and os.environ.get('DISPLAY') and not os.environ.get('QT_QPA_PLATFORM')):
        return {'QT_QPA_PLATFORM': 'xcb'}
    return {}


def _rendered_session(request):
    """Start a non-offscreen UiSession, or skip/fail when it cannot render.

    :return: ``(session, unavailable)``.  ``unavailable`` skips, or fails when
        ``JS_UITEST_DISPLAY`` promises a display.
    """
    _require_ui_stack()
    _require_firmware_current(request)
    unavailable = pytest.fail if os.environ.get('JS_UITEST_DISPLAY') else pytest.skip
    if not _has_display():
        unavailable('no display; rendered-waveform tests need a real display')
    session = _new_session(offscreen=False, env=_rendered_env())
    session.start()
    request.node._ui_session = session
    return session, unavailable


def _waveforms(session):
    return {i for i in session.enumerate('registry') if i.startswith('WaveformWidget:')}


@pytest.fixture
def rendered_waveform(request, tmp_path):
    """A started UiSession showing a *rendered* file waveform, for mouse tests.

    Yields ``(session, waveform_id, source_id)``.  Launches non-offscreen with a
    large window (the plot needs room to lay out its rows), opens a generated
    recording, and closes the attached-device waveforms so the file plot gets
    the space.  When there is no display or the GL plot does not render
    (headless/no-GPU), skips, or fails when ``JS_UITEST_DISPLAY`` promises a
    display.  ``@pytest.mark.waveform_data(factory=fn)`` replaces the recording
    data with ``fn()``, and ``@pytest.mark.waveform_path(factory=fn)`` opens the
    file at path ``fn()`` instead.
    """
    import numpy as np
    from uitest.jls_fixtures import write_fsr_v2

    session, unavailable = _rendered_session(request)
    try:
        path_marker = request.node.get_closest_marker('waveform_path')
        if path_marker is not None:
            path = path_marker.kwargs['factory']()
        else:
            path = str(tmp_path / 'rendered.jls')
            marker = request.node.get_closest_marker('waveform_data')
            if marker is None:
                data = (0.4 + 0.1 * np.sin(np.arange(40000) / 40.0)).astype(np.float32)
            else:
                data = marker.kwargs['factory']()
            write_fsr_v2(path, sample_rate=1000, data=data)
        live = _waveforms(session)
        source_id = session.open_file(path)
        session.wait(2.0)
        wf = sorted(_waveforms(session) - live)[-1]
        for widget_id in sorted(live):
            session.publish('registry/view/actions/!widget_close', widget_id)
        session.resize_window_settled(1600, 900)
        if not session.wait_for_render(wf, timeout=15.0):
            unavailable('waveform plot not rendering (no GL/compositor)')
        yield session, wf, source_id
    finally:
        request.node._ui_session = None
        session.stop()


@pytest.fixture
def rendered_live_waveform(request, device_model):
    """A started UiSession showing the *rendered* live waveform of a device.

    Yields ``(session, waveform_id, device)`` with the Oscilloscope view active
    and the device streaming.  Skips or fails like :func:`rendered_waveform`.
    """
    session, unavailable = _rendered_session(request)
    try:
        device = _resolve_device(session, device_model)
        session.set_view('oscilloscope')
        wf = sorted(_waveforms(session))[0]
        session.publish('registry/app/settings/signal_stream_enable', True)
        session.resize_window_settled(1600, 900)
        if not session.wait_for_render(wf, timeout=15.0):
            unavailable('waveform plot not rendering (no GL/compositor)')
        yield session, wf, device
    finally:
        request.node._ui_session = None
        session.stop()


_CAPTURE_SUBDIR = 'joulescope_uitest'


@pytest.fixture(scope='session')
def _capture_root():
    """The ``JS_UITEST_CAPTURE_DIR`` subdirectory for this session's
    captures, or None when unset.  Clears what a killed run left behind."""
    base = os.environ.get(discover.ENV_CAPTURE_DIR)
    if not base:
        yield None
        return
    root = Path(os.path.expanduser(base)) / _CAPTURE_SUBDIR
    fsutil.remove(root)
    root.mkdir(parents=True)
    yield root
    fsutil.remove(root)


@pytest.fixture
def tmp_capture(tmp_path, request, _capture_root):
    """A temp directory for A/B/C capture & export files.

    Under ``JS_UITEST_CAPTURE_DIR`` when set, removed after the test, since
    captures can be tens of GB; else in pytest's temp directory.
    """
    if _capture_root is None:
        d = tmp_path / 'captures'
        d.mkdir()
        yield d
        return
    d = _capture_root / re.sub(r'[^\w.-]', '_', request.node.name)
    d.mkdir()
    yield d
    fsutil.remove(d)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """On failure, save a screenshot of the running UI as a test artifact."""
    outcome = yield
    report = outcome.get_result()
    if report.when != 'call' or not report.failed:
        return
    session = getattr(item, '_ui_session', None)
    if session is None or session.client is None:
        return
    try:
        os.makedirs(_ARTIFACTS_DIR, exist_ok=True)
        safe = item.nodeid.replace('/', '_').replace('::', '__').replace(':', '_')
        dest = os.path.join(_ARTIFACTS_DIR, f'{safe}.png')
        session.screenshot(dest)
        report.sections.append(('UI screenshot', dest))
    except Exception:
        pass  # never let artifact capture mask the real failure
