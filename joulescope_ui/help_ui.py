# Copyright 2019-2022 Jetperch LLC
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
import markdown
import os
import re
from PySide6 import QtCore, QtWidgets
from . import frozen


_MY_PATH = os.path.dirname(os.path.abspath(__file__))
_APP_PATH = os.path.dirname(_MY_PATH)
_HELP_FILES = {
    'changelog': 'CHANGELOG.md',
    'credits': 'CREDITS.html',
    'getting_started': 'getting_started.html',
    'preferences': 'preferences.html',
}


def _load_filename(filename):
    for path in [['joulescope_ui'], []]:
        try:
            if frozen:
                bin_data = pkgutil.get_data(*path, filename)
            else:
                fname = os.path.join(_APP_PATH, *path, filename)
                with open(fname, 'rb') as f:
                    bin_data = f.read()
            return bin_data.decode('utf-8')
        except Exception:
            pass
    raise RuntimeError(f'Could not load file: {filename}')


def _load_help(pubsub, name):
    # style = cmdp.preferences['Appearance/__index__']['generator']['files']['style.html']
    style = ''
    filename = _HELP_FILES[name]
    html = _load_filename(filename)
    if filename.endswith('.md'):
        md = markdown.Markdown()
        html = md.convert(html)
    try:
        title = re.search(r'<title>(.*?)<\/title>', html)[1]
    except Exception:
        title = name
    html = html.format(style=style)
    return title, html


# Inspired by https://stackoverflow.com/questions/47345776/pyqt5-how-to-add-a-scrollbar-to-a-qmessagebox
class HelpHtmlMessageBox(QtWidgets.QMessageBox):
    """Display user-meaningful help information."""

    def __init__(self, pubsub, name):
        title, html = _load_help(pubsub, name)
        parent = None  # pubsub.query('registry/ui/instance')
        QtWidgets.QMessageBox.__init__(self, parent=parent)
        self.setObjectName("help_html_message_box")
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setObjectName("help_message_scroll")
        self._scroll.setWidgetResizable(True)
        self._content = QtWidgets.QWidget()
        self._scroll.setWidget(self._content)
        self._layout = QtWidgets.QVBoxLayout(self._content)
        self._label = QtWidgets.QLabel(html, self)
        self._label.setWordWrap(True)
        self._label.setOpenExternalLinks(True)
        self._layout.addWidget(self._label)
        self.layout().addWidget(self._scroll, 0, 0, 1, self.layout().columnCount())
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setWindowTitle(title)

    @staticmethod
    def on_cls_action_show(pubsub, topic, value):
        log = logging.getLogger(__name__ + f'.{value}')
        log.info('show start %s', value)
        dialog = HelpHtmlMessageBox(pubsub, value)
        log.info('show help dialog')
        dialog.exec_()
        log.info('show done')
