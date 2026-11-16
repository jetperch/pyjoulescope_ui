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

"""Tools → Event Analyzer (alpha): analyze a JLS file with joulescope_event_analyzer.

The analysis runs in a worker thread and writes an HTML report, CSV and
summary JSON, then opens the report in the browser.
See docs/plans/event_analyzer.md.
"""

from joulescope_ui import N_, pubsub_singleton, register_decorator, get_topic_name
from joulescope_ui.units import str_to_number, unit_prefix
from PySide6 import QtCore, QtWidgets
import logging
import math
import os
import pathlib
import threading


_log = logging.getLogger(__name__)
_TOPIC = 'registry/event_analyzer'
PLOTLY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'plotly', 'plotly.min.js')


# Analyzer options shown in the dialog: (setting, Config section, Config field)
OPTIONS = [
    ('sleep_current', 'sleep', 'level'),
    ('start_threshold', 'detect', 'start_threshold'),
    ('merge_gap', 'detect', 'merge_gap'),
    ('match_tolerance', 'match', 'tolerance'),
    ('battery_capacity_mAh', 'report', 'battery_capacity_mAh'),
]


def _setting(brief, default=None):
    # Remembered dialog state: hidden from Settings and Reset, and kept off the
    # global undo stack so Ctrl+Z after a run undoes the user's last real edit.
    return {'dtype': 'obj', 'brief': brief, 'default': default, 'flags': ['hide', 'skip_undo']}


SETTINGS = {
    'sleep_current': _setting(N_('Sleep current in A, or None for automatic')),
    'start_threshold': _setting(N_('Event start threshold above sleep in A, or None for automatic')),
    'merge_gap': _setting(N_('Join events closer than this, in seconds')),
    'match_tolerance': _setting(N_('Waveform match tolerance; smaller gives more event types')),
    'battery_capacity_mAh': _setting(N_('Battery capacity in mAh for the battery-life estimate')),
    'templates': _setting(N_('Event type templates file')),
}


class Cancelled(Exception):
    """Raised from the progress callback to cancel the analysis."""


def parse_value(text, allow_none=True):
    """Parse a number with an optional SI prefix and unit, such as '4e-6', '4 µA' or '200us'.

    :return: The float value, or None for empty text when allow_none.
    :raise ValueError: on invalid text.
    """
    text = '' if text is None else str(text).strip()
    if not text or text.lower() == 'auto':
        if allow_none:
            return None
        raise ValueError('value required')
    try:
        v = float(text)
    except ValueError:
        v = float(str_to_number(text))   # SI prefix; it does not accept exponents
    if not math.isfinite(v):
        raise ValueError(f'not a finite number: {text}')
    return v


def format_value(value, units=''):
    """Format a value for :func:`parse_value` without losing precision."""
    if value is None:
        return ''
    if not units:
        return f'{value:g}'
    v, prefix, _ = unit_prefix(value)
    return f'{v:g} {prefix}{units}'


def default_jls(mru_files):
    """Return the most recently used JLS file that still exists, or ''."""
    for f in (mru_files or []):
        if isinstance(f, str) and f.lower().endswith('.jls') and os.path.isfile(f):
            return f
    return ''


def default_output_dir(path):
    from joulescope_event_analyzer import default_output_dir
    return default_output_dir(path) if path else ''


def report_exists(path, output_dir):
    """True if output_dir already holds the report for capture path."""
    stem = pathlib.Path(path).stem
    return os.path.isfile(os.path.join(output_dir, f'{stem}_events.html'))


def options_to_config(options):
    """Convert the dialog options dict to a joulescope_event_analyzer Config.

    None (or missing) keeps the analyzer default.
    """
    from joulescope_event_analyzer import Config
    cfg = Config()
    for name, section, field in OPTIONS:
        value = options.get(name)
        if value is not None:
            setattr(getattr(cfg, section), field, float(value))
    if os.path.isfile(PLOTLY_PATH):
        cfg.report.plotly = PLOTLY_PATH    # bundled: reports work offline with no download
    return cfg


def run_analysis(path, output_dir, options, progress=None, cancel_event=None):
    """Run the analysis (blocking).

    :param path: The JLS file.
    :param output_dir: The output directory.
    :param options: The options dict, see :data:`OPTIONS` plus 'templates'.
    :param progress: Optional callable(fraction, message).
    :param cancel_event: Optional threading.Event that cancels when set.
    :return: The dict of output files from analyze_file.
    :raise Cancelled: if cancelled.
    """
    from joulescope_event_analyzer import analyze_file

    def on_progress(fraction, msg):
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()
        if progress is not None:
            progress(fraction, msg)

    templates = options.get('templates') or None
    _, files = analyze_file(path, output_dir, options_to_config(options), templates=templates,
                            progress=on_progress)
    return files


class _Worker(QtCore.QObject):
    """Runs :func:`run_analysis` on a thread and reports through Qt signals."""

    sig_progress = QtCore.Signal(float, str)
    sig_done = QtCore.Signal(object)       # files dict
    sig_failed = QtCore.Signal(str)        # error message, '' when cancelled

    def __init__(self, path, output_dir, options):
        super().__init__()
        self._args = (path, output_dir, options)
        self.cancel_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name='event_analyzer', daemon=True)

    def start(self):
        self._thread.start()

    def join(self, timeout=None):
        self._thread.join(timeout)

    def _run(self):
        try:
            files = run_analysis(*self._args, progress=self.sig_progress.emit, cancel_event=self.cancel_event)
        except Cancelled:
            _log.info('cancelled')
            self.sig_failed.emit('')
        except Exception as ex:
            _log.exception('event analysis failed')
            self.sig_failed.emit(str(ex) or ex.__class__.__name__)
        else:
            self.sig_done.emit(files)


@register_decorator('event_analyzer')
class EventAnalyzerDialog(QtWidgets.QDialog):
    """Configure and run the event analyzer on a JLS file."""

    SETTINGS = SETTINGS

    def __init__(self, parent=None, pubsub=None):
        super().__init__(parent)
        self._pubsub = pubsub_singleton if pubsub is None else pubsub
        self._worker = None
        self.files = None
        self.setObjectName('event_analyzer_dialog')
        self.setWindowTitle(N_('Event Analyzer (alpha)'))
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

        intro = QtWidgets.QLabel(N_(
            'Find the wake-up events in a capture, group them into types and account for '
            'all charge.  The report opens in your web browser.  This feature is an alpha '
            'preview: please share your feedback.'), self)
        intro.setWordWrap(True)
        self._layout.addWidget(intro)

        self._form = QtWidgets.QFormLayout()
        self._layout.addLayout(self._form)
        self._path = self._file_row(N_('JLS file'), 'path', self._on_path_browse)
        self._output = self._file_row(N_('Output directory'), 'output', self._on_output_browse)
        self._path.textChanged.connect(self._on_path_changed)

        self._options = {}
        self._option_row('sleep_current', N_('Sleep current'), 'A', N_('Auto'))
        self._option_row('start_threshold', N_('Start threshold'), 'A', N_('Auto'))
        self._option_row('merge_gap', N_('Merge gap'), 's', '200 µs')
        self._option_row('match_tolerance', N_('Match tolerance'), '', '0.3')
        self._option_row('battery_capacity_mAh', N_('Battery capacity (mAh)'), '', N_('None'))
        self._templates = self._file_row(N_('Templates file'), 'templates', self._on_templates_browse)
        self._templates.setPlaceholderText(N_('None'))

        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setObjectName('progress')
        self._progress.setRange(0, 1000)
        self._progress.setVisible(False)
        self._layout.addWidget(self._progress)
        self._status = QtWidgets.QLabel('', self)
        self._status.setObjectName('status')
        self._status.setWordWrap(True)
        self._layout.addWidget(self._status)

        self._buttons = QtWidgets.QDialogButtonBox(self)
        self._run = self._buttons.addButton(N_('Analyze'), QtWidgets.QDialogButtonBox.AcceptRole)
        self._run.setObjectName('analyze')
        self._cancel = self._buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self._cancel.setObjectName('cancel')
        self._run.clicked.connect(self._on_run)
        self._cancel.clicked.connect(self._on_cancel)
        self._layout.addWidget(self._buttons)

        self._load_settings()
        self.resize(560, 0)

    # --- construction helpers ---

    def _file_row(self, label, name, browse_fn):
        row = QtWidgets.QHBoxLayout()
        edit = QtWidgets.QLineEdit(self)
        edit.setObjectName(name)
        button = QtWidgets.QPushButton(N_('Browse...'), self)
        button.setObjectName(f'{name}_browse')
        button.clicked.connect(browse_fn)
        row.addWidget(edit, 1)
        row.addWidget(button)
        self._form.addRow(label, row)
        return edit

    def _option_row(self, name, label, units, placeholder):
        edit = QtWidgets.QLineEdit(self)
        edit.setObjectName(name)
        edit.setPlaceholderText(placeholder)
        self._options[name] = (edit, units)
        self._form.addRow(label, edit)

    # --- settings ---

    def _topic(self, name):
        return f'{_TOPIC}/settings/{name}'

    def _load_settings(self):
        for name, (edit, units) in self._options.items():
            value = self._pubsub.query(self._topic(name), default=None)
            edit.setText(format_value(value, units))
        self._templates.setText(self._pubsub.query(self._topic('templates'), default=None) or '')
        mru = self._pubsub.query('registry/paths/settings/mru_files', default=[])
        self._path.setText(default_jls(mru))

    def options(self):
        """Return the options dict parsed from the dialog.

        :raise ValueError: with a user message if any value is invalid.
        """
        result = {}
        for name, (edit, _) in self._options.items():
            try:
                value = parse_value(edit.text())
            except ValueError:
                raise ValueError(N_('Invalid value') + f': {edit.text()}')
            if value is not None and value <= 0:
                raise ValueError(N_('Values must be positive') + f': {edit.text()}')
            result[name] = value
        result['templates'] = self._templates.text().strip() or None
        return result

    # --- browse ---

    def _start_dir(self, text):
        if text:
            return os.path.dirname(text) if os.path.isfile(text) else text
        return self._pubsub.query('registry/paths/settings/path', default='') or ''

    @QtCore.Slot()
    def _on_path_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, N_('Select capture'), self._start_dir(self._path.text()), 'Joulescope Data (*.jls)')
        if path:
            self._path.setText(path)

    @QtCore.Slot()
    def _on_output_browse(self):
        start = self._output.text() or self._output.placeholderText()
        path = QtWidgets.QFileDialog.getExistingDirectory(self, N_('Select output directory'),
                                                          self._start_dir(start))
        if path:
            self._output.setText(path)

    @QtCore.Slot()
    def _on_templates_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, N_('Select templates'), self._start_dir(self._templates.text()), 'JSON (*.json)')
        if path:
            self._templates.setText(path)

    @QtCore.Slot(str)
    def _on_path_changed(self, text):
        self._output.setPlaceholderText(default_output_dir(text.strip()))

    # --- run ---

    def output_dir(self):
        return self._output.text().strip() or default_output_dir(self._path.text().strip())

    def _error(self, msg):
        self._status.setText(msg)
        QtWidgets.QMessageBox.warning(self, N_('Event Analyzer'), msg)

    @QtCore.Slot()
    def _on_run(self):
        path = self._path.text().strip()
        if not os.path.isfile(path):
            return self._error(N_('Select an existing JLS file.'))
        try:
            options = self.options()
        except ValueError as ex:
            return self._error(str(ex))
        if options['templates'] and not os.path.isfile(options['templates']):
            return self._error(N_('The templates file does not exist.'))
        output_dir = self.output_dir()
        if report_exists(path, output_dir) and not self.confirm_overwrite(output_dir):
            return
        for name, value in options.items():
            self._pubsub.publish(self._topic(name), value)
        self._set_running(True)
        self._worker = _Worker(path, output_dir, options)
        self._worker.sig_progress.connect(self._on_progress)
        self._worker.sig_done.connect(self._on_done)
        self._worker.sig_failed.connect(self._on_failed)
        _log.info('analyze %s -> %s', path, output_dir)
        self._worker.start()

    def confirm_overwrite(self, output_dir):
        rv = QtWidgets.QMessageBox.question(
            self, N_('Event Analyzer'),
            N_('This directory already contains a report for this capture.  Replace it?') + f'\n\n{output_dir}')
        return rv == QtWidgets.QMessageBox.StandardButton.Yes

    def _set_running(self, running):
        for w in self.findChildren(QtWidgets.QLineEdit) + self.findChildren(QtWidgets.QPushButton):
            if w is not self._cancel:
                w.setEnabled(not running)
        self._progress.setVisible(running)
        self._progress.setValue(0)
        self._status.setText(N_('Analyzing...') if running else '')

    @QtCore.Slot(float, str)
    def _on_progress(self, fraction, msg):
        self._progress.setValue(int(round(max(0.0, min(1.0, fraction)) * 1000)))
        if msg:
            self._status.setText(msg)

    @QtCore.Slot(object)
    def _on_done(self, files):
        self._worker = None
        self.files = files
        self._set_running(False)
        html = files.get('html')
        _log.info('done: %s', files)
        if html:
            self._pubsub.publish('registry/ui/actions/!url_open', pathlib.Path(html).as_uri())
        self.accept()

    @QtCore.Slot(str)
    def _on_failed(self, msg):
        self._worker = None
        self._set_running(False)
        if msg:
            self._error(N_('Event analysis failed') + f': {msg}')
        else:
            self._status.setText(N_('Cancelled'))

    @QtCore.Slot()
    def _on_cancel(self):
        if self._worker is not None:
            self._status.setText(N_('Cancelling...'))
            self._worker.cancel_event.set()
        else:
            self.reject()

    def closeEvent(self, event):
        if self._worker is not None:   # stay open until the worker stops
            self._on_cancel()
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self):
        if self._worker is not None:   # Escape while running cancels instead of closing
            self._on_cancel()
            return
        super().reject()

    @staticmethod
    def on_cls_action_show(pubsub, topic, value):
        parent = pubsub.query('registry/ui/instance', default=None)
        dialog = EventAnalyzerDialog(parent)
        dialog.open()
