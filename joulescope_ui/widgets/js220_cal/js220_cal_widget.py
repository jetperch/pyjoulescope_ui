# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtWidgets, QtGui, QtCore
import pkgutil
from joulescope_ui import N_, register, get_topic_name
from joulescope_ui.styles import styled_widget
from joulescope_ui.widget_tools import CallableSlotAdapter
from pyjoulescope_driver import calibration_hash
import time
import logging
import numpy as np


_CAUTION = """\
⚠ Before performing calibration, ensure that you save any 
data in the UI that you wish to keep."""

_CALIBRATION_NOTE = """\
The Joulescope JS220 is designed to meet its specifications
without recalibration.  You can use offset calibration to
further reduce the offset error.  If you wish to perform
scale calibration, ensure that your test setup gives a 
sufficient test uncertainty ratio (TUR)."""

_FACTORY = N_('Restore factory calibration')
_START = N_('Start')
_CANCEL = N_('Cancel')
_EXIT = N_('Exit')
_CALIBRATION_TITLE = N_('Calibration in progress')
_CALIBRATION_BODY = N_('Please wait...')

_CURRENT_CAL_TEXT = N_('Disconnect all sensor terminals')
_VOLTAGE_CAL_TEXT = N_("""\
Short together Voltage+, Voltage-, and Current+ using wires.

If you are using the BNC front panel, simply connect Voltage to Current.\
""")


_OPERATION = {
    'current_offset': {
        'name': N_('Current offset'),
        'image': 'current_offset.png',
        'text': _CURRENT_CAL_TEXT,
    },
    # 'current_scale': {
    #     'name': N_('Current scale'),
    #     'text': _CURRENT_CAL_TEXT,
    # },
    'voltage_offset': {
        'name': N_('Voltage offset'),
        'text': _VOLTAGE_CAL_TEXT,
    },
    # 'voltage_scale': {
    #     'name': N_('Voltage scale'),
    #     'text': _VOLTAGE_CAL_TEXT,
    # },
}

_CURRENT_RANGES = ['10 A', '180 mA', '18 mA', '1.8 mA', '180 µA', '18 µA']
_VOLTAGE_RANGES = ['15 V', '2 V']
_CALIBRATIONS = ['cal_t', 'cal_a', 'cal_f']
_CALIBRATION_HEADER = np.frombuffer(b"joulescope_calibration\x0D\x0A \x0A \x1A  \xB2\x1C", dtype=np.uint8)
_DURATION_SAMPLES = 2 * 2_000_000


def _is_cal_valid(cal):
    cal_u8 = cal.view(np.uint8)
    if not np.array_equal(cal_u8[:32], _CALIBRATION_HEADER):
        return False
    hash_cal_u32 = cal_u8[1920:1984].view(np.uint32)
    hash_calc_u32 = calibration_hash(cal_u8[:1920])
    return np.array_equal(hash_cal_u32, hash_calc_u32)


def _cal_hash_update(cal):
    u8 = cal.view(np.uint8)
    hash_calc_u32 = calibration_hash(u8[:1920])
    u8[1920:1984] = hash_calc_u32.view(np.uint8)
    u8[1984:2048] = 0


def _cal_offset(k):
    return int(round(k * (2 ** 20), 0))


class _CalibrationThread(QtCore.QThread):
    progress = QtCore.Signal(str)
    warning = QtCore.Signal(str)

    def __init__(self, parent, device, op_name, pubsub):
        self._log = logging.getLogger(__name__ + '.calibration')
        self._device = device
        self._topic = get_topic_name(self._device)
        self._op_name = op_name
        self.pubsub = pubsub
        self._device_state = {}
        self._cal_read_data = []
        self._adc_data = {0: [], 1: [], 2: [], 3: []}
        self._adc_data_incoming = {0: [], 1: [], 2: [], 3: []}
        self._on_adc_data_fn = self._on_adc_data
        self._on_calibration_read_data_fn = self._on_calibration_read_data
        super().__init__(parent=parent)

    def _on_calibration_read_data(self, topic, value):
        cal = topic.split('/')[-2]
        self._cal_read_data.append((cal, value))

    def _adc_data_clear(self):
        for value in self._adc_data.values():
            value.clear()
        for value in self._adc_data_incoming.values():
            value.clear()

    def _adc_data_wait(self, signals, count):
        for adc in self._adc_data_incoming.keys():
            value, self._adc_data_incoming[adc] = self._adc_data_incoming[adc], []
            self._adc_data[adc].extend(value)
        for signal in signals:
            signal_len = sum([len(x) for x in self._adc_data[signal]])
            if signal_len < count:
                return False
        return True

    def _on_adc_data(self, topic, value):
        adc = int(topic.split('/')[-2])
        self._adc_data_incoming[adc].append(value['data'].copy())

    def _adc_mean(self, signal):
        return np.mean(np.concatenate(self._adc_data[signal]))

    def _direct_subscribe(self, topic, flags, fn):
        self.pubsub.publish(f'{self._topic}/actions/!direct', {
            'action': 'subscribe',
            'topic': topic,
            'flags': flags,
            'fn': fn,
        })

    def _direct_unsubscribe(self, topic, fn):
        self.pubsub.publish(f'{self._topic}/actions/!direct', {
            'action': 'unsubscribe',
            'topic': topic,
            'fn': fn,
        })

    def _direct_publish(self, topic, value):
        self.pubsub.publish(f'{self._topic}/actions/!direct', {
            'action': 'publish',
            'topic': topic,
            'value': value,
        })

    def _state_save(self):
        signals = self.pubsub.enumerate(f'{self._topic}/settings/signals')
        enables = [f'signals/{signal}/enable' for signal in signals]
        settings = enables + [
            'current_range',
            'voltage_range',
        ]
        for setting in settings:
            topic = f'{self._topic}/settings/{setting}'
            self._device_state[topic] = self.pubsub.query(topic)
        for enable in enables:
            self.pubsub.publish(f'{self._topic}/settings/{enable}', False)
        for adc in self._adc_data.keys():
            self._direct_subscribe(f's/adc/{adc}/!data', ['pub'], self._on_adc_data_fn)
        for cal in _CALIBRATIONS:
            self._direct_subscribe(f'h/mem/s/{cal}/!rdata', ['pub'], self._on_calibration_read_data_fn)
        self._direct_publish(f's/stats/ctrl', 'off')

    def _state_restore(self):
        for adc in self._adc_data.keys():
            self._direct_unsubscribe(f's/adc/{adc}/!data', self._on_adc_data_fn)
        for topic, value in self._device_state.items():
            self.pubsub.publish(topic, value)
        for cal in _CALIBRATIONS:
            self._direct_unsubscribe(f'h/mem/s/{cal}/!rdata', self._on_calibration_read_data_fn)
        time.sleep(0.1)
        self._direct_publish('h/!reset', 'app')

    def _cal_read(self, cal):
        self._cal_read_data.clear()
        self._direct_publish(f'h/mem/s/{cal}/!read', 2048)
        t_start = time.time()
        while not len(self._cal_read_data):
            if (time.time() - t_start) > 1.0:
                raise RuntimeError('Timed out reading calibration')
            time.sleep(0.01)
        cal = self._cal_read_data[0][1]
        if isinstance(cal, bytes):
            cal = np.frombuffer(cal, dtype=np.uint8).copy()
        if _is_cal_valid(cal):
            return cal
        else:
            return None

    def _progress(self, msg):
        self._log.info(msg)
        self.progress.emit(msg)

    def _warning(self, msg):
        self._log.warning('Could not get factory calibration')
        self.warning.emit(msg)

    def _cal_read_best(self):
        cal = self._cal_read('cal_a')
        if cal is None:
            cal = self._cal_read('cal_f')
            if cal is None:
                self._warning('Could not get factory calibration')
                return None
        cal_i64 = cal.view(np.int64)
        return cal_i64

    def _cal_update(self, cal_i64, cal_update):
        for idx, v in cal_update.items():
            cal_i64[idx] = v
        _cal_hash_update(cal_i64)

    def _cal_save(self, cal):
        self._direct_publish('h/mem/s/cal_t/!erase', 0)
        self._direct_publish('h/mem/s/cal_a/!erase', 0)
        self._direct_publish(f'h/mem/s/cal_a/!write', cal.tobytes())

    def _cal_read_update_save(self, cal_update):
        cal = self._cal_read_best()
        if cal is None:
            return
        self._cal_update(cal, cal_update)
        self._cal_save(cal)

    def _run_current_offset(self):
        cal_update = {}
        current_range_topic = f'{self._topic}/settings/current_range'

        self._progress('Current range 10 A for adc0')
        self._adc_data_clear()
        self.pubsub.publish(current_range_topic, '10 A')
        self._direct_publish(f's/adc/0/ctrl', 'on')
        while not self._adc_data_wait([0], _DURATION_SAMPLES):
            time.sleep(0.01)
        self._direct_publish(f's/adc/0/ctrl', 'off')
        cal_update[4] = _cal_offset(self._adc_mean(0))

        for idx, current_range in enumerate(_CURRENT_RANGES):
            self._progress(f'Current range {current_range} for adc1 & adc2')
            self._adc_data_clear()
            self.pubsub.publish(current_range_topic, current_range)
            time.sleep(0.1)
            self._direct_publish(f's/adc/1/ctrl', 'on')
            self._direct_publish(f's/adc/2/ctrl', 'on')
            while not self._adc_data_wait([1, 2], _DURATION_SAMPLES):
                time.sleep(0.01)
            self._direct_publish(f's/adc/1/ctrl', 'off')
            self._direct_publish(f's/adc/2/ctrl', 'off')
            cal_update[5 + idx] = _cal_offset(self._adc_mean(1))
            cal_update[12 + idx] = _cal_offset(self._adc_mean(2))
            time.sleep(0.1)
        return self._cal_read_update_save(cal_update)

    def _run_voltage_offset(self):
        cal_update = {}
        current_range_topic = f'{self._topic}/settings/current_range'
        self.pubsub.publish(current_range_topic, _CURRENT_RANGES[-1])
        voltage_range_topic = f'{self._topic}/settings/voltage_range'
        for idx, voltage_range in enumerate(_VOLTAGE_RANGES):
            self._progress(f'Voltage range {voltage_range}')
            self._adc_data_clear()
            self.pubsub.publish(voltage_range_topic, voltage_range)
            time.sleep(0.1)
            self._direct_publish(f's/adc/3/ctrl', 'on')
            while not self._adc_data_wait([3], _DURATION_SAMPLES):
                time.sleep(0.01)
            self._direct_publish(f's/adc/3/ctrl', 'off')
            cal_update[19 + idx] = _cal_offset(self._adc_mean(3))
            time.sleep(0.1)
        return self._cal_read_update_save(cal_update)

    def _run_factory_restore(self):
        self._direct_publish('h/mem/s/cal_t/!erase', 0)
        self._direct_publish('h/mem/s/cal_a/!erase', 0)
        cal = self._cal_read('cal_f')
        self._direct_publish(f'h/mem/s/cal_a/!write', cal.tobytes())

    def run(self):
        self._log.info('%s %s start', self._device, self._op_name)
        self._state_save()
        try:
            if self._op_name == 'current_offset':
                self._run_current_offset()
            elif self._op_name == 'voltage_offset':
                self._run_voltage_offset()
            elif self._op_name == 'factory_restore':
                self._run_factory_restore()
            else:
                self._log.warning('Unsupported operation: %s', self._op_name)
        finally:
            self._state_restore()
            self._log.info('%s %s done', self._device, self._op_name)


class _ContentsWidget(QtWidgets.QWidget):

    def __init__(self, parent, device):
        self._log = logging.getLogger(__name__)
        self._device = device
        self._widgets = []
        super().__init__(parent=parent)
        self.setObjectName('js220_calibration_contents_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 6, 0, 6)

        self._caution_label = QtWidgets.QLabel('<p>' + _CAUTION + '</p>')
        self._caution_label.setWordWrap(True)
        self._layout.addWidget(self._caution_label)

        self._note_label = QtWidgets.QLabel('<p>' + _CALIBRATION_NOTE + '</p>')
        self._note_label.setWordWrap(True)
        self._layout.addWidget(self._note_label)

        self._op_widget = QtWidgets.QWidget(self)
        self._op_layout = QtWidgets.QGridLayout(self._op_widget)
        self._layout.addWidget(self._op_widget)

        for name in _OPERATION.keys():
            self._add_operation(name)

        self._factory_button = QtWidgets.QPushButton(_FACTORY)
        self._layout.addWidget(self._factory_button)
        self._factory_button.pressed.connect(self._on_factory_button_pressed)

        self._spacer = QtWidgets.QSpacerItem(0, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._button_widget = QtWidgets.QWidget(self)
        self._button_layout = QtWidgets.QHBoxLayout(self._button_widget)
        self._button_spacer = QtWidgets.QSpacerItem(0, 0,
                                                    QtWidgets.QSizePolicy.Expanding,
                                                    QtWidgets.QSizePolicy.Minimum)
        self._button_layout.addItem(self._button_spacer)
        self._exit_button = QtWidgets.QPushButton(_EXIT)
        self._button_layout.addWidget(self._exit_button)
        self._exit_button.pressed.connect(parent.exit)
        self._layout.addWidget(self._button_widget)

    def _on_factory_button_pressed(self):
        self.parent().calibrate('factory_restore')

    def _add_operation(self, op_name):
        row = self._op_layout.rowCount()
        op = _OPERATION[op_name]
        name_widget = QtWidgets.QLabel(op['name'])
        button_widget = QtWidgets.QPushButton(_START)
        self._op_layout.addWidget(name_widget, row, 0, 1, 1)
        self._op_layout.addWidget(button_widget, row, 1, 1, 1)
        adapter = CallableSlotAdapter(button_widget, lambda: self.parent().start(op_name))
        button_widget.pressed.connect(adapter.slot)
        self._widgets.append((name_widget, button_widget))


class _SetupWidget(QtWidgets.QWidget):

    def __init__(self, parent, device, op_name):
        self._log = logging.getLogger(__name__)
        self._device = device
        self._op_name = op_name
        super().__init__(parent=parent)
        self.setObjectName('js220_calibration_setup_widget')
        self._layout = QtWidgets.QVBoxLayout(self)
        op = _OPERATION[op_name]

        self._title = QtWidgets.QLabel(op['name'])
        self._layout.addWidget(self._title)

        self._image = QtWidgets.QLabel()
        image_data = pkgutil.get_data('joulescope_ui.widgets.js220_cal', op_name + '.png')
        self._image_bin = QtGui.QPixmap()
        self._image_bin.loadFromData(image_data, format='PNG')
        self._image.setPixmap(self._image_bin)
        self._layout.addWidget(self._image)

        self._text = QtWidgets.QLabel('<p>' + op['text'] + '</p>')
        self._text.setWordWrap(True)
        self._layout.addWidget(self._text)

        self._spacer = QtWidgets.QSpacerItem(0, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._button_widget = QtWidgets.QWidget(self)
        self._button_layout = QtWidgets.QHBoxLayout(self._button_widget)
        self._button_spacer = QtWidgets.QSpacerItem(0, 0,
                                                    QtWidgets.QSizePolicy.Expanding,
                                                    QtWidgets.QSizePolicy.Minimum)
        self._button_layout.addItem(self._button_spacer)
        self._cancel_button = QtWidgets.QPushButton(_CANCEL)
        self._button_layout.addWidget(self._cancel_button)
        self._start_button = QtWidgets.QPushButton(_START)
        self._button_layout.addWidget(self._start_button)
        self._layout.addWidget(self._button_widget)

        self._cancel_button.pressed.connect(parent.cancel)
        self._start_button.pressed.connect(self._on_start_button_pressed)

    @QtCore.Slot()
    def _on_start_button_pressed(self):
        self.parent().calibrate(self._op_name)


class _WaitWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setObjectName('js220_calibration_wait_widget')
        self._layout = QtWidgets.QVBoxLayout(self)

        self._title = QtWidgets.QLabel('<p>' + _CALIBRATION_TITLE + '</p>')
        self._title.setWordWrap(True)
        self._layout.addWidget(self._title)

        self._text = QtWidgets.QLabel('<p>' + _CALIBRATION_BODY + '</p>')
        self._text.setWordWrap(True)
        self._layout.addWidget(self._text)

        self._progress = QtWidgets.QLabel()
        self._progress.setWordWrap(True)
        self._layout.addWidget(self._progress)

        self._spacer = QtWidgets.QSpacerItem(0, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

    def progress(self, msg):
        self._progress.setText(msg)

    def warning(self, msg):
        self._progress.setText('WARNING: ' + msg)


@register
@styled_widget(N_('JS220 Calibration'))
class JS220CalibrationWidget(QtWidgets.QWidget):
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
        self._thread = None
        super().__init__(parent=parent)
        self.setObjectName('js220_calibration_widget')
        self._layout = QtWidgets.QVBoxLayout(self)

        self._title_label = QtWidgets.QLabel()
        self._layout.addWidget(self._title_label)
        self._body_set(_ContentsWidget(self, self._device))

    def on_pubsub_register(self):
        if self._device is not None:
            self.device = self._device
        self._title_label.setText('<p><b>' + self.device + ' ' + N_('Calibration') + '</b></p>')

    def _clear(self):
        body, self._body = self._body, None
        if body is not None:
            self._layout.removeWidget(body)
            body.hide()
            body.deleteLater()

    def _body_set(self, body):
        self._clear()
        self._body = body
        self._body.show()
        self._layout.addWidget(self._body)

    def start(self, op_name):
        self._body_set(_SetupWidget(self, self._device, op_name))

    def calibrate(self, op_name):
        widget = _WaitWidget(self)
        self._body_set(widget)
        self._thread = _CalibrationThread(self, self._device, op_name, self.pubsub)
        self._thread.progress.connect(widget.progress)
        self._thread.warning.connect(widget.warning)
        self._thread.finished.connect(self.thread_finished)
        self._thread.start()

    def thread_finished(self):
        thread, self._thread = self._thread, None
        if thread is None:
            return
        thread.deleteLater()
        self._body_set(_ContentsWidget(self, self._device))

    def cancel(self):
        self._body_set(_ContentsWidget(self, self._device))

    def exit(self):
        self.pubsub.publish('registry/view/actions/!widget_close', self)
