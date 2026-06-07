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

"""Launch the Joulescope UI and drive it through its TCP control socket.

:class:`UiSession` starts the UI with ``--tcp-server``, waits for the
auto-generated ``server.json`` credentials, connects a
:class:`joulescope_ui.tcp_client.Client`, and exposes lifecycle + helper
methods for the test suite.  On exit it asks the UI to close cleanly (optionally
clearing config), then force-kills if the UI fails to exit so a wedged run never
strands the bench.

The ``joulescope_ui.tcp_client`` import is **deferred** to :meth:`UiSession.start`
so this module can be imported (and the Qt-free helpers unit-tested) on a machine
without PySide6.
"""

import logging
import os
import signal
import subprocess
import time

from uitest import discover, installer

_log = logging.getLogger(__name__)

# A query topic that exists as soon as the pubsub bridge is live.
_READY_TOPIC = 'common/settings/paths/app'


class UiSessionError(RuntimeError):
    """Raised when the UI fails to start or become ready."""


class UiSession:
    """A running UI instance under automated control.

    :param executable: Path to the installed ``joulescope`` executable.  When
        None, launches the dev module (``python -m joulescope_ui ui``).
    :param app: Application name (drives the ``server.json`` location).
    :param offscreen: When True, set ``QT_QPA_PLATFORM=offscreen`` (headless,
        for the hardware-free suite on CI runners).
    :param config_clear_on_exit: When True, clear UI config on shutdown so each
        session starts from defaults.
    :param startup_timeout: Seconds to wait for ``server.json`` to appear.
    :param ready_timeout: Seconds to wait for the pubsub bridge to answer.
    :param client_timeout: Per-request socket timeout for the control client.
        The client default of 5 s is marginal for a fully-loaded UI, so the
        harness uses a longer default.
    :param env: Extra environment variables for the UI process.
    """

    def __init__(self, executable=None, app=discover.APP_NAME, *, offscreen=False,
                 config_clear_on_exit=True, startup_timeout=30.0, ready_timeout=30.0,
                 client_timeout=10.0, env=None):
        self.executable = executable
        self.app = app
        self.offscreen = offscreen
        self.config_clear_on_exit = config_clear_on_exit
        self.startup_timeout = startup_timeout
        self.ready_timeout = ready_timeout
        self.client_timeout = client_timeout
        self._extra_env = dict(env or {})
        self._proc = None
        self._client = None
        self._server_json = discover.server_json_path(app)
        #: True if the last stop() exited the UI cleanly (config saved); False
        #: if it had to be terminated/killed (config NOT saved).
        self.exited_cleanly = None

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        """Launch the UI and connect the control client."""
        from joulescope_ui.tcp_client import Client  # deferred: needs PySide6 stack

        self._remove_server_json()
        argv = installer.launch_command(self.executable)
        env = dict(os.environ)
        env.update(self._extra_env)
        if self.offscreen:
            env['QT_QPA_PLATFORM'] = 'offscreen'
        _log.info('launching UI: %s', ' '.join(argv))
        self._proc = subprocess.Popen(argv, env=env)

        creds = self._wait_for_credentials()
        self._client = Client(port=creds['port'], token=creds['token'],
                              timeout=self.client_timeout)
        self._client.open()
        self._wait_until_ready()
        _log.info('UI session ready (pid=%s, port=%s)', self._proc.pid, creds['port'])
        return self

    def stop(self):
        """Close the UI cleanly, then ensure the process is gone."""
        if self._client is not None:
            try:
                value = {'config_clear': True} if self.config_clear_on_exit else {}
                self._client.publish('registry/ui/actions/!close', value)
            except Exception:
                _log.warning('clean close request failed', exc_info=True)
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._terminate_process()
        self._remove_server_json()

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    @property
    def client(self):
        """The connected :class:`Client` (or None before :meth:`start`)."""
        return self._client

    # -- generic pass-throughs --------------------------------------------

    def query(self, topic):
        """Query a retained pubsub topic value."""
        return self._client.query(topic)

    def publish(self, topic, value=None):
        """Publish a value to a pubsub topic."""
        return self._client.publish(topic, value)

    def enumerate(self, topic, absolute=None):
        """Enumerate child topics."""
        return self._client.enumerate(topic, absolute=absolute)

    def subscribe(self, topic, callback, flags=None):
        """Subscribe to a pubsub topic."""
        return self._client.subscribe(topic, callback, flags)

    def qt_inspect(self, path='', max_depth=50):
        """Inspect the Qt widget tree."""
        return self._client.qt_inspect(path=path, max_depth=max_depth)

    def qt_action(self, action, path='', **kwargs):
        """Perform a Qt action (click/key/set_property/get_property)."""
        return self._client.qt_action(action, path=path, **kwargs)

    def qt_screenshot(self, path=''):
        """Return a PNG screenshot of a widget (root by default) as bytes."""
        return self._client.qt_screenshot(path=path)

    # -- helpers -----------------------------------------------------------

    def devices(self):
        """Enumerate connected Joulescope devices (see :func:`discover.enumerate_devices`)."""
        return discover.enumerate_devices(self._client)

    def wait_for_statistics(self, unique_id, timeout=15.0):
        """Enable statistics streaming and return the next statistics sample.

        :param unique_id: Device unique id (e.g. ``'JS220-002557'``).
        :param timeout: Seconds to wait for a sample.
        :raises TimeoutError: If no statistics arrive (device closed/absent).
        :return: The statistics data dict (``time``/``signals``/``accumulators``).
        """
        samples = []
        topic = f'registry/{unique_id}/events/statistics/!data'
        self.subscribe(topic, lambda t, v: samples.append(v), ['pub'])
        self.publish(f'registry/{unique_id}/settings/auto_open', True)
        self.publish('registry/app/settings/statistics_stream_enable', True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if samples:
                return samples[-1]
            self.wait(0.1)
        raise TimeoutError(f'no statistics from {unique_id} within {timeout}s')

    def screenshot(self, dest_path, widget=''):
        """Capture a screenshot of ``widget`` and write it to ``dest_path``."""
        png = self.qt_screenshot(path=widget)
        with open(dest_path, 'wb') as f:
            f.write(png)
        return dest_path

    def show_about(self):
        """Open Help -> About and return its widget subtree for inspection."""
        self.publish('registry/help_html/actions/!show', 'about')
        # Let the dialog construct before inspecting.
        self.wait(0.3)
        return self.qt_inspect()

    def wait_for(self, topic, predicate, timeout=10.0, interval=0.1):
        """Poll ``topic`` until ``predicate(value)`` is truthy or timeout.

        :return: The value that satisfied the predicate.
        :raises TimeoutError: If the predicate is never satisfied.
        """
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = self.query(topic)
                if predicate(last):
                    return last
            except Exception:
                pass
            self.wait(interval)
        raise TimeoutError(f'wait_for({topic!r}) timed out; last={last!r}')

    @staticmethod
    def wait(seconds):
        """Sleep helper (kept as a method so tests can monkeypatch timing)."""
        time.sleep(seconds)

    # -- internals ---------------------------------------------------------

    def _wait_for_credentials(self):
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise UiSessionError(
                    f'UI exited during startup (code {self._proc.returncode})')
            creds = discover.find_credentials(self._server_json, self.app)
            if creds and 'port' in creds and 'token' in creds:
                return creds
            self.wait(0.2)
        raise UiSessionError(
            f'server.json not found within {self.startup_timeout}s at {self._server_json}')

    def _wait_until_ready(self):
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            try:
                if self._client.query(_READY_TOPIC):
                    return
            except Exception:
                pass
            self.wait(0.2)
        raise UiSessionError(f'UI pubsub bridge not ready within {self.ready_timeout}s')

    def _terminate_process(self):
        proc = self._proc
        if proc is None:
            return
        # The !close action makes the UI save config and quit on its own
        # (clean exit, returncode 0).  Terminate/kill are last-resort fallbacks
        # and mean config was NOT saved, so record that for persistence tests.
        self.exited_cleanly = True
        if proc.poll() is None:
            try:
                proc.wait(timeout=15.0)   # wait for the !close-initiated exit
            except subprocess.TimeoutExpired:
                self.exited_cleanly = False
                _log.warning('UI did not exit on !close; terminating (config NOT saved)')
                proc.terminate()
                try:
                    proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    _log.error('UI did not terminate; killing')
                    proc.kill()
                    proc.wait(timeout=5.0)
        if proc.returncode not in (0, None):
            # Non-zero exit: clean save not guaranteed.
            self.exited_cleanly = self.exited_cleanly and (proc.returncode == 0)
        self._proc = None

    def _remove_server_json(self):
        try:
            os.remove(self._server_json)
        except FileNotFoundError:
            pass
        except OSError:
            _log.warning('could not remove %s', self._server_json, exc_info=True)
