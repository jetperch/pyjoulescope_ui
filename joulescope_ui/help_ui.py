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
import logging
import os
import re
from PySide2 import QtCore, QtWidgets
from . import frozen


MY_PATH = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.dirname(MY_PATH)


# Inspired by https://stackoverflow.com/questions/47345776/pyqt5-how-to-add-a-scrollbar-to-a-qmessagebox
class ScrollMessageBox(QtWidgets.QMessageBox):

    def __init__(self, msg, *args, **kwargs):
        QtWidgets.QMessageBox.__init__(self, *args, **kwargs)
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setObjectName("help_ui")
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


HELP_FILES = {
    'credits': 'CREDITS.html',
    'getting_started': 'getting_started.html',
    'preferences': 'preferences.html',
}


def load_help(name):
    filename = HELP_FILES[name]
    for path in [['joulescope_ui'], []]:
        try:
            if frozen:
                bin_data = pkgutil.get_data(*path, filename)
            else:
                fname = os.path.join(APP_PATH, *path, filename)
                with open(fname, 'rb') as f:
                    bin_data = f.read()
            return bin_data.decode('utf-8')
        except:
            pass
    raise RuntimeError(f'Could not load help {name}')


def display_help(parent, cmdp, name):
    style = cmdp.preferences['Appearance/__index__']['generator']['files']['style.html']
    logging.getLogger(__name__).info('display_help(%s)', name)
    html = load_help(name)
    title = re.search(r'<title>(.*?)<\/title>', html)[1]
    html = html.format(style=style)
    dialog = ScrollMessageBox(html, parent)
    dialog.setWindowTitle(title)
    dialog.exec_()
