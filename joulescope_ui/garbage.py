# notes from refactoring


# --- oscilloscope widget commands


# --- main.py

self.disable_floating()
self.adjustSize()
self.center()
self.center_and_resize(0.85, 0.85)  # oscilloscope


    if self.dmm_dock_widget.isVisible() and not self.control_dock_widget.isVisible():
        self._multimeter_configure_device()

    def _multimeter_select_device(self):
        if self._device is self._device_disable:
            self._device_scan()
        elif not hasattr(self._device, 'is_streaming') and self._cmdp['Device/autostream']:
            # close file reader and attempt to open Joulescope
            self._device_close()
            self._device_scan()
        self._multimeter_configure_device()

    def _multimeter_configure_device(self):
        if hasattr(self._device, 'is_streaming'):
            if not self._device.is_streaming and self._cmdp['Device/autostream']:
                self._device_stream(True)
            # self._on_param_change('i_range', value='auto')

    self._multimeter_select_device()


    def _device_cfg_apply(self, previous_cfg=None, do_open=False):
        log.info('_device_cfg_apply')
        reopen = False
        self.gpio_widget.update(self._cmdp)
        if self._has_active_device:
            self._on_param_change('source', value=self._cmdp['Device/parameter/source'])
            self._on_param_change('i_range', value=self._cmdp['Device/parameter/i_range'])
            self._on_param_change('v_range', value=self._cmdp['Device/parameter/v_range'])
            self._gpio_cfg_apply(previous_cfg)
            if hasattr(self._device, 'stream_buffer_duration') and previous_cfg is not None and \
                    previous_cfg['Device']['buffer_duration'] != self._cmdp['Device/buffer_duration']:
                reopen = True
            elif do_open and self._cmdp['Device/autostream']:
                self._device_stream(True)
        rescan_interval = self._cmdp['Device/rescan_interval']
        if rescan_interval == 'off':
            self.rescan_timer.stop()
        else:
            self.rescan_timer.setInterval(int(rescan_interval) * 1000)  # milliseconds
            self.rescan_timer.start()
        if reopen:
            self._device_reopen()


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
            self._cmdp.publish('Device/' + param_name, value)
        if hasattr(self._device, 'parameter_set'):
            try:
                self._device.parameter_set(param_name, value)
            except Exception:
                log.exception('during parameter_set')
                self.status('Parameter set %s failed, value=%s' % (param_name, value))
                self._device_recover()


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
            # todo combobox.currentIndexChanged.connect(self._param_cbk_construct(p.name))
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


    def _preferences_apply(self, previous_cfg=None):
        log.debug('_preferences_apply: start')
        #self._device_cfg_apply(previous_cfg=previous_cfg)  # includes GPIO
        #self._current_ranging_cfg_apply(previous_cfg=previous_cfg)
        #self._waveform_cfg_apply(previous_cfg=previous_cfg)
        #self._developer_cfg_apply(previous_cfg=previous_cfg)
        log.debug('_preferences_apply: end')


####  COMPLIANCE ####

self._compliance = {  # state for compliance testing
    'gpo_value': 0,  # automatically toggle GPO, loopback & measure GPI
    'status': None,
}

if self._cmdp['Developer/compliance']:
    if self._compliance['status'] is not None:
        sample_id_prev = self._compliance['status']['buffer']['sample_id']['value']
        sample_id_now = s['buffer']['sample_id']['value']
        sample_id_delta = sample_id_now - sample_id_prev
        if sample_id_delta < 2000000 * 0.5 * 0.80:
            self._compliance_error('orange')
    self._compliance['status'] = s


if self._cmdp['Developer/compliance'] and self._cmdp['Developer/compliance_gpio_loopback']:
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


def _compliance_error(self, color=None):
    if self._cmdp['Developer/compliance']:
        if color is None:
            style_sheet = ''
        else:
            style_sheet = 'background-color: {color};'.format(color=color)
            log.warning('compliance error: %s', color)
        self.setStyleSheet(style_sheet)


def _developer_cfg_apply(self, previous_cfg=None):
    log.info('_developer_cfg_apply')
    return
    self._compliance['gpo_value'] = 0
    self._compliance['status'] = None
    self._compliance_error(None)
    if self._device is not None and hasattr(self._device, 'parameter_set'):
        self._device.parameter_set('gpo0', '0')
        self._device.parameter_set('gpo1', '0')

    if self._cmdp['Developer/compliance']:
        self.setStyleSheet("background-color: yellow;")

    # --- DEVELOPER ---


p.define('Developer/', 'Developer settings')
p.define(
    topic='Developer/compliance',
    brief='Compliance testing mode',
    dtype='bool',
    default=False)
p.define(
    topic='Developer/compliance_gpio_loopback',
    brief='GPI/O loopback for compliance testing',
    dtype='bool',
    default=False)

