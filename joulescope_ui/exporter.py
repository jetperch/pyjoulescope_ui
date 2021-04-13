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

from joulescope_ui.file_dialog import FileDialog
from joulescope_ui.paths import data_path, data_path_saved_set
from joulescope.data_recorder import DataRecorder, construct_record_filename
import numpy as np
import os
import logging
log = logging.getLogger(__name__)


def _filetype(filename):
    if filename is None:
        return None
    _, filetype = os.path.splitext(filename)
    if filetype and filetype[0] == '.':
        filetype = filetype[1:]
    return filetype


class Exporter:

    def __init__(self):
        self._filename = None

    def run_pre(self, data):  # RangeToolInvocation
        path = data_path(data.cmdp)
        self._filename = self._filename_select(data.parent(), path)
        if self._filename is None:
            return 'Cancelled'

    def run_post(self, data):
        data.cmdp.publish('!General/mru_add', self._filename)
        data_path_saved_set(data.cmdp, os.path.dirname(self._filename))

    def run(self, data):  # RangeToolInvocation
        registry = {
            'bin': self._export_bin,
            'csv': self._export_csv,
            'jls': self._export_jls,
            'raw': self._export_raw,
        }
        filetype = _filetype(self._filename)
        fn = registry.get(filetype)
        if fn is None:
            return f'Invalid export file type: {filetype}'
        rv = fn(data)
        if data.is_cancelled:
            if os.path.isfile(self._filename):
                os.unlink(self._filename)
        elif filetype == 'jls':
            annofile = self._filename[:-4] + '.anno.jls'
            t_min, t_max = data.time_range
            data.cmdp.publish('!Widgets/Waveform/annotation/save', [annofile, t_min, t_max])
        return rv

    def _filename_select(self, parent, path):
        filename = construct_record_filename()
        filename = os.path.join(path, filename)
        filters = [
            'Joulescope Data (*.jls)',
            'Binary 32-bit float (*.bin)',
            'Comma Separated Values (*.csv)',
            'Raw 16-bit samples (*.raw)',
        ]
        filter_str = ';;'.join(filters)
        dialog = FileDialog(parent, 'Save Joulescope Data', filename, 'any')
        dialog.setNameFilter(filter_str)
        filename = dialog.exec_()
        if bool(filename):
            log.info('save filename selected: %s', filename)
            filename = str(filename)
        else:
            filename = None
        return filename

    def _export_bin(self, data):
        with open(self._filename, 'wb') as f:
            for block in data:
                current = block['signals']['current']['value'].reshape((-1, 1))
                voltage = block['signals']['voltage']['value'].reshape((-1, 1))
                values = np.hstack((current, voltage))
                f.write(values.tobytes())

    def _export_csv(self, data):
        sampling_frequency = data.sample_frequency
        sampling_period = 1.0 / sampling_frequency
        time_offset = 0.0
        with open(self._filename, 'wt') as f:
            # f.write('#time (s),current (A),voltage (V)\n')
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
        data_recorder = DataRecorder(
            self._filename,
            calibration=data.calibration.data)

        try:
            for block in data:
                log.info('export_jls iteration')
                data_recorder.insert(block)
        finally:
            data_recorder.close()

    def _export_raw(self, data):
        with open(self._filename, 'wb') as f:
            for block in data:
                if 'raw' not in block['signals']:
                    raise ValueError('Source does have RAW data')
                values = block['signals']['raw']['value']
                f.write(values.tobytes())
