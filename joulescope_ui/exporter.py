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
from joulescope_ui import N_, time64, pubsub_singleton, register, register_decorator, get_topic_name
from joulescope_ui.widgets import ProgressBarWidget
import datetime
import logging
import os
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
        self._signals = signals
        unique_id = pubsub_singleton.register(self)
        cancel_topic = f'{get_topic_name(self)}/actions/!cancel'
        self._progress_bar = ProgressBarWidget(N_("Export in progress..."), cancel_topic)
        pubsub_singleton.register(self._progress_bar)
        self._quit = False
        self._log.info('start %s', unique_id)
        self._thread = threading.Thread(target=self.run)
        self._thread.start()

    def on_cbk_data(self, value):
        print(value)

    def on_action_cancel(self):
        self._log.info('cancel')
        self._quit = True
        self.on_action_finalize()

    def on_action_finalize(self):
        self._thread.join()
        pubsub_singleton.unregister(self)
        self._log.info('finalized')

    def run(self):
        self._log.info('thread start')
        progress = f'{get_topic_name(self._progress_bar)}/settings/progress'
        cbk_topic = f'{get_topic_name(self)}/cbk/!data'
        for i in range(1001):
            if self._quit:
                break
            pubsub_singleton.publish(progress, i / 1000)
            time.sleep(0.002)
        self._log.info('thread done')


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

        self._log.info(f'start {x_range}, {signals}')
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

        :param value: [(time64_min, time64_max), kwargs, (source_unique_id, signal_id), ...]
        """
        x0, x1 = value[0]
        kwargs = value[1]
        signals = value[2]
        dx = (x1 - x0) / time64.SECOND
        if kwargs is None or not len(kwargs):
            ExporterDialog(dx, signals)
        else:
            raise NotImplementedError('kwargs not yet supported')
