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

from joulescope_ui import N_
from PySide6 import QtCore, QtGui, QtWidgets
import os
import sys
import zipfile
import logging


_TITLE = N_('ZIP Inspector')
_EXTENSION = '.zip'
_log = logging.getLogger(__name__)


class ListWidget(QtWidgets.QListWidget):

    selected = QtCore.Signal(str)

    def __init__(self, parent):
        self._items = []
        super().__init__(parent=parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.itemClicked.connect(self._on_item_clicked)

    def set_items(self, items, default=None):
        block = self.blockSignals(True)
        self.clear()
        self._items = list(items)
        for item in self._items:
            self.addItem(item)
        self.blockSignals(block)
        self.selected.emit(self.select(default))
        QtCore.QTimer.singleShot(0, self._on_timer)

    def _on_timer(self):
        self.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOn)
        width = self.sizeHintForColumn(0) + 2 * self.frameWidth()
        width += self.verticalScrollBar().width()
        self.setFixedWidth(width)
        self.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarAsNeeded)

    def select(self, item):
        if isinstance(item, str):
            try:
                index = self._items.index(item)
            except ValueError:
                index = 0
        elif isinstance(item, int):
            index = item
        else:
            index = 0
        if len(self._items):
            item = self._items[index]
            _log.info('select %d %s', index, item)
            self.setCurrentRow(index)
            return item
        else:
            return None

    @QtCore.Slot(QtWidgets.QListWidgetItem)
    def _on_item_clicked(self, item):
        item = self._items[self.currentRow()]
        self.selected.emit(item)


class ZipInspectorWidget(QtWidgets.QWidget):

    finished = QtCore.Signal()

    def __init__(self, parent, path):
        self._zipfile = None
        super().__init__(parent=parent)
        self._selected_zip = None
        self._selected_filename = None
        self._layout = QtWidgets.QGridLayout(self)
        self._zip_label = QtWidgets.QLabel(N_('ZIP File'), self)
        self._filename_label = QtWidgets.QLabel(N_('Filename'), self)
        self._contents_label = QtWidgets.QLabel(N_('Contents'), self)

        self._zip = ListWidget(self)
        self._filename = ListWidget(self)
        self._contents = QtWidgets.QPlainTextEdit(self)
        self._contents.setReadOnly(True)
        self._contents.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self._layout.addWidget(self._zip_label, 0, 0, 1, 1)
        self._layout.addWidget(self._filename_label, 0, 1, 1, 1)
        self._layout.addWidget(self._contents_label, 0, 2, 1, 1)
        self._layout.addWidget(self._zip, 1, 0, 1, 1)
        self._layout.addWidget(self._filename, 1, 1, 1, 1)
        self._layout.addWidget(self._contents, 1, 2, 1, 1)
        self._layout.setColumnStretch(2, 2)

        self._zip.selected.connect(self._on_zip)
        self._filename.selected.connect(self._on_filename)
        if os.path.isdir(path):
            self._path = path
            zip_default = None
        elif os.path.isfile(path) and path.endswith(_EXTENSION):
            self._path = os.path.dirname(path)
            zip_default = os.path.basename(path)
        self._zip_populate(self._path, zip_default)

    def finalize(self):
        zf, self._zipfile = self._zipfile, None
        if zf is not None:
            zf.close()

    def _zip_populate(self, dir_path, default=None):
        if default is not None and default.endswith(_EXTENSION):
            default = default[:-len(_EXTENSION)]
        filenames = sorted(os.listdir(dir_path), reverse=True)

        items = []
        for idx, filename in enumerate(filenames):
            if not filename.endswith(_EXTENSION):
                continue
            item = filename[:-len(_EXTENSION)]
            items.append(item)
        self._zip.set_items(items, default)

    @QtCore.Slot(str)
    def _on_zip(self, item):
        _log.info('on_zip %s', item)
        if self._zipfile is not None:
            self._zipfile.close()
        self._filename.clear()
        self._contents.clear()
        path = os.path.join(self._path, item + _EXTENSION)
        self._zipfile = zipfile.ZipFile(path, 'r')
        infos = {}
        for info in self._zipfile.infolist():
            infos[info.filename] = info
        self._filename.set_items(sorted(infos.keys()))

    @QtCore.Slot(str)
    def _on_filename(self, item):
        self._contents.clear()
        if self._zipfile is not None:
            with self._zipfile.open(item) as f:
                txt = f.read().decode('utf-8')
                self._contents.setPlainText(txt)

    def close(self):
        super().close()


class ZipInspectorDialog(QtWidgets.QDialog):

    def __init__(self, parent, path):
        super().__init__(parent=parent)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._zip_inspector = ZipInspectorWidget(self, path)
        self._layout.addWidget(self._zip_inspector)
        self._buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

        self.setWindowTitle(_TITLE)
        self.finished.connect(self._on_finish)

        screen = QtGui.QGuiApplication.screenAt(self.geometry().center())
        if screen is not None:
            geometry = screen.geometry()
            self.resize(0.9 * geometry.width(), 0.8 * geometry.height())
        else:
            self.resize(800, 600)
        self.open()

    @QtCore.Slot(int)
    def _on_finish(self, value):
        self._zip_inspector.finalize()
        self.close()
