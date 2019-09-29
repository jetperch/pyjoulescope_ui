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
from joulescope_ui.developer_widget import Ui_DeveloperDockWidget
from joulescope_ui.error_window import Ui_ErrorWindow
from joulescope_ui.main_window import Ui_mainWindow
from joulescope_ui.control_widget import Ui_ControlDockWidget
from joulescope_ui.oscilloscope import Oscilloscope
from joulescope_ui.uart import UartWidget
from joulescope_ui.meter_widget import MeterWidget
from joulescope_ui.data_view_api import NullView
from joulescope_ui.single_value_widget import SingleValueWidget
from joulescope.usb import DeviceNotify
from joulescope.units import unit_prefix, three_sig_figs
from joulescope_ui.data_recorder_process import DataRecorderProcess as DataRecorder
from joulescope.data_recorder import construct_record_filename  # DataRecorder
from joulescope_ui.recording_viewer_device import RecordingViewerDevice
from joulescope_ui.preferences import PreferencesDialog
from joulescope_ui.config import load_config_def, load_config, save_config
from joulescope_ui.update_check import check as software_update_check
from joulescope_ui.logging_util import logging_config
from joulescope_ui.oscilloscope.signal_statistics import si_format, html_format, three_sig_figs
from joulescope_ui.range_tool import RangeToolInvoke
from joulescope_ui import help_ui
from joulescope_ui import firmware_manager
from joulescope_ui.plugin_manager import PluginManager
from joulescope_ui.exporter import Exporter
import io
import ctypes
import collections
import copy
import traceback
import time
import webbrowser
import logging
log = logging.getLogger(__name__)


STATUS_BAR_TIMEOUT = 5000  # milliseconds
USERS_GUIDE_URL = "https://www.joulescope.com/docs/JoulescopeUsersGuide.html"


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
<p><a href="https://www.joulescope.com/download">Download</a> now.</p>
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
    on_softwareUpdateSignal = QtCore.Signal(str, str)
    on_deviceEventSignal = QtCore.Signal(int, str)  # event, message
    on_dataUpdateSignal = QtCore.Signal(object)

    on_progressValue = QtCore.Signal(int)
    on_progressMessage = QtCore.Signal(str)

    def __init__(self, app, device_name=None, cfg_def=None, cfg=None):
        self._app = app
        self._device_scan_name = 'joulescope' if device_name is None else str(device_name)
        self._devices = []
        self._device = None
        self._is_streaming = False
        self._streaming_status = None
        self._compliance = {  # state for compliance testing
            'gpo_value': 0,   # automatically toggle GPO, loopback & measure GPI
            'status': None,
        }

        self._fps_counter = 0
        self._fps_time = None
        self._fps_limit_timer = QtCore.QTimer()
        self._fps_limit_timer.setSingleShot(True)
        self._fps_limit_timer.timeout.connect(self.on_fpsTimer)

        self._parameters = {}
        self._status = {}
        self._status_row = 0
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

        if cfg_def is None:
            self._cfg_def = load_config_def()
        else:
            self._cfg_def = cfg_def
        if cfg is None:
            self._cfg = load_config(self._cfg_def, default_on_error=True)
        else:
            self._cfg = cfg  # warning: shared mutable data, update only (no replace)
        self._path = self._cfg['General']['data_path']
        self._plugins = PluginManager(self._cfg)

        super(MainWindow, self).__init__()
        self.ui = Ui_mainWindow()
        self.ui.setupUi(self)

        # Central widget to keep top at top
        self.central_widget = QtWidgets.QWidget(self)
        self.central_widget.setMaximumWidth(1)
        self.setCentralWidget(self.central_widget)

        self._multimeter_default_action = self.ui.menuView.addAction("Multimeter")
        self._multimeter_default_action.triggered.connect(self.on_multimeterMenu)
        self._oscilloscope_default_action = self.ui.menuView.addAction("Oscilloscope")
        self._oscilloscope_default_action.triggered.connect(self.on_oscilloscopeMenu)
        self.ui.menuView.addSeparator()

        # Developer widget
        self.dev_dock_widget = QtWidgets.QDockWidget('Developer', self)
        self.dev_ui = Ui_DeveloperDockWidget()
        self.dev_ui.setupUi(self.dev_dock_widget)
        self.dev_dock_widget.setVisible(False)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.dev_dock_widget)
        self.ui.menuView.addAction(self.dev_dock_widget.toggleViewAction())
        self.on_deviceNotifySignal.connect(self.device_notify)
        self._deviceOpenRequestSignal.connect(self.on_deviceOpen, type=QtCore.Qt.QueuedConnection)
        self._deviceScanRequestSignal.connect(self.on_deviceScan, type=QtCore.Qt.QueuedConnection)

        # Control widget
        self.control_dock_widget = QtWidgets.QDockWidget('Control', self)
        self.control_ui = Ui_ControlDockWidget()
        self.control_ui.setupUi(self.control_dock_widget)
        self.control_dock_widget.setVisible(False)
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.control_dock_widget)
        self.ui.menuView.addAction(self.control_dock_widget.toggleViewAction())
        self.control_ui.playButton.toggled.connect(self._device_stream)
        self.control_ui.recordButton.toggled.connect(self._device_stream_save)

        # Device selection
        self.device_action_group = QtWidgets.QActionGroup(self)
        self._device_disable = DeviceDisable()
        self._device_add(self._device_disable)

        # Other menu items
        self.ui.actionOpen.triggered.connect(self.on_recording_open)
        self.ui.actionPreferences.triggered.connect(self.on_preferences)
        self.ui.actionExit.triggered.connect(self.close)
        self.ui.actionDeveloper.triggered.connect(self.on_developer)

        # Digital multimeter display widget
        self.dmm_dock_widget = QtWidgets.QDockWidget('Multimeter', self)
        self.dmm_widget = MeterWidget(self.dmm_dock_widget)
        self.dmm_dock_widget.setVisible(False)
        self.dmm_dock_widget.setWidget(self.dmm_widget)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.dmm_dock_widget)
        self.ui.menuView.addAction(self.dmm_dock_widget.toggleViewAction())

        # Single value display widget
        self.single_value_dock_widget = QtWidgets.QDockWidget('Single Value Display', self)
        self.single_value_widget = SingleValueWidget(self.single_value_dock_widget)
        self.single_value_widget.source(self.dmm_widget)
        self.single_value_dock_widget.setVisible(False)
        self.single_value_dock_widget.setWidget(self.single_value_widget)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.single_value_dock_widget)
        self.ui.menuView.addAction(self.single_value_dock_widget.toggleViewAction())

        # UART widget
        self.uart_dock_widget = QtWidgets.QDockWidget('Uart', self)
        self.uart_widget = UartWidget(self.uart_dock_widget)
        self.uart_dock_widget.setVisible(False)
        self.uart_dock_widget.setWidget(self.uart_widget)
        # todo implement UART widget
        # self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.uart_dock_widget)
        # self.ui.menuView.addAction(self.uart_dock_widget.toggleViewAction())

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
                'y_limit': [-0.1, 1.1],
                'y_range': 'manual',
            },
            {
                'name': 'voltage_lsb',
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
        self.on_dataUpdateSignal.connect(self._on_data_update, type=QtCore.Qt.QueuedConnection)

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
        self._plugins.builtin_register(app_config=self._cfg)

        self._dock_widgets = [
            self.dev_dock_widget,
            self.control_dock_widget,
            self.dmm_dock_widget,
            self.single_value_dock_widget,
            self.uart_dock_widget,
            self.oscilloscope_dock_widget,
        ]

        self._device_close()
        self._cfg_apply()

    def run(self, filename=None):
        if filename is not None:
            self._recording_open(filename)
            self.on_oscilloscopeMenu(True)
        else:
            self._multimeter_show()
        self._software_update_check()
        log.debug('Qt show()')
        self.show()
        log.debug('Qt show() success')
        if filename is None:
            self._multimeter_select_device()

    @QtCore.Slot()
    def on_statusUpdateTimer(self):
        if self._has_active_device and hasattr(self._device, 'status'):
            try:
                s = self._device.status()
                if s['driver']['return_code']['value']:
                    self._device_recover()
                    return
                self._status_fn(s)
                if self._cfg['Developer']['compliance']:
                    if self._compliance['status'] is not None:
                        sample_id_prev = self._compliance['status']['buffer']['sample_id']['value']
                        sample_id_now = s['buffer']['sample_id']['value']
                        sample_id_delta = sample_id_now - sample_id_prev
                        if sample_id_delta < 2000000 * 0.5 * 0.80:
                            self._compliance_error('orange')
                    self._compliance['status'] = s
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
        self._fps_counter += 1
        self.oscilloscope_widget.data_update(data)
        if self._is_streaming and self._data_view is not None:
            self._fps_limit_timer.stop()
            self._fps_limit_timer.start(30)  # help to limit the frame rate for smoother animation
        # self.oscilloscope_widget.data_clear()

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
        self.control_ui.energyValueLabel.setText(energy_str)

        self.dmm_widget.update(statistics)

        if self._cfg['Developer']['compliance'] and self._cfg['Developer']['compliance_gpio_loopback']:
            gpo_value = self._compliance['gpo_value']
            if hasattr(self._device, 'extio_status'):
                gpi_value = self._device.extio_status()['gpi_value']['value']
            if gpo_value != gpi_value:
                log.warning('gpi mismatch: gpo=0x%02x, gpi=0x%02x', gpo_value, gpi_value)
                self._compliance_error('red')
            else:
                self._compliance_error(None)
            gpo_value = (gpo_value + 1) & 0x03
            if hasattr(self._device, 'parameter_set'):
                self._device.parameter_set('gpo0', '1' if (gpo_value & 0x01) else '0')
                self._device.parameter_set('gpo1', '1' if (gpo_value & 0x02) else '0')
            self._compliance['gpo_value'] = gpo_value

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

    def on_developer(self, do_show):
        log.info('on_developer(%r)', do_show)
        self.dev_dock_widget.setVisible(do_show)

    @QtCore.Slot(object, object)
    def device_notify(self, inserted, info):
        log.info('Device notify')
        self._device_scan()

    def disable_floating(self):
        for widget in self._dock_widgets:
            widget.setFloating(False)

    def _multimeter_show(self):
        self.disable_floating()
        self.dev_dock_widget.setVisible(False)
        self.control_dock_widget.setVisible(False)
        self.dmm_dock_widget.setVisible(True)
        self.single_value_dock_widget.setVisible(False)
        self.uart_dock_widget.setVisible(False)
        self.oscilloscope_dock_widget.setVisible(False)

        self.adjustSize()
        self.center()

    def _multimeter_configure_device(self):
        if hasattr(self._device, 'is_streaming'):
            if not self._device.is_streaming and self._cfg['Device']['autostream']:
                self._device_stream(True)
            self._on_param_change('i_range', value='auto')

    def _multimeter_select_device(self):
        if self._device is self._device_disable:
            self._device_scan()
        elif not hasattr(self._device, 'is_streaming') and self._cfg['Device']['autostream']:
            # close file reader and attempt to open Joulescope
            self._device_close()
            self._device_scan()
        self._multimeter_configure_device()

    @QtCore.Slot(bool)
    def on_multimeterMenu(self, checked):
        log.info('on_multimeterMenu(%r)', checked)
        self._multimeter_show()
        self._multimeter_select_device()

    @QtCore.Slot(bool)
    def on_oscilloscopeMenu(self, checked):
        log.info('on_oscilloscopeMenu(%r)', checked)
        self.disable_floating()
        self.dev_dock_widget.setVisible(False)
        self.control_dock_widget.setVisible(True)
        self.dmm_dock_widget.setVisible(False)
        self.single_value_dock_widget.setVisible(False)
        self.uart_dock_widget.setVisible(False)
        self.oscilloscope_dock_widget.setVisible(True)
        self.center_and_resize(0.85, 0.85)
        # docks = [self.oscilloscope_dock_widget]
        # self.resizeDocks(docks, [1000], QtCore.Qt.Vertical)

    def _software_update_check(self):
        if self._cfg['General']['update_check']:
            software_update_check(self.on_softwareUpdateSignal.emit)

    def _on_software_update(self, current_version, latest_version):
        log.info('_on_software_update(current_version=%r, latest_version=%r)', current_version, latest_version)
        txt = SOFTWARE_UPDATE.format(current_version=current_version, latest_version=latest_version)
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

    def _source_indicator_set(self, text, color=None, tooltip=None):
        tooltip = '' if tooltip is None else str(tooltip)
        self._source_indicator.setText(text)
        if color is None:
            style = ""
        else:
            style = f"QLabel {{ background-color : {color} }}"
        self._source_indicator.setStyleSheet(style)
        self._source_indicator.setToolTip(tooltip)

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
        self._compliance_error('yellow')
        return None

    def _compliance_error(self, color=None):
        if self._cfg['Developer']['compliance']:
            if color is None:
                style_sheet = ''
            else:
                style_sheet = 'background-color: {color};'.format(color=color)
                log.warning('compliance error: %s', color)
            self.setStyleSheet(style_sheet)

    @QtCore.Slot(int, str)
    def _on_device_event(self, event, msg):
        # Must connect with Qt.QueuedConnection since likely called from the
        # device's python data thread.
        level = logging.WARNING if event > 0 else logging.INFO
        log.log(level, '_on_device_event(%r, %r)', event, msg)

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
                self._device.stream_buffer_duration = float(self._cfg['Device']['buffer_duration'])
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
                self.setWindowTitle(str(self._device))
                if not self._device.ui_action.isChecked():
                    self._device.ui_action.setChecked(True)
                self._param_init()
                self._control_ui_init()
                if hasattr(self._device, 'view_factory'):
                    self._data_view = self._device.view_factory()
                    self.on_xChangeSignal.connect(self._data_view.on_x_change)
                    self._data_view.on_update_fn = self.on_dataUpdateSignal.emit
                    self._data_view.open()
                    self._data_view.refresh()
                self._device_cfg_apply(do_open=True)
                if hasattr(self._device, 'statistics_callback'):
                    self._device.statistics_callback = self.on_statisticSignal.emit
            except:
                log.exception('while initializing after open device')
                return self._device_open_failed('Could not initialize device')
            self._developer_cfg_apply()
            if self.dmm_dock_widget.isVisible() and not self.control_dock_widget.isVisible():
                self._multimeter_configure_device()

    def _control_ui_disconnect(self):
        for combobox in [self.control_ui.iRangeComboBox, self.control_ui.vRangeComboBox]:
            try:
                combobox.currentIndexChanged.disconnect()
            except:
                pass

    def _control_ui_init(self):
        log.info('_control_ui_init')
        if not self._has_active_device:
            self._control_ui_clean()
            return
        else:
            self._control_ui_disconnect()
        self.control_ui.playButton.setEnabled(hasattr(self._device, 'start'))
        self.control_ui.recordButton.setEnabled(False)
        params = [('i_range', self.control_ui.iRangeComboBox),
                  ('v_range', self.control_ui.vRangeComboBox)]
        if hasattr(self._device, 'parameters'):
            for name, combobox in params:
                combobox.clear()
                p = self._device.parameters(name=name)
                current_value = self._device.parameter_get(name)
                current_index = None
                for idx, (value_name, value, _) in enumerate(p.values):
                    combobox.addItem(value_name)
                    if value_name == current_value:
                        current_index = idx
                if current_index is not None:
                    log.info('control ui init %s %d', name, current_index)
                    combobox.setCurrentIndex(current_index)
                combobox.currentIndexChanged.connect(self._param_cbk_construct(p.name))

    def _control_ui_clean(self):
        self._control_ui_disconnect()
        self.control_ui.playButton.setChecked(False)
        self.control_ui.playButton.setEnabled(False)
        self.control_ui.recordButton.setChecked(False)
        self.control_ui.recordButton.setEnabled(False)
        self.control_ui.iRangeComboBox.setEnabled(False)
        self.control_ui.vRangeComboBox.setEnabled(False)

    def _waveform_cfg_apply(self, previous_cfg=None):
        self.oscilloscope_widget.config_apply(self._cfg['Waveform'])

    def _device_cfg_apply(self, previous_cfg=None, do_open=False):
        reopen = False
        if self._has_active_device:
            log.info('_device_cfg_apply')
            self._on_param_change('source', value=self._cfg['Device']['source'])
            self._on_param_change('i_range', value=self._cfg['Device']['i_range'])
            self._on_param_change('v_range', value=self._cfg['Device']['v_range'])
            if hasattr(self._device, 'stream_buffer_duration') and previous_cfg is not None and \
                    previous_cfg['Device']['buffer_duration'] != self._cfg['Device']['buffer_duration']:
                reopen = True
            elif do_open and self._cfg['Device']['autostream']:
                self._device_stream(True)
        rescan_interval = self._cfg['Device']['rescan_interval']
        if rescan_interval == 'off':
            self.rescan_timer.stop()
        else:
            self.rescan_timer.setInterval(int(rescan_interval) * 1000)  # milliseconds
            self.rescan_timer.start()
        if reopen:
            self._device_reopen()

    def _developer_cfg_apply(self, previous_cfg=None):
        log.info('_developer_cfg_apply')
        return
        self._compliance['gpo_value'] = 0
        self._compliance['status'] = None
        self._compliance_error(None)
        if self._device is not None and hasattr(self._device, 'parameter_set'):
            self._device.parameter_set('gpo0', '0')
            self._device.parameter_set('gpo1', '0')

    def _device_close(self):
        log.debug('_device_close: start')
        self.setWindowTitle('Joulescope')
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
            on_close = self._cfg['Device']['on_close']
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
        self._status_clean()
        self._param_clean()
        self._control_ui_clean()
        self._accumulators_zero_last()
        self.oscilloscope_widget.data_clear()
        self.oscilloscope_widget.markers_clear()
        if self._cfg['Developer']['compliance']:
            self.setStyleSheet("background-color: yellow;")
        self._source_indicator_set('None', color='yellow', tooltip=TOOLTIP_NO_SOURCE)
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
        firmware_update_cfg = self._cfg['Device']['firmware_update']
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

    def _on_param_change(self, param_name, index=None, value=None):
        if param_name == 'i_range':
            combobox = self.control_ui.iRangeComboBox
        elif param_name == 'v_range':
            combobox = self.control_ui.vRangeComboBox
        else:
            try:
                combobox = self._parameters[param_name][1]
            except KeyError:
                return
        if index is not None:
            if index < 0:
                return  # combobox was just cleared, ignore
            value = str(combobox.itemText(index))
        elif value is not None:
            for i in range(combobox.count()):
                if value == str(combobox.itemText(i)):
                    index = i
                    break
            if index is None:
                log.warning('Could not find param %s value %s' % (param_name, value))
                return
        else:
            log.warning('_on_param_change with no change!')
            return
        if combobox.currentIndex() != index:
            combobox.setCurrentIndex(index)
        log.info('param_name=%s, value=%s, index=%s', param_name, value, index)
        if param_name in ['i_range', 'v_range', 'source']:
            self._cfg['Device'][param_name] = value
        if hasattr(self._device, 'parameter_set'):
            try:
                self._device.parameter_set(param_name, value)
            except Exception:
                log.exception('during parameter_set')
                self.status('Parameter set %s failed, value=%s' % (param_name, value))
                self._device_recover()

    def _param_cbk_construct(self, param_name: str):
        @QtCore.Slot()
        def cbk(x):
            log.info('_param_cbk(%s)', param_name)
            return self._on_param_change(param_name, index=x)
        return cbk

    def _param_init(self):
        self._param_clean()
        if not hasattr(self._device, 'parameters'):
            return
        params = self._device.parameters()
        for row_idx, p in enumerate(params):
            if p.name in ['i_range', 'v_range']:
                continue
            label_name = QtWidgets.QLabel(self.dev_ui.parameter_groupbox)
            combobox = QtWidgets.QComboBox(self.dev_ui.parameter_groupbox)
            label_units = QtWidgets.QLabel(self.dev_ui.parameter_groupbox)
            current_value = self._device.parameter_get(p.name)
            current_index = None
            for idx, (value_name, value, _) in enumerate(p.values):
                combobox.addItem(value_name)
                if value_name == current_value:
                    current_index = idx
            if current_index is not None:
                combobox.setCurrentIndex(current_index)
            combobox.currentIndexChanged.connect(self._param_cbk_construct(p.name))
            self.dev_ui.parameter_layout.addWidget(label_name, row_idx, 0, 1, 1)
            self.dev_ui.parameter_layout.addWidget(combobox, row_idx, 1, 1, 1)
            self.dev_ui.parameter_layout.addWidget(label_units, row_idx, 2, 1, 1)
            label_name.setText(p.name)
            label_units.setText(p.units)
            self._parameters[p.name] = [label_name, combobox, label_units]

    def _param_clean(self):
        for key, (label_name, combobox, label_units) in self._parameters.items():
            label_name.setParent(None)
            try:
                combobox.currentIndexChanged.disconnect()
            except:
                pass
            combobox.setParent(None)
            label_units.setParent(None)
        self._parameters = {}

    def _status_clean(self):
        for key, (w1, w2, w3) in self._status.items():
            w1.setParent(None)
            w2.setParent(None)
            w3.setParent(None)
        self._status = {}

    @QtCore.Slot(int, str)
    def _on_stop(self, event, message):
        log.debug('_on_stop(%d, %s)', event, message)
        self.control_ui.playButton.setChecked(False)
        self.control_ui.recordButton.setChecked(False)
        self.control_ui.recordButton.setEnabled(False)
        self.control_ui.iRangeComboBox.setEnabled(False)
        self.control_ui.vRangeComboBox.setEnabled(False)
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
        self._is_streaming = True
        self._streaming_status = None
        self.control_ui.playButton.setChecked(True)
        self.control_ui.recordButton.setEnabled(True)
        self.control_ui.iRangeComboBox.setEnabled(True)
        self.control_ui.vRangeComboBox.setEnabled(True)
        self.oscilloscope_widget.set_sampling_frequency(self._device.sampling_frequency)
        try:
            self._device.start(stop_fn=self.on_stopSignal.emit)
        except Exception:
            log.exception('_device_stream_start')
            self.status('Could not start device streaming')
        self.oscilloscope_widget.request_x_change()
        self._source_indicator_set(' USB ', tooltip=str(self._device))

    def _device_stream_stop(self):
        log.debug('_device_stream_stop')
        self._is_streaming = False
        self._streaming_status = None
        if not self._has_active_device:
            log.info('_device_stream_stop when no device')
            return
        if hasattr(self._device, 'stop'):
            self._device.stop()  # always safe to call
        self.oscilloscope_widget.set_display_mode('buffer')
        self._source_indicator_set(' Buffer ', tooltip=str(self._device))

    def _device_stream(self, checked):
        log.info('_device_stream(%s)' % checked)
        if self._is_streaming == checked:
            return
        if checked:
            self._device_stream_start()
        else:
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
            self.control_ui.recordButton.setChecked(True)
        else:
            log.warning('start recording failed for %s', filename)
            self.control_ui.recordButton.setChecked(False)

    def _device_stream_record_close(self):
        if self._recording is not None:
            if self._has_active_device and hasattr(self._device, 'stream_process_unregister'):
                self._device.stream_process_unregister(self._recording)
            self._recording.close()
            self._recording = None

    def _device_stream_record_stop(self):
        self._device_stream_record_close()
        self.control_ui.recordButton.setChecked(False)

    def _device_stream_save(self, checked):
        if checked:
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
        elif not checked:
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
        self._source_indicator_set(' File ', tooltip=filename)
        self.setWindowTitle('Joulescope: ' + os.path.basename(filename))

    def closeEvent(self, event):
        log.info('closeEvent(%r)', event)
        self._device_close()
        event.accept()

    def _source_indicator_status_update(self, status):
        if not self._is_streaming or status is None or 'buffer' not in status:
            return
        buffer = status['buffer']
        n_sample_id = buffer.get('sample_id')
        n_sample_missing_count = buffer.get('sample_missing_count')
        if n_sample_id is None or n_sample_missing_count is None:
            return

        try:
            color = None
            n_sample_id = n_sample_id['value']
            n_sample_missing_count = n_sample_missing_count['value']
            if self._streaming_status is None:
                self._streaming_status = {}
            else:
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
            self._streaming_status['sample_id'] = n_sample_id
            self._streaming_status['sample_missing_count'] = n_sample_missing_count
            self._source_indicator_set(' USB ', color=color, tooltip=str(self._device))
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
        self._source_indicator_status_update(status)
        for root_key, root_value in status.items():
            if root_key == 'endpoints':
                root_value = root_value.get('2', {})
            for key, value in root_value.items():
                # print(f'{root_key}.{key} = {value}')
                s = self._status.get(key)
                if s is None:  # create
                    label_name = QtWidgets.QLabel(self.dev_ui.status_groupbox)
                    label_value = QtWidgets.QLabel(self.dev_ui.status_groupbox)
                    label_units = QtWidgets.QLabel(self.dev_ui.status_groupbox)
                    self.dev_ui.status_layout.addWidget(label_name, self._status_row, 0, 1, 1)
                    self.dev_ui.status_layout.addWidget(label_value, self._status_row, 1, 1, 1)
                    self.dev_ui.status_layout.addWidget(label_units, self._status_row, 2, 1, 1)
                    self._status_row += 1
                    label_name.setText(key)
                    s = [label_name, label_value, label_units]
                    self._status[key] = s
                fmt = value.get('format', None)
                v = value['value']
                c = ''
                if fmt is None:
                    v, c, _ = unit_prefix(v)
                    k = three_sig_figs(v)
                else:
                    k = fmt.format(v)
                units = str(c + value['units'])
                s[1].setText(k)
                s[2].setText(units)

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
        d = PreferencesDialog(self._cfg_def, self._cfg)
        cfg = d.exec_()
        if cfg is not None:
            if cfg['General']['data_path'] != self._cfg['General']['data_path']:
                self._path = cfg['General']['data_path']
            log.info(cfg)

            # Maintain existing i_range and v_range unless changed.
            cfg['Device']['i_range_update'] = (self._cfg['Device']['i_range'] != cfg['Device']['i_range'])
            cfg['Device']['v_range_update'] = (self._cfg['Device']['v_range'] != cfg['Device']['v_range'])

            previous_cfg = copy.deepcopy(self._cfg)
            dict_update_recursive(self._cfg, cfg)
            save_config(self._cfg)
            self._cfg_apply(previous_cfg=previous_cfg)

    def _cfg_apply(self, previous_cfg=None):
        log.debug('_cfg_apply: start')
        self._device_cfg_apply(previous_cfg=previous_cfg)
        self._waveform_cfg_apply(previous_cfg=previous_cfg)
        self._developer_cfg_apply(previous_cfg=previous_cfg)
        log.debug('_cfg_apply: end')

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
        d = self._data_view.statistics_get(t1, t2, units='seconds')
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
        plugin_config = self._cfg.get('plugins', {}).get(name, {})
        app_state = {}
        if hasattr(self._device, 'voltage_range'):
            app_state['voltage_range'] = self._device.voltage_range
        elif hasattr(self._device, 'stream_buffer'):
            app_state['voltage_range'] = self._device.stream_buffer.voltage_range
        else:
            log.warning('cannot get voltage_range')
        invoke = RangeToolInvoke(self, range_tool, app_config=self._cfg,
                                 app_state=app_state, plugin_config=plugin_config)
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
        cfg_def = load_config_def()
        cfg = load_config(cfg_def, default_on_error=True)
        if file_log_level is None:
            file_log_level = cfg['General']['log_level']
        logging_config(file_log_level=file_log_level,
                       stream_log_level=log_level)

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
    ui = MainWindow(app, device_name=device_name, cfg_def=cfg_def, cfg=cfg)
    ui.run(filename)
    device_notify = DeviceNotify(ui.on_deviceNotifySignal.emit)
    rc = app.exec_()
    device_notify.close()
    return rc
