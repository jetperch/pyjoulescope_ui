# Copyright 2018 Jetperch LLC
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

from joulescope_ui.export_dialog import Ui_Form
from PySide2 import QtWidgets, QtGui, QtCore
from joulescope.data_recorder import DataRecorder
from joulescope.stream_buffer import StreamBuffer
import numpy as np
import os
import logging
log = logging.getLogger(__name__)


class Worker(QtCore.QObject):
    sigProgress = QtCore.Signal(int)  # 0 to 1000
    sigFinished = QtCore.Signal(str)

    def __init__(self, view, cfg):
        super().__init__()
        self._view = view
        self._cfg = cfg
        self._stop = False

    @QtCore.Slot()
    def stop(self):
        self._stop = True

    def run(self):
        registry = {
            'csv': self._export_csv,
            'jls': self._export_jls,
        }
        filetype = self._cfg['filetype']
        fn = registry.get(filetype)
        if fn is None:
            msg = f'Invalid export file type: {filetype}'
            log.warning(msg)
            self.sigFinished.emit(msg)
        else:
            try:
                msg = fn()
                if msg is None and self._stop:
                    msg = 'Export aborted'
                self.sigFinished.emit(msg)
            except:
                log.exception('while exporting')
                self.sigFinished.emit('Export failed: internal exception')

    def _export_csv(self):
        view = self._view
        cfg = self._cfg
        sampling_frequency = view.sampling_frequency
        sampling_period = 1.0 / sampling_frequency
        idx_start = cfg['sample_id_start']
        idx_stop = cfg['sample_id_stop']
        idx_range = idx_stop - idx_start
        idx = idx_start
        self.sigProgress.emit(0)
        with open(cfg['filename'], 'wt') as f:
            if cfg.get('add_header'):
                f.write('#time (s),current (A),voltage (V)\n')
            while not self._stop and idx < idx_stop:
                log.debug('export_csv iteration')
                idx_next = idx + int(view.sampling_frequency / 10)
                if idx_next > idx_stop:
                    idx_next = idx_stop
                data = view.samples_get(idx, idx_next)
                current = data['current']['value'].reshape((-1, 1))
                voltage = data['voltage']['value'].reshape((-1, 1))
                x = np.arange(len(current), dtype=np.float64).reshape((-1, 1))
                x *= sampling_period
                x += (idx - idx_start) * sampling_period
                values = np.hstack((x, current, voltage))
                log.debug('export_csv savetxt start')
                np.savetxt(f, values, ['%.7f', '%.4e', '%.4f'], delimiter=',')
                log.debug('export_csv savetxt done')
                idx = idx_next
                self.sigProgress.emit(int(1000 * (idx - idx_start) / idx_range))

    def _export_jls(self):
        view = self._view
        cfg = self._cfg
        sampling_frequency = view.sampling_frequency
        sample_step_size = sampling_frequency
        stream_buffer = StreamBuffer(sampling_frequency * 2, [])
        data_recorder = DataRecorder(
            cfg['filename'],
            calibration=view.calibration.data,
            sampling_frequency=sampling_frequency)
        data_recorder.process(stream_buffer)

        try:
            idx_start = cfg['sample_id_start']
            idx_stop = cfg['sample_id_stop']
            idx_range = idx_stop - idx_start
            idx = idx_start
            self.sigProgress.emit(0)
            while not self._stop and idx < idx_stop:
                log.info('export_jls iteration')
                idx_next = idx + sample_step_size
                if idx_next > idx_stop:
                    idx_next = idx_stop
                data = view.raw_get(idx, idx_next)
                log.info('export_jls (%d, %d) -> %d', idx, idx_next, len(data))
                stream_buffer.insert_raw(data)
                stream_buffer.process()
                data_recorder.process(stream_buffer)
                idx = idx_next
                self.sigProgress.emit(int(1000 * (idx - idx_start) / idx_range))
        finally:
            data_recorder.close()


class Exporter(QtCore.QObject):

    sigFinished = QtCore.Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self._worker = None
        self._thread = None
        self._progress = None

    def export(self, view, x_start, x_stop, path_default=None):
        """Export data request.

        :param view: The view implementation with TBD API.
        :param x_start: The starting position in x-axis units.
        :param x_stop: The stopping position in x-axis units.
        :param path_default: The default path.  None (default)
            uses the current directory.
        """
        if self._thread is not None:
            self.sigFinished.emit('busy')
        self._thread = QtCore.QThread()
        t1, t2 = min(x_start, x_stop), max(x_start, x_stop)
        log.info('exportData(%s, %s)', t1, t2)
        s1 = view.time_to_sample_id(x_start)
        s2 = view.time_to_sample_id(x_stop)
        if s1 is None or s2 is None:
            return 'Export time out of range'

        rv = ExportDialog(path_default).exec_()
        if rv is None:
            return
        rv['sample_id_start'] = s1
        rv['sample_id_stop'] = s2

        self._progress = QtWidgets.QProgressDialog('Export in progress...', 'Cancel', 0, 1000, self.parent())
        self._progress.setWindowModality(QtCore.Qt.WindowModal)
        self._worker = Worker(view, rv)
        self._worker.sigProgress.connect(self._progress.setValue)
        self._worker.sigFinished.connect(self.on_finished)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._worker.deleteLater)
        self._progress.canceled.connect(self._worker.stop)
        self._thread.start()
        self._progress.forceShow()

    def on_finished(self, msg):
        self._thread.quit()
        self._thread.wait()
        self._progress.hide()
        self._progress.close()
        self._thread = None
        self._progress = None
        self.sigFinished.emit(msg)


class ExportDialog(QtWidgets.QDialog):

    def __init__(self, path):
        QtWidgets.QDialog.__init__(self)
        self._path = path
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.saveButton.pressed.connect(self.accept)
        self.ui.cancelButton.pressed.connect(self.reject)
        self.ui.filenameLineEdit.textChanged.connect(self.on_filename_text_edit)
        self.ui.filenameSelectButton.pressed.connect(self.on_filename_select_button)

    def on_filename_select_button(self):
        filename, select_mask = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Joulescope Data', self._path, 'Joulescope Data (*.jls);;Comma Separated Values (*.csv)')
        log.info('save filename selected: %s', filename)
        filename = str(filename)
        self.ui.filenameLineEdit.setText(filename)
        self.ui.saveButton.setEnabled(True)

    def on_filename_text_edit(self, text):
        self.ui.saveButton.setEnabled(True)

    def _field_flags(self):
        d = {}
        for name, widget in self._fields:
            d[name] = widget.isChecked()
        return d

    def exec_(self):
        if QtWidgets.QDialog.exec_(self) == 1:
            filename = str(self.ui.filenameLineEdit.text())
            _, filetype = os.path.splitext(filename)
            if filetype and filetype[0] == '.':
                filetype = filetype[1:]
            return {
                'filetype': filetype,
                'filename': filename,
            }
        else:
            return None
