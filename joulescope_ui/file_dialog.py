# Copyright 2020 Jetperch LLC
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


from PySide6 import QtWidgets
import os


class FileDialog:
    """Select a file without blocking the main event loop.

    The "default" Qt selection dialogs do not service the timers in the
    main event loop, which causes sample drops and other bad behavior.
    This implementation keeps the main event loop running and also
    simplifies the API.
    """

    def __init__(self, parent, title, path, file_mode=None, filter_=None):
        if filter_ is None:
            filter_ = 'Joulescope Data (*.jls)'
        self.dialog = QtWidgets.QFileDialog(parent, title, path, filter_)
        file_mode = 'existingfile' if file_mode is None else file_mode.lower()
        if file_mode in [None, 'existingfile', 'existing']:
            self._mode = QtWidgets.QFileDialog.ExistingFile
            self.dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        elif file_mode in [None, 'existingfiles', 'files', 'multiple']:
            self._mode = QtWidgets.QFileDialog.ExistingFiles
            self.dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        elif file_mode in ['any', 'anyfile']:
            self._mode = QtWidgets.QFileDialog.AnyFile
            self.dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        else:
            raise RuntimeError(f'Invalid file mode {file_mode}')
        self.dialog.setFileMode(self._mode)
        self.dialog.updateGeometry()

    def setNameFilter(self, filter_str):
        self.dialog.setNameFilter(filter_str)

    def filenames(self):
        filenames = self.dialog.selectedFiles()
        if filenames is None or len(filenames) == 0:
            return []
        file_filter = str(self.dialog.selectedNameFilter())[:-1].split('*')[-1]
        fnames = []
        for f in filenames:
            f = str(f)
            if not f.endswith(file_filter):
                f = f'{f}{file_filter}'
            fnames.append(f)
        return fnames

    def exec_(self):
        if not self.dialog.exec_():
            return None
        filenames = self.filenames()
        if len(filenames) == 0:
            return None
        if self._mode in [QtWidgets.QFileDialog.ExistingFile, QtWidgets.QFileDialog.ExistingFiles]:
            for f in filenames:
                if not os.path.isfile(f):
                    raise RuntimeError(f'selected file does not exist: {f}')
        if self._mode == QtWidgets.QFileDialog.ExistingFiles:
            return filenames
        elif len(filenames) != 1:
            return None
        return filenames[0]
