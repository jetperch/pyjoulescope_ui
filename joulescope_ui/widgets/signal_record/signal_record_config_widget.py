# Copyright 2023-2024 Jetperch LLC
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
from joulescope_ui import CAPABILITIES, register, pubsub_singleton, N_, get_topic_name
from joulescope_ui.filename_formatter import filename_tooltip, filename_formatter
from joulescope_ui.styles import styled_widget
import logging
import os


_FILENAME_DEFAULT = '{timestamp}.jls'
_FILENAME_TOPIC = 'registry/SignalRecordConfigWidget/settings/filename'


@register
@styled_widget(N_('SignalRecordConfig'))
class SignalRecordConfigWidget(QtWidgets.QWidget):
    CAPABILITIES = []  # no widget, since not directly instantiable
    SETTINGS = {
        'filename': {
            'dtype': 'str',
            'brief': N_('The filename with optional replacements.'),
            'default': _FILENAME_DEFAULT,
        },
    }

    def __init__(self, parent=None):
        self.SETTINGS = {}
        self._menu = None
        self._dialog = None
        self._row = 0
        super().__init__(parent=parent)
        self.setObjectName('signal_record_config')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QGridLayout(self)

        filename = pubsub_singleton.query(_FILENAME_TOPIC)
        self._filename_label = QtWidgets.QLabel(N_('Filename'), self)
        self._filename = QtWidgets.QLineEdit(self)
        self._filename.setText(filename)
        self._filename.setToolTip(filename_tooltip())
        self._file_reset = QtWidgets.QPushButton()
        self._file_reset.pressed.connect(self._on_file_reset)
        icon = self._file_reset.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogDiscardButton)
        self._file_reset.setIcon(icon)
        self._file_sel = QtWidgets.QPushButton(self)
        self._file_sel.pressed.connect(self._on_file_button)
        icon = self._file_sel.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileIcon)
        self._file_sel.setIcon(icon)
        self._layout.addWidget(self._filename_label, self._row, 0, 1, 1)
        self._layout.addWidget(self._filename, self._row, 1, 1, 1)
        self._layout.addWidget(self._file_reset, self._row, 2, 1, 1)
        self._layout.addWidget(self._file_sel, self._row, 3, 1, 1)
        self._row += 1

        self._location_label = QtWidgets.QLabel(N_('Directory'), self)
        self._location = QtWidgets.QLineEdit(self)
        self._location.setText(pubsub_singleton.query('registry/paths/settings/path'))
        self._location_reset = QtWidgets.QPushButton()
        self._location_reset.pressed.connect(self._on_location_reset)
        icon = self._location_reset.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogDiscardButton)
        self._location_reset.setIcon(icon)
        self._location_sel = QtWidgets.QPushButton(self)
        self._location_sel.pressed.connect(self._on_location_button)
        icon = self._location_sel.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirIcon)
        self._location_sel.setIcon(icon)
        self._layout.addWidget(self._location_label, self._row, 0, 1, 1)
        self._layout.addWidget(self._location, self._row, 1, 1, 1)
        self._layout.addWidget(self._location_reset, self._row, 2, 1, 1)
        self._layout.addWidget(self._location_sel, self._row, 3, 1, 1)
        self._row += 1

        self._source_widgets = {}
        self._signals_to_record_label = QtWidgets.QLabel(N_('Signals to record'), self)
        self._layout.addWidget(self._signals_to_record_label, self._row, 0, 1, 4)
        self._row += 1
        self._sources_add()

        self._notes_label = QtWidgets.QLabel(N_('Notes'), self)
        self._layout.addWidget(self._notes_label, self._row, 0, 1, 4)
        self._notes = QtWidgets.QTextEdit(self)
        self._layout.addWidget(self._notes, self._row + 4, 0, 4, 4)
        self._row += 5

    def _sources_add(self):
        sources = pubsub_singleton.query(f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_STREAM_SOURCE}/list')
        for source in sorted(sources):
            topic = get_topic_name(source)
            name = pubsub_singleton.query(f'{topic}/settings/name')
            label = QtWidgets.QLabel(f'   {name}', self)
            self._layout.addWidget(label, self._row, 0, 1, 1)
            signals = pubsub_singleton.enumerate(f'{topic}/settings/signals')

            signal_widget = QtWidgets.QWidget(self)
            signal_layout = QtWidgets.QHBoxLayout(signal_widget)
            signal_layout.setContentsMargins(3, 3, 3, 3)
            signal_layout.setSpacing(3)
            self._layout.addWidget(signal_widget, self._row, 1, 1, 1)
            self._row += 1

            signal_widgets = {}
            for signal_id in signals:
                enabled = pubsub_singleton.query(f'{topic}/settings/signals/{signal_id}/enable')
                b = QtWidgets.QPushButton(signal_widget)
                b.setCheckable(True)
                b.setEnabled(enabled)
                b.setChecked(enabled)
                b.setText(signal_id)
                b.setFixedSize(20, 20)
                signal_layout.addWidget(b)
                signal_widgets[signal_id] = b

            spacer = QtWidgets.QSpacerItem(0, 0,
                                           QtWidgets.QSizePolicy.Expanding,
                                           QtWidgets.QSizePolicy.Minimum)
            signal_layout.addItem(spacer)
            self._source_widgets[source] = (signal_widgets, signal_widget, signal_layout, label, spacer)

    def config(self):
        filename = self._filename.text()
        pubsub_singleton.publish(_FILENAME_TOPIC, filename)
        path = os.path.join(self._location.text(), filename)
        signals = []
        for source, values in self._source_widgets.items():
            topic = get_topic_name(source)
            for signal_id, b in values[0].items():
                if b.isChecked():
                    signals.append(f'{topic}/events/signals/{signal_id}/!data')
        return {
            'path': path,
            'signals': signals,
            'notes': self._notes.toPlainText(),
        }

    @QtCore.Slot()
    def _on_file_reset(self):
        self._filename.setText(_FILENAME_DEFAULT)

    @QtCore.Slot()
    def _on_file_button(self):
        path = os.path.join(self._location.text(), self._filename.text())
        filter_ = 'Joulescope Data (*.jls)'
        self._dialog = QtWidgets.QFileDialog(self.parent(), N_('Select save location'), path, filter_)
        self._dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        self._dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        self._dialog.setDefaultSuffix('.jls')
        self._dialog.updateGeometry()
        self._dialog.open()
        self._dialog.finished.connect(self._on_file_dialog_finished)

    @QtCore.Slot(int)
    def _on_file_dialog_finished(self, result):
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            files = self._dialog.selectedFiles()
            if files and len(files) == 1:
                self._location.setText(os.path.dirname(files[0]))
                self._filename.setText(os.path.basename(files[0]))
        else:
            pass
        self._dialog.close()
        self._dialog = None

    @QtCore.Slot()
    def _on_location_reset(self):
        self._location.setText(pubsub_singleton.query('registry/paths/settings/path'))

    @QtCore.Slot()
    def _on_location_button(self):
        path = self._location.text()
        self._dialog = QtWidgets.QFileDialog(self.parent(), N_('Select save location'), path)
        self._dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        self._dialog.updateGeometry()
        self._dialog.open()
        self._dialog.finished.connect(self._on_location_dialog_finished)

    @QtCore.Slot(int)
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
    count = 0

    def __init__(self, parent=None, is_action_show=None):
        self._log = logging.getLogger(f'{__name__}.dialog')
        self._log.info('start')
        if parent is None:
            parent = pubsub_singleton.query('registry/ui/instance', default=None)
        super().__init__(parent=parent)
        self.setObjectName("signal_record_config_dialog")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

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
        if bool(is_action_show):
            self.finished.connect(self._on_is_action_show_finished)

        self.resize(600, 400)
        self.setWindowTitle(N_('Configure signal recording'))
        self._log.info('open')
        self.open()

    @QtCore.Slot(int)
    def _on_is_action_show_finished(self, value):
        self._log.info('finished: %d', value)
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._log.info('finished: accept - start recording')
            config = self._w.config()
            config['path'] = filename_formatter(config['path'], SignalRecordConfigDialog.count)
            SignalRecordConfigDialog.count += 1
            pubsub_singleton.publish('registry/SignalRecord/actions/!start', config)
        else:
            self._log.info('finished: reject - abort recording')
            pubsub_singleton.publish('registry/app/settings/signal_stream_record', False)
        self.close()

    @staticmethod
    def on_cls_action_show():
        SignalRecordConfigDialog(is_action_show=True)
