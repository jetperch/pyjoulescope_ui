# Copyright 2019 Jetperch LLC
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


import pkgutil
import os
from PySide2 import QtCore, QtWidgets


MY_PATH = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.dirname(MY_PATH)


# Inspired by https://stackoverflow.com/questions/47345776/pyqt5-how-to-add-a-scrollbar-to-a-qmessagebox
class ScrollMessageBox(QtWidgets.QMessageBox):

    def __init__(self, msg, *args, **kwargs):
        QtWidgets.QMessageBox.__init__(self, *args, **kwargs)
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self.content = QtWidgets.QWidget()
        self._scroll.setWidget(self.content)
        self._layout = QtWidgets.QVBoxLayout(self.content)
        self._label = QtWidgets.QLabel(msg, self)
        self._label.setWordWrap(True)
        self._label.setOpenExternalLinks(True)
        self._layout.addWidget(self._label)
        self.layout().addWidget(self._scroll, 0, 0, 1, self.layout().columnCount())
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setStyleSheet("QScrollArea{min-width:600 px; min-height: 400px}")


def load_credits():
    fname = os.path.join(APP_PATH, 'CREDITS.html')
    if os.path.isfile(fname):
        with open(fname, 'rb') as f:
            bin_data = f.read()
    else:
        bin_data = pkgutil.get_data('joulescope_ui', 'CREDITS.html')
    return bin_data.decode('utf-8')


def load_getting_started():
    fname = os.path.join(APP_PATH, 'joulescope_ui', 'getting_started.html')
    if os.path.isfile(fname):
        with open(fname, 'rb') as f:
            bin_data = f.read()
    else:
        bin_data = pkgutil.get_data('joulescope_ui', 'getting_started.html')
    return bin_data.decode('utf-8')
