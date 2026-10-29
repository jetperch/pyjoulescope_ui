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
import shutil
import signal
import subprocess
import time

from uitest import discover, installer

_log = logging.getLogger(__name__)

# A query topic that exists as soon as the pubsub bridge is live.
_READY_TOPIC = 'common/settings/paths/app'

# Recent files; the exporter adds its path on success.
_MRU_TOPIC = 'registry/paths/settings/mru_files'

#: objectName of the startup firmware DeviceUpdateDialog.
DEVICE_UPDATE_DIALOG = 'device_update_dialog'
HELP_DIALOG = 'help_html_message_box'   # Getting Started, changelog, and help


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
    :param log_copy_dir: When set, :meth:`stop` copies the UI's log file
        here, such as the artifacts directory a CI job keeps.
    :param cwd: The UI process working directory.  ``python -m joulescope_ui``
        imports the package from here first, so it selects the UI source.
    """

    def __init__(self, executable=None, app=discover.APP_NAME, *, offscreen=False,
                 config_clear_on_exit=True, startup_timeout=30.0, ready_timeout=30.0,
                 client_timeout=10.0, suppress_startup_dialogs=True, env=None, cwd=None,
                 log_copy_dir=None):
        self.executable = executable
        self.app = app
        self.offscreen = offscreen
        self.config_clear_on_exit = config_clear_on_exit
        self.suppress_startup_dialogs = suppress_startup_dialogs
        self.startup_timeout = startup_timeout
        self.ready_timeout = ready_timeout
        self.client_timeout = client_timeout
        self._extra_env = dict(env or {})
        self._cwd = cwd
        self.log_copy_dir = log_copy_dir
        self._log_names = None   # the UI log files before start()
        self._ui_pid = None      # the UI's pid from server.json
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
        self._log_names = discover.ui_log_names(discover.ui_log_dir(self.app))
        saved_version = discover.saved_changelog_version(self.app)
        argv = installer.launch_command(self.executable)
        env = dict(os.environ)
        env.update(self._extra_env)
        if self.offscreen:
            env['QT_QPA_PLATFORM'] = 'offscreen'
        _log.info('launching UI: %s', ' '.join(argv))
        self._proc = subprocess.Popen(argv, env=env, cwd=self._cwd)

        creds = self._wait_for_credentials()
        self._ui_pid = creds.get('pid')
        self._client = Client(port=creds['port'], token=creds['token'],
                              timeout=self.client_timeout)
        self._client.open()
        self._wait_until_ready()
        if self.suppress_startup_dialogs:
            self._suppress_startup_dialogs(saved_version)
        _log.info('UI session ready (pid=%s, port=%s)', self._proc.pid, creds['port'])
        return self

    def _suppress_startup_dialogs(self, saved_version, timeout=30.0):
        """Dismiss the "Getting Started" or changelog dialog shown at startup.

        The UI shows it when its version differs from the saved
        ``changelog_version_show`` (``main._startup_display_maybe``): after a
        cleared config, as every session leaves it, and after an upgrade.  The
        dialog is window-modal, and the UI queues the Device Update dialog
        behind it, so it must close before any test runs.

        :param saved_version: ``changelog_version_show`` saved before launch.
        :raises UiSessionError: If the expected dialog does not appear and close.
        """
        deadline = time.monotonic() + timeout
        version = None
        while version is None:   # the MainWindow stores its version at startup
            version = self.query('registry/ui/settings/changelog_version_show')
            if version is None:
                if time.monotonic() >= deadline:
                    raise UiSessionError('UI never stored changelog_version_show')
                self.wait(0.1)
        if version == saved_version:
            return
        shown = False
        while time.monotonic() < deadline:
            try:
                visible = self.qt_inspect(path=HELP_DIALOG, max_depth=0).get('visible')
            except RuntimeError:   # not found: not shown yet, or closed
                if shown:
                    return
                visible = False
            if visible:
                self.qt_action('key', path=HELP_DIALOG, key='Escape')   # reject -> close
                shown = True
            self.wait(0.1)
        raise UiSessionError(f'startup dialog {HELP_DIALOG} did not '
                             f'{"close" if shown else "appear"} within {timeout}s')

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
        self._copy_log(discover.ui_log_dir(self.app))

    def _copy_log(self, log_dir):
        """Copy the log files this session's UI started in ``log_dir`` (those
        absent at :meth:`start`) to ``log_copy_dir``; never raises."""
        if self.log_copy_dir is None or self._log_names is None:
            return
        try:
            for name in sorted(discover.ui_log_names(log_dir) - self._log_names):
                os.makedirs(self.log_copy_dir, exist_ok=True)
                shutil.copy2(os.path.join(log_dir, name), self.log_copy_dir)
        except OSError:
            _log.warning('could not copy the UI log', exc_info=True)

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    @property
    def pid(self):
        """The launched process id (or None before :meth:`start`)."""
        return None if self._proc is None else self._proc.pid

    @property
    def ui_pid(self):
        """The UI's own process id, from its ``server.json``.

        On Windows a venv ``python.exe`` is a launcher whose child runs the
        UI, so :attr:`pid` is not the UI.  UIs before 1.7.8 do not write it:
        then this is :attr:`pid`.
        """
        return self._ui_pid or self.pid

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

    def set_signal_frequency(self, unique_id, freq):
        """Set a device's streaming sample rate (Hz) and wait for it to apply."""
        self.publish(f'registry/{unique_id}/settings/signal_frequency', int(freq))
        self.wait_for(f'registry/{unique_id}/settings/signal_frequency',
                      lambda v: int(v) == int(freq), timeout=5.0)

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

    def record_stop(self, record_id, timeout=60.0):
        """Stop a recording and wait until its JLS file is closed.

        The recorder closes the file, then unregisters, so this waits for
        ``record_id`` to leave the registry; a long recording takes a while
        to finalize.

        :raises TimeoutError: If the recorder is still registered.
        """
        self.publish(f'registry/{record_id}/actions/!stop', None)
        self._wait_unregistered(record_id, timeout)

    def close_file(self, source_id, timeout=30.0):
        """Close a JLS file that :meth:`open_file` opened, releasing it.

        :raises TimeoutError: If the ``JlsSource`` is still registered.
        """
        self.publish(f'registry/{source_id}/actions/!close', None)
        self._wait_unregistered(source_id, timeout)

    def _wait_unregistered(self, unique_id, timeout):
        deadline = time.monotonic() + timeout
        while unique_id in self.enumerate('registry'):
            if time.monotonic() >= deadline:
                raise TimeoutError(f'{unique_id} still registered after {timeout}s')
            self.wait(0.2)

    # -- rendered-waveform mouse interaction --------------------------------
    # These need a real display (offscreen Qt does not render the GL plot, so
    # the waveform's hit-test geometry never populates).  See
    # is_waveform_rendered() to gate tests.

    def resize_window(self, width, height):
        """Resize the main window (the plot needs room to lay out its rows)."""
        return self.qt_action('resize', path='', width=int(width), height=int(height))

    def resize_window_settled(self, width, height, timeout=10.0):
        """Resize the main window until the size holds.  Returns bool.

        A Wayland compositor may restore an earlier size shortly after startup,
        such as when a startup dialog closes, so resize until it sticks.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.resize_window(width, height)
            self.wait(1.0)
            geo = self.qt_inspect(path='', max_depth=0).get('geometry') or [0, 0, 0, 0]
            if geo[2:] == [int(width), int(height)]:
                return True
        return False

    def plot_geometry(self, waveform_id):
        """Return the ``_PlotOpenGLWidget`` geometry ``[x, y, w, h]`` (or None)."""
        tree = self.qt_inspect(max_depth=60)
        out = [None]

        def walk(n):
            if n.get('objectName') == waveform_id:
                for c in n.get('children', []) or []:
                    if c.get('class') in ('_PlotOpenGLWidget', '_PlotWidget'):
                        out[0] = c.get('geometry')
            for c in n.get('children', []) or []:
                walk(c)
        walk(tree)
        return out[0]

    def plot_path(self, waveform_id):
        """Path to the plot widget for mouse actions."""
        return f'{waveform_id}/_PlotOpenGLWidget:0'

    def right_click(self, waveform_id, x, y):
        """Right-click the plot at local pixel (x, y) to open a context menu.

        Closes any stale menu first so the new menu is detected unambiguously.
        """
        self.qt_action('menu_close')
        self.wait(0.2)
        self.qt_action('click', path=self.plot_path(waveform_id), pos=[int(x), int(y)],
                       button='RightButton')
        self.wait(0.4)

    def menu_items(self):
        """List the open context menu's action texts ('Submenu/Item' form)."""
        return self.qt_action('menu_items').get('items', [])

    def menu_invoke(self, text):
        """Trigger the named action in the open context menu (recurses submenus)."""
        return self.qt_action('menu_invoke', text=text)

    def x_markers_info(self, waveform_id):
        """Return x-markers with pixel positions (see WaveformWidget.x_markers_info)."""
        return self.qt_action('call', path=waveform_id,
                              method='x_markers_info').get('result', [])

    def right_click_marker(self, waveform_id, pixel, y):
        """Right-click a marker at ``pixel`` (trying small offsets for the 5 px
        hit tolerance) and return its open context menu items, or [] if missed."""
        for dx in (0, -2, 2, -4, 4):
            self.right_click(waveform_id, pixel + dx, y)
            items = self.menu_items()
            if 'Remove' in items:
                return items
            self.qt_action('menu_close')
            self.wait(0.15)
        return []

    def plot_render_info(self, waveform_id):
        """Return the plot's on-screen paint state (see WaveformWidget.plot_render_info).

        :return: ``{paint_count, plots}``; ``plots`` keys are plot index strings.
        """
        return self.qt_action('call', path=waveform_id,
                              method='plot_render_info').get('result') or {}

    def is_waveform_rendered(self, waveform_id, midy=None):
        """True if the plot painted on-screen with room for its plot rows.

        Offscreen/headless does not render the GL plot, so it never paints.
        Uses no input events: synthetic clicks cannot open popup menus on
        Wayland.  Defensive: any transient qt error counts as "not yet rendered".

        :param midy: Unused, kept for compatibility.
        """
        try:
            geo = self.plot_geometry(waveform_id)
            if not geo or geo[3] < 100:
                return False
            info = self.plot_render_info(waveform_id)
            return info.get('paint_count', 0) > 0 and bool(info.get('plots'))
        except Exception:
            return False

    def wait_for_paint(self, waveform_id, paint_count, timeout=5.0):
        """Wait for an on-screen paint after ``paint_count``.  Returns bool."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.plot_render_info(waveform_id).get('paint_count', 0) > paint_count:
                return True
            self.wait(0.1)
        return False

    def wait_for_render(self, waveform_id, timeout=15.0):
        """Poll until the plot renders (geometry populated).  Returns bool."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_waveform_rendered(waveform_id):
                return True
            self.wait(1.0)
        return False

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
        ``annotation_path(path)`` (markers).  The exporter runs in a background
        thread and, after it closes the file successfully, adds ``path`` to the
        front of the recent-files list, which is the completion signal.

        :raises ValueError: If ``path`` is already the most recent file, so its
            completion cannot be detected.
        :raises TimeoutError: If the export does not complete.
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
        mru = self.query(_MRU_TOPIC) or []
        if mru and mru[0] == path:
            raise ValueError(f'export to the most recent file: {path}')
        self.publish(f'registry/{waveform_id}/actions/!export', value)
        try:
            self.wait_for(_MRU_TOPIC, lambda v: bool(v) and v[0] == path, timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f'export to {path} did not complete within {timeout}s')
        if annotations:
            # The sidecar is written from the export's start callback.
            deadline = time.monotonic() + 5.0
            while not os.path.exists(self.annotation_path(path)):
                if time.monotonic() >= deadline:
                    break   # no markers in range: no sidecar
                self.wait(0.1)
        return path

    def buffer_signals(self, source_id):
        """Return analysis signal-ids (``source.device.quantity``) for a buffer source."""
        return [f'{source_id}.{s}'
                for s in self.enumerate(f'registry/{source_id}/settings/signals')]

    def source_utc_range(self, source_id):
        """The UTC extent (time64) common to all of a buffer source's signals.

        Reads the source's own ``settings/signals/*/range`` metadata, which is
        valid as soon as the source opens.  The waveform widget's ``x_range``
        setting is NOT a substitute: it only updates when the plot paints,
        which never happens on offscreen/headless stations (it stays [0, 0]).

        :return: ``(t0, t1)`` intersected across signals (signals from one
            recording can differ in length by a few samples).
        :raises ValueError: If the source has no signals.
        """
        t0, t1 = [], []
        for s in self.enumerate(f'registry/{source_id}/settings/signals'):
            r = self.query(f'registry/{source_id}/settings/signals/{s}/range')
            t0.append(r['utc'][0])
            t1.append(r['utc'][1])
        if not t0:
            raise ValueError(f'{source_id} has no signals')
        return max(t0), min(t1)

    def menubar_invoke(self, text):
        """Trigger a main window menu bar action by text path, e.g. ``'File/Exit'``."""
        rsp = self.qt_action('menubar_invoke', text=text)
        if not rsp.get('ok'):
            raise ValueError(f'menubar_invoke {text!r}: {rsp.get("error")}')
        return rsp

    def wait_for_root(self, name, timeout=10.0):
        """Wait until the root (modal or active) window's class or objectName is ``name``.

        :raises TimeoutError: If it does not appear within ``timeout``.
        """
        deadline = time.monotonic() + timeout
        while True:
            root = self.qt_inspect(max_depth=0)
            if name in (root.get('class'), root.get('objectName')):
                return root
            if time.monotonic() >= deadline:
                raise TimeoutError(f'{name} did not appear within {timeout}s')
            self.wait(0.2)

    def wait_exit(self, timeout=15.0):
        """Wait for the UI to exit on its own (e.g. File -> Exit).

        :return: The process exit code.
        :raises TimeoutError: If the UI is still running after ``timeout``.
        """
        try:
            return self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f'UI did not exit within {timeout}s')

    def set_view(self, name):
        """Activate a view (``'multimeter'``, ``'oscilloscope'`` or ``'file'``)."""
        view = f'view:{name}'
        self.publish('registry/view/settings/active', view)
        self.wait_for('registry/view/settings/active', lambda v: v == view, timeout=5.0)

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

    def publish_and_wait(self, topic, value, timeout=10.0, interval=0.05):
        """Publish ``value`` to ``topic`` and wait until the retained value reflects it.

        Publishes arriving over TCP are queued to the UI's pubsub thread and
        applied asynchronously (see ``PubSub.publish``), so an immediate
        :meth:`query` can still observe the prior value.  Poll until the change
        lands so callers get read-after-write semantics.

        :return: The confirmed value.
        :raises TimeoutError: If the value is not observed within ``timeout``.
        """
        self.publish(topic, value)
        return self.wait_for(topic, lambda v: v == value, timeout=timeout, interval=interval)

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
