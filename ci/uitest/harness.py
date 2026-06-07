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
    :param suppress_startup_dialogs: Dismiss the first-run "Getting Started" /
        changelog dialog at startup so it does not steal the active window from
        automation (default True).
    :param env: Extra environment variables for the UI process.
    """

    def __init__(self, executable=None, app=discover.APP_NAME, *, offscreen=False,
                 config_clear_on_exit=True, startup_timeout=30.0, ready_timeout=30.0,
                 client_timeout=10.0, suppress_startup_dialogs=True, env=None):
        self.executable = executable
        self.app = app
        self.offscreen = offscreen
        self.config_clear_on_exit = config_clear_on_exit
        self.suppress_startup_dialogs = suppress_startup_dialogs
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
        if self.suppress_startup_dialogs:
            self._suppress_startup_dialogs()
        _log.info('UI session ready (pid=%s, port=%s)', self._proc.pid, creds['port'])
        return self

    def _suppress_startup_dialogs(self):
        """Dismiss the first-run "Getting Started" / changelog dialog.

        On fresh or cleared config the UI pops a ``HelpHtmlMessageBox`` at
        startup (see ``main._startup_display_maybe``).  It is window-stay-on-top
        and becomes the active window, so ``qt_inspect``/``qt_screenshot`` and
        windowTitle queries would target the dialog instead of the main window.

        Persist ``changelog_version_show`` so a clean restart skips it, then
        dismiss any dialog already shown (it may arrive slightly after ready via
        the deferred ``!pend`` action, so poll briefly).
        """
        try:
            # Owned by the MainWindow (registry/ui), not registry/app.
            from joulescope_ui import __version__ as ui_version
            self._client.publish('registry/ui/settings/changelog_version_show', ui_version)
        except Exception:
            _log.debug('could not set changelog_version_show', exc_info=True)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                root = self._client.qt_inspect(path='', max_depth=0)
            except Exception:
                return
            cls = root.get('class', '')
            name = root.get('objectName', '')
            is_dialog = (name == 'help_html_message_box'
                         or 'MessageBox' in cls or cls.endswith('Dialog'))
            if not is_dialog:
                return  # main window is active; nothing to dismiss
            try:
                self._client.qt_action('key', key='Escape')   # QDialog -> reject -> close
            except Exception:
                pass
            self.wait(0.25)

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

    def _record_config(self, path, source_ids):
        """Build a SignalRecord config (replicates signal_record_config.config_default)."""
        if source_ids is None:
            source_ids = self.query(
                'registry_manager/capabilities/signal_stream.source/list') or []
        sources = {}
        for sid in source_ids:
            signals = {}
            for signal_id in self.enumerate(f'registry/{sid}/settings/signals'):
                enable_topic = f'registry/{sid}/settings/signals/{signal_id}/enable'
                try:
                    enabled = bool(self.query(enable_topic))
                except Exception:
                    enabled = False
                signals[signal_id] = {
                    'source_id': sid, 'signal_id': signal_id,
                    'enabled': enabled, 'selected': enabled,
                    'enable_topic': enable_topic,
                    'data_topic': f'registry/{sid}/events/signals/{signal_id}/!data',
                }
            sources[sid] = signals
        return {'path': path, 'filename': os.path.splitext(os.path.basename(path))[0],
                'location': os.path.dirname(path), 'sources': sources, 'notes': ''}

    def record_start(self, path, source_ids=None, settle=1.0):
        """Start recording stream data to ``path`` and return the record id.

        :param path: Output ``.jls`` path.
        :param source_ids: Restrict to these stream-source unique ids
            (default all). Scope to one device to keep files small.
        :param settle: Seconds to wait for the SignalRecord instance to register.
        :raises TimeoutError: If the recorder does not start.
        :return: The ``SignalRecord:*`` unique id (pass to :meth:`record_stop`).
        """
        self.publish('registry/app/settings/signal_stream_enable', True)
        before = {i for i in self.enumerate('registry') if i.startswith('SignalRecord:')}
        self.publish('registry/SignalRecord/actions/!start',
                     self._record_config(path, source_ids))
        deadline = time.monotonic() + max(settle, 5.0)
        while time.monotonic() < deadline:
            new = {i for i in self.enumerate('registry')
                   if i.startswith('SignalRecord:')} - before
            if new:
                return sorted(new)[0]
            self.wait(0.2)
        raise TimeoutError(f'recording did not start for {path}')

    def record_stop(self, record_id):
        """Stop a recording and finalize (close) its JLS file."""
        self.publish(f'registry/{record_id}/actions/!stop', None)
        self.wait(0.5)   # let the Writer close the file

    def buffer_sources(self):
        """List unique ids advertising the signal-buffer-source capability.

        These are open files (``JlsSource:*``) and live device stream buffers.
        """
        try:
            return self.query('registry_manager/capabilities/signal_buffer.source/list') or []
        except Exception:
            return []

    @staticmethod
    def annotation_path(path):
        """The sidecar annotation path the exporter writes (``<base>.anno<ext>``)."""
        base, ext = os.path.splitext(path)
        return f'{base}.anno{ext}'

    def add_dual_markers(self, waveform_id, pos1, pos2):
        """Add a dual (pair) x-marker at the given time64 positions."""
        self.publish(f'registry/{waveform_id}/actions/!x_markers',
                     ['add_dual', int(pos1), int(pos2)])
        self.wait(0.3)

    def export_range(self, waveform_id, path, *, x_range, signals=None,
                     annotations=True, timeout=30.0):
        """Export an x-range to a JLS file non-interactively and wait for it.

        Writes ``path`` (data) and, when ``annotations`` and markers are present,
        ``annotation_path(path)`` (markers).  Polls until the data file size is
        stable (the export runs in a background thread with no socket-visible
        completion signal).

        :raises TimeoutError: If the export does not produce a stable file.
        :return: ``path``.
        """
        value = {'path': path, 'x_range': list(x_range), 'annotations': annotations}
        if signals is not None:
            value['signals'] = signals
        for f in (path, self.annotation_path(path)):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
        self.publish(f'registry/{waveform_id}/actions/!export', value)
        anno = self.annotation_path(path) if annotations else None
        deadline = time.monotonic() + timeout
        last_size = -1
        while time.monotonic() < deadline:
            if os.path.exists(path):
                size = os.path.getsize(path)
                # The annotation sidecar is written on a separate path; wait for
                # it too (it can lag the data file for small/fast exports).
                anno_ready = anno is None or os.path.exists(anno)
                if size > 0 and size == last_size and anno_ready:
                    return path        # data size stable + sidecar present
                last_size = size
            self.wait(0.5)
        raise TimeoutError(f'export to {path} did not complete within {timeout}s')

    def buffer_signals(self, source_id):
        """Return analysis signal-ids (``source.device.quantity``) for a buffer source."""
        return [f'{source_id}.{s}'
                for s in self.enumerate(f'registry/{source_id}/settings/signals')]

    def waveform(self):
        """Return the most-recently-created WaveformWidget unique id (or None)."""
        wfs = [i for i in self.enumerate('registry') if i.startswith('WaveformWidget:')]
        return wfs[-1] if wfs else None

    def subrange(self, waveform_id, lo=0.3, hi=0.7):
        """A sub-window of the waveform's data extent (time64), as ``[x0, x1]``.

        Range tools need sample-level data; a fraction of the full extent keeps
        the request below the summary threshold.
        """
        x0, x1 = self.query(f'registry/{waveform_id}/settings/x_range')
        span = x1 - x0
        return [int(x0 + lo * span), int(x0 + hi * span)]

    def run_analysis(self, waveform_id, tool, *, signals=None, x_range=None,
                     accept=True, timeout=10.0):
        """Run a range-tool analysis and return the new result-widget unique ids.

        Drives the non-interactive ``!range_tool`` waveform action, accepts the
        tool's configuration dialog, and waits for its result widget.

        :param tool: range-tool class name (e.g. ``'HistogramRangeTool'``).
        :param signals: explicit signal-id list (see :meth:`buffer_signals`);
            default uses the waveform's displayed signals.
        :param x_range: ``[x0, x1]`` time64 sub-range to analyze.
        :param accept: accept the tool's config dialog (Return) when it appears.
        :return: list of new ``registry`` instance ids whose name contains ``tool``.
        """
        value = {'tool': tool}
        if signals is not None:
            value['signals'] = signals
            value['signal_default'] = signals[0]
        if x_range is not None:
            value['x_range'] = list(x_range)
        before = set(self.enumerate('registry'))
        self.publish(f'registry/{waveform_id}/actions/!range_tool', value)
        if accept:
            # The tool opens a config dialog; poll for it, then accept (Return).
            dlg_deadline = time.monotonic() + 5.0
            while time.monotonic() < dlg_deadline:
                if self.qt_inspect(path='', max_depth=0).get('class', '').endswith('Dialog'):
                    self.qt_action('key', key='Return')
                    break
                self.wait(0.2)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new = [i for i in (set(self.enumerate('registry')) - before) if tool in i]
            if new:
                return new
            self.wait(0.3)
        return []

    def open_file(self, path, timeout=20.0):
        """Open a JLS file in the UI and return the new ``JlsSource`` unique id.

        :param path: Absolute path to a ``.jls`` file (v1 or v2).
        :param timeout: Seconds to wait for the source to register.
        :raises TimeoutError: If no new JlsSource appears.
        :return: The new ``JlsSource:*`` unique id.
        """
        before = {s for s in self.buffer_sources() if s.startswith('JlsSource')}
        self.publish('registry/ui/actions/!file_open', path)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            now = {s for s in self.buffer_sources() if s.startswith('JlsSource')}
            new = now - before
            if new:
                return sorted(new)[0]
            self.wait(0.25)
        raise TimeoutError(f'no JlsSource registered for {path} within {timeout}s')

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
