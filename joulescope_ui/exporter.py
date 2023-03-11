# Copyright 2018-2023 Jetperch LLC
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


from PySide6 import QtCore, QtWidgets
from pyjls import Writer, SignalType, DataType
from joulescope_ui import N_, time64, pubsub_singleton, register, register_decorator, get_topic_name
from joulescope_ui.widgets import ProgressBarWidget
from joulescope_ui.jls_v2 import TO_JLS_SIGNAL_NAME
import datetime
import json
import logging
import os
import queue
import threading
import time


def _construct_record_filename(extension=None):
    if extension is None:
        extension = '.jls'
    if extension and extension[0] != '.':
        extension = '.' + extension
    time_start = datetime.datetime.utcnow()
    timestamp_str = time_start.strftime('%Y%m%d_%H%M%S')
    return f'{timestamp_str}{extension}'


class ExporterWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        self._parent = parent
        self._menu = None
        self._dialog = None
        self._row = 0
        super().__init__(parent=parent)
        self.setObjectName('exporter_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QGridLayout()

        self._location_label = QtWidgets.QLabel(N_('Directory'), self)
        self._location = QtWidgets.QLineEdit(self)
        self._location.setText(pubsub_singleton.query('registry/paths/settings/save_path'))
        self._location_sel = QtWidgets.QPushButton(self)
        self._location_sel.pressed.connect(self._on_location_button)
        self._layout.addWidget(self._location_label, self._row, 0, 1, 1)
        self._layout.addWidget(self._location, self._row, 1, 1, 1)
        self._layout.addWidget(self._location_sel, self._row, 2, 1, 1)
        self._row += 1

        self._filename_label = QtWidgets.QLabel(N_('Filename'), self)
        self._layout.addWidget(self._filename_label, self._row, 0, 1, 1)

        self._filename = QtWidgets.QLineEdit(self)
        self._filename.setText(_construct_record_filename())
        self._layout.addWidget(self._filename, self._row, 1, 1, 2)

        self.setLayout(self._layout)

    @property
    def path(self):
        return os.path.join(self._location.text(), self._filename.text())

    def _on_location_button(self):
        path = self._location.text()
        self._dialog = QtWidgets.QFileDialog(self._parent, N_('Select save location'), path)
        self._dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        self._dialog.updateGeometry()
        self._dialog.open()
        self._dialog.finished.connect(self._on_location_dialog_finished)

    def _on_location_dialog_finished(self, result):
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            files = self._dialog.selectedFiles()
            if files and len(files) == 1:
                self._location.setText(files[0])
        else:
            pass
        self._dialog.close()
        self._dialog = None

    def closeEvent(self, event):
        return super().closeEvent(event)


@register_decorator('exporter_worker')
class ExporterWorker:
    def __init__(self, x_range, kwargs, signals):
        self._log = logging.getLogger(f'{__name__}.worker')
        self._x_range = x_range
        self._kwargs = kwargs
        self._signals_list = signals
        self._signals = {}
        pubsub_singleton.register(self)
        cancel_topic = f'{get_topic_name(self)}/actions/!cancel'
        self._progress_bar = ProgressBarWidget(N_("Export in progress..."), cancel_topic)
        pubsub_singleton.register(self._progress_bar)
        self._quit = False
        self._log.info('start %s', self.unique_id)
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self.run)
        self._thread.start()
        self._rsp_id = 1

    def on_callback_data(self, value):
        self._queue.put(value, timeout=0.5)

    def on_action_cancel(self):
        self._log.info('cancel')
        self._quit = True
        self.on_action_finalize()

    def on_action_finalize(self):
        self._thread.join()
        pubsub_singleton.unregister(self)
        self._log.info('finalized')

    def _jls_init(self, jls: Writer):
        sources = []
        jls_signal_id = 1
        for idx, signal in enumerate(self._signals_list):
            (source_unique_id, signal_id) = signal
            meta_topic = f'registry/{source_unique_id}/settings/signals/{signal_id}/meta'
            meta = pubsub_singleton.query(meta_topic)
            source, signal_id_brief = signal_id.split('.')
            if source not in sources:
                sources.append(source)
                source_idx = source.index(source) + 1
                version = meta['version']
                if isinstance(version, dict):
                    version = json.dumps(version)
                jls.source_def(
                    source_id=source_idx,
                    name=source,
                    vendor=meta['vendor'],
                    model=meta['model'],
                    version=version,
                    serial_number=meta['serial_number'],
                )
            r = pubsub_singleton.query(f'{get_topic_name(source_unique_id)}/settings/signals/{signal_id}/range')
            d = self._request(signal, 'utc', self._x_range[0], 0, 1, timeout=5.0)
            info = d['info']
            jls.signal_def(
                signal_id=jls_signal_id,
                source_id=source.index(source) + 1,
                signal_type=SignalType.FSR,
                data_type=d['data_type'],
                sample_rate=info['time_map']['counter_rate'],
                name=TO_JLS_SIGNAL_NAME[info['field']],
                units=info['units'],
            )
            utc_start = info['time_range_utc']['start']
            d_utc = (utc_start - self._x_range[0]) / time64.SECOND
            if abs(d_utc) > 0.001:
                self._log.error('UTC error: %.3f: %d %d, %s', d_utc, utc_start, self._x_range[0], d['data'][0])
            self._signals[(source_unique_id, signal_id)] = {
                'signal': (source_unique_id, signal_id),
                'jls_signal_id': jls_signal_id,
                'info': info,
                'range': r,
                'sample_start': info['time_range_samples']['start'],
                'utc_start': utc_start,
            }
            jls_signal_id += 1

    def _request(self, signal, time_type, start, end, length, timeout=None):
        if time_type not in ['utc', 'samples']:
            raise ValueError(f'invalid time_type: {time_type}')
        rsp_id = self._rsp_id
        if isinstance(signal, dict):
            signal = signal['signal']
        req = {
            'signal_id': signal[1],
            'time_type': time_type,
            'start': start,
            'end': end,
            'length': length,
            'rsp_topic': f'{get_topic_name(self)}/callbacks/!data',
            'rsp_id': rsp_id,
        }
        self._rsp_id += 1
        pubsub_singleton.publish(f'{get_topic_name(signal[0])}/actions/!request', req)
        if timeout is None:
            return rsp_id
        t_end = time.time() + timeout
        while True:
            timeout = max(0.0, t_end - time.time())
            rsp = self._queue.get(timeout=timeout)
            if rsp['rsp_id'] == rsp_id:
                return rsp
            else:
                self._log.warning('discarding message')

    def run(self):
        self._log.info('thread start')
        progress = f'{get_topic_name(self._progress_bar)}/settings/progress'
        path = self._kwargs['path']

        with Writer(path) as jls:
            notes = self._kwargs.get('notes')
            if notes is not None:
                jls.user_data(0, notes)
            self._jls_init(jls)
            for signal in self._signals.values():
                utc = signal['utc_start']
                utc_start, utc_end = self._x_range
                self._log.info('%s: %d %d | %.3f', signal['signal'], utc_start, utc_end,
                               (utc_end - utc_start) / time64.SECOND)
                sample_id = signal['sample_start']
                sample_id_offset = sample_id
                jls_signal_id = signal['jls_signal_id']
                self._log.info('utc@start: %d %d', 0, signal['utc_start'])
                jls.utc(jls_signal_id, 0, signal['utc_start'])
                fs = signal['info']['time_map']['counter_rate']
                count = 0
                while True:
                    length = int(((utc_end - utc) / time64.SECOND) * fs)
                    if length <= 0:
                        if count:
                            sample_id_end = info['time_range_samples']['end'] - sample_id_offset
                            self._log.info('utc@end: %d %d', sample_id_end, utc_end)
                            jls.utc(jls_signal_id, sample_id_end, utc_end)
                        self._log.info(f'{signal["signal"]}: exported {count} samples')
                        break
                    length = min(10_000, length)
                    d = self._request(signal, 'samples', sample_id, 0, length, timeout=1.0)
                    info = d['info']
                    sample_id_start = info['time_range_samples']['start']
                    if sample_id_start != sample_id:
                        self._log.warning(f'sample_id mismatch: {sample_id_start} != {sample_id}')
                        sample_id = sample_id_start
                    jls.fsr(jls_signal_id, sample_id - sample_id_offset, d['data'])
                    sample_id += info['time_range_samples']['length']
                    utc = info['time_range_utc']['end'] + int(time64.SECOND / (fs * 2))
                    count += length
            pubsub_singleton.publish(progress, 1.0)
        if self._quit:
            self._log.info('thread done with quit/abort')
            os.remove(path)
        else:
            self._log.info('thread done with success')


@register_decorator('exporter')
class ExporterDialog(QtWidgets.QDialog):
    CAPABILITIES = ['range_tool@']
    SETTINGS = {
        'progress': {
            'dtype': 'float',
            'brief': N_('The fractional progress.'),
            'default': 0.0,
        },
    }
    _instances = []

    def __init__(self, x_range, signals):
        self._x_range = x_range
        self._signals = signals
        self._progress = None
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        ExporterDialog._instances.append(self)
        self._log = logging.getLogger(f'{__name__}.dialog')

        duration = (self._x_range[1] - self._x_range[0]) / time64.SECOND
        second = self._x_range[0] // time64.SECOND
        self._log.info(f'start duration={duration}, x_range={x_range}, x0_second={second}, signals={signals}')
        self.setObjectName('exporter_dialog')
        self._layout = QtWidgets.QVBoxLayout()
        self.setLayout(self._layout)
        self._w = ExporterWidget(self)
        self._layout.addWidget(self._w)
        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)
        self.finished.connect(self._on_finished)

        self.resize(600, 400)
        self.setWindowTitle(N_('Configure export'))
        self._log.info('open')
        pubsub_singleton.register(self)
        self.open()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        self._log.info('finished: %d', value)

        if value == QtWidgets.QDialog.DialogCode.Accepted:
            path = self._w.path
            self._log.info('finished: accept - start export to %s', path)
            kwargs = {'path': path}
            ExporterWorker(self._x_range, kwargs, self._signals)
        else:
            self._log.info('finished: reject - abort export')  # no action required
        self.close()

    def close(self):
        super().close()
        pubsub_singleton.unregister(self)
        ExporterDialog._instances.remove(self)

    @staticmethod
    def on_cls_action_run(value):
        """Run the range tool.

        :param value: See CAPABILITIES.RANGE_TOOL_CLASS
        """
        x_range = value['x_range']
        signals = value['signals']
        ExporterDialog(x_range, signals)
