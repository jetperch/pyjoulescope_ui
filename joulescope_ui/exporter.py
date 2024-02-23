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
from pyjls import Writer, SignalType
from joulescope_ui import N_, time64, pubsub_singleton, register_decorator, get_topic_name
from joulescope_ui.range_tool import RangeToolBase
from joulescope_ui.jls_v2 import TO_JLS_SIGNAL_NAME
import datetime
import json
import logging
import numpy as np
import os


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
        self._menu = None
        self._dialog = None
        self._row = 0
        super().__init__(parent=parent)
        self.setObjectName('exporter_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QGridLayout(self)

        self._location_label = QtWidgets.QLabel(N_('Directory'), self)
        self._location = QtWidgets.QLineEdit(self)
        self._location.setText(pubsub_singleton.query('registry/paths/settings/path'))
        self._location_sel = QtWidgets.QPushButton(self)
        self._location_sel.pressed.connect(self._on_location_button)
        icon = self._location_sel.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirIcon)
        self._location_sel.setIcon(icon)
        self._layout.addWidget(self._location_label, self._row, 0, 1, 1)
        self._layout.addWidget(self._location, self._row, 1, 1, 1)
        self._layout.addWidget(self._location_sel, self._row, 2, 1, 1)
        self._row += 1

        self._filename_label = QtWidgets.QLabel(N_('Filename'), self)
        self._layout.addWidget(self._filename_label, self._row, 0, 1, 1)
        self._filename = QtWidgets.QLineEdit(self)
        self._filename.setText(_construct_record_filename())
        self._layout.addWidget(self._filename, self._row, 1, 1, 2)
        self._row += 1

        self._notes_label = QtWidgets.QLabel(N_('Notes'), self)
        self._layout.addWidget(self._notes_label, self._row, 0, 1, 3)
        self._row += 1
        self._notes = QtWidgets.QPlainTextEdit(self)
        self._layout.addWidget(self._notes, self._row, 0, 1, 3)
        self._row += 1

    @property
    def path(self):
        return os.path.join(self._location.text(), self._filename.text())

    @property
    def notes(self):
        return self._notes.toPlainText()

    @QtCore.Slot()
    def _on_location_button(self):
        path = self._location.text()
        self._dialog = QtWidgets.QFileDialog(self.parent(), N_('Select save location'), path)
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


class ExporterDialog(QtWidgets.QDialog):

    def __init__(self, value):
        self.CAPABILITIES = []
        self._value = value
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._log = logging.getLogger(f'{__name__}.dialog')

        x_range = value['x_range']
        if callable(x_range):
            self._log.info('start x_range is callable, defer')
        else:
            duration = (x_range[1] - x_range[0]) / time64.SECOND
            second = x_range[0] // time64.SECOND
            self._log.info('start duration=%r, x_range=%r, x0_second=%r, signals=%r',
                           duration, x_range, second, value['signals'])
        self.setObjectName('exporter_dialog')
        self._layout = QtWidgets.QVBoxLayout(self)
        self._w = ExporterWidget(self)
        self._layout.addWidget(self._w)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)
        self.finished.connect(self._on_finished)

        self.resize(600, 400)
        self.setWindowTitle(N_('Export configuration'))
        self._log.info('open')
        pubsub_singleton.register(self)
        self.open()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        self._log.info('finished: %d', value)

        if value == QtWidgets.QDialog.DialogCode.Accepted:
            path = self._w.path
            self._log.info('finished: accept - start export to %s', path)
            kwargs = self._value.get('kwargs', None)
            if kwargs is None:
                kwargs = {}
                self._value['kwargs'] = kwargs
            kwargs['path'] = path
            kwargs['notes'] = self._w.notes
            w = Exporter(self._value)
            pubsub_singleton.register(w)
            self._value['path'] = path
        else:
            self._log.info('finished: reject - abort export')  # no action required
        self.close()

    def close(self):
        pubsub_singleton.unregister(self, delete=True)
        super().close()


@register_decorator('exporter')
class Exporter(RangeToolBase):
    NAME = N_('Exporter')
    BRIEF = N_('Export data to a JLS file')
    DESCRIPTION = N_("""\
                Exporting data to a JLS file.  You can open this file
                later to display the exported data.""")

    def __init__(self, value):
        self._signals = {}
        super().__init__(value=value)

    def _jls_init(self, jls: Writer):
        sources = []
        jls_signal_id = 1
        for idx, signal_id in enumerate(self.signals):
            source, device, quantity = signal_id.split('.')
            meta_topic = f'registry/{source}/settings/signals/{device}.{quantity}/meta'
            meta = pubsub_singleton.query(meta_topic)
            if device not in sources:
                sources.append(device)
                source_idx = sources.index(device) + 1
                version = meta['version']
                if isinstance(version, dict):
                    version = json.dumps(version)
                jls.source_def(
                    source_id=source_idx,
                    name=device,
                    vendor=meta['vendor'],
                    model=meta['model'],
                    version=version,
                    serial_number=meta['serial_number'],
                )
            r = pubsub_singleton.query(f'registry/{source}/settings/signals/{device}.{quantity}/range')
            d = self.request(signal_id, 'utc', self.x_range[0], 0, 1, timeout=5.0)
            info = d['info']
            jls.signal_def(
                signal_id=jls_signal_id,
                source_id=sources.index(device) + 1,
                signal_type=SignalType.FSR,
                data_type=d['data_type'],
                sample_rate=info['time_map']['counter_rate'],
                name=TO_JLS_SIGNAL_NAME[info['field']],
                units=info['units'],
            )
            utc_start = info['time_range_utc']['start']
            d_utc = (utc_start - self.x_range[0]) / time64.SECOND
            if abs(d_utc) > 0.001:
                self._log.error('UTC error: %.3f: %d %d, %s', d_utc, utc_start, self.x_range[0], d['data'][0])
            self._signals[signal_id] = {
                'signal': signal_id,
                'jls_signal_id': jls_signal_id,
                'info': info,
                'range': r,
                'sample_start': info['time_range_samples']['start'],
                'utc_start': utc_start,
            }
            jls_signal_id += 1

    def _run(self):
        self._log.info('thread start')
        path = self.kwargs['path']
        progress_iter = 1.0 / len(self.signals)

        with Writer(path) as jls:
            notes = self.kwargs.get('notes')
            if notes is not None and isinstance(notes, str) and len(notes):
                jls.user_data(0, notes)
            self._jls_init(jls)
            for signal_idx, signal in enumerate(self._signals.values()):
                if self.abort:
                    break
                utc = signal['utc_start']
                utc_start, utc_end = self.x_range
                self._log.info('%s: %d %d | %.3f', signal['signal'], utc_start, utc_end,
                               (utc_end - utc_start) / time64.SECOND)
                sample_id = signal['sample_start']
                sample_id_offset = sample_id
                jls_signal_id = signal['jls_signal_id']
                self._log.info('utc@start: %d %d', 0, signal['utc_start'])
                jls.utc(jls_signal_id, 0, signal['utc_start'])
                fs = signal['info']['time_map']['counter_rate']
                count = 0
                length_total = int(((utc_end - utc) / time64.SECOND) * fs)
                while not self.abort:
                    length_remaining = int(((utc_end - utc) / time64.SECOND) * fs)
                    if length_remaining <= 0:
                        if count:
                            sample_id_end = info['time_range_samples']['end'] - sample_id_offset
                            self._log.info('utc@end: %d %d', sample_id_end, utc_end)
                            jls.utc(jls_signal_id, sample_id_end, utc_end)
                        self._log.info(f'{signal["signal"]}: exported {count} samples')
                        break
                    length = min(100_000, length_remaining)
                    d = self.request(signal['signal'], 'samples', sample_id, 0, length, timeout=1.0)
                    info = d['info']
                    sample_id_start = info['time_range_samples']['start']
                    if sample_id_start != sample_id:
                        self._log.warning(f'sample_id mismatch: {sample_id_start} != {sample_id}')
                        sample_id = sample_id_start
                    data = np.ascontiguousarray(d['data'])
                    jls.fsr(jls_signal_id, sample_id - sample_id_offset, data)
                    sample_id += info['time_range_samples']['length']
                    utc = info['time_range_utc']['end'] + int(time64.SECOND / (fs * 2))
                    count += length
                    self.progress((signal_idx + (1 - length_remaining / length_total)) * progress_iter)

        if self.abort:
            self._log.info('thread done with quit/abort')
            os.remove(path)
        else:
            self._log.info('thread done with success')
            pubsub_singleton.publish('registry/paths/actions/!mru_save', path)

    @staticmethod
    def on_cls_action_run(value):
        """Run the range tool.

        :param value: See CAPABILITIES.RANGE_TOOL_CLASS
        """
        ExporterDialog(value)
