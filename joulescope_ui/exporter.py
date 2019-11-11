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


class Exporter:

    def __init__(self):
        self._cfg = None

    def run_pre(self, data):  # RangeToolInvocation
        path = data.cmdp['General/data_path']
        rv = ExportDialog(path).exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):  # RangeToolInvocation
        registry = {
            'bin': self._export_bin,
            'csv': self._export_csv,
            'jls': self._export_jls,
            'raw': self._export_raw,
        }
        filetype = self._cfg['filetype']
        fn = registry.get(filetype)
        if fn is None:
            return f'Invalid export file type: {filetype}'
        return fn(data)

    def _export_bin(self, data):
        cfg = self._cfg
        with open(cfg['filename'], 'wb') as f:
            for block in data:
                current = block['signals']['current']['value'].reshape((-1, 1))
                voltage = block['signals']['voltage']['value'].reshape((-1, 1))
                values = np.hstack((current, voltage))
                f.write(values.tobytes())

    def _export_csv(self, data):
        cfg = self._cfg
        sampling_frequency = data.sample_frequency
        sampling_period = 1.0 / sampling_frequency
        time_offset = 0.0
        with open(cfg['filename'], 'wt') as f:
            if cfg.get('add_header'):
                f.write('#time (s),current (A),voltage (V)\n')
            for block in data.iterate(sampling_frequency):
                current = block['signals']['current']['value'].reshape((-1, 1))
                voltage = block['signals']['voltage']['value'].reshape((-1, 1))
                x = np.arange(len(current), dtype=np.float64).reshape((-1, 1))
                x *= sampling_period
                x += time_offset
                time_offset += 1.0
                values = np.hstack((x, current, voltage))
                np.savetxt(f, values, ['%.7f', '%.4e', '%.4f'], delimiter=',')

    def _export_jls(self, data):
        cfg = self._cfg
        sampling_frequency = data.sample_frequency
        stream_buffer = StreamBuffer(sampling_frequency * 2, [], sampling_frequency=sampling_frequency)
        stream_buffer.calibration_set(data.calibration.current_offset, data.calibration.current_gain,
                                      data.calibration.voltage_offset, data.calibration.voltage_gain)
        stream_buffer.voltage_range = data.cmdp['Plugins/#state/voltage_range']
        data_recorder = DataRecorder(
            cfg['filename'],
            calibration=data.calibration.data,
            sampling_frequency=sampling_frequency)
        data_recorder.stream_notify(stream_buffer)

        try:
            for block in data:
                log.info('export_jls iteration')
                stream_buffer.insert_raw(block['signals']['raw']['value'])
                stream_buffer.process()
                data_recorder.stream_notify(stream_buffer)
        finally:
            data_recorder.close()

    def _export_raw(self, data):
        cfg = self._cfg
        with open(cfg['filename'], 'wb') as f:
            for block in data:
                values = block['signals']['raw']['value']
                f.write(values.tobytes())


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
        filters = [
            'Joulescope Data (*.jls)',
            'Binary 32-bit float (*.bin)',
            'Comma Separated Values (*.csv)',
            'Raw 16-bit samples (*.raw)',
        ]
        filter_str = ';;'.join(filters)
        filename, select_mask = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Joulescope Data', self._path, filter_str)
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
