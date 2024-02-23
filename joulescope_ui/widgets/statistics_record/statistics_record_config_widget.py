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
from joulescope_ui.ui_util import comboBoxConfig
import datetime
import logging
import os


_TIME_FORMAT_OPTIONS = ['relative', 'UTC', 'off']


def _construct_record_filename(device):
    time_start = datetime.datetime.utcnow()
    timestamp_str = time_start.strftime('%Y%m%d_%H%M%S')
    return f'{timestamp_str}-{device}.csv'


@register
@styled_widget(N_('StatisticsRecordConfig'))
class StatisticsRecordConfigWidget(QtWidgets.QWidget):
    CAPABILITIES = []  # no widget, since not directly instantiable

    def __init__(self, parent=None):
        self._menu = None
        self._dialog = None
        self._row = 0
        super().__init__(parent=parent)
        self.setObjectName('signal_record_config')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QGridLayout(self)

        self._location_label = QtWidgets.QLabel(N_('Directory'), self)
        self._location = QtWidgets.QLineEdit(self)
        self._location.setText(pubsub_singleton.query('registry/paths/settings/path'))
        self._location_sel = QtWidgets.QPushButton(self)
        self._location_sel.pressed.connect(self._on_location_button)
        icon = self._location_sel.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirIcon)
        self._location_sel.setIcon(icon)
        self._layout.addWidget(self._location_label, self._row, 0, 1, 2)
        self._layout.addWidget(self._location, self._row, 2, 1, 1)
        self._layout.addWidget(self._location_sel, self._row, 3, 1, 1)
        self._row += 1

        self._time_format_label = QtWidgets.QLabel(N_('Time Format'), self)
        self._time_format = QtWidgets.QComboBox(self)
        comboBoxConfig(self._time_format, _TIME_FORMAT_OPTIONS, _TIME_FORMAT_OPTIONS[0])
        self._layout.addWidget(self._time_format_label, self._row, 0, 1, 2)
        self._layout.addWidget(self._time_format, self._row, 2, 1, 1)
        self._row += 1

        self._source_widgets = {}
        self._sources_add()

    def _sources_add(self):
        sources = pubsub_singleton.query(f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list')
        for source in sorted(sources):
            topic = get_topic_name(source)
            name = pubsub_singleton.query(f'{topic}/settings/name')
            checkbox = QtWidgets.QCheckBox(self)
            checkbox.setChecked(True)
            self._layout.addWidget(checkbox, self._row, 0, 1, 1)

            label = QtWidgets.QLabel(name, self)
            self._layout.addWidget(label, self._row, 1, 1, 1)

            filename = QtWidgets.QLineEdit(self)
            filename.setText(_construct_record_filename(name))
            checkbox.clicked.connect(filename.setEnabled)

            self._layout.addWidget(filename, self._row, 2, 1, 2)
            self._source_widgets[source] = (checkbox, filename, label)
            self._row += 1

    def config(self):
        path = self._location.text()
        sources = []
        for source, values in self._source_widgets.items():
            checkbox, filename = values[:2]
            if checkbox.isChecked():
                topic = f'{get_topic_name(source)}/events/statistics/!data'
                filename = os.path.join(path, filename.text())
                sources.append([topic, filename])
        return {
            'sources': sources,
            'config': {
                'time_format': self._time_format.currentText(),
            }
        }
        return sources

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


class StatisticsRecordConfigDialog(QtWidgets.QDialog):

    def __init__(self):
        self._log = logging.getLogger(f'{__name__}.dialog')
        self._log.info('start')
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self.setObjectName("signal_record_config_dialog")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._w = StatisticsRecordConfigWidget(self)
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
            pubsub_singleton.publish('registry/StatisticsRecord/actions/!start', config)
        else:
            self._log.info('finished: reject - abort recording')
            pubsub_singleton.publish('registry/app/settings/statistics_stream_record', False)
        self.close()

    @staticmethod
    def on_cls_action_show():
        StatisticsRecordConfigDialog()
