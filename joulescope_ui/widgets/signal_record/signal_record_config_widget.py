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
import copy
import logging
import os


_FILENAME_DEFAULT = '{timestamp}.jls'
_FILENAME_TOPIC = 'registry/SignalRecordConfigWidget/settings/filename'


def config_default() -> dict:
    """Get the default configuration.

    :return: The config dict.
    """
    config = {
        'filename': pubsub_singleton.query(_FILENAME_TOPIC, default=_FILENAME_DEFAULT),
        'location': pubsub_singleton.query('registry/paths/settings/path'),
        'sources': {},
        'notes': '',
    }

    sources_ids = pubsub_singleton.query(f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_STREAM_SOURCE}/list')
    for source_id in sorted(sources_ids):
        signals = {}
        config['sources'][source_id] = signals
        topic = get_topic_name(source_id)
        signal_ids = pubsub_singleton.enumerate(f'{topic}/settings/signals')
        for signal_id in signal_ids:
            enable_topic = f'{topic}/settings/signals/{signal_id}/enable'
            enabled = pubsub_singleton.query(enable_topic)
            signals[signal_id] = {
                'source_id': source_id,
                'signal_id': signal_id,
                'enabled': enabled,
                'selected': enabled,
                'enable_topic': enable_topic,
                'data_topic': f'{topic}/events/signals/{signal_id}/!data',
            }
    return config


def config_constrain(config: dict) -> dict:
    """Constrain the config to the available sources.

    :param config: The configuration.
    :return: The possibly modified configuration copy.
    """
    config = copy.deepcopy(config)
    default = config_default()
    sources_orig = config['sources']

    for source_id, signals in default['sources'].items():
        if source_id not in sources_orig:
            for d in signals.values():
                d['enabled'] = False
        else:
            for signal_id, d in signals.items():
                signal_orig = sources_orig[source_id].get(signal_id, {})
                d['enabled'] &= signal_orig.get('enabled', False)
                d['selected'] &= signal_orig.get('selected', False) & d['enabled']
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
    filename = config['filename']
    location = config['location']
    filename = filename_formatter(filename, count=count, **kwargs)
    config['filename'] = filename
    config['path'] = os.path.join(location, filename)
    return config


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

    def __init__(self, parent=None, config=None):
        self.SETTINGS = {}
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

        tooltip = filename_tooltip()
        self._filename_label = QtWidgets.QLabel(N_('Filename'), self)
        self._filename_label.setToolTip(tooltip)
        self._filename = QtWidgets.QLineEdit(self)
        self._filename.setText(self._config['filename'])
        self._filename.textChanged.connect(self._on_filename)
        self._filename.setToolTip(tooltip)
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
        self._location.setText(self._config['location'])
        self._location.textChanged.connect(self._on_location)
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

        self._signals_to_record_label = QtWidgets.QLabel(N_('Signals to record'), self)
        self._layout.addWidget(self._signals_to_record_label, self._row, 0, 1, 4)
        self._row += 1
        self._sources_add()

        self._notes_label = QtWidgets.QLabel(N_('Notes'), self)
        self._layout.addWidget(self._notes_label, self._row, 0, 1, 4)
        self._notes = QtWidgets.QTextEdit(self)
        self._notes.textChanged.connect(self._on_notes)
        self._layout.addWidget(self._notes, self._row + 4, 0, 4, 4)
        self._row += 5

    def _sources_add(self):
        sources = self._config['sources']
        for source_id in sorted(sources.keys()):
            topic = get_topic_name(source_id)
            name = pubsub_singleton.query(f'{topic}/settings/name')
            label = QtWidgets.QLabel(f'   {name}')
            self._layout.addWidget(label, self._row, 0, 1, 1)

            signal_widget = QtWidgets.QWidget()
            signal_layout = QtWidgets.QHBoxLayout(signal_widget)
            signal_layout.setContentsMargins(3, 3, 3, 3)
            signal_layout.setSpacing(3)
            self._layout.addWidget(signal_widget, self._row, 1, 1, 1)
            self._row += 1

            for signal_id, signals in sources[source_id].items():
                b = self._signal_pushbutton_factory(source_id, signal_id)
                signal_layout.addWidget(b)

            spacer = QtWidgets.QSpacerItem(0, 0,
                                           QtWidgets.QSizePolicy.Expanding,
                                           QtWidgets.QSizePolicy.Minimum)
            signal_layout.addItem(spacer)

    @QtCore.Slot(str)
    def _on_filename(self, txt):
        pubsub_singleton.publish(_FILENAME_TOPIC, txt)
        self._config['filename'] = txt

    @QtCore.Slot(str)
    def _on_location(self, txt):
        self._config['location'] = txt

    @QtCore.Slot(str)
    def _on_notes(self):
        self._config['notes'] = self._notes.toPlainText()

    def _signal_pushbutton_factory(self, source_id, signal_id):
        signal = self._config['sources'][source_id][signal_id]

        def on_toggled(checked):
            signal['selected'] = checked

        b = QtWidgets.QPushButton()
        b.setCheckable(True)
        b.setEnabled(signal['enabled'])
        b.setChecked(signal['selected'])
        b.setText(signal_id)
        b.setFixedSize(20, 20)
        b.toggled.connect(on_toggled)
        return b

    def config(self):
        return copy.deepcopy(self._config)

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

        self._w = SignalRecordConfigWidget(self, config=config)
        self._layout.addWidget(self._w)

        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)
        self.finished.connect(self._on_is_action_show_finished)

        self.resize(600, 400)
        self.setWindowTitle(N_('Configure signal recording'))
        self.open()

    @QtCore.Slot(int)
    def _on_is_action_show_finished(self, value):
        self._log.info('finished: %d', value)
        if value == QtWidgets.QDialog.DialogCode.Accepted:
            config = self._w.config()
            self.config_changed.emit(config)
            if not self._skip_default_actions:
                self._log.info('finished: accept - start recording')
                config = config_update(config, count=SignalRecordConfigDialog.count)
                SignalRecordConfigDialog.count += 1
                pubsub_singleton.publish('registry/SignalRecord/actions/!start', config)
        else:
            if not self._skip_default_actions:
                self._log.info('finished: reject - abort recording')
                pubsub_singleton.publish('registry/app/settings/signal_stream_record', False)
        self.close()

    @staticmethod
    def on_cls_action_show():
        SignalRecordConfigDialog()
