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
from joulescope_ui.ui_util import comboBoxConfig
import copy
import datetime
import logging
import os


_TIME_FORMAT_OPTIONS = ['relative', 'UTC', 'off']
_FILENAME_DEFAULT = '{timestamp}-{device_id}.csv'
_FILENAME_TOPIC = 'registry/StatisticsRecordConfigWidget/settings/filename'


def config_default() -> dict:
    """Get the default configuration.

    :return: The config dict.
    """
    config = {
        'location': pubsub_singleton.query('registry/paths/settings/path'),
        'time_format': 'relative',
        'sources': {},
    }

    sources_ids = pubsub_singleton.query(f'registry_manager/capabilities/{CAPABILITIES.STATISTIC_STREAM_SOURCE}/list')
    for source_id in sorted(sources_ids):
        config['sources'][source_id] = {
            'enabled': True,
            'filename': _FILENAME_DEFAULT,
        }
    return config


def config_constrain(config: dict) -> dict:
    """Constrain the config to the available sources.

    :param config: The configuration.
    :return: The possibly modified configuration copy.
    """
    config = copy.deepcopy(config)
    default = config_default()
    for source_id, signals in default['sources'].items():
        if source_id not in config['sources']:
            default['sources'][source_id]['enabled'] = False
        else:
            default['sources'][source_id] = config['sources'][source_id]
    config['sources'] = default['sources']
    return config


def config_update(config: dict, count: int, **kwargs) -> dict:
    """Update the config with replacement values.

    :param config: The configuration dict.
    :param count: The count substitution value.
    :param kwargs: Additional filename_formatter arguments.
    :return: The possibly modified configuration copy.
    """
    config = copy.deepcopy(config)
    location = config['location']
    for source_id, source in config['sources'].items():
        filename = filename_formatter(source['filename'], count=count, device_id=source_id, **kwargs)
        source['filename'] = filename
        source['path'] = os.path.join(location, filename)
    return config


@register
@styled_widget(N_('StatisticsRecordConfig'))
class StatisticsRecordConfigWidget(QtWidgets.QWidget):
    CAPABILITIES = []  # no widget, since not directly instantiable
    SETTINGS = {
        'filename': {
            'dtype': 'str',
            'brief': N_('The filename with optional replacements.'),
            'default': _FILENAME_DEFAULT,
        },
    }

    def __init__(self, parent=None, config=None):
        self._menu = None
        self._dialog = None
        self._row = 0
        if config is None:
            self._config = config_default()
        else:
            self._config = config_constrain(config)

        super().__init__(parent=parent)
        self.setObjectName('signal_record_config')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QGridLayout(self)

        self._location_label = QtWidgets.QLabel(N_('Directory'), self)
        self._location = QtWidgets.QLineEdit(self)
        self._location.setText(self._config['location'])
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
        comboBoxConfig(self._time_format, _TIME_FORMAT_OPTIONS, self._config['time_format'])
        self._layout.addWidget(self._time_format_label, self._row, 0, 1, 2)
        self._layout.addWidget(self._time_format, self._row, 2, 1, 1)
        self._row += 1

        self._source_widgets = {}
        self._sources_add()

    def _sources_add(self):
        for source_id in sorted(self._config['sources'].keys()):
            source = self._config['sources'][source_id]
            topic = get_topic_name(source_id)
            name = pubsub_singleton.query(f'{topic}/settings/name')
            checkbox = QtWidgets.QCheckBox(self)
            checkbox.setChecked(source['enabled'])
            self._layout.addWidget(checkbox, self._row, 0, 1, 1)

            tooltip = filename_tooltip(device_id=True)
            label = QtWidgets.QLabel(name)
            label.setToolTip(tooltip)
            self._layout.addWidget(label, self._row, 1, 1, 1)
            filename = QtWidgets.QLineEdit()
            filename.setText(source['filename'])
            filename.setToolTip(tooltip)
            checkbox.clicked.connect(filename.setEnabled)

            self._layout.addWidget(filename, self._row, 2, 1, 2)
            self._source_widgets[source_id] = (checkbox, filename, label)
            self._row += 1

    def config(self):
        path = self._location.text()
        sources = {}
        for source_id, values in self._source_widgets.items():
            checkbox, filename = values[:2]
            sources[source_id] = {
                'enabled': checkbox.isChecked(),
                'filename': filename.text(),
                'path': os.path.join(path, filename.text())
            }
        return {
            'location': path,
            'time_format': self._time_format.currentText(),
            'sources': sources,
        }

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
    config_changed = QtCore.Signal(object)
    count = 0

    def __init__(self, parent=None, skip_default_actions=None, config=None):
        self._log = logging.getLogger(f'{__name__}.dialog')
        self._log.info('start')
        self._skip_default_actions = bool(skip_default_actions)
        if parent is None:
            parent = pubsub_singleton.query('registry/ui/instance', default=None)
        super().__init__(parent=parent)
        self.setObjectName("signal_record_config_dialog")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)

        self._w = StatisticsRecordConfigWidget(self, config)
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
        self.setWindowTitle(N_('Configure statistics recording'))
        self._log.info('open')
        self.open()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        self._log.info('finished: %d', value)

        if value == QtWidgets.QDialog.DialogCode.Accepted:
            config = self._w.config()
            self.config_changed.emit(config)
            if not self._skip_default_actions:
                self._log.info('finished: accept - start recording')
                config = config_update(config, count=StatisticsRecordConfigDialog.count)
                StatisticsRecordConfigDialog.count += 1
                pubsub_singleton.publish('registry/StatisticsRecord/actions/!start', config)
        else:
            if not self._skip_default_actions:
                self._log.info('finished: reject - abort recording')
                pubsub_singleton.publish('registry/app/settings/statistics_stream_record', False)
        self.close()

    @staticmethod
    def on_cls_action_show():
        StatisticsRecordConfigDialog(is_action_show=True)
