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

import logging
import pkgutil
import threading

from PySide6 import QtCore, QtGui, QtWidgets
from pyjoulescope_driver import time64

from joulescope_ui import N_, P_, register, get_topic_name, get_instance
from joulescope_ui.styles import styled_widget
from joulescope_ui.widget_tools import CallableSlotAdapter

from . import _driver_cal as cal
from ._cal_record import parse_record


# Display order — top-down list shown in the slot table.
_SLOT_DISPLAY = [
    (cal.SLOT_ACTIVE,  'ACTIVE'),
    (cal.SLOT_TRIM1,   'TRIM1'),
    (cal.SLOT_TRIM2,   'TRIM2'),
    (cal.SLOT_FIELD,   'FIELD'),
    (cal.SLOT_LAB,     'LAB'),
    (cal.SLOT_FACTORY, 'FACTORY'),
]
_SLOT_NAME = dict(_SLOT_DISPLAY)

_SOURCE_CANDIDATES = [cal.SLOT_FACTORY, cal.SLOT_TRIM1, cal.SLOT_TRIM2,
                      cal.SLOT_FIELD, cal.SLOT_LAB]
_SAVE_TARGETS = [(cal.SLOT_TRIM1, 'TRIM1'), (cal.SLOT_TRIM2, 'TRIM2')]


_CAUTION = N_("""Before performing calibration, ensure that you save any
data in the UI that you wish to keep.""")

_NOTE = P_([
    N_('The Joulescope JS320 is designed to meet its specifications without recalibration.'),
    N_('Offset calibration can further reduce offset error for the present temperature and aging.'),
    N_('Optionally save offset calibrations to TRIM1 or TRIM2 to preserve them.')
])

_OPS_LABEL = N_('Operations')
_SLOTS_LABEL = N_('Calibration slots')
_REFRESH = N_('Refresh')
_START = N_('Start')
_CANCEL = N_('Cancel')
_EXIT = N_('Exit')
_DISMISS = N_('Dismiss')
_COPY_TO_ACTIVE = N_('Copy → ACTIVE')
_SAVE_ACTIVE_TO = N_('Save ACTIVE to:')
_SAVE = N_('Save')
_COPY_FROM = N_('Copy from:')
_CALIBRATION_TITLE = N_('Calibration in progress')
_CALIBRATION_BODY = N_('Please wait...')

_CURRENT_NAME = N_('Current offset')
_CURRENT_TEXT = N_('Disconnect all sensor terminals (open).')
_VOLTAGE_NAME = N_('Voltage offset')
_VOLTAGE_TEXT = P_([
    N_('Short together Voltage+ and Voltage-.'),
    N_('If you are using the BNC front panel, simply connect Voltage to Current.'),
])

_OPERATION = {
    'current_offset': {
        'op': cal.OP_CURRENT_OFFSET,
        'name': _CURRENT_NAME,
        'image': 'current_offset.png',
        'text': _CURRENT_TEXT,
    },
    'voltage_offset': {
        'op': cal.OP_VOLTAGE_OFFSET,
        'name': _VOLTAGE_NAME,
        'image': 'voltage_offset.png',
        'text': _VOLTAGE_TEXT,
    },
}

_ACTIVE_INVALID_TOOLTIP = N_('ACTIVE slot is invalid — copy from a valid source first.')
_NO_VALID_SOURCE_TOOLTIP = N_('No valid source calibration available.')
_ACTIVE_INVALID_FOR_SAVE_TOOLTIP = N_('ACTIVE slot must be valid before saving.')
_DRIVER_BADGE = ' (driver)'


def _create_time_str(t):
    if not t:
        return ''
    try:
        return time64.as_datetime(int(t)).strftime('%Y-%m-%d')
    except Exception:
        return ''


def _resolve_driver(device):
    """Return ``(driver, device_path)`` for the Js320 wrapping ``device``.

    Returns ``(None, None)`` if the device has not been registered yet or
    is a non-JS320 instance.
    """
    inst = get_instance(device, default=None)
    if inst is None:
        return None, None
    driver = getattr(inst, '_wrapper', None)
    if driver is not None:
        driver = getattr(driver, 'driver', None)
    path = getattr(inst, '_path', None)
    if driver is None or path is None:
        return None, None
    return driver, path


class _CalThread(QtCore.QThread):
    """Runs a single cal_js320 operation off the UI thread."""

    progress = QtCore.Signal(int, str)
    done = QtCore.Signal(object)        # bytes for slot_read, None otherwise
    error = QtCore.Signal(str)

    def __init__(self, parent, driver, device_path, op_kind, *,
                 src_slot=0, dst_slot=0, samples_per_point=0):
        super().__init__(parent=parent)
        self._log = logging.getLogger(__name__ + '.thread')
        self._driver = driver
        self._device_path = device_path
        self._op_kind = op_kind
        self._src_slot = src_slot
        self._dst_slot = dst_slot
        self._samples = samples_per_point
        self._abort = threading.Event()

    def abort(self):
        self._abort.set()

    def _progress(self, pct, msg):
        self.progress.emit(int(round(pct * 100)), msg)

    def run(self):
        try:
            data = None
            if self._op_kind == 'slot_read':
                data = cal.slot_read(self._driver, self._device_path,
                                     self._src_slot, progress=self._progress,
                                     abort_event=self._abort, timeout=15.0)
            elif self._op_kind == 'slot_copy':
                cal.slot_copy(self._driver, self._device_path,
                              self._src_slot, self._dst_slot,
                              progress=self._progress, abort_event=self._abort,
                              timeout=15.0)
            elif self._op_kind == 'current_offset':
                cal.current_offset_cal(self._driver, self._device_path,
                                       samples_per_point=self._samples,
                                       progress=self._progress,
                                       abort_event=self._abort)
            elif self._op_kind == 'voltage_offset':
                cal.voltage_offset_cal(self._driver, self._device_path,
                                       samples_per_point=self._samples,
                                       progress=self._progress,
                                       abort_event=self._abort)
            else:
                raise RuntimeError(f'unknown op kind: {self._op_kind}')
            self.done.emit(data)
        except Exception as ex:
            self._log.warning('cal op %s failed: %s', self._op_kind, ex)
            self.error.emit(str(ex))


class _ContentsWidget(QtWidgets.QWidget):

    def __init__(self, parent, device):
        super().__init__(parent=parent)
        self._parent = parent
        self._device = device
        self._slot_rows = {}        # slot_id -> dict of QLabel
        self._slot_records = {}     # slot_id -> parsed record dict or None
        self.setObjectName('js320_calibration_contents_widget')
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)

        caution = QtWidgets.QLabel('<p>⚠ ' + _CAUTION + '</p>')
        caution.setWordWrap(True)
        layout.addWidget(caution)

        note = QtWidgets.QLabel('<p>' + _NOTE + '</p>')
        note.setWordWrap(True)
        layout.addWidget(note)

        slots_group = QtWidgets.QGroupBox(_SLOTS_LABEL, self)
        slot_grid = QtWidgets.QGridLayout(slots_group)
        slot_grid.addWidget(QtWidgets.QLabel('<b>' + N_('Slot') + '</b>'), 0, 0)
        slot_grid.addWidget(QtWidgets.QLabel('<b>' + N_('Valid') + '</b>'), 0, 1)
        slot_grid.addWidget(QtWidgets.QLabel('<b>' + N_('Source info') + '</b>'), 0, 2)
        slot_grid.addWidget(QtWidgets.QLabel('<b>' + N_('Date') + '</b>'), 0, 3)
        for row, (slot_id, name) in enumerate(_SLOT_DISPLAY, start=1):
            slot_grid.addWidget(QtWidgets.QLabel(name), row, 0)
            valid_label = QtWidgets.QLabel('…')
            info_label = QtWidgets.QLabel('')
            time_label = QtWidgets.QLabel('')
            slot_grid.addWidget(valid_label, row, 1)
            slot_grid.addWidget(info_label, row, 2)
            slot_grid.addWidget(time_label, row, 3)
            self._slot_rows[slot_id] = {
                'valid': valid_label,
                'info': info_label,
                'time': time_label,
            }
        self._refresh_button = QtWidgets.QPushButton(_REFRESH)
        self._refresh_button.pressed.connect(self._on_refresh_pressed)
        slot_grid.addWidget(self._refresh_button, slot_grid.rowCount(), 3)
        slot_grid.setColumnStretch(2, 1)
        layout.addWidget(slots_group)

        actions_group = QtWidgets.QGroupBox(_OPS_LABEL, self)
        actions_grid = QtWidgets.QGridLayout(actions_group)
        actions_grid.setColumnStretch(1, 1)

        # Rows 0..1: offset operations (no selector — column 1 left empty).
        self._op_buttons = {}
        for row, (key, info) in enumerate(_OPERATION.items()):
            actions_grid.addWidget(QtWidgets.QLabel(info['name']), row, 0)
            btn = QtWidgets.QPushButton(_START)
            btn.setEnabled(False)
            actions_grid.addWidget(btn, row, 2)
            adapter = CallableSlotAdapter(btn, lambda k=key: self._parent.start(k))
            btn.pressed.connect(adapter.slot)
            self._op_buttons[key] = btn

        # Row 2: copy a source slot into ACTIVE.
        copy_row = len(_OPERATION)
        actions_grid.addWidget(QtWidgets.QLabel(_COPY_FROM), copy_row, 0)
        self._copy_combo = QtWidgets.QComboBox(actions_group)
        actions_grid.addWidget(self._copy_combo, copy_row, 1)
        self._copy_button = QtWidgets.QPushButton(_COPY_TO_ACTIVE)
        self._copy_button.setEnabled(False)
        self._copy_button.pressed.connect(self._on_copy_pressed)
        actions_grid.addWidget(self._copy_button, copy_row, 2)

        # Row 3: save ACTIVE into a TRIM slot.
        save_row = copy_row + 1
        actions_grid.addWidget(QtWidgets.QLabel(_SAVE_ACTIVE_TO), save_row, 0)
        self._save_combo = QtWidgets.QComboBox(actions_group)
        for slot_id, name in _SAVE_TARGETS:
            self._save_combo.addItem(name, slot_id)
        actions_grid.addWidget(self._save_combo, save_row, 1)
        self._save_button = QtWidgets.QPushButton(_SAVE)
        self._save_button.setEnabled(False)
        self._save_button.pressed.connect(self._on_save_pressed)
        actions_grid.addWidget(self._save_button, save_row, 2)

        layout.addWidget(actions_group)

        layout.addItem(QtWidgets.QSpacerItem(0, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding))

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        exit_button = QtWidgets.QPushButton(_EXIT)
        exit_button.pressed.connect(self._parent.exit)
        button_row.addWidget(exit_button)
        layout.addLayout(button_row)

        self._update_actions_enabled()

    def _on_refresh_pressed(self):
        self._parent.refresh_slots()

    def _on_copy_pressed(self):
        slot_id = self._copy_combo.currentData()
        if slot_id is None:
            return
        self._parent.copy_from(int(slot_id))

    def _on_save_pressed(self):
        slot_id = self._save_combo.currentData()
        if slot_id is None:
            return
        self._parent.save_to(int(slot_id))

    def _update_actions_enabled(self):
        active_valid = self._slot_records.get(cal.SLOT_ACTIVE) is not None
        for btn in self._op_buttons.values():
            btn.setEnabled(active_valid)
            btn.setToolTip('' if active_valid else _ACTIVE_INVALID_TOOLTIP)
        has_source = self._copy_combo.count() > 0
        self._copy_button.setEnabled(has_source)
        self._copy_button.setToolTip('' if has_source else _NO_VALID_SOURCE_TOOLTIP)
        self._save_button.setEnabled(active_valid and self._save_combo.count() > 0)
        self._save_button.setToolTip('' if active_valid else _ACTIVE_INVALID_FOR_SAVE_TOOLTIP)

    def slot_pending(self, slot_id):
        row = self._slot_rows.get(slot_id)
        if row is None:
            return
        row['valid'].setText('…')
        row['info'].setText('')
        row['time'].setText('')

    def slot_clear_all(self):
        self._slot_records.clear()
        self._copy_combo.clear()
        for slot_id in self._slot_rows:
            self.slot_pending(slot_id)
        self._update_actions_enabled()

    def slot_update(self, slot_id, record):
        row = self._slot_rows.get(slot_id)
        if row is None:
            return
        self._slot_records[slot_id] = record
        if record is None:
            row['valid'].setText('—')
            row['info'].setText('')
            row['time'].setText('')
        else:
            badge = _DRIVER_BADGE if record.get('is_driver_generated') else ''
            row['valid'].setText('✓')
            row['info'].setText(record.get('source_info', '') + badge)
            row['time'].setText(_create_time_str(record.get('create_time', 0)))

    def slot_scan_complete(self):
        previous = self._copy_combo.currentData()
        self._copy_combo.blockSignals(True)
        self._copy_combo.clear()
        for slot_id in _SOURCE_CANDIDATES:
            if self._slot_records.get(slot_id) is not None:
                self._copy_combo.addItem(_SLOT_NAME[slot_id], slot_id)
        idx = self._copy_combo.findData(previous) if previous is not None else -1
        if idx >= 0:
            self._copy_combo.setCurrentIndex(idx)
        self._copy_combo.blockSignals(False)
        self._update_actions_enabled()


class _SetupWidget(QtWidgets.QWidget):

    def __init__(self, parent, device, op_name):
        super().__init__(parent=parent)
        self._parent = parent
        self._op_name = op_name
        op = _OPERATION[op_name]
        self.setObjectName('js320_calibration_setup_widget')
        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel('<p><b>' + op['name'] + '</b></p>')
        layout.addWidget(title)

        image = QtWidgets.QLabel()
        try:
            image_data = pkgutil.get_data('joulescope_ui.widgets.js320_cal', op['image'])
            pix = QtGui.QPixmap()
            pix.loadFromData(image_data, format='PNG')
            image.setPixmap(pix)
        except Exception:
            pass
        layout.addWidget(image)

        text = QtWidgets.QLabel('<p>' + op['text'] + '</p>')
        text.setWordWrap(True)
        layout.addWidget(text)

        layout.addItem(QtWidgets.QSpacerItem(0, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding))

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        cancel = QtWidgets.QPushButton(_CANCEL)
        cancel.pressed.connect(self._parent.cancel)
        button_row.addWidget(cancel)
        start = QtWidgets.QPushButton(_START)
        start.pressed.connect(self._on_start_pressed)
        button_row.addWidget(start)
        layout.addLayout(button_row)

    @QtCore.Slot()
    def _on_start_pressed(self):
        self._parent.calibrate(self._op_name)


class _WaitWidget(QtWidgets.QWidget):

    dismissed = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setObjectName('js320_calibration_wait_widget')
        layout = QtWidgets.QVBoxLayout(self)

        self._title = QtWidgets.QLabel('<p><b>' + _CALIBRATION_TITLE + '</b></p>')
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._body = QtWidgets.QLabel('<p>' + _CALIBRATION_BODY + '</p>')
        self._body.setWordWrap(True)
        layout.addWidget(self._body)

        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._progress = QtWidgets.QLabel()
        self._progress.setWordWrap(True)
        layout.addWidget(self._progress)

        layout.addItem(QtWidgets.QSpacerItem(0, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding))

        self._button_row = QtWidgets.QHBoxLayout()
        self._button_row.addStretch(1)
        self._dismiss_button = QtWidgets.QPushButton(_DISMISS)
        self._dismiss_button.setVisible(False)
        self._dismiss_button.pressed.connect(self.dismissed)
        self._button_row.addWidget(self._dismiss_button)
        layout.addLayout(self._button_row)

    def set_progress(self, pct, msg):
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(max(0, min(100, int(pct))))
        if msg:
            self._progress.setText(msg)

    def set_error(self, msg):
        self._title.setText('<p><b>' + N_('Calibration failed') + '</b></p>')
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress.setText('<p style="color:red">' + str(msg) + '</p>')
        self._dismiss_button.setVisible(True)


@register
@styled_widget(N_('JS320 Calibration'))
class JS320CalibrationWidget(QtWidgets.QWidget):
    CAPABILITIES = []
    SETTINGS = {
        'device': {
            'dtype': 'str',
            'brief': N_('The target device.'),
            'default': None,
            'flags': ['hide', 'ro'],
        },
    }

    def __init__(self, parent=None, device=None):
        self._log = logging.getLogger(__name__)
        self._device = device
        self._body = None
        self._contents = None
        self._thread = None
        self._slot_scan_queue = []
        self._driver = None
        self._device_path = None
        self._closing = False
        super().__init__(parent=parent)
        self.setObjectName('js320_calibration_widget')
        self._layout = QtWidgets.QVBoxLayout(self)

        self._title_label = QtWidgets.QLabel()
        self._layout.addWidget(self._title_label)

        self._show_contents()

    def on_pubsub_register(self):
        if self._device is not None:
            self.device = self._device
        self._title_label.setText('<p><b>' + str(self.device) + ' ' + N_('Calibration') + '</b></p>')
        self._driver, self._device_path = _resolve_driver(self._device)
        if self._driver is None:
            self._show_fatal(N_('Device is not available.'))
            return
        # settings/state is an int per Js320.SETTINGS:
        #   0=closed, 1=opening, 2=open, 3=closing
        state = self.pubsub.query(f'{get_topic_name(self._device)}/settings/state', default=0)
        if state != 2:
            self._show_fatal(N_('The device must be open to calibrate.  '
                                'Open the device, then reopen this window.'))
            return
        self.refresh_slots()

    def _show_fatal(self, msg):
        wait = _WaitWidget(self)
        self._set_body(wait)
        wait.set_error(msg)
        wait.dismissed.connect(self.exit)

    def _clear_body(self):
        body, self._body = self._body, None
        if body is None:
            return
        if body is self._contents:
            self._contents = None
        self._layout.removeWidget(body)
        body.hide()
        body.deleteLater()

    def _set_body(self, body):
        self._clear_body()
        self._body = body
        body.show()
        self._layout.addWidget(body)

    def _show_contents(self):
        self._contents = _ContentsWidget(self, self._device)
        self._set_body(self._contents)

    def refresh_slots(self):
        if self._closing or self._thread is not None:
            return
        if self._contents is None or self._driver is None:
            return
        self._contents.slot_clear_all()
        self._slot_scan_queue = [slot_id for slot_id, _ in _SLOT_DISPLAY]
        self._scan_next()

    def _scan_next(self):
        if self._closing:
            self._dispose_thread()
            return
        if not self._slot_scan_queue:
            if self._contents is not None:
                self._contents.slot_scan_complete()
            self._dispose_thread()
            return
        slot_id = self._slot_scan_queue.pop(0)
        if self._contents is not None:
            self._contents.slot_pending(slot_id)
        thread = self._new_thread('slot_read', src_slot=slot_id)
        thread.done.connect(lambda data, s=slot_id: self._on_scan_done(s, data))
        thread.error.connect(lambda msg, s=slot_id: self._on_scan_error(s, msg))
        thread.start()

    def _on_scan_done(self, slot_id, data):
        if self._closing:
            return
        record = parse_record(data) if data else None
        if self._contents is not None:
            self._contents.slot_update(slot_id, record)
        self._dispose_thread()
        self._scan_next()

    def _on_scan_error(self, slot_id, msg):
        if self._closing:
            return
        self._log.warning('slot_read(%s) failed: %s', slot_id, msg)
        if self._contents is not None:
            self._contents.slot_update(slot_id, None)
        self._dispose_thread()
        self._scan_next()

    def _new_thread(self, op_kind, **kwargs):
        thread = _CalThread(self, self._driver, self._device_path, op_kind, **kwargs)
        self._thread = thread
        return thread

    def _dispose_thread(self):
        thread, self._thread = self._thread, None
        if thread is not None:
            if thread.isRunning():
                thread.wait(2000)
            thread.deleteLater()

    # --- _ContentsWidget hooks --------------------------------------------

    def start(self, op_name):
        if op_name not in _OPERATION:
            return
        self._set_body(_SetupWidget(self, self._device, op_name))

    def _run_op(self, op_kind, **kwargs):
        wait = _WaitWidget(self)
        wait.dismissed.connect(self._show_contents_and_refresh)
        self._set_body(wait)
        thread = self._new_thread(op_kind, **kwargs)
        thread.progress.connect(wait.set_progress)
        thread.done.connect(lambda _data: self._on_op_done())
        thread.error.connect(wait.set_error)
        thread.error.connect(lambda _msg: self._dispose_thread())
        thread.start()

    def _on_op_done(self):
        if self._closing:
            return
        self._dispose_thread()
        self._show_contents_and_refresh()

    def calibrate(self, op_name):
        op_info = _OPERATION[op_name]
        if op_info['op'] == cal.OP_CURRENT_OFFSET:
            self._run_op('current_offset')
        elif op_info['op'] == cal.OP_VOLTAGE_OFFSET:
            self._run_op('voltage_offset')

    def copy_from(self, src_slot):
        self._run_op('slot_copy', src_slot=src_slot, dst_slot=cal.SLOT_ACTIVE)

    def save_to(self, dst_slot):
        self._run_op('slot_copy', src_slot=cal.SLOT_ACTIVE, dst_slot=dst_slot)

    def _show_contents_and_refresh(self):
        self._show_contents()
        self.refresh_slots()

    def cancel(self):
        self._show_contents()

    def exit(self):
        self.pubsub.publish('registry/view/actions/!widget_close', self)

    def closeEvent(self, event):
        self._closing = True
        self._slot_scan_queue = []
        thread, self._thread = self._thread, None
        if thread is not None:
            # Drop queued signal deliveries so nothing fires on this widget
            # after closeEvent returns and the Qt event loop drains.
            for sig in (thread.progress, thread.done, thread.error):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
            thread.abort()
            thread.wait(3000)
            thread.deleteLater()
        return super().closeEvent(event)
