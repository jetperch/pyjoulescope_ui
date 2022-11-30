# Copyright 2018-2022 Jetperch LLC
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

# https://stackoverflow.com/questions/11874767/real-time-plotting-in-while-loop-with-matplotlib
# https://wiki.qt.io/Gallery_of_Qt_CSS_Based_Styles

from joulescope_ui.logging_util import logging_preconfig, logging_config
from PySide6 import QtCore, QtGui, QtWidgets
from .error_window import ErrorWindow
from .pubsub import PubSub
from .resources import load_resources, load_fonts
from .joulescope_driver_adapter import DriverWrapper
import logging
import appnope


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, pubsub):
        self._pubsub = pubsub
        self._log = logging.getLogger(__name__)

        super(MainWindow, self).__init__()
        self.resize(800, 600)
        icon = QtGui.QIcon()
        icon.addFile(u":/icon_64x64.ico", QtCore.QSize(), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)

        self._menu_bar = QtWidgets.QMenuBar(self)
        self._jsdrv = DriverWrapper(self._pubsub)

        self.show()

    def closeEvent(self, event):
        self._log.info('closeEvent()')
        # todo pubsub save
        self._jsdrv.finalize()
        return super(MainWindow, self).closeEvent(event)


def run(log_level=None, file_log_level=None, filename=None):
    """Run the Joulescope UI application.

    :param log_level: The logging level for the stdout console stream log.
        The allowed levels are in :data:`joulescope_ui.logging_util.LEVELS`.
        None (default) disables console logging.
    :param file_log_level: The logging level for the file log.
        The allowed levels are in :data:`joulescope_ui.logging_util.LEVELS`.
        None (default) uses the configuration value.
    :param filename: The optional filename to display immediately.

    :return: 0 on success or error code on failure.
    """
    app = None
    try:
        logging_preconfig()
        pubsub = PubSub()
        logging_config(pubsub.query('common/paths/log'), stream_log_level=log_level, file_log_level=file_log_level)
        app = QtWidgets.QApplication([])
        resources = load_resources()
        fonts = load_fonts()
        appnope.nope()
        ui = MainWindow(pubsub)
        rc = app.exec_()
        del ui
        return rc
    except Exception:
        if app is None:
            app = QtWidgets.QApplication([])
        w = ErrorWindow()
        return app.exec_()

