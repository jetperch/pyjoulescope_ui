# Copyright 2018-2023 Jetperch LLC
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

from joulescope_ui import pubsub_singleton, N_, get_topic_name, get_instance, \
    tooltip_format, CAPABILITIES, Metadata, __version__
from joulescope_ui.pubsub import UNDO_TOPIC, REDO_TOPIC
from joulescope_ui.pubsub_aggregator import PubsubAggregator
from joulescope_ui.shortcuts import Shortcuts
from joulescope_ui.widgets import *   # registers all built-in widgets
from joulescope_ui import logging_util
from joulescope_ui.reporter import create as reporter_create
from joulescope_ui.styles.manager import style_settings
from joulescope_ui.process_monitor import ProcessMonitor
from joulescope_ui import software_update
from joulescope_ui.ui_util import show_in_folder
from joulescope_ui import urls
from joulescope_ui.dev_signal_buffer_source import DevSignalBufferSource
from PySide6 import QtCore, QtGui, QtWidgets
import PySide6QtAds as QtAds
from .error_window import ErrorWindow
from .help_ui import HelpHtmlMessageBox
from joulescope_ui.widgets.report_issue import ReportIssueDialog
from joulescope_ui.disk_monitor import DiskMonitor
from joulescope_ui.error_dialog import ErrorMessageBox
from .exporter import ExporterDialog   # register the exporter
from .jls_source import JlsSource      # register the source
from .resources import load_resources, load_fonts
from joulescope_ui.devices.jsdrv.jsdrv_wrapper import JsdrvWrapper
from .styles import StyleManager
from .app import App
# from .mem_leak_debugger import MemLeakDebugger
from .paths import Paths
from .view import View  # registers the view manager
import joulescope_ui.plugins   # register plugins
import appnope
import logging
import os
import shutil
import sys
import webbrowser


_software_update = None
_config_clear = None
_log = logging.getLogger(__name__)
_UI_WINDOW_TITLE = 'Joulescope'
_JLS_WINDOW_TITLE = 'Joulescope file viewer'
_DEVELOPER_WIDGETS = [
    DebugWidget,
    PublishSpyWidget,
]


_SETTINGS = {
    'changelog_version_show': {
        'dtype': 'str',
        'brief': 'The version for the last changelog show',
        'default': None,
        'flags': ['hide'],
    },
    'status_bar': {
        'dtype': 'str',
        'brief': N_('The UI status bar display mode'),
        'detail': N_('''\
            This setting controls the amount of detail shown on
            the status bar at the bottom of the UI window.
            You should usually leave this set to "normal" unless
            you want more detail concerning the UI internal operation.'''),
        'options': [
            ['normal', N_('Normal')],
            ['troubleshoot', N_('Troubleshoot')],
        ],
        'default': 'normal',
    },
    'developer': {
        'dtype': 'bool',
        'brief': N_('Enable developer mode.'),
        'default': False,
    },
}


_PUBSUB_UTILIZATION_TOOLTIP = tooltip_format(
    N_('PubSub utilization'),
    N_("""\
    Display the number of actions processed by the
    publish-subscribe broker in each second."""))


_CPU_UTILIZATION_TOOLTIP = tooltip_format(
    N_('CPU utilization'),
    N_("""\
    Display the CPU utilization by this application and
    the total CPU utilization by all applications.
    The value is displayed in percent."""))


_MEMORY_UTILIZATION_TOOLTIP = tooltip_format(
    N_('Memory utilization'),
    N_("""\
    Display the memory (RAM) utilization by this application
    and by all applications.
    The value is displayed in percent."""))


class QResyncEvent(QtCore.QEvent):
    """An event containing a request for pubsub.process."""
    EVENT_TYPE = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())

    def __init__(self):
        super().__init__(self.EVENT_TYPE)

    def __str__(self):
        return 'QResyncEvent()'

    def __len__(self):
        return 0


def _menu_setup(parent, d):
    def _publish_factory(value):
        return lambda checked=False: pubsub_singleton.publish(*value)

    k = {}
    for name_safe, name, value in d:
        if name_safe.endswith('_menu'):
            menu = QtWidgets.QMenu(parent)
            menu.setTitle(name)
            parent.addAction(menu.menuAction())
            w = [menu, _menu_setup(menu, value)]
        else:
            action = QtGui.QAction(parent)
            action.setText(name)
            if callable(value):
                action.triggered.connect(value)
            else:
                action.triggered.connect(_publish_factory(value))
            parent.addAction(action)
            w = [action, None]
        k[name_safe] = w
    return k


def _device_factory_add():
    # pubsub_singleton.register(DevSignalBufferSource())
    jsdrv = JsdrvWrapper()
    pubsub_singleton.register(jsdrv, 'jsdrv')
    topic = get_topic_name(jsdrv)
    pubsub_singleton.process()
    pubsub_singleton.publish(f'{topic}/actions/mem/!add', 1)  # use singleton memory buffer
    pubsub_singleton.process()


def _device_factory_finalize():
    _log.info('_device_factory_finalize enter')
    factories = pubsub_singleton.query(f'registry_manager/capabilities/{CAPABILITIES.DEVICE_FACTORY}/list')
    for factory in factories:
        _log.info('_device_factory_finalize %s', factory)
        topic = f'registry/{factory}/actions/!finalize'
        pubsub_singleton.publish(topic, None)
    pubsub_singleton.process()
    _log.info('_device_factory_finalize done')


class MainWindow(QtWidgets.QMainWindow):

    EVENTS = {
        'blink_slow': Metadata('bool', 'Periodic slow blink signal (0.5 Hz).', flags=['ro', 'skip_undo']),
        'blink_medium': Metadata('bool', 'Periodic medium blink signal (1 Hz).', flags=['ro', 'skip_undo']),
        'blink_fast': Metadata('bool', 'Periodic fast blink signal (2 Hz).', flags=['ro', 'skip_undo']),
    }

    def __init__(self, filename=None, is_config_load=False):
        self._log = logging.getLogger(__name__)
        self._filename = filename
        self._resync_event = None
        super(MainWindow, self).__init__()
        self.setWindowTitle(_UI_WINDOW_TITLE if filename is None else _JLS_WINDOW_TITLE)
        self._dialog = None
        self._pubsub = pubsub_singleton
        self._pubsub_process_count_last = self._pubsub.process_count
        self._shortcuts = Shortcuts(self)
        self.SETTINGS = style_settings(N_('UI'))
        for key, value in _SETTINGS.items():
            self.SETTINGS[key] = value
        self._app = App().register(mode='normal' if filename is None else 'file_viewer')
        self._paths = Paths().register()
        self.resize(800, 600)
        self._icon = QtGui.QIcon()
        self._icon.addFile(u":/icon_64x64.ico", QtCore.QSize(), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(self._icon)

        self._blink_count = 0
        self._blink_timer = None

        # Create the central widget with horizontal layout
        self._central_widget = QtWidgets.QWidget(self)
        self._central_widget.setObjectName('central_widget')
        self.setCentralWidget(self._central_widget)
        size_policy_xx = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._central_widget.setSizePolicy(size_policy_xx)
        self._central_layout = QtWidgets.QHBoxLayout()
        self._central_layout.setObjectName('central_layout')
        self._central_layout.setSpacing(0)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_widget.setLayout(self._central_layout)

        self._status_bar = QtWidgets.QStatusBar(self)
        self._status_bar.setObjectName('status_bar')
        self.setStatusBar(self._status_bar)

        QtAds.CDockManager.setConfigFlags(
            0
            | QtAds.CDockManager.DockAreaHasCloseButton
            | QtAds.CDockManager.DockAreaHasUndockButton
            | QtAds.CDockManager.DockAreaHasTabsMenuButton
            | QtAds.CDockManager.ActiveTabHasCloseButton
            | QtAds.CDockManager.FloatingContainerHasWidgetTitle
            | QtAds.CDockManager.XmlAutoFormattingEnabled
            | QtAds.CDockManager.OpaqueSplitterResize
            # | QtAds.CDockManager.OpaqueUndocking
            | QtAds.CDockManager.FocusHighlighting
            | QtAds.CDockManager.MiddleMouseButtonClosesTab
        )
        self._dock_manager = QtAds.CDockManager(self._central_widget)
        self._dock_manager.setStyleSheet('')
        self._dock_manager.setSizePolicy(size_policy_xx)
        self._central_layout.addWidget(self._dock_manager)

        self._pubsub_utilization = QtWidgets.QLabel(self._status_bar)
        self._pubsub_utilization.setToolTip(_PUBSUB_UTILIZATION_TOOLTIP)
        self._status_bar.addPermanentWidget(self._pubsub_utilization)
        self._cpu_utilization = QtWidgets.QLabel(self._status_bar)
        self._cpu_utilization.setToolTip(_CPU_UTILIZATION_TOOLTIP)
        self._status_bar.addPermanentWidget(self._cpu_utilization)
        self._mem_utilization = QtWidgets.QLabel(self._status_bar)
        self._mem_utilization.setToolTip(_MEMORY_UTILIZATION_TOOLTIP)
        self._status_bar.addPermanentWidget(self._mem_utilization)

        self._pubsub.register(self, 'ui', parent=None)
        self._style_manager = StyleManager()
        self._pubsub.register(self._style_manager, 'style')
        self._pubsub.subscribe('registry/app/settings/signal_stream_record',
                               get_instance('SignalRecord').on_cls_action_toggled, ['pub'])
        self._pubsub.subscribe('registry/app/settings/statistics_stream_record',
                               get_instance('StatisticsRecord').on_cls_action_toggled, ['pub'])

        self._pubsub.publish('registry/view/actions/!ui_connect', {
            'ui': self,
            'dock_manager': self._dock_manager,
        })
        self._pubsub.process()

        if filename is not None:
            if not is_config_load:
                self._pubsub.publish('registry/view/actions/!add', 'view:file')
                self._pubsub.publish('registry/view:file/settings/name', N_('File'))
            else:
                self._pubsub.publish('registry/view/settings/active', None)
                self._pubsub.register(View(), 'view:file')
                self._pubsub.publish('registry/view/settings/active', 'view:file')
            source = self.on_action_file_open(filename)
            self._pubsub.publish('registry/app/settings/defaults/signal_buffer_source', source)
            self._center(resize=True)

        else:
            _device_factory_add()
            # open JLS sources
            for source_unique_id in self._pubsub.query('registry/JlsSource/instances', default=[]):
                self._pubsub.register(JlsSource(), source_unique_id)

            if not is_config_load:
                self._pubsub.publish('registry/view/actions/!add', 'view:multimeter')
                self._pubsub.publish('registry/view:multimeter/settings/name', N_('Multimeter'))
                self._pubsub.publish('registry/view/actions/!add', 'view:oscilloscope')
                self._pubsub.publish('registry/view:oscilloscope/settings/name', N_('Oscilloscope'))
                self._pubsub.publish('registry/view/actions/!add', 'view:file')
                self._pubsub.publish('registry/view:file/settings/name', N_('File'))
            else:
                # open views
                view_active = self._pubsub.query('registry/view/settings/active')
                if view_active is None:
                    self._log.warning(f'view_active is None, use "view:multimeter"')
                    view_active = 'view:multimeter'
                self._pubsub.publish('registry/view/settings/active', None)
                for view_unique_id in self._pubsub.query('registry/view/instances'):
                    self._pubsub.register(View(), view_unique_id)

        help_menu = ['help_menu', N_('&Help'), [
                ['getting_started', N_('Getting Started'), ['registry/help_html/actions/!show', 'getting_started']],
                ['users_guide', N_("User's Guide"), ['registry/ui/actions/!url_open', urls.UI_USERS_GUIDE]],
                ['changelog', N_('Changelog'), ['registry/help_html/actions/!show', 'changelog']],
                ['report_issue', N_('Report Issue'), ['registry/report_issue/actions/!show', self]],
                ['view_logs', N_('View logs...'), ['registry/ui/actions/!view_logs', None]],
                ['credits', N_('Credits'), ['registry/help_html/actions/!show', 'credits']],
                ['about', N_('About'), ['registry/help_html/actions/!show', 'about']],
            ]]

        if filename is None:
            # Create the singleton sidebar widget
            self._side_bar = SideBar(self._central_widget)
            self._side_bar.register()
            self._central_layout.insertWidget(0, self._side_bar)

            self._signal_record_status = RecordStatusWidget(self, 'SignalRecord')
            self._pubsub.register(self._signal_record_status, 'SignalRecord:0', parent='ui')
            self._status_bar.addPermanentWidget(self._signal_record_status)

            self._statistics_record_status = RecordStatusWidget(self, 'StatisticsRecord')
            self._pubsub.register(self._statistics_record_status, 'StatisticsRecord:0', parent='ui')
            self._status_bar.addPermanentWidget(self._statistics_record_status)

            self._menu_bar = QtWidgets.QMenuBar(self)
            self._menu_items = _menu_setup(self._menu_bar, [
                ['file_menu', N_('&File'), [
                    ['open', N_('Open'), ['registry/ui/actions/!file_open_request', '']],
                    ['open_recent_menu', N_('Open recent'), []],  # dynamically populated from MRU
                    # '&Preferences': self.on_preferences,
                    ['exit_cfg', N_('Clear config and exit'), ['registry/ui/actions/!close', {'config_clear': True}]],
                    ['exit', N_('Exit'), ['registry/ui/actions/!close', '']],
                ]],
                ['view_menu', N_('View'), []],     # dynamically populated from available views
                ['widgets_menu', N_('Widgets'), []],  # dynamically populated from available widgets
                ['tools_menu', N_('Tools'), [
                    ['accum_clear', N_('Clear Accumulators'), ['registry/ui/actions/!accum_clear', None]]
                ]],
                help_menu,
            ])
            self._view_menu_group = QtGui.QActionGroup(self._menu_items['view_menu'][0])
            self._view_menu_group.setExclusive(True)
            self.setMenuBar(self._menu_bar)
            self._pubsub.subscribe('registry/paths/settings/mru_files', self._on_mru, flags=['pub', 'retain'])

            self._pubsub.subscribe('registry_manager/capabilities/view.object/list',
                                   self._on_change_views, flags=['pub', 'retain'])
            self._pubsub.subscribe('registry/view/settings/active', self._on_change_views, flags=['pub'])
            self._pubsub.subscribe('registry_manager/capabilities/widget.class/list',
                                   self._on_change_widgets, flags=['pub', 'retain'])

            if not is_config_load:
                self._pubsub.publish('registry/view/settings/active', 'view:file')
                self._center(resize=True)

                self._pubsub.publish('registry/view/settings/active', 'view:oscilloscope')
                self._pubsub.publish('registry/view/actions/!widget_open', {
                    'value': 'WaveformWidget',
                    'kwargs': {'source_filter': 'JsdrvStreamBuffer:001'},
                })
                self._center(resize=True)

                self._pubsub.publish('registry/view/settings/active', 'view:multimeter')
                self._pubsub.publish('registry/view/actions/!widget_open', 'MultimeterWidget')
                self.resize(580, 560)
                self._center(resize=False)
            else:
                self._pubsub.publish('registry/view/settings/active', view_active)
        else:
            self._menu_bar = QtWidgets.QMenuBar(self)
            self._menu_items = _menu_setup(self._menu_bar, [
                ['file_menu', N_('&File'), [
                    ['info', N_('Info'), ['registry/view/actions/!widget_open', 'JlsInfoWidget']],
                    ['settings', N_('Settings'), ['registry/view/actions/!widget_open', {
                        'value': 'registry/settings',
                        'floating': True,
                    }]],
                    ['exit_cfg', N_('Clear config and exit'), ['registry/ui/actions/!close', {'config_clear': True}]],
                    ['exit', N_('Exit'), ['registry/ui/actions/!close', '']],
                ]],
                help_menu,
            ])
            self.setMenuBar(self._menu_bar)

        self._pubsub.publish('registry/style/settings/enable', True)
        self._pubsub.publish('registry/style/actions/!render', None)
        self._pubsub.process()

        self._process_monitor = ProcessMonitor(self)
        self._process_monitor.update.connect(self._on_process_monitor)

        self._shortcuts.add(QtGui.QKeySequence.Undo, UNDO_TOPIC, None)
        self._shortcuts.add(QtGui.QKeySequence.Redo, REDO_TOPIC, None)
        self._shortcuts.add(QtCore.Qt.Key_Space, 'registry/app/settings/signal_stream_enable', '__toggle__')

        if filename is None:
            self.setAcceptDrops(True)
        self.show()

        self._pubsub.publish(UNDO_TOPIC, 'clear', defer=True)
        self._pubsub.publish(REDO_TOPIC, 'clear', defer=True)

        # self._mem_leak_debugger = MemLeakDebugger(self)
        # self._side_bar.on_cmd_show(1)
        if self._pubsub.query('registry/app/settings/software_update_check'):
            self._software_update_thread = software_update.check(
                callback=self._do_cbk,
                path=self._pubsub.query('common/settings/paths/update'),
                channel=self._pubsub.query('registry/app/settings/software_update_channel'))

        # display changelog on version change
        topic = f'{self.topic}/settings/changelog_version_show'
        changelog_version_show = self._pubsub.query(topic, default=None)
        if filename is not None:
            pass  # show nothing
        elif changelog_version_show is None:
            self._pubsub.publish(topic, __version__)
            self._pubsub.publish('registry/help_html/actions/!show', 'getting_started')
        elif __version__ != self._pubsub.query(topic, default=None):
            self._pubsub.publish(topic, __version__)
            self._pubsub.publish('registry/help_html/actions/!show', 'changelog')
        self.resync_request()

        self._fuse_aggregator = PubsubAggregator(self._pubsub, 'device.object', 'settings/fuse_engaged', any,
                                                 'registry/app/settings/fuse_engaged')

        self._pubsub.register(DiskMonitor)
        self._pubsub.register(DiskMonitor(), 'DiskMonitor:0')

        self._blink_timer = QtCore.QTimer()
        self._blink_timer.timeout.connect(self._on_blink_timer)
        self._blink_timer.start(250)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            txt = event.mimeData().text()
            if txt.startswith('file:///') and txt.endswith('.jls'):
                event.acceptProposedAction()

    def dropEvent(self, event):  # QDropEvent
        if event.mimeData().hasText():
            txt = event.mimeData().text()
            if txt.startswith('file:///') and txt.endswith('.jls'):
                self._pubsub.publish(f'{get_topic_name(self)}/actions/!file_open', txt[8:])
                event.acceptProposedAction()

    def on_setting_status_bar(self, value):
        visible = (value != 'normal')
        self._pubsub_utilization.setVisible(visible)
        self._cpu_utilization.setVisible(visible)
        self._mem_utilization.setVisible(visible)

    def on_setting_developer(self, value):
        if bool(value):
            for cls in _DEVELOPER_WIDGETS:
                self._pubsub.register(cls)
        else:
            for cls in _DEVELOPER_WIDGETS:
                if getattr(cls, 'pubsub_is_registered', False):
                    try:
                        self._pubsub.query(cls.topic)
                        for instance in self._pubsub.query(f'{cls.topic}/instances'):
                            self._pubsub.publish('registry/view/actions/!widget_close', instance)
                        self._pubsub.unregister(cls, delete=True)
                    except KeyError:
                        pass

    def _center(self, resize=None):
        screen = self.screen()
        sz = screen.size()
        sw, sh = sz.width(), sz.height()
        if resize == True:
            w, h = int(sw * 0.8), int(sh * 0.8)
        elif resize == 'preferred':
            sz = self.sizeHint()
            w, h = sz.width(), sz.height()
        else:
            w, h = self.width(), self.height()
        x, y = (sw - w) // 2, (sh - h) // 2
        self.setGeometry(x, y, w, h)

    def on_setting_stylesheet(self, value):
        self.setStyleSheet(value)

    def _do_cbk(self, v):
        self._pubsub.publish('registry/ui/callbacks/!software_update', v)

    def on_callback_software_update(self, value):
        update_thread, self._software_update_thread = self._software_update_thread, None
        if update_thread is not None:
            update_thread.join()
        if not isinstance(value, dict):
            return
        self._log.info('Display software update available dialog')
        self._pubsub.publish('registry/software_update/actions/!show', value)

    def _on_process_monitor(self, obj):
        x1 = obj['cpu_utilization']['self']
        x2 = obj['cpu_utilization']['all']
        self._cpu_utilization.setText(f'CPU: {x1:.1f}%, {x2:.1f}%')
        x1 = obj['memory_utilization']['self'] / 1e6
        x2 = obj['memory_utilization_percent']['self']
        x3 = obj['memory_utilization_percent']['used']
        self._mem_utilization.setText(f'Mem: {x1:.0f} MB {x2:.0f}%, {x3:.0f}%')

    def _on_blink_timer(self):
        topic = get_topic_name(self)
        self._blink_count = (self._blink_count + 1) & 0x07
        self._pubsub.publish(f'{topic}/events/blink_fast', (self._blink_count & 1) != 0)
        if (self._blink_count & 1) == 0:
            self._pubsub.publish(f'{topic}/events/blink_medium', (self._blink_count & 2) != 0)
        if (self._blink_count & 3) == 0:
            self._pubsub.publish(f'{topic}/events/blink_slow', (self._blink_count & 4) != 0)
            c = self._pubsub.process_count
            self._pubsub_utilization.setText(f'PubSub: {c - self._pubsub_process_count_last}')
            self._pubsub_process_count_last = c

    def _on_mru(self, value):
        _, items = self._menu_items['file_menu']
        open_recent_list = items['open_recent_menu']
        menu, _ = open_recent_list
        menu.clear()
        if not len(value):
            menu.menuAction().setVisible(False)
            return
        menu.menuAction().setVisible(True)
        menu_items = []
        topic = get_topic_name(self)
        for idx, mru in enumerate(value):
            menu_items.append([str(idx), mru, [f'{topic}/actions/!file_open', mru]])
        open_recent_list[1] = _menu_setup(menu, menu_items)

    def _on_change_views(self, value):
        value = self._pubsub.query('registry/view/instances')
        active_view = self._pubsub.query('registry/view/settings/active', default=None)
        menu, k = self._menu_items['view_menu']
        for action, _ in k.values():
            self._view_menu_group.removeAction(action)
        menu.clear()

        menu_items = []
        for unique_id in value:
            name = self._pubsub.query(f'registry/{unique_id}/settings/name', default=unique_id)
            menu_items.append([unique_id, name, ['registry/view/settings/active', unique_id]])
        m = _menu_setup(menu, menu_items)

        m['_separator1'] = (None, menu.addSeparator())
        manage_action = QtGui.QAction(N_('Manage'))
        manage_action.triggered.connect(self._on_view_manage)
        menu.addAction(manage_action)
        m['_hello'] = (manage_action, None)

        self._menu_items['view_menu'][1] = m

        k = self._menu_items['view_menu'][1]  # map of children
        for view_unique_id, (action, _) in k.items():
            if view_unique_id[0] == '_':
                continue
            action.setCheckable(True)
            action.setChecked(view_unique_id == active_view)
            self._view_menu_group.addAction(action)

    def _on_view_manage(self, checked=False):
        self._log.info('View Manage')
        dialog = ViewManagerDialog(self)
        dialog.finished.connect(lambda x: self._on_change_views(None))

    def _on_change_widgets(self, value):
        menu, _ = self._menu_items['widgets_menu']
        menu.clear()
        menu_items = []
        for unique_id in value:
            name = self._pubsub.query(f'registry/{unique_id}/settings/name', default=unique_id)
            menu_items.append([unique_id, name, ['registry/view/actions/!widget_open', unique_id]])
        self._menu_items['widgets_menu'][1] = _menu_setup(menu, menu_items)

    def event(self, event: QtCore.QEvent):
        if event.type() == QResyncEvent.EVENT_TYPE:
            event.accept()
            self._resync_event = None
            self._pubsub.process()
            return True
        else:
            return super(MainWindow, self).event(event)

    def resync_request(self):
        # safely resynchronize pubsub processing to the main Qt event thread
        if self._resync_event is None:
            self._resync_event = QResyncEvent()
            QtCore.QCoreApplication.postEvent(self, self._resync_event)

    def on_action_file_open_request(self):
        """Request file open; prompt user to select file."""
        self._log.info('file_open_request')
        path = pubsub_singleton.query('registry/paths/settings/path')
        self._dialog = QtWidgets.QFileDialog(self, N_('Select file to open'), path)
        self._dialog.setNameFilter('Joulescope Data (*.jls)')
        self._dialog.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        self._dialog.updateGeometry()
        self._dialog.open()
        self._dialog.finished.connect(self._on_file_open_request_dialog_finished)

    def _on_file_open_request_dialog_finished(self, result):
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            files = self._dialog.selectedFiles()
            if files and len(files) == 1:
                path = files[0]
                self._pubsub.publish(f'{get_topic_name(self)}/actions/!file_open', path, defer=True)
            else:
                self._log.info('file_open invalid files: %s', files)
        else:
            self._log.info('file_open cancelled')

    def on_action_file_open(self, path):
        """Open the specified file."""
        self._log.info('file_open %s', path)
        topic = f'registry_manager/capabilities/{CAPABILITIES.SIGNAL_BUFFER_SOURCE}/list'
        sources_start = self._pubsub.query(topic)
        self._pubsub.publish(f'registry/JlsSource/actions/!open', path)
        sources_end = self._pubsub.query(topic)
        source = sources_end[-1]
        if source in sources_start:
            self._log.warning('Could not determine added source')
            source = 'JlsSource'
        name = os.path.splitext(os.path.basename(path))[0]
        self._pubsub.publish(
            'registry/view/actions/!widget_open',
            {
                'value': 'WaveformWidget',
                'kwargs': {
                    'name': name,
                    'source_filter': source,
                    'on_widget_close_actions': [[f'{get_topic_name(source)}/actions/!close', None]],
                 }
            })
        return source

    def on_action_accum_clear(self, value):
        sources = pubsub_singleton.query('registry_manager/capabilities/statistics_stream.source/list')
        for source in sources:
            pubsub_singleton.publish(f'{get_topic_name(source)}/actions/!accum_clear', value)

    def on_action_view_logs(self):
        path = pubsub_singleton.query('common/settings/paths/log')
        self._log.info('view logs: %s', path)
        show_in_folder(path)

    def on_action_url_open(self, value):
        webbrowser.open_new_tab(value)

    def on_action_error_msg(self, value):
        self._log.info('error_msg %s', value)
        ErrorMessageBox(self, value)

    def on_action_status_msg(self, value):
        self._log.info('status_msg %s', value)
        self._status_bar.showMessage(value, timeout=3000)

    def closeEvent(self, event):
        pubsub = self._pubsub
        self._log.info('closeEvent() start')
        self._blink_timer.stop()
        if self._filename is not None:
            pubsub.publish('registry/view/actions/!widget_close', '*')
        pubsub.publish('registry/app/settings/signal_stream_record', False)
        pubsub.publish('registry/app/settings/statistics_stream_record', False)
        pubsub.publish('registry/view/actions/!ui_disconnect', None)
        pubsub.publish('registry/JlsSource/actions/!finalize', None)
        event.accept()
        self._log.info('closeEvent() done')

    def on_action_close(self, value):
        global _software_update, _config_clear
        if isinstance(value, dict):
            _software_update = value.get('software_update')
            _config_clear = value.get('config_clear')
        # call self.close() on the Qt Event loop later
        QtCore.QMetaObject.invokeMethod(self, 'close', QtCore.Qt.ConnectionType.QueuedConnection)


def _finalize():
    if _config_clear:
        _log.info('finalize: config clear')
        path = pubsub_singleton.query('common/settings/paths/styles')
        if len(path) and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        pubsub_singleton.config_clear()


def _opengl_config(renderer):
    renderer_map = {
        'desktop': QtCore.Qt.AA_UseDesktopOpenGL,
        'angle': QtCore.Qt.AA_UseOpenGLES,
        'software': QtCore.Qt.AA_UseSoftwareOpenGL,
    }
    renderer_qt = renderer_map.get(renderer, None)
    if renderer_qt is not None:
        _log.info('OpenGL render map: %s', renderer)
        QtCore.QCoreApplication.setAttribute(renderer_qt)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    fmt = QtGui.QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    if renderer == 'software':
        fmt.setVersion(2, 1)
    else:
        fmt.setVersion(3, 3)
    fmt.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)


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
    ui = None
    try:
        logging_util.preconfig()
        pubsub_singleton.register(HelpHtmlMessageBox, 'help_html')
        pubsub_singleton.register(ReportIssueDialog, 'report_issue')
        # pubsub_singleton.publish(PUBSUB_TOPICS.PUBSUB_APP_NAME, N_('Joulescope UI'))
        log_path = pubsub_singleton.query('common/settings/paths/log')
        logging_util.config(log_path, stream_log_level=log_level, file_log_level=file_log_level)

        pubsub_singleton.process()
        if filename is not None:
            pubsub_singleton.config_filename = 'joulescope_ui_file_config.json'
        is_config_load = False
        try:
            is_config_load = pubsub_singleton.load()
        except Exception:
            _log.exception('pubsub load failed')

        opengl_renderer = pubsub_singleton.query('registry/app/settings/opengl', default='desktop')
        _opengl_config(opengl_renderer)
        app = QtWidgets.QApplication([])
        resources = load_resources()
        fonts = load_fonts()
        appnope.nope()

        ui = MainWindow(filename=filename, is_config_load=is_config_load)
        pubsub_singleton.notify_fn = ui.resync_request
        try:
            _log.info('app.exec start')
            rc = app.exec()
            _log.info('app.exec done')
        finally:
            if filename is None:
                _device_factory_finalize()
            _finalize()
        ui = None
        if not _config_clear:
            pubsub_singleton.save()

        try:
            if _software_update is not None:
                software_update.apply(_software_update)
        except Exception:
            print('could not apply software update')

    except Exception as ex:
        _log.exception('UI crash')
        logging_util.flush_all()
        if app is None:
            app = QtWidgets.QApplication([])
        path = reporter_create('crash', exception=ex)
        if ui is not None:
            ui.hide()
            ui.close()
        ui = ErrorWindow(report_path=path)
        app.exec()
        rc = 1

    _log.info('exit %s', rc)
    sys.exit(rc)
