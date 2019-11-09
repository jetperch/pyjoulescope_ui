# Copyright 2018 Jetperch LLC
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

import os
import sys
from . import VERSION
import joulescope
from PySide2 import QtCore, QtGui, QtWidgets
from joulescope_ui.error_window import Ui_ErrorWindow
from joulescope_ui.main_window import Ui_mainWindow
from joulescope_ui.oscilloscope import Oscilloscope
from joulescope_ui.widgets import widget_register
from joulescope.usb import DeviceNotify
from joulescope_ui.data_recorder_process import DataRecorderProcess as DataRecorder
from joulescope.data_recorder import construct_record_filename  # DataRecorder
from joulescope_ui.recording_viewer_device import RecordingViewerDevice
from joulescope_ui.preferences_ui import PreferencesDialog
from joulescope_ui.update_check import check as software_update_check
from joulescope_ui.logging_util import logging_config
from joulescope_ui.oscilloscope.signal_statistics import si_format, html_format, three_sig_figs
from joulescope_ui.range_tool import RangeToolInvoke
from joulescope_ui import help_ui
from joulescope_ui import firmware_manager
from joulescope_ui.plugin_manager import PluginManager
from joulescope_ui.exporter import Exporter
from joulescope_ui.command_processor import CommandProcessor
from joulescope_ui.preferences_def import preferences_def
import io
import ctypes
import collections
import traceback
import time
import webbrowser
import logging
log = logging.getLogger(__name__)


STATUS_BAR_TIMEOUT = 5000  # milliseconds
USERS_GUIDE_URL = "https://download.joulescope.com/docs/JoulescopeUsersGuide/index.html"
FRAME_LIMIT_DELAY_MS = 30


ABOUT = """\
<html>
Joulescope UI version {ui_version}<br/> 
Joulescope driver version {driver_version}<br/>
<a href="https://www.joulescope.com">https://www.joulescope.com</a>

<pre>
Copyright 2018-2019 Jetperch LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
</pre>
</html>
"""


SOFTWARE_UPDATE = """\
<html>
<p>
A software update is available:<br/>
Current version = {current_version}<br/>
Available version = {latest_version}<br/>
</p>
<p><a href="{url}">Download</a> now.</p>
</html>
"""


TOOLTIP_NO_SOURCE = """\
No data source selected.
Connect a Joulescope or 
open a file."""


class ValueLabel(QtWidgets.QLabel):

    def __init__(self, parent=None, text=''):
        QtWidgets.QLabel.__init__(self, parent)
        self._text = text

    def set(self, value):
        self.setText('%s=%-8.2f' % (self._text, value))


def dict_update_recursive(tgt, src):
    """Merge src into tgt, overwriting as needed.

    :param tgt: The target dict.
    :param src: the source dict.
    """
    for key, value in src.items():
        if key in tgt and isinstance(tgt[key], dict) and isinstance(value, collections.Mapping):
            dict_update_recursive(tgt[key], value)
        else:
            tgt[key] = value


class DeviceDisable:

    def __str__(self):
        return "disable"

    def close(self):
        pass


class MainWindow(QtWidgets.QMainWindow):
    on_deviceNotifySignal = QtCore.Signal(object, object)
    _deviceOpenRequestSignal = QtCore.Signal(object)
    _deviceScanRequestSignal = QtCore.Signal()
    on_stopSignal = QtCore.Signal(int, str)
    on_statisticSignal = QtCore.Signal(object)
    on_xChangeSignal = QtCore.Signal(str, object)
    on_softwareUpdateSignal = QtCore.Signal(str, str, str)
    on_deviceEventSignal = QtCore.Signal(int, str)  # event, message
    on_markerStatisticsReadySignal = QtCore.Signal(object, object, object)

    on_progressValue = QtCore.Signal(int)
    on_progressMessage = QtCore.Signal(str)

    def __init__(self, app, device_name, cmdp):
        self._app = app
        self._device_scan_name = 'joulescope' if device_name is None else str(device_name)
        self._devices = []
        self._device = None
        self._streaming_status = None
        self._fps_counter = 0
        self._fps_time = None
        self._fps_limit_timer = QtCore.QTimer()
        self._fps_limit_timer.setSingleShot(True)
        self._fps_limit_timer.timeout.connect(self.on_fpsTimer)

        self._parameters = {}
        self._data_view = None  # created when device is opened
        self._recording = None  # created to record stream to JLS file
        self._accumulators = {
            'time': 0.0,
            'fields': {
                'charge': [0.0, 0.0],  # accumulated value, last stats value
                'energy': [0.0, 0.0],  # accumulated value, last stats value
            },
        }
        self._is_scanning = False
        self._progress_dialog = None

        self._cmdp = cmdp
        self._path = self._cmdp['General/data_path']
        self._plugins = PluginManager(self._cmdp)

        super(MainWindow, self).__init__()
        self.ui = Ui_mainWindow()
        self.ui.setupUi(self)

        # Central widget to keep top at top
        self.central_widget = QtWidgets.QWidget(self)
        self.central_widget.setMaximumWidth(1)
        self.setCentralWidget(self.central_widget)

        # todo convert multimeter and oscilloscope into profiles, allow other profiles
        self._oscilloscope_default_action = self.ui.menuView.addAction("Oscilloscope")
        self._oscilloscope_default_action.triggered.connect(self.on_oscilloscopeMenu)
        self.ui.menuView.addSeparator()

        self.on_deviceNotifySignal.connect(self.device_notify)
        self._deviceOpenRequestSignal.connect(self.on_deviceOpen, type=QtCore.Qt.QueuedConnection)
        self._deviceScanRequestSignal.connect(self.on_deviceScan, type=QtCore.Qt.QueuedConnection)

        self._widget_defs = widget_register(self._cmdp)
        self._widgets = []

        for widget_def in self._widget_defs.values():
            name = widget_def['name']
            if widget_def.get('singleton', False):
                w = self._widget_create(name)
                self.ui.menuView.addAction(w.toggleViewAction())
            else:
                name = widget_def['name']
                action = self.ui.menuView.addAction(name)
                action.triggered.connect(lambda checked: self._widget_create(name, visible=True))
                widget_def['action'] = action

        self._cmdp.subscribe('Device/#state/source', self._device_state_source)
        self._cmdp.subscribe('Device/#state/sample_drop_color', self._device_state_color)
        self._cmdp.subscribe('Device/#state/name', self._on_device_state_name)
        self._cmdp.subscribe('Device/#state/play', self._on_device_state_play)
        self._cmdp.subscribe('Device/#state/record', self._on_device_state_record)

        # Device selection
        self.device_action_group = QtWidgets.QActionGroup(self)
        self._device_disable = DeviceDisable()
        self._device_add(self._device_disable)

        # Other menu items
        self.ui.actionOpen.triggered.connect(self.on_recording_open)
        self.ui.actionPreferences.triggered.connect(self.on_preferences)
        self.ui.actionExit.triggered.connect(self.close)

        # Oscilloscope: current, voltage, power, GPI0, GPI1, i_range
        self.oscilloscope_dock_widget = QtWidgets.QDockWidget('Waveforms', self)
        self.oscilloscope_widget = Oscilloscope(self.oscilloscope_dock_widget, plugins=self._plugins)
        self.oscilloscope_dock_widget.setVisible(False)
        self.oscilloscope_dock_widget.setWidget(self.oscilloscope_widget)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.oscilloscope_dock_widget)
        self.ui.menuView.addAction(self.oscilloscope_dock_widget.toggleViewAction())
        signals = [
            {
                'name': 'current',
                'units': 'A',
                'y_limit': [-2.0, 10.0],
                'y_log_min': 1e-9,
                'y_range': 'auto',
                'show': True,
            },
            {
                'name': 'voltage',
                'units': 'V',
                'y_limit': [-1.2, 15.0],
                'y_range': 'auto',
                'show': True,
            },
            {
                'name': 'power',
                'units': 'W',
                'y_limit': [-2.4, 150.0],
                'y_log_min': 1e-9,
                'y_range': 'auto',
            },
            {
                'name': 'current_range',
                'y_limit': [-0.1, 8.1],
                'y_range': 'manual',
            },
            {
                'name': 'current_lsb',
                'display_name': 'in0',
                'y_limit': [-0.1, 1.1],
                'y_range': 'manual',
            },
            {
                'name': 'voltage_lsb',
                'display_name': 'in1',
                'y_limit': [-0.1, 1.1],
                'y_range': 'manual',
            },
        ]
        self.oscilloscope_widget.signal_configure(signals)

        self.oscilloscope_widget.set_xlimits(0.0, 30.0)
        self.oscilloscope_widget.set_xview(25.0, 30.0)
        self.oscilloscope_widget.on_xChangeSignal.connect(self._on_x_change)
        self.oscilloscope_widget.sigRefreshRequest.connect(self._on_refresh)
        self.oscilloscope_widget.sigMarkerSingleAddRequest.connect(self.on_markerSingleAddRequest)
        self.oscilloscope_widget.sigMarkerDualAddRequest.connect(self.on_markerDualAddRequest)
        self.oscilloscope_widget.sigMarkerRemoveRequest.connect(self.on_markerRemoveRequest)
        self.oscilloscope_widget.sigMarkerDualUpdateRequest.connect(self.on_markerDualUpdateRequest)
        self.oscilloscope_widget.sigRangeToolRequest.connect(self.on_rangeTool)
        self._cmdp.subscribe('Device/#state/data', lambda topic, data: self.oscilloscope_widget.data_update(data))
        self._cmdp.subscribe('Device/#state/data', self._device_state_data_for_fps)

        # status update timer
        self.status_update_timer = QtCore.QTimer(self)
        self.status_update_timer.setInterval(500)  # milliseconds
        self.status_update_timer.timeout.connect(self.on_statusUpdateTimer)
        self.status_update_timer.start()

        # Status bar
        self._source_indicator = QtWidgets.QLabel(self.ui.statusbar)
        self.ui.statusbar.addPermanentWidget(self._source_indicator)

        # device scan timer - because bad things happen, see rescan_interval config
        self.rescan_timer = QtCore.QTimer(self)
        self.rescan_timer.timeout.connect(self.on_rescanTimer)

        self.on_stopSignal.connect(self._on_stop, type=QtCore.Qt.QueuedConnection)
        self.on_statisticSignal.connect(self._on_statistic, type=QtCore.Qt.QueuedConnection)
        self.on_deviceEventSignal.connect(self._on_device_event, type=QtCore.Qt.QueuedConnection)
        self.on_markerStatisticsReadySignal.connect(self.on_markererStatistics, type=QtCore.Qt.QueuedConnection)

        # Software update
        self.on_softwareUpdateSignal.connect(self._on_software_update, type=QtCore.Qt.QueuedConnection)

        # help
        self.ui.actionGettingStarted.triggered.connect(self._help_getting_started)
        self.ui.actionUsersGuide.triggered.connect(self._help_users_guide)
        self.ui.actionCredits.triggered.connect(self._help_credits)
        self.ui.actionAbout.triggered.connect(self._help_about)

        # tools
        self.ui.actionClearEnergy.triggered.connect(self._accumulators_zero_total)
        with self._plugins as p:
            p.range_tool_register('Export data', Exporter)
        self._plugins.builtin_register()

        self._dock_widgets = [
            self.oscilloscope_dock_widget,
        ] + [x[0] for x in self._widgets]

        self._device_close()

    @property
    def _is_streaming(self):
        return self._streaming_status is not None

    @property
    def _is_streaming_device(self):
        return hasattr(self._device, 'start')

    def run(self, filename=None):
        if filename is not None:
            self._recording_open(filename)
            self.on_oscilloscopeMenu(True)
        self._software_update_check()
        log.debug('Qt show()')
        self.show()
        log.debug('Qt show() success')
        self._device_scan()

    def _widget_create(self, name, visible=False):
        dock_widget = QtWidgets.QDockWidget(name, self)
        log.info('_widget_create(%s)', name)
        widget_def = self._widget_defs[name]
        w = widget_def['class'](self, self._cmdp)
        location = widget_def.get('location', QtCore.Qt.RightDockWidgetArea)
        dock_widget.setWidget(w)
        self.addDockWidget(location, dock_widget)
        self._widgets.append((dock_widget, w, widget_def))
        dock_widget.setVisible(visible)
        return dock_widget

    @QtCore.Slot()
    def on_statusUpdateTimer(self):
        if self._has_active_device and hasattr(self._device, 'status'):
            try:
                s = self._device.status()
                if s['driver']['return_code']['value']:
                    self._device_recover()
                    return
                self._status_fn(s)
            except:
                log.exception("statusUpdateTimer failed - assume device error")
                self._device_recover()
                return

    @QtCore.Slot()
    def on_rescanTimer(self):
        log.debug('rescanTimer')
        self._device_scan()

    @QtCore.Slot(object)
    def _on_data_update(self, data):
        self.oscilloscope_widget.data_update(data)

    def _device_state_data_for_fps(self, topic, data):
        self._fps_counter += 1
        if self._is_streaming and self._data_view is not None:
            self._fps_limit_timer.stop()
            self._fps_limit_timer.start(FRAME_LIMIT_DELAY_MS)  # help to limit the frame rate for smoother animation

    @QtCore.Slot()
    def on_fpsTimer(self):
        if self._data_view is not None:
            self._data_view.refresh()

    @QtCore.Slot(object)
    def _on_statistic(self, statistics):
        self._accumulators['time'] += statistics['time']['delta']
        statistics['time']['accumulator'] = self._accumulators['time']
        for field in ['charge', 'energy']:
            x = statistics['accumulators'][field]['value']
            z = self._accumulators['fields'][field]
            z[0] += x - z[1]
            z[1] = x
            statistics['accumulators'][field]['value'] = z[0]

        energy = statistics['accumulators']['energy']['value']
        energy_str = three_sig_figs(energy, statistics['accumulators']['energy']['units'])
        self._cmdp.publish('Device/#state/energy', energy_str)
        self._cmdp.publish('Device/#state/statistics', statistics)

    @QtCore.Slot(float, float, int)
    def _on_x_change(self, x_min, x_max, x_count):
        log.info('_on_x_change(%s, %s, %s)', x_min, x_max, x_count)
        self.on_xChangeSignal.emit('resize', {'pixels': x_count})
        self.on_xChangeSignal.emit('span_absolute', {'range': [x_min, x_max]})

    @QtCore.Slot()
    def _on_refresh(self):
        log.info('_on_refresh')
        if self._data_view is not None:
            self._data_view.refresh(force=True)

    @QtCore.Slot(object, object)
    def device_notify(self, inserted, info):
        log.info('Device notify')
        self._device_scan()

    def disable_floating(self):
        for widget in self._dock_widgets:
            widget.setFloating(False)

    @QtCore.Slot(bool)
    def on_oscilloscopeMenu(self, checked):
        log.info('on_oscilloscopeMenu(%r)', checked)
        self.disable_floating()
        self.oscilloscope_dock_widget.setVisible(True)
        self.center_and_resize(0.85, 0.85)
        # docks = [self.oscilloscope_dock_widget]
        # self.resizeDocks(docks, [1000], QtCore.Qt.Vertical)

    def _software_update_check(self):
        if self._cmdp['General/update_check']:
            software_update_check(self.on_softwareUpdateSignal.emit)

    def _on_software_update(self, current_version, latest_version, url):
        log.info('_on_software_update(current_version=%r, latest_version=%r, url=%r)',
                 current_version, latest_version, url)
        txt = SOFTWARE_UPDATE.format(current_version=current_version, latest_version=latest_version, url=url)
        QtWidgets.QMessageBox.about(self, 'Joulescope Software Update Available', txt)

    def _help_about(self):
        log.info('_help_about')
        txt = ABOUT.format(ui_version=VERSION, driver_version=joulescope.VERSION)
        QtWidgets.QMessageBox.about(self, 'Joulescope', txt)

    def _help_credits(self):
        log.info('_help_credits')
        html = help_ui.load_credits()
        dialog = help_ui.ScrollMessageBox(html, self)
        dialog.setWindowTitle('Joulescope Credits')
        dialog.exec_()

    def _help_getting_started(self):
        log.info('_help_getting_started')
        html = help_ui.load_getting_started()
        dialog = help_ui.ScrollMessageBox(html, self)
        dialog.setWindowTitle('Getting Started with Your Joulescope')
        dialog.exec_()

    def _help_users_guide(self):
        log.info('_help_users_guide')
        webbrowser.open_new_tab(USERS_GUIDE_URL)

    def _accumulators_zero_total(self):
        log.info('_accumulators_zero_total')
        self._accumulators['time'] = 0.0
        for z in self._accumulators['fields'].values():
            z[0] = 0.0  # accumulated value

    def _accumulators_zero_last(self):
        log.info('_accumulators_zero_last')
        for z in self._accumulators['fields'].values():
            z[1] = 0.0  # last update value

    def _device_state_source(self, topic, data):
        self._source_indicator.setText(f'  {data}  ')
        self._source_indicator.setToolTip(self._cmdp['Device/#state/name'])

    def _device_state_color(self, topic, data):
        if data is None or data == '':
            style = ""
        else:
            style = f"QLabel {{ background-color : {data} }}"
        self._source_indicator.setStyleSheet(style)

    @property
    def _has_active_device(self):
        return self._device not in [None, self._device_disable]

    def center(self):
        try:
            geometry = self.window().windowHandle().screen().availableGeometry()
        except AttributeError:
            return
        sz = self.size()
        self.setGeometry(
            QtWidgets.QStyle.alignedRect(
                QtCore.Qt.LeftToRight,
                QtCore.Qt.AlignCenter,
                sz,
                geometry
            )
        )

    def center_and_resize(self, width_fract, height_fract):
        # https://wiki.qt.io/Center_and_Resize_MainWindow
        try:
            screen = self.window().windowHandle().screen()
        except AttributeError:
            return
        geometry = screen.availableGeometry()
        available_size = geometry.size()
        width, height = available_size.width(), available_size.height()
        log.info('Available dimensions [%d, %d]', width, height)
        sz = QtCore.QSize(int(width * width_fract), int(height * height_fract))
        self.setGeometry(
            QtWidgets.QStyle.alignedRect(
                QtCore.Qt.LeftToRight,
                QtCore.Qt.AlignCenter,
                sz,
                geometry
            )
        )

    def _device_open_failed(self, msg):
        self.status(msg)
        self._device_recover()
        return None

    @QtCore.Slot(int, str)
    def _on_device_event(self, event, msg):
        # Must connect with Qt.QueuedConnection since likely called from the
        # device's python data thread.
        level = logging.WARNING if event > 0 else logging.INFO
        log.log(level, '_on_device_event(%r, %r)', event, msg)

    def _on_device_state_name(self, topic, data):
        self.setWindowTitle(f'Joulescope: {data}')

    def _device_open(self, device):
        if self._device == device:
            log.info('device_open reopen %s', str(device))
            return
        self._device_close()
        log.info('device_open %s', str(device))
        self._accumulators_zero_last()
        self._device = device
        if self._has_active_device:
            if hasattr(self._device, 'stream_buffer_duration'):
                self._device.stream_buffer_duration = float(self._cmdp['Device/buffer_duration'])
            try:
                self._device.open(self.on_deviceEventSignal.emit)
            except:
                log.exception('while opening device')
                return self._device_open_failed('Could not open device')
            try:
                self._firmware_update_on_open()
            except:
                log.exception('firmware update failed')
                self._device_close()
                return
            try:
                self._cmdp.publish('Device/#state/name', str(self._device))
                if not self._device.ui_action.isChecked():
                    self._device.ui_action.setChecked(True)
                if hasattr(self._device, 'view_factory'):
                    self._data_view = self._device.view_factory()
                    self.on_xChangeSignal.connect(self._data_view.on_x_change)
                    self._data_view.on_update_fn = self._data_view_update_fn
                    self._data_view.open()
                    self._data_view.refresh()
                if hasattr(self._device, 'statistics_callback'):
                    self._device.statistics_callback = self.on_statisticSignal.emit
                self._cmdp.publish('Device/#state/play', False)
                self._cmdp.publish('Device/#state/record', False)
                self._cmdp.publish('Device/#state/source', 'Buffer')
                self._cmdp.subscribe('Device/parameter/', self._on_device_parameter, update_now=True)
                if self._cmdp['Device/autostream']:
                    self._cmdp.publish('Device/#state/play', True)
            except:
                log.exception('while initializing after open device')
                return self._device_open_failed('Could not initialize device')

    def _data_view_update_fn(self, data):
        self._cmdp.publish('Device/#state/data', data)

    def _on_device_parameter(self, topic, value):
        if not hasattr(self._device, 'parameter_set'):
            return
        topic = topic.replace('Device/parameter/', '')
        try:
            self._device.parameter_set(topic, value)
        except Exception:
            log.exception('during parameter_set')
            self.status('Parameter set %s failed, value=%s' % (topic, value))
            self._device_recover()

    def _device_close(self):
        log.debug('_device_close: start')
        self._cmdp.unsubscribe('Device/parameter/', self._on_device_parameter)
        device = self._device
        is_active_device = self._has_active_device
        self._device = self._device_disable
        log.info('device_close %s', str(device))
        if self._data_view is not None:
            try:
                self.on_xChangeSignal.disconnect(self._data_view.on_x_change)
            except:
                log.warning('Could not disconnect device.view.on_x_change')
            self._data_view.close()
            self._data_view = None
        if device:
            on_close = self._cmdp['Device/on_close']
            try:
                if hasattr(device, 'status'):
                    if on_close == 'sensor_off':
                        device.parameter_set('sensor_power', 'off')
                    elif on_close == 'current_off':
                        device.parameter_set('i_range', 'off')
                    elif on_close == 'current_auto':
                        device.parameter_set('i_range', 'auto')
                    else:  # keep
                        pass
            except:
                log.warning('could not set Device.on_close behavior %s', on_close)
            device.close()

        if is_active_device and hasattr(device, 'ui_action') and device.ui_action.isChecked():
            device.ui_action.setChecked(False)
        if hasattr(device, 'ui_on_close'):
            device.ui_on_close()

        self._device_disable.ui_action.setChecked(True)
        self._accumulators_zero_last()
        self.oscilloscope_widget.data_clear()
        self.oscilloscope_widget.markers_clear()
        self._cmdp.publish('Device/#state/name', '')
        self._cmdp.publish('Device/#state/source', 'None')
        self._cmdp.publish('Device/#state/sample_drop_color', '')
        log.debug('_device_close: done')

    def _device_recover(self):
        log.info('_device_recover: start')
        devices, self._devices = self._devices, []
        for device in devices:
            self._device_remove(device)
        self._deviceScanRequestSignal.emit()
        log.info('_device_recover: done')

    def _device_reopen(self):
        d = self._device
        self._device_close()
        self._deviceOpenRequestSignal.emit(d)

    @QtCore.Slot(object)
    def on_deviceOpen(self, d):
        self._device_open(d)

    def _device_add(self, device):
        """Add device to the user interface"""
        log.info('_device_change add %s', device)
        action = QtWidgets.QAction(str(device), self)
        action.setCheckable(True)
        action.setChecked(False)
        action.triggered.connect(lambda x: self._device_open(device))
        self.device_action_group.addAction(action)
        self.ui.menuDevice.addAction(action)
        device.ui_action = action

    def _device_remove(self, device):
        """Remove the device from the user interface"""
        log.info('_device_change remove')
        self.device_action_group.removeAction(device.ui_action)
        self.ui.menuDevice.removeAction(device.ui_action)
        if self._device == device:
            self._device_close()
        device.ui_action.triggered.disconnect()

    def _bootloader_scan(self):
        try:
            bootloaders = joulescope.scan('bootloader')
        except:
            return
        if not len(bootloaders):
            return

        log.info('Found %d Joulescope bootloaders', len(bootloaders))
        data = firmware_manager.load()

        if data is None:
            # no firmware, just attempt to kick into existing application
            for b in list(bootloaders):
                try:
                    b.open()
                except:
                    log.exception('while attempting to open bootloader')
                    continue
                try:
                    b.go()
                except:
                    log.exception('while attempting to run the application')
            return False

        for b in list(bootloaders):
            self.status('Programming firmware')
            try:
                b.open()
            except:
                log.exception('while attempting to open bootloader')
                continue
            try:
                self._firmware_update(b)
            except:
                log.exception('while attempting to run the application')

    def _device_scan(self):
        """Scan for new physical Joulescope devices."""
        if self._is_scanning:
            log.info('_device_scan already in progress')
            return
        log.info('_device_scan start')
        try:
            self._is_scanning = True
            self._bootloader_scan()
            physical_devices = [d for d in self._devices if hasattr(d, 'usb_device')]
            virtual_devices = [d for d in self._devices if not hasattr(d, 'usb_device')]
            devices, added, removed = joulescope.scan_for_changes(name=self._device_scan_name, devices=physical_devices)
            if self._device in removed:
                self._device_close()
            for d in removed:
                self._device_remove(d)
            for d in added:
                self._device_add(d)
            self._devices = virtual_devices + devices
            log.info('current device = %s, %s', self._device, self._device is self._device_disable)
            if self._device is self._device_disable and len(devices):
                log.info('device_scan activate first device %s', devices[0])
                devices[0].ui_action.trigger()
        finally:
            self._is_scanning = False
        log.info('_device_scan done')

    @QtCore.Slot()
    def on_deviceScan(self):
        self._device_scan()

    def _progress_dialog_construct(self):
        dialog = QtWidgets.QProgressDialog()
        dialog.setCancelButton(None)
        dialog.setWindowTitle('Joulescope')
        dialog.setLabelText('Firmware update in progress\nDo not unplug or turn off power')
        dialog.setRange(0, 1000)
        width = QtGui.QFontMetrics(dialog.font()).width('Do not unplug or turn off power') + 100
        dialog.resize(width, dialog.height())
        self._progress_dialog = dialog
        return dialog

    def _progress_dialog_finalize(self):
        self.on_progressValue.disconnect()
        self.on_progressMessage.disconnect()
        self._progress_dialog = None

    def _firmware_update_on_open(self):
        if not hasattr(self._device, 'parameters'):
            return
        firmware_update_cfg = self._cmdp['Device/firmware_update']
        if firmware_update_cfg in ['off', 'never'] or not bool(firmware_update_cfg):
            log.info('Skip firmware update: %s', firmware_update_cfg)
            return
        info = self._device.info()
        ver = None
        ver_required = firmware_manager.version_required()
        if info is not None and firmware_update_cfg != 'always':
            ver = info.get('ctl', {}).get('fw', {}).get('ver', '0.0.0')
            ver = tuple([int(x) for x in ver.split('.')])
            if ver >= ver_required:
                log.info('controller firmware is up to date: %s >= %s', ver, ver_required)
                return
        log.info('firmware update required: %s < %s', ver, ver_required)
        self.status('Firmware update required')
        self._device, d = None, self._device
        self._firmware_update(d)
        d.open()
        self._device = d

    def _firmware_update(self, device):
        data = firmware_manager.load()
        if data is None:
            self.status('Firmware update required, but could not find firmware image')
            return False

        dialog = self._progress_dialog_construct()
        progress = {
            'stage': '',
            'device': None,
        }

        self.on_progressValue.connect(dialog.setValue)
        self.on_progressMessage.connect(self.status)

        def progress_cbk(value):
            self.on_progressValue.emit(int(value * 1000))
            self.on_progressMessage.emit('Firmware upgrade [%.1f%%] %s' % (value * 100, progress['stage']))

        def stage_cbk(s):
            progress['stage'] = s

        def done_cbk(d):
            progress['device'] = d
            if d is None:
                self.on_progressMessage.emit('Firmware upgrade failed - unplug and retry')
            dialog.accept()

        self._is_scanning, is_scanning = True, self._is_scanning
        try:
            t = firmware_manager.upgrade(device, data, progress_cbk=progress_cbk, stage_cbk=stage_cbk, done_cbk=done_cbk)
            dialog.exec()
            t.join()
        finally:
            self._progress_dialog_finalize()
            self._is_scanning = is_scanning
            # self.status_update_timer.start()

    @QtCore.Slot(int, str)
    def _on_stop(self, event, message):
        log.debug('_on_stop(%d, %s)', event, message)
        self._cmdp.publish('Device/#state/play', False)
        self.oscilloscope_widget.set_display_mode('buffer')

    def _device_stream_start(self):
        log.debug('_device_stream_start')
        if not self._has_active_device:
            log.warning('_device_stream_start when no device')
            return
        if not hasattr(self._device, 'start'):
            log.info('device does not support start')
            return
        self._accumulators_zero_last()
        self._streaming_status = {}
        self._cmdp.publish('Device/#state/sampling_frequency', self._device.sampling_frequency)
        try:
            self._device.start(stop_fn=self.on_stopSignal.emit)
        except Exception:
            log.exception('_device_stream_start')
            self.status('Could not start device streaming')
        self.oscilloscope_widget.request_x_change()
        self._cmdp.publish('Device/#state/source', 'USB')

    def _device_stream_stop(self):
        log.debug('_device_stream_stop')
        self._streaming_status = None
        if not self._has_active_device:
            log.info('_device_stream_stop when no device')
            return
        if hasattr(self._device, 'stop'):
            self._device.stop()  # always safe to call
        self.oscilloscope_widget.set_display_mode('buffer')
        self._cmdp.publish('Device/#state/source', 'Buffer')
        self._cmdp.publish('Device/#state/sample_drop_color', '')

    def _on_device_state_play(self, topic, checked):
        log.info('_on_device_state_play(%s, %s)', topic, checked)
        if not self._is_streaming_device:
            return
        elif checked and not self._is_streaming:
            self._device_stream_start()
        elif not checked and self._is_streaming:
            self._device_stream_stop()

    def _device_can_record(self):
        return self._has_active_device and hasattr(self._device, 'stream_process_register')

    def _device_stream_record_start(self, filename):
        self._device_stream_record_close()
        if self._device_can_record():
            self._recording = DataRecorder(filename,
                                           sampling_frequency=self._device.sampling_frequency,
                                           calibration=self._device.calibration)
            self._device.stream_process_register(self._recording)
        else:
            log.warning('start recording failed for %s', filename)

    def _device_stream_record_close(self):
        if self._recording is not None:
            if self._has_active_device and hasattr(self._device, 'stream_process_unregister'):
                self._device.stream_process_unregister(self._recording)
            self._recording.close()
            self._recording = None

    def _device_stream_record_stop(self):
        self._device_stream_record_close()

    def _on_device_state_record(self, topic, enable):
        if enable:
            if self._device_can_record():
                self._device_stream_record_close()
                fname = construct_record_filename()
                path = os.path.join(self._path, os.path.basename(fname))
                filename, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
                    self, 'Save Joulescope Recording', path, 'Joulescope Data (*.jls)')
                filename = str(filename)
                if not len(filename):
                    self.status('Invalid filename, do not record')
                    self._device_stream_record_stop()
                else:
                    self._device_stream_record_start(filename)
            else:
                self.status('Selected device cannot record')
        elif not enable:
            self._device_stream_record_stop()

    def _save(self):
        if self._device is None:
            self.status('Device not open, cannot save buffer')
            return
        # Save the current buffer
        filename, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Joulescope buffer', self._path, 'Joulescope Data (*.jls)')
        filename = str(filename)
        if not len(filename):
            self.status('Invalid filename, do not open')
            return
        # todo

    def on_recording_open(self):
        filename, selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open Joulescope Recording', self._path, 'Joulescope Data (*.jls)')
        filename = str(filename)
        if not len(filename) or not os.path.isfile(filename):
            self.status('Invalid filename, do not open')
            return
        self._recording_open(filename)

    def _recording_open(self, filename):
        if filename is None:
            return
        self._device_close()
        log.info('open recording %s', filename)
        self.oscilloscope_widget.set_display_mode('buffer')
        device = RecordingViewerDevice(filename)
        device.ui_on_close = lambda: self._device_remove(device)
        self._device_add(device)
        self._device_open(device)

        self._cmdp.publish('Device/#state/name', os.path.basename(filename))
        self._cmdp.publish('Device/#state/source', 'File')
        self._cmdp.publish('Device/#state/sample_drop_color', '')

    def stateSave(self):
        children = []
        state = {
            'geometry': self.saveGeometry().data(),
            'state': self.saveState().data(),
            'maximized': self.isMaximized(),
            'pos': self.pos(),
            'size': self.size(),
            'children': children,
        }
        # todo save to preferences

    def stateRestore(self, state=None):
        pass

    def closeEvent(self, event):
        log.info('closeEvent(%r)', event)
        self.stateSave()
        self._device_close()
        return super(MainWindow, self).closeEvent(event)

    def _source_indicator_status_update(self, status):
        if not self._is_streaming or status is None or 'buffer' not in status:
            return
        buffer = status['buffer']
        n_sample_id = buffer.get('sample_id')
        n_sample_missing_count = buffer.get('sample_missing_count')
        if n_sample_id is None or n_sample_missing_count is None:
            return

        try:
            n_sample_id = n_sample_id['value']
            n_sample_missing_count = n_sample_missing_count['value']
            if len(self._streaming_status):  # skip first time
                d_sample_id = n_sample_id - self._streaming_status['sample_id']
                d_sample_missing_count = n_sample_missing_count - self._streaming_status['sample_missing_count']
                if (0 == d_sample_id) or ((d_sample_missing_count / d_sample_id) > 0.001):
                    color = 'red'
                    log.warning('status RED: d_sample_id=%d, d_sample_missing_count=%d',
                                d_sample_id, d_sample_missing_count)
                elif d_sample_missing_count:
                    color = 'yellow'
                    log.warning('status YELLOW: d_sample_id=%d, d_sample_missing_count=%d',
                                d_sample_id, d_sample_missing_count)
                else:
                    color = 'LightGreen'
            else:
                color = ''
            self._streaming_status['sample_id'] = n_sample_id
            self._streaming_status['sample_missing_count'] = n_sample_missing_count
            self._cmdp.publish('Device/#state/sample_drop_color', color)
            self._cmdp.publish('Device/#state/source', 'USB')
        except:
            log.exception('_source_indicator_status_update')

    def _fps_compute(self):
        fps_time = time.time()
        if self._fps_time is None:
            fps = 0.0
        else:
            fps = self._fps_counter / (fps_time - self._fps_time)
        self._fps_counter = 0
        self._fps_time = fps_time
        return fps

    def _status_fn(self, status):
        status['ui'] = {
            'display_rate': {
                'value': self._fps_compute(),
                'units': 'fps',
            },
        }
        self._cmdp.publish('Device/#state/status', status)
        self._source_indicator_status_update(status)

    @QtCore.Slot(str)
    def status(self, msg, timeout=STATUS_BAR_TIMEOUT):
        """Display a status message.

        :param msg: The message to display.
        :param timeout: The optional timeout in milliseconds.  0 
            does not time out.
        """
        log.info(msg)
        self.ui.statusbar.showMessage(msg, timeout)

    def on_preferences(self):
        log.info('on_preferences')
        d = PreferencesDialog(self._preferences)
        p = d.exec_()
        if p is not None:
            if p['General/data_path'] != self._cmdp['General/data_path']:
                self._path = p['General/data_path']
            # todo save
            # todo config apply?
            # todo update listeners

    @QtCore.Slot(float)
    def on_markerSingleAddRequest(self, x):
        m = self.oscilloscope_widget.marker_single_add(x)
        # no further action necessary, updates handled by oscilloscope_widget

    @QtCore.Slot(float)
    def on_markerDualAddRequest(self, x1, x2):
        m1, m2 = self.oscilloscope_widget.marker_dual_add(x1, x2)
        # No further action necessary, updates handled by on_markerDualUpdateRequest

    @QtCore.Slot(object)
    def on_markerRemoveRequest(self, markers):
        self.oscilloscope_widget.marker_remove(*markers)

    @QtCore.Slot(object, object)
    def on_markerDualUpdateRequest(self, m1, m2):
        # log.info('on_markerDualUpdateRequest(%s, %s)', m1, m2)
        t1 = m1.get_pos()
        t2 = m2.get_pos()
        if t1 > t2:
            t1, t2 = t2, t1
        if not hasattr(self._data_view, 'statistics_get'):
            self.status('Dual markers not supported by selected device')
            return
        self._data_view.statistics_get(t1, t2, units='seconds',
                                       callback=lambda d: self.on_markerStatisticsReadySignal.emit(m1, m2, d))

    @QtCore.Slot(object, object, object)
    def on_markererStatistics(self, m1, m2, d):
        for key, value in d['signals'].items():
            f = d['signals'][key]['statistics']
            dt = d['time']['delta']
            if f is None or not len(f):
                m2.html_set(key, '')
                continue
            txt_result = si_format(f, units=value['units'])
            if value.get('integral_units'):
                integral = f['μ'] * dt
                txt_result += ['∫=' + three_sig_figs(integral, units=value['integral_units'])]
            html = html_format(txt_result)
            m2.html_set(key, html)

    @QtCore.Slot(str, float, float)
    def on_rangeTool(self, name, x_start, x_stop):
        range_tool = self._plugins.range_tools.get(name)
        if range_tool is None:
            self.status('Range tool not found')
            return
        if not hasattr(self._data_view, 'statistics_get'):
            self.status('Range tool not supported by selected device')
            return
        app_state = {}
        if hasattr(self._device, 'voltage_range'):
            app_state['voltage_range'] = self._device.voltage_range
        elif hasattr(self._device, 'stream_buffer'):
            app_state['voltage_range'] = self._device.stream_buffer.voltage_range
        else:
            log.warning('cannot get voltage_range')
        invoke = RangeToolInvoke(self, range_tool, app_config=self._cmdp,
                                 app_state=app_state)
        invoke.sigFinished.connect(self.on_rangeToolFinished)
        s = self._data_view.statistics_get(x_start, x_stop, units='seconds')
        invoke.run(self._data_view, s, x_start, x_stop)

    @QtCore.Slot(object, str)
    def on_rangeToolFinished(self, range_tool, msg):
        if msg:
            log.warning(msg)
            self.status(msg)
        else:
            self.status(range_tool.name + ' done')

    def range_tool_menu_construct(self, menu=None):
        instances = []  # hold on to QT objects
        if menu is None:
            menu = QtGui.QMenu()
            menu.setToolTipsVisible(True)
        export_data = QtGui.QAction('&Export data', self)
        export_data.triggered.connect(self._range_tool_constructor('export'))
        menu.addAction(export_data)
        tools = self._axis().range_tools
        for name, in tools.keys():
            t = QtGui.QAction(name, self)
            t.triggered.connect(self._analysis_menu_callback_constructor(name))
            menu.addAction(t)
            instances.append(t)
        menu.instances = instances
        return menu


class ErrorWindow(QtWidgets.QMainWindow):

    def __init__(self, msg):
        super(ErrorWindow, self).__init__()
        self.ui = Ui_ErrorWindow()
        self.ui.setupUi(self)
        self.ui.label.setText(msg)
        self.show()

            
def run(device_name=None, log_level=None, file_log_level=None, filename=None):
    """Run the Joulescope UI application.

    :param device_name: The optional Joulescope device name.  None (default)
        searches for normal Joulescope devices.
    :param log_level: The logging level for the stdout console stream log.
        The allowed levels are in :data:`joulescope_ui.logging_util.LEVELS`.
        None (default) disables console logging.
    :param file_log_level: The logging level for the file log.
        The allowed levels are in :data:`joulescope_ui.logging_util.LEVELS`.
        None (default) uses the configuration value.
    :param filename: The optional filename to display immediately.

    :return: 0 on success or error code on failure.
    """
    try:
        cmdp = CommandProcessor()
        cmdp = preferences_def(cmdp)
        if file_log_level is None:
            file_log_level = cmdp.preferences['General/log_level']
        logging_config(file_log_level=file_log_level,
                       stream_log_level=log_level)
        logging.getLogger('joulescope').setLevel(logging.WARNING)

    except Exception:
        log.exception('during initialization')
        with io.StringIO() as f:
            traceback.print_exc(file=f)
            t = f.getvalue()
        app = QtWidgets.QApplication()
        ui = ErrorWindow("Exception trace:\n" + t)
        return app.exec_()

    try:
        log.info('configure high DPI scaling')
        # http://doc.qt.io/qt-5/highdpi.html
        # https://vicrucann.github.io/tutorials/osg-qt-high-dpi/
        if sys.platform.startswith('win'):
            ctypes.windll.user32.SetProcessDPIAware()
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    except:
        log.exception('while configuring high DPI scaling')

    log.info('Arguments: %s', (sys.argv, ))
    log.info('Start Qt')
    app = QtWidgets.QApplication(sys.argv)
    ui = MainWindow(app, device_name, cmdp)
    ui.run(filename)
    device_notify = DeviceNotify(ui.on_deviceNotifySignal.emit)
    rc = app.exec_()
    device_notify.close()
    return rc
