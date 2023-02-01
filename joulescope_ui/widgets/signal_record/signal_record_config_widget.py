# Copyright 2023 Jetperch LLC
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

from PySide6 import QtWidgets, QtGui, QtCore
from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name, tooltip_format
from joulescope_ui.styles import styled_widget
import datetime
import logging
import os


def _construct_record_filename():
    time_start = datetime.datetime.utcnow()
    timestamp_str = time_start.strftime('%Y%m%d_%H%M%S')
    return f'{timestamp_str}.jls'


@register
@styled_widget(N_('SignalRecordConfig'))
class SignalRecordConfigWidget(QtWidgets.QWidget):
    CAPABILITIES = []  # no widget, since not directly instantiable

    def __init__(self, parent=None):
        self._parent = parent
        self._menu = None
        self._dialog = None
        super().__init__(parent=parent)
        self.setObjectName('signal_record_config')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QGridLayout()

        self._filename_label = QtWidgets.QLabel(N_('Filename'), self)
        self._filename = QtWidgets.QLineEdit(self)
        self._filename.setText(_construct_record_filename())
        self._layout.addWidget(self._filename_label, 0, 0, 1, 1)
        self._layout.addWidget(self._filename, 0, 1, 1, 1)

        self._location_label = QtWidgets.QLabel(N_('Directory'), self)
        self._location = QtWidgets.QLineEdit(self)
        self._location.setText(pubsub_singleton.query('registry/paths/settings/save_path'))
        self._location_sel = QtWidgets.QPushButton(self)
        self._location_sel.pressed.connect(self._on_location_button)
        self._layout.addWidget(self._location_label, 1, 0, 1, 1)
        self._layout.addWidget(self._location, 1, 1, 1, 1)
        self._layout.addWidget(self._location_sel, 1, 2, 1, 1)

        self._signals_to_record_label = QtWidgets.QLabel(N_('Signals to record'), self)
        self._layout.addWidget(self._signals_to_record_label, 2, 0, 1, 3)
        # todo add signals

        self._notes_label = QtWidgets.QLabel(N_('Notes'), self)
        self._layout.addWidget(self._notes_label, 3, 0, 1, 3)
        self._notes = QtWidgets.QTextEdit(self)
        self._layout.addWidget(self._notes, 4, 0, 4, 3)

        self.setLayout(self._layout)

    def config(self):
        path = os.path.join(self._location.text(), self._filename.text())
        return {
            'path': path,
            'signals': [],  # todo
            'notes': self._notes.toPlainText(),
        }

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


class SignalRecordConfigDialog(QtWidgets.QDialog):
    _singleton = None

    def __init__(self):
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        SignalRecordConfigDialog._singleton = self
        self._log = logging.getLogger(f'{__name__}.dialog')

        self._log.info('start')
        self.setObjectName("signal_record_config_dialog")
        self._layout = QtWidgets.QVBoxLayout()
        self.setLayout(self._layout)

        self._w = SignalRecordConfigWidget(self)
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
        self.setWindowTitle(N_('Configure signal recording'))
        self._log.info('open')
        self.open()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        self._log.info('finished: %d', value)

        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._log.info('finished: accept - start recording')
            config = self._w.config()
            pubsub_singleton.publish('registry/SignalRecord/actions/!start', config)
        else:
            self._log.info('finished: reject - abort recording')
            pubsub_singleton.publish('registry/app/settings/signal_stream_record', False)
        self.close()
        SignalRecordConfigDialog._singleton = None

    @staticmethod
    def on_cls_action_show():
        SignalRecordConfigDialog()
