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
from joulescope.driver import scan, scan_for_changes
from joulescope import VERSION as DRIVER_VERSION
from PySide2 import QtCore, QtWidgets
from joulescope_ui.developer_widget import Ui_DeveloperDockWidget
from joulescope_ui.main_window import Ui_mainWindow
from joulescope_ui.control_widget import Ui_ControlDockWidget
from joulescope_ui.oscilloscope import Oscilloscope
from joulescope_ui.uart import UartWidget
from joulescope_ui.meter_widget import MeterWidget
from joulescope_ui.data_view_api import NullView
from joulescope_ui.single_value_widget import SingleValueWidget
from joulescope.usb import DeviceNotify
from joulescope.units import unit_prefix, three_sig_figs
from joulescope.data_recorder import construct_record_filename
from joulescope_ui.recording_viewer_device import RecordingViewerDevice
from joulescope_ui.preferences import PreferencesDialog
from joulescope_ui.save_data import SaveDataDialog
from joulescope_ui.config import load_config_def, load_config, save_config
from joulescope_ui import usb_inrush
from joulescope_ui.update_check import check as software_update_check
from joulescope_ui.save import save_csv
import ctypes
import logging
log = logging.getLogger(__name__)


STATUS_BAR_TIMEOUT = 5000
DATA_BUFFER_DURATION = 60.0  # seconds


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


class ValueLabel(QtWidgets.QLabel):

    def __init__(self, parent=None, text=''):
        QtWidgets.QLabel.__init__(self, parent)
        self._text = text

    def set(self, value):
        self.setText('%s=%-8.2f' % (self._text, value))


class DeviceDisable:
    def __init__(self):
        self.view = NullView()

    def __str__(self):
        return "disable"

    def open(self):
        pass

    def close(self):
        pass


class MainWindow(QtWidgets.QMainWindow):
    on_deviceNotifySignal = QtCore.Signal(object, object)
    on_dataSignal = QtCore.Signal(object, object)  # x, data[length][3][4]
    on_stopSignal = QtCore.Signal()
    on_statisticSignal = QtCore.Signal(object, float)
    on_xChangeSignal = QtCore.Signal(str, object)
    on_softwareUpdateSignal = QtCore.Signal(str, str)

    def __init__(self, app, device_name=None):
        self._app = app
        self._device_scan_name = 'joulescope' if device_name is None else str(device_name)
        self._devices = []
        self._device = None
        self._is_streaming = False
        self._compliance = {  # state for compliance testing
            'gpo_value': 0,   # automatically toggle GPO, loopback & measure GPI
            'status': None,
        }

        self._parameters = {}
        self._status = {}
        self._status_row = 0
        self._data_view = None  # created when device is opened
        self._energy = [0, 0]  # value, offset

        self._cfg_def = load_config_def()
        self._cfg = load_config(self._cfg_def)
        self._path = self._cfg['General']['data_path']

        super(MainWindow, self).__init__()
        self.ui = Ui_mainWindow()
        self.ui.setupUi(self)

        # Central widget to keep top at top
        self.central_widget = QtWidgets.QWidget(self)
        self.central_widget.setMaximumWidth(1)
        self.setCentralWidget(self.central_widget)

        self._multimeter_default_action = self.ui.menuView.addAction("Multimeter Default")
        self._multimeter_default_action.triggered.connect(self.on_multimeterMenu)
        self._oscilloscope_default_action = self.ui.menuView.addAction("Oscilloscope Default")
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
        self.ui.actionOpen.triggered.connect(self.recording_open)
        #self.ui.actionSave.triggered.connect(self._save)
        #self.ui.actionClose.triggered.connect(self.close)
        self.ui.actionSave.triggered.connect(self.on_saveData)
        self.ui.actionSave.setEnabled(False)
        self.ui.actionClose.setEnabled(False)

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

        # Oscilloscope: current
        self._view_current = Oscilloscope(self, 'Current')
        self._view_current.on_xChangeSignal.connect(self._on_x_change)
        self._view_current.setVisible(False)
        self.ui.menuView.addAction(self._view_current.widget.toggleViewAction())
        self._view_current.y_limit_set(-2.0, 10.0, update=True)

        # Oscilloscope: voltage
        self._view_voltage = Oscilloscope(self, 'Voltage')
        self._view_voltage.on_xChangeSignal.connect(self._on_x_change)
        self._view_voltage.setVisible(False)
        self.ui.menuView.addAction(self._view_voltage.widget.toggleViewAction())
        self._view_voltage.y_limit_set(-1.2, 15.0, update=True)

        # Oscilloscope: voltage
        self._view_power = Oscilloscope(self, 'Power')
        self._view_power.on_xChangeSignal.connect(self._on_x_change)
        self._view_power.setVisible(False)
        self.ui.menuView.addAction(self._view_power.widget.toggleViewAction())
        self._view_power.y_limit_set(-2.4, 150.0, update=True)

        # Connect oscilloscope views together
        views = [self._view_current, self._view_voltage, self._view_power]
        for v1 in views:
            for v2 in views:
                if v1 == v2:
                    continue
                v1.on_markerSignal.connect(v2.on_marker)

        # status update timer
        self.status_update_timer = QtCore.QTimer(self)
        self.status_update_timer.setInterval(500)  # milliseconds
        self.status_update_timer.timeout.connect(self.on_statusUpdateTimer)
        self.status_update_timer.start()

        # data update timer
        self.data_update_timer = QtCore.QTimer(self)
        self.data_update_timer.setInterval(33)  # milliseconds
        self.data_update_timer.timeout.connect(self.on_dataUpdateTimer)

        self.on_stopSignal.connect(self._on_stop)
        self.on_statisticSignal.connect(self._on_statistic)

        # Software update
        self.on_softwareUpdateSignal.connect(self._on_software_update)

        # help about
        self.ui.actionAbout.triggered.connect(self._help_about)

        # tools
        self.ui.actionClearEnergy.triggered.connect(self._tool_clear_energy)
        self.ui.actionUsbInrush.triggered.connect(self._tool_usb_inrush)
        self.ui.actionUsbInrush.setEnabled(usb_inrush.is_available())

        self._dock_widgets = [
            self.dev_dock_widget,
            self.control_dock_widget,
            self.dmm_dock_widget,
            self.single_value_dock_widget,
            self.uart_dock_widget,
            self._view_current.widget,
            self._view_voltage.widget,
            self._view_power.widget,
        ]

        self.on_multimeterMenu(True)
        self._waveform_cfg_apply()
        self.show()
        self._device_close()
        self._device_scan()
        self._software_update_check()

    @QtCore.Slot()
    def on_statusUpdateTimer(self):
        if self._has_active_device and hasattr(self._device, 'status'):
            s = self._device.status()
            if s['driver']['return_code']['value']:
                self._device_close()
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

    def _update_data(self):
        if self._has_active_device:
            is_changed, (x, data) = self._device.view.update()
            if is_changed:
                self._view_current.update(x, data)
                self._view_voltage.update(x, data)
                self._view_power.update(x, data)
        else:
            self._view_current.clear()
            self._view_voltage.clear()
            self._view_power.clear()

    @QtCore.Slot()
    def on_dataUpdateTimer(self):
        if not self._has_active_device and self._is_streaming:
            return
        self._update_data()

    @QtCore.Slot(object, float)
    def _on_statistic(self, statistics, energy):
        self._energy[0] = energy
        energy -= self._energy[1]
        energy_str = three_sig_figs(energy, 'J')
        self.control_ui.energyValueLabel.setText(energy_str)
        self.dmm_widget.update(statistics, energy)

        if self._cfg['Developer']['compliance'] and self._cfg['Developer']['compliance_gpio_loopback']:
            gpo_value = self._compliance['gpo_value']
            gpi_value = self._device.extio_status()['gpi_value']['value']
            if gpo_value != gpi_value:
                log.warning('gpi mismatch: gpo=0x%02x, gpi=0x%02x', gpo_value, gpi_value)
                self._compliance_error('red')
            else:
                self._compliance_error(None)
            gpo_value = (gpo_value + 1) & 0x03
            self._device.parameter_set('gpo0', '1' if (gpo_value & 0x01) else '0')
            self._device.parameter_set('gpo1', '1' if (gpo_value & 0x02) else '0')
            self._compliance['gpo_value'] = gpo_value

    @QtCore.Slot(str, object)
    def _on_x_change(self, cmd, kwargs):
        log.info('on_x_change(%s, %s)', cmd, kwargs)
        self.on_xChangeSignal.emit(cmd, kwargs)
        if not self.data_update_timer.isActive():
            # force data update
            self.data_update_timer.timeout.emit()

    def on_developer(self, do_show):
        self.dev_dock_widget.setVisible(do_show)

    def device_notify(self, inserted, info):
        self._device_scan()

    def disable_floating(self):
        for widget in self._dock_widgets:
            widget.setFloating(False)

    @QtCore.Slot(bool)
    def on_multimeterMenu(self, checked):
        log.info('on_multimeterMenu(%r)', checked)
        self.disable_floating()
        self.dev_dock_widget.setVisible(False)
        self.control_dock_widget.setVisible(False)
        self.dmm_dock_widget.setVisible(True)
        self.single_value_dock_widget.setVisible(False)
        self.uart_dock_widget.setVisible(False)
        self._view_current.setVisible(False)
        self._view_voltage.setVisible(False)
        self._view_power.setVisible(False)

        self.adjustSize()
        self.center()

    @QtCore.Slot(bool)
    def on_oscilloscopeMenu(self, checked):
        log.info('on_oscilloscopeMenu(%r)', checked)
        self.disable_floating()
        self.dev_dock_widget.setVisible(False)
        self.control_dock_widget.setVisible(True)
        self.dmm_dock_widget.setVisible(False)
        self.single_value_dock_widget.setVisible(False)
        self.uart_dock_widget.setVisible(False)
        self._view_current.setVisible(True)
        self._view_voltage.setVisible(True)
        self._view_power.setVisible(False)
        self.center_and_resize(0.85, 0.85)

        docks = [self._view_current.widget, self._view_voltage.widget]
        self.resizeDocks(docks, [1000, 1000], QtCore.Qt.Vertical)

    def _software_update_check(self):
        if self._cfg['General']['update_check']:
            software_update_check(self.on_softwareUpdateSignal.emit)

    def _on_software_update(self, current_version, latest_version):
        txt = SOFTWARE_UPDATE.format(current_version=current_version, latest_version=latest_version)
        QtWidgets.QMessageBox.about(self, 'Joulescope Software Update Available', txt)

    def _help_about(self):
        txt = ABOUT.format(ui_version=VERSION, driver_version=DRIVER_VERSION)
        QtWidgets.QMessageBox.about(self, 'Joulescope', txt)

    def _tool_clear_energy(self):
        log.info('_tool_clear_energy: offset= %g J', self._energy[0])
        self._energy[1] = self._energy[0]

    def _tool_usb_inrush(self):
        data = self._device.view.extract()
        rv = usb_inrush.run(data, self._device.view.sampling_frequency)

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
                self.window().windowHandle().screen().availableGeometry()
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

    def _device_view_force(self):
        length, x_range = self._view_current.x_state_get()
        if length is None:
            length = 100
        self._device.view.on_x_change('resize', {'pixels': length})

    def _device_open_failed(self, msg):
        self.status(msg)
        self._device_close()
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

    def _device_open(self, device):
        if self._device == device:
            log.info('device_open reopen %s', str(device))
            return
        self._device_close()
        self._energy_offset = 0
        log.info('device_open %s', str(device))
        self._device = device
        if self._has_active_device:
            try:
                self._device.open()
            except:
                return self._device_open_failed('Could not open device')
            try:
                if not self._device.ui_action.isChecked():
                    self._device.ui_action.setChecked(True)
                self._param_init()
                self._control_ui_init()
                self.on_xChangeSignal.connect(self._device.view.on_x_change)
                self._device_view_force()
                self._device_cfg_apply(do_open=True)
                self._device.statistics_callback = self.on_statisticSignal.emit
                self._update_data()
            except:
                return self._device_open_failed('Could not initialize device')
            self._developer_cfg_apply()

    def _control_ui_init(self):
        log.info('_control_ui_init')
        if not self._has_active_device:
            self._control_ui_clean()
            return
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
        self.control_ui.playButton.setChecked(False)
        self.control_ui.playButton.setEnabled(False)
        self.control_ui.recordButton.setChecked(False)
        self.control_ui.recordButton.setEnabled(False)

    def _waveform_cfg_apply(self):
        for waveform in [self._view_current, self._view_voltage, self._view_power]:
            waveform.config(self._cfg['Waveform'])

    def _device_cfg_apply(self, do_open=False):
        if self._has_active_device:
            self._on_param_change('source', value=self._cfg['Device']['source'])
            self._on_param_change('i_range', value=self._cfg['Device']['i_range'])
            self._on_param_change('v_range', value=self._cfg['Device']['v_range'])
            if do_open and self._cfg['Device']['autostream']:
                self._device_stream(True)

    def _developer_cfg_apply(self):
        self._compliance['gpo_value'] = 0
        self._compliance['status'] = None
        self._compliance_error(None)
        if self._device is not None:
            self._device.parameter_set('gpo0', '0')
            self._device.parameter_set('gpo1', '0')

    def _device_close(self):
        device = self._device
        is_active_device = self._has_active_device
        self._device = self._device_disable
        log.info('device_close %s', str(device))
        if is_active_device:
            if device.view is not None:
                self.on_xChangeSignal.disconnect(device.view.on_x_change)
            device.close()
            if device.ui_action.isChecked():
                device.ui_action.setChecked(False)
        self._device_disable.ui_action.setChecked(True)
        self._status_clean()
        self._param_clean()
        self._control_ui_clean()
        self._view_current.clear()
        self._view_voltage.clear()
        self._view_power.clear()
        if self._cfg['Developer']['compliance']:
            self.setStyleSheet("background-color: yellow;")

    def _device_add(self, device):
        """Add device to the user interface"""
        action = QtWidgets.QAction(str(device), self)
        action.setCheckable(True)
        action.setChecked(False)
        action.triggered.connect(lambda x: self._device_open(device))
        self.device_action_group.addAction(action)
        self.ui.menuDevice.addAction(action)
        device.ui_action = action

    def _device_remove(self, device):
        """Remove the device from the user interface"""
        self.device_action_group.removeAction(device.ui_action)
        self.ui.menuDevice.removeAction(device.ui_action)
        if self._device == device:
            self._device_close()
        device.ui_action.triggered.disconnect()

    def _device_scan(self):
        """Scan for new physical Joulescope devices."""
        physical_devices = [d for d in self._devices if hasattr(d, 'usb_device')]
        virtual_devices = [d for d in self._devices if not hasattr(d, 'usb_device')]
        devices, added, removed = scan_for_changes(name=self._device_scan_name, devices=physical_devices)
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
                log.warning('Could not find value %s' % (value, ))
                return
            combobox.setCurrentIndex(index)
        else:
            log.warning('_on_param_change with no change!')
            return
        log.info('param_name=%s, value=%s, index=%s', param_name, value, index)
        if hasattr(self._device, 'parameter_set'):
            try:
                self._device.parameter_set(param_name, value)
            except Exception:
                log.exception('during parameter_set')
                self.status('Parameter set %s failed, value=%s' % (param_name, value))

    def _param_cbk_construct(self, param_name: str):
        return lambda x: self._on_param_change(param_name, index=x)

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
        for key, (w1, w2, w3) in self._parameters.items():
            w1.setParent(None)
            w2.setParent(None)
            w3.setParent(None)
        self._parameters = {}

    def _status_clean(self):
        for key, (w1, w2, w3) in self._status.items():
            w1.setParent(None)
            w2.setParent(None)
            w3.setParent(None)
        self._status = {}

    @QtCore.Slot()
    def _on_stop(self):
        log.debug('_on_stop')
        self.data_update_timer.stop()
        self.control_ui.playButton.setChecked(False)
        self.control_ui.recordButton.setChecked(False)
        self.control_ui.recordButton.setEnabled(False)

    def _device_stream_start(self):
        log.debug('_device_stream_start')
        if not self._has_active_device:
            log.warning('_device_stream_start when no device')
            return
        if not hasattr(self._device, 'start'):
            log.info('device does not support start')
            return
        self._is_streaming = True
        self.control_ui.playButton.setChecked(True)
        self.control_ui.recordButton.setEnabled(True)
        self.data_update_timer.start()
        try:
            self._device.start(stop_fn=self.on_stopSignal.emit)
        except Exception:
            log.exception('_device_stream_start')
            self.status('Could not start device streaming')

    def _device_stream_stop(self):
        log.debug('_device_stream_stop')
        self._is_streaming = False
        if not self._has_active_device:
            log.warning('_device_stream_stop when no device')
            self._device_close()
            return
        if hasattr(self._device, 'stop'):
            self._device.stop()  # always safe to call

    def _device_stream(self, checked):
        log.info('_device_stream(%s)' % checked)
        if self._is_streaming == checked:
            return
        if checked:
            self._device_stream_start()
        else:
            self._device_stream_stop()

    def _device_stream_record_start(self, filename):
        if self._has_active_device and self._device.recording_start(filename):
            self.control_ui.recordButton.setChecked(True)
        else:
            log.warning('start recording failed for %s', filename)
            self.control_ui.recordButton.setChecked(False)

    def _device_stream_record_stop(self):
        if self._has_active_device:
            self._device.recording_stop()
        self.control_ui.recordButton.setChecked(False)

    def _device_stream_save(self, checked):
        if checked and self._device is not None and not self._device.is_recording:
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

    def recording_open(self):
        self._device_close()
        filename, selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open Joulescope Recording', self._path, 'Joulescope Data (*.jls)')
        filename = str(filename)
        if not len(filename):
            self.status('Invalid filename, do not open')
            return
        log.info('open recording %s', filename)
        device = RecordingViewerDevice(filename)
        device.on_close = lambda: self._device_remove(device)
        self._device_add(device)
        self._device_open(device)
        self._update_data()

    def closeEvent(self, event):
        self._device_close()
        event.accept()

    def _status_fn(self, status):
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

    def on_preferences(self, *args, **kwargs):
        d = PreferencesDialog(self._cfg_def, self._cfg)
        cfg = d.exec_()
        if cfg is not None:
            if cfg['General']['data_path'] != self._cfg['General']['data_path']:
                self._path = cfg['General']['data_path']
            log.info(cfg)
            self._cfg = cfg
            save_config(self._cfg)
            self._device_cfg_apply()
            self._waveform_cfg_apply()
            self._developer_cfg_apply()

    def on_saveData(self):
        rv = SaveDataDialog(self._path).exec_()
        if rv is None:
            return
        filename = rv['filename']
        log.info('save to %s', filename)
        sample_frequency = self._device.view.sampling_frequency
        if filename.endswith('.csv'):
            extracted_data = self._device.view.extract()
            save_csv(filename, extracted_data, sample_frequency)
        # WARNING need to implement recording_viewer_device
        # define & improve the buffer API to be compatible
        #elif filename.endswith('.jls'):
        #    pass
        else:
            self.ui.statusbar.showMessage('Save failed')

            
def kick_bootloaders():
    for d in scan(name='bootloader'):
        d.open()
        d.go()


def run(device_name=None):
    logging.basicConfig(level=logging.INFO)
    # http://doc.qt.io/qt-5/highdpi.html
    # https://vicrucann.github.io/tutorials/osg-qt-high-dpi/
    kick_bootloaders()
    if sys.platform.startswith('win'):
        ctypes.windll.user32.SetProcessDPIAware()
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    app = QtWidgets.QApplication(sys.argv)
    ui = MainWindow(app, device_name=device_name)
    device_notify = DeviceNotify(ui.on_deviceNotifySignal.emit)
    rc = app.exec_()
    device_notify.close()
    return rc
