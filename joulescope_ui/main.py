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
import PySide6QtAds as QtAds
from .capabilities import CAPABILITIES
from .error_window import ErrorWindow
from .help_ui import HelpHtmlMessageBox
from .pubsub import PubSub
from .resources import load_resources, load_fonts
from .joulescope_driver_adapter import DriverWrapper
import appnope
import ctypes
import logging
import os
import sys


class QResyncEvent(QtCore.QEvent):
    """An event containing a request for pubsub.process."""
    EVENT_TYPE = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())

    def __init__(self):
        QtCore.QEvent.__init__(self, self.EVENT_TYPE)

    def __str__(self):
        return 'QResyncEvent()'

    def __len__(self):
        return 0


def _menu_setup(pubsub, parent, d):
    def _publish_factory(pubsub, value):
        return lambda: pubsub.publish(*value)

    k = {}
    for name, value in d.items():
        name_safe = name.replace('&', '')
        if isinstance(value, dict):
            wroot = QtWidgets.QMenu(parent)
            wroot.setTitle(name)
            parent.addAction(wroot.menuAction())
            w = _menu_setup(pubsub, wroot, value)
            w['__root__'] = wroot
        else:
            w = QtGui.QAction(parent)
            w.setText(name)
            if callable(value):
                w.triggered.connect(value)
            else:
                w.triggered.connect(_publish_factory(pubsub, value))
            parent.addAction(w)
        k[name_safe] = w
    return k


class Flyout(QtWidgets.QWidget):

    def __init__(self, parent):
        super(Flyout, self).__init__(parent)
        self.setObjectName('side_bar_flyout')
        self.setGeometry(50, 0, 0, 100)
        self.setStyleSheet('QWidget {\n	background: #D0000000;\n}')
        self._layout = QtWidgets.QStackedLayout()
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._label = QtWidgets.QLabel()
        self._label.setWordWrap(True)
        self._label.setText('<html><body><p>Page 1</p><p>Lorem ipsum dolor sit amet, consectetuer adipiscing elit.</p></body></html>')
        self._layout.addWidget(self._label)
        self._visible = 0
        self.show()
        self.animations = []

    def animate(self, show):
        for a in self.animations:
            a.stop()
        self.animations.clear()
        x_start = self.width()
        x_end = 150 if show else 0
        print(f'animate {show}: {x_start} -> {x_end}')
        for p in [b'minimumWidth', b'maximumWidth']:
            a = QtCore.QPropertyAnimation(self, p)
            a.setDuration(500)
            a.setStartValue(x_start)
            a.setEndValue(x_end)
            a.setEasingCurve(QtCore.QEasingCurve.InOutQuart)
            a.start()
            self.animations.append(a)
        self._visible = show

    def on_cmd_show(self, value):
        if value == -1:
            value = 1 if self.isHidden() else 0
        if value == self._visible:
            return
        self.raise_()
        self.animate(value)

    def on_sidebar_geometry(self, r):
        width = self.width()
        g = self.geometry()
        self.setGeometry(r.right(), r.y(), width, r.height())
        print(f'{r}: {g} -> {self.geometry()}')
        self.repaint()


class SideBar(QtWidgets.QWidget):

    def __init__(self, parent):
        super(SideBar, self).__init__(parent)
        self.setObjectName('side_bar_icons')
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)

        # Create the flyout widget
        self._flyout = Flyout(parent)

        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self._playButton = QtWidgets.QPushButton(self)
        self._playButton.setObjectName('play')
        self._playButton.setProperty('blink', False)
        self._playButton.setCheckable(True)
        self._playButton.setFlat(True)
        self._playButton.setProperty('blink', False)
        self._playButton.setFixedSize(24, 24)
        self._layout.addWidget(self._playButton)

        self._recordButton = QtWidgets.QPushButton(self)
        self._recordButton.setObjectName('record')
        self._recordButton.setEnabled(True)
        self._recordButton.setProperty('blink', False)
        self._recordButton.setCheckable(True)
        self._recordButton.setFlat(True)
        self._recordButton.setFixedSize(24, 24)
        self._layout.addWidget(self._recordButton)

        self._recordStatisticsButton = QtWidgets.QPushButton(self)
        self._recordStatisticsButton.setObjectName('record_statistics')
        self._recordStatisticsButton.setEnabled(True)
        self._recordStatisticsButton.setProperty('blink', False)
        self._recordStatisticsButton.setCheckable(True)
        self._recordStatisticsButton.setFlat(True)
        self._recordStatisticsButton.setFixedSize(24, 24)
        self._layout.addWidget(self._recordStatisticsButton)

        self._spacer = QtWidgets.QSpacerItem(10, 0,
                                             QtWidgets.QSizePolicy.Minimum,
                                             QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        # todo implement fly-out widget

    def on_cmd_show(self, value):
        self._flyout.on_cmd_show(value)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._flyout.on_sidebar_geometry(self.geometry())


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, pubsub):
        self.pubsub = pubsub
        self._log = logging.getLogger(__name__)

        super(MainWindow, self).__init__()
        pubsub.register_instance(self, 'ui')
        self.resize(800, 600)
        icon = QtGui.QIcon()
        icon.addFile(u":/icon_64x64.ico", QtCore.QSize(), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)

        # Create the central widget with horizontal layout
        self._central_widget = QtWidgets.QWidget(self)
        self._central_widget.setObjectName('central_widget')
        self.setCentralWidget(self._central_widget)
        size_policy_xx = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        #self._central_widget.setSizePolicy(size_policy_xx)
        self._central_layout = QtWidgets.QHBoxLayout()
        self._central_layout.setObjectName('central_layout')
        self._central_layout.setSpacing(0)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_widget.setLayout(self._central_layout)

        # Create the singleton icon side-bar
        self._side_bar = SideBar(self._central_widget)
        pubsub.register_instance(self._side_bar, 'icon_side_bar')
        self._central_layout.addWidget(self._side_bar)

        self._dock_widget = QtWidgets.QWidget(self._central_widget)
        self._dock_widget.setObjectName('main_widget')
        self._dock_widget.setSizePolicy(size_policy_xx)
        self._central_layout.addWidget(self._dock_widget)

        self._status_bar = QtWidgets.QStatusBar(self)
        self._status_bar.setObjectName('status_bar')
        self.setStatusBar(self._status_bar)

        self._dock_layout = QtWidgets.QVBoxLayout(self._dock_widget)
        self._dock_layout.setContentsMargins(0, 0, 0, 0)
        self._dock_manager = QtAds.CDockManager(self._dock_widget)
        self._dock_layout.addWidget(self._dock_manager)

        # Create a dock widget with the title Label 1 and set the created label
        # as the dock widget content
        self.label = QtWidgets.QLabel()
        self.label.setText('Lorem ipsum dolor sit amet, consectetuer adipiscing elit.')
        self.dock_widget = QtAds.CDockWidget("Label 1")
        # self.dock_widget.setWindowTitle('Other')
        self.dock_widget.setWidget(self.label)
        self._dock_manager.addDockWidget(QtAds.TopDockWidgetArea, self.dock_widget)

        # Create an example editor
        self.te = QtWidgets.QPlainTextEdit()
        self.te.setPlaceholderText("Please enter your text here into this QPlainTextEdit...")
        self.dock_widget = QtAds.CDockWidget("Editor 1")
        # self.menuView.addAction(self.dock_widget.toggleViewAction())
        self._dock_manager.addDockWidget(QtAds.BottomDockWidgetArea, self.dock_widget)

        self._menu_bar = QtWidgets.QMenuBar(self)
        self._menu_items = _menu_setup(self.pubsub, self._menu_bar, {
            '&File': {
                # '&Open': self.on_recording_open,
                # 'Open &Recent': {},  # dynamically populated from MRU
                # '&Preferences': self.on_preferences,
                '&Exit': ['registry/ui/actions/!close', ''],
            },
            # '&Device': {},  # dynamically populated
            # '&View': {},    # dynamically populated from widgets
            # '&Tools': {
            #     '&Clear Accumulator': self._on_accumulators_clear,
            #     '&Record Statistics': self._on_record_statistics,
            # },
            '&Help': {
                '&Getting Started': ['registry/help_html/actions/!show', 'getting_started'],
                #'JS220 User\'s Guide': self._help_js220_users_guide,
                #'JS110 User\'s Guide': self._help_js110_users_guide,
                #'&View logs...': self._view_logs,
                'Changelog': ['registry/help_html/actions/!show', 'changelog'],
                '&Credits': ['registry/help_html/actions/!show', 'credits'],
                #'&About': self._help_about,
            }
        })
        self.setMenuBar(self._menu_bar)
        self._jsdrv = DriverWrapper(self.pubsub)

        self.show()
        self._side_bar.on_cmd_show(1)

    def event(self, event: QtCore.QEvent):
        if event.type() == QResyncEvent.EVENT_TYPE:
            event.accept()
            self.pubsub.process()
            return True
        else:
            return super(MainWindow, self).event(event)

    def resync_request(self):
        # safely resynchronize pubsub processing to the main Qt event thread
        event = QResyncEvent()
        QtCore.QCoreApplication.postEvent(self, event)

    def closeEvent(self, event):
        self._log.info('closeEvent()')
        # todo pubsub save
        self._jsdrv.finalize()
        return super(MainWindow, self).closeEvent(event)

    def on_action_close(self, value):
        self.close()


def pubsub_factory():
    pubsub = PubSub()
    pubsub.registry_initialize()
    for capability in CAPABILITIES:
        pubsub.register_capability(capability.value)
    return pubsub


def dpi_awareness_enable():
    try:
        log = logging.getLogger()
        log.info('Configure high DPI scaling')
        # https://doc.qt.io/qt-6/highdpi.html
        # https://vicrucann.github.io/tutorials/osg-qt-high-dpi/
        if sys.platform.startswith('win'):
            # https://learn.microsoft.com/en-us/windows/win32/api/shellscalingapi/ne-shellscalingapi-process_dpi_awareness
            # ctypes.windll.user32.SetProcessDPIAware()
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    except Exception:
        log.exception('while configuring high DPI scaling')


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
    # os.environ["QT_SCALE_FACTOR"] = "0.75"
    app = None
    try:
        logging_preconfig()
        pubsub = pubsub_factory()
        pubsub.register_class(HelpHtmlMessageBox, 'help_html')
        logging_config(pubsub.query('common/paths/log'), stream_log_level=log_level, file_log_level=file_log_level)
        #dpi_awareness_enable()
        app = QtWidgets.QApplication([])
        #if sys.platform.startswith('win'):
        #    app.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
        #    app.setAttribute(QtCore.Qt.AA_NativeWindows, True)
        resources = load_resources()
        fonts = load_fonts()
        appnope.nope()
        ui = MainWindow(pubsub)
        pubsub.notify_fn = ui.resync_request
        rc = app.exec_()
        del ui
        return rc
    except Exception:
        if app is None:
            app = QtWidgets.QApplication([])
        w = ErrorWindow()
        return app.exec_()

