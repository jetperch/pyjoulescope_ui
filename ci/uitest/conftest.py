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
* ``device`` -- requires a connected Joulescope; parametrized per advertised
  model on the active station (see :mod:`ci.uitest.stations`).
* ``slow``   -- long-running (e.g. the 1 h / 10 h captures); excluded from the
  release gate, scheduled separately.

Run the hardware-free subset anywhere with::

    pytest ci/uitest -m "not device"
"""

import os
import time

import pytest

from uitest import stations
from uitest.harness import UiSession


_ARTIFACTS_DIR = os.environ.get('JS_UITEST_ARTIFACTS',
                                os.path.join(os.getcwd(), 'uitest_artifacts'))


def pytest_configure(config):
    config.addinivalue_line('markers', 'device: requires a connected Joulescope device')
    config.addinivalue_line('markers', 'slow: long-running test (hours); not in the release gate')


def pytest_generate_tests(metafunc):
    """Parametrize ``device`` tests over the active station's advertised models."""
    if 'device_model' not in metafunc.fixturenames:
        return
    station = stations.current_station()
    models = list(station.devices) if station else []
    if not models:
        metafunc.parametrize(
            'device_model',
            [pytest.param(None, marks=pytest.mark.skip(reason='no devices advertised by station'))],
        )
    else:
        metafunc.parametrize('device_model', models, ids=[m.lower() for m in models])


@pytest.fixture(scope='session')
def station():
    """The active HIL station (or the no-device ``default``)."""
    return stations.current_station()


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


def _new_session(**kwargs):
    kwargs.setdefault('offscreen', _offscreen_default())
    executable = os.environ.get('JS_UITEST_EXECUTABLE') or None
    return UiSession(executable=executable, **kwargs)


@pytest.fixture
def ui_session(request):
    """A started :class:`UiSession`, torn down (and config-cleared) after the test.

    Skips when the UI stack (PySide6 / joulescope_ui) is unavailable so the
    suite still collects on a bare developer machine.
    """
    _require_ui_stack()
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


@pytest.fixture
def device(ui_session, device_model):
    """Resolve the parametrized model to a connected :class:`discover.Device`.

    Polls briefly because USB enumeration completes asynchronously after the UI
    launches.  Fails (not skips) when the station advertises the model but it is
    still absent after the timeout -- a missing advertised device is a real
    fault on the bench.
    """
    if device_model is None:
        pytest.skip('no devices advertised by station')
    timeout = float(os.environ.get('JS_UITEST_DEVICE_TIMEOUT', '10'))
    deadline = time.monotonic() + timeout
    while True:
        found = [d for d in ui_session.devices() if d.model == device_model]
        if found:
            return found[0]
        if time.monotonic() >= deadline:
            pytest.fail(
                f'station advertises {device_model} but no such device is '
                f'connected (waited {timeout:g}s)')
        ui_session.wait(0.5)


def _has_display():
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@pytest.fixture
def rendered_waveform(request, tmp_path):
    """A started UiSession showing a *rendered* file waveform, for mouse tests.

    Yields ``(session, waveform_id, source_id)``.  Launches non-offscreen with a
    large window (the plot needs room to lay out its rows), opens a generated
    recording, and skips when there is no display or the GL plot does not render
    (headless/no-GPU) -- mouse hit-testing needs the painted geometry.
    """
    _require_ui_stack()
    if not _has_display():
        pytest.skip('no display; rendered-waveform tests need a real display')
    import numpy as np
    from uitest.jls_fixtures import write_fsr_v2

    session = _new_session(offscreen=False)
    session.start()
    request.node._ui_session = session
    try:
        session.resize_window(1600, 900)
        session.wait(1.0)
        path = str(tmp_path / 'rendered.jls')
        write_fsr_v2(path, sample_rate=1000,
                     data=(0.4 + 0.1 * np.sin(np.arange(40000) / 40.0)).astype(np.float32))
        source_id = session.open_file(path)
        session.wait(2.0)
        wf = session.waveform()
        if not session.wait_for_render(wf, timeout=15.0):
            pytest.skip('waveform plot not rendering (no GL/compositor)')
        yield session, wf, source_id
    finally:
        request.node._ui_session = None
        session.stop()


@pytest.fixture
def tmp_capture(tmp_path):
    """A temp directory for A/B/C capture & export files."""
    d = tmp_path / 'captures'
    d.mkdir()
    return d


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
