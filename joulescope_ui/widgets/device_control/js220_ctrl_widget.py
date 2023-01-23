# 2023 Jetperch LLC
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

from PySide6 import QtCore, QtGui, QtWidgets
from joulescope_ui.expanding_widget import ExpandingWidget
import logging
from joulescope_ui import N_, register, tooltip_format, pubsub_singleton, get_topic_name, Metadata
from joulescope_ui.devices.jsdrv.js220 import SETTINGS
from joulescope_ui.ui_util import comboBoxConfig
from .device_info_dialog import DeviceInfoDialog
import webbrowser
from joulescope_ui.styles import styled_widget


JS220_USERS_GUIDE_URL = 'https://download.joulescope.com/products/JS220/JS220-K000/users_guide/index.html'


_DOC_TOOLTIP = tooltip_format(
    N_('Device documentation'),
    N_('Click to display the device documentation PDF.')
)

_INFO_TOOLTIP = tooltip_format(
    N_('Device information'),
    N_('Click to display detailed information about the device.')
)

_DEFAULT_DEVICE_TOOLTIP = tooltip_format(
    N_('Select this device as the default'),
    N_("""\
    When selected, this device because the default.  All widgets
    using the default device will use the data provided by this
    device.
    
    When unselected, another device is the default.  Widgets
    can still be configured to use data from this device.\
    """),
)

_OPEN_TOOLTIP = tooltip_format(
    N_('Open and close the device'),
    N_("""\
    When closed, click to attempt to open the device.  The icon
    will only change on a successful device open.  Only one
    application can use a Joulescope device at a time.
    
    When open, click to close the device.  This allows the device
    to be used in other programs.\
    """),
)

_RESET_TO_DEFAULTS_TOOLTIP = tooltip_format(
    N_('Reset to default settings'),
    N_('Click this button to reset this device to the default settings'),
)

_CLEAR_ACCUM_TOOLTIP = tooltip_format(
    N_('Clear accumulators'),
    N_("""\
    Click this button to clear the charge and energy accumulators.
    The "Accrue" feature of the value display widgets, including
    the multimeter, will be unaffected.\
    """),
)

_BUTTON_SIZE = (20, 20)


def _construct_pushbutton(parent, name, checkable=False, tooltip=None):
    b = QtWidgets.QPushButton(parent)
    b.setObjectName(name)
    b.setProperty('blink', False)
    b.setCheckable(checkable)
    b.setFixedSize(*_BUTTON_SIZE)
    b.setToolTip(tooltip)
    return b


class Js220CtrlWidget(QtWidgets.QWidget):

    def __init__(self, parent, unique_id):
        self._parent = parent
        self._unique_id = unique_id
        self._widgets = []
        self._unsub = []  # (topic, fn)
        self._row = 0
        self._signals = {}
        self._gpo = {}
        self._footer = {}
        self._log = logging.getLogger(f'{__name__}.{unique_id}')
        self._buttons_blink = []
        self._target_power_button: QtWidgets.QPushButton = None
        self._info_button: QtWidgets.QPushButton = None
        super().__init__(parent)

        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._expanding = ExpandingWidget(self)
        self._expanding.title = unique_id

        self._body = QtWidgets.QWidget(self)
        self._body_layout = QtWidgets.QGridLayout(self)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(1)
        self._body.setLayout(self._body_layout)
        self._expanding.body_widget = self._body

        self._layout.addWidget(self._expanding)
        self.setLayout(self._layout)

        self._header_widgets = []
        self._expanding.header_ex_widget = self._construct_header()

        self._add_signal_buttons()
        self._add_settings()
        self._add_gpo()
        self._add_footer()
        self._subscribe('registry/ui/events/blink_slow', self._on_blink)
        self._subscribe('registry/app/settings/target_power', self._on_target_power_app)
        topic = get_topic_name(self._unique_id)
        for signal in ['0', '1', '2', '3', 'T']:
            self._gpi_subscribe(f'{topic}/signals/{signal}/!data', signal)
        self._subscribe(f'{topic}/settings/state', self._on_setting_state)

    def _subscribe(self, topic, update_fn):
        pubsub_singleton.subscribe(topic, update_fn, ['pub', 'retain'])
        self._unsub.append((topic, update_fn))

    def _gpi_subscribe(self, topic, signal):
        self._subscribe(topic, lambda v: self._on_gpi_n(signal, v))

    def _on_gpi_n(self, signal, value):
        d = value.get('data')
        if d is None or 0 == len(d):
            self._log.info('Empty GPI %s', signal)
            return
        signal_level = (d[0] != 0)
        b = self._signals['buttons'][signal]
        b.setProperty('signal_level', signal_level)

    def _on_setting_state(self, value):
        if self._info_button is not None:
            self._info_button.setEnabled(value == 2)

    def _on_target_power_app(self, value):
        b = self._target_power_button
        b.setEnabled(bool(value))
        b.style().unpolish(b)
        b.style().polish(b)

    def _on_info(self, *args, **kwargs):
        self._log.info('on_info')
        info = pubsub_singleton.query(f'{get_topic_name(self._unique_id)}/settings/info')
        DeviceInfoDialog(info)

    def _construct_header(self):
        w = QtWidgets.QWidget(self._expanding)
        layout = QtWidgets.QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        doc = _construct_pushbutton(w, 'doc', tooltip=_DOC_TOOLTIP)
        doc.clicked.connect(lambda checked: webbrowser.open_new_tab(JS220_USERS_GUIDE_URL))
        layout.addWidget(doc)

        info = _construct_pushbutton(w, 'info', tooltip=_INFO_TOOLTIP)
        info.clicked.connect(self._on_info)
        self._info_button = info
        layout.addWidget(info)

        default_device = self._construct_default_device_button(w)
        layout.addWidget(default_device)

        target_power = self._construct_target_power_button(w)
        layout.addWidget(target_power)

        open_button = self._construct_open_button(w)
        layout.addWidget(open_button)

        w.setLayout(layout)
        self._header_widgets = [w, layout, doc, info, default_device, target_power, open_button]
        return w

    def _construct_default_device_button(self, parent):
        topics = [
            'registry/app/settings/defaults/statistics_stream_source',
            'registry/app/settings/defaults/signal_stream_source',
        ]
        b = _construct_pushbutton(parent, 'default_device', checkable=True, tooltip=_DEFAULT_DEVICE_TOOLTIP)

        def update_from_pubsub(value):
            block_state = b.blockSignals(True)
            b.setChecked(value == self._unique_id)
            b.blockSignals(block_state)

        def on_pressed(checked):
            block_state = b.blockSignals(True)
            b.setChecked(True)
            b.blockSignals(block_state)
            for topic in topics:
                pubsub_singleton.publish(topic, self._unique_id)

        self._target_power_button = b
        self._subscribe(topics[0], update_from_pubsub)
        b.toggled.connect(on_pressed)
        return b

    def _construct_target_power_button(self, parent):
        topic = f'{get_topic_name(self._unique_id)}/settings/target_power'
        meta = pubsub_singleton.metadata(topic)
        b = _construct_pushbutton(parent, 'target_power', checkable=True,
                                  tooltip=tooltip_format(meta.brief, meta.detail))
        self._buttons_blink.append(b)

        def update_from_pubsub(value):
            block_state = b.blockSignals(True)
            b.setChecked(bool(value))
            b.blockSignals(block_state)

        self._target_power_button = b
        self._subscribe(topic, update_from_pubsub)
        b.toggled.connect(lambda checked: pubsub_singleton.publish(topic, bool(checked)))
        return b

    def _construct_open_button(self, parent):
        self_topic = get_topic_name(self._unique_id)
        state_topic = f'{self_topic}/settings/state'
        b = _construct_pushbutton(parent, 'open', checkable=True, tooltip=_OPEN_TOOLTIP)

        def state_from_pubsub(value):
            checked = (value == 2)  # open (not closed, opening, or closing)
            block_state = b.blockSignals(True)
            b.setChecked(checked)
            b.blockSignals(block_state)

        def on_toggle(checked):
            checked = bool(checked)
            block_state = b.blockSignals(True)
            b.setChecked(not checked)
            b.blockSignals(block_state)
            state_req = 1 if checked else 0
            pubsub_singleton.publish(f'{self_topic}/settings/state_req', state_req)

        self._subscribe(state_topic, state_from_pubsub)
        b.toggled.connect(on_toggle)
        return b

    def _add_signal_buttons(self):
        widget = QtWidgets.QWidget(self)
        self._body_layout.addWidget(widget, self._row, 0, 1, 2)
        self._widgets.append(widget)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        widget.setLayout(layout)
        self._signals = {
            'widget': widget,
            'layout': layout,
            'buttons': {},
            'spacer': QtWidgets.QSpacerItem(0, 0,
                                            QtWidgets.QSizePolicy.Expanding,
                                            QtWidgets.QSizePolicy.Minimum),
        }
        for name, value in SETTINGS.items():
            if not name.startswith('enable/'):
                continue
            signal = name[7:]
            meta = Metadata(value)
            self._add_signal_button(signal, meta)
        layout.addItem(self._signals['spacer'])
        self._row += 1

    def _add_signal_button(self, signal, meta):
        topic = f'{get_topic_name(self._unique_id)}/settings/enable/{signal}'
        b = QtWidgets.QPushButton(self._signals['widget'])
        b.setObjectName('device_control_signal')
        b.setProperty('signal_level', 0)
        b.setCheckable(True)
        b.setText(signal)
        b.setFixedSize(20, 20)
        b.setToolTip(tooltip_format(meta.brief, meta.detail))

        def update_from_pubsub(value):
            block_state = b.blockSignals(True)
            b.setChecked(bool(value))
            b.blockSignals(block_state)

        pubsub_singleton.subscribe(topic, update_from_pubsub, ['pub', 'retain'])
        b.toggled.connect(lambda checked: pubsub_singleton.publish(topic, bool(checked)))
        self._signals['layout'].addWidget(b)
        self._signals['buttons'][signal] = b

    def _add_gpo(self):
        lbl = QtWidgets.QLabel(N_('GPO'), self)
        self._body_layout.addWidget(lbl, self._row, 0, 1, 1)
        self._widgets.append(lbl)

        widget = QtWidgets.QWidget(self)
        self._body_layout.addWidget(widget, self._row, 1, 1, 1)
        self._widgets.append(widget)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        widget.setLayout(layout)
        self._gpo = {
            'widget': widget,
            'layout': layout,
            'buttons': [],
            'spacer': QtWidgets.QSpacerItem(0, 0,
                                            QtWidgets.QSizePolicy.Expanding,
                                            QtWidgets.QSizePolicy.Minimum),
        }
        for name, value in SETTINGS.items():
            if not name.startswith('out/'):
                continue
            signal = name[4:]
            meta = Metadata(value)
            self._add_gpo_button(signal, meta)
        layout.addItem(self._gpo['spacer'])
        self._row += 1

    def _add_gpo_button(self, signal, meta):
        topic = f'{get_topic_name(self._unique_id)}/settings/out/{signal}'
        b = QtWidgets.QPushButton(self._gpo['widget'])
        b.setObjectName('device_ctrl_gpo')
        b.setCheckable(True)
        b.setText(signal)
        b.setFixedSize(20, 20)
        b.setToolTip(tooltip_format(meta.brief, meta.detail))

        def update_from_pubsub(value):
            block_state = b.blockSignals(True)
            b.setChecked(bool(value))
            b.blockSignals(block_state)

        pubsub_singleton.subscribe(topic, update_from_pubsub, ['pub', 'retain'])
        b.toggled.connect(lambda checked: pubsub_singleton.publish(topic, bool(checked)))
        self._gpo['layout'].addWidget(b)
        self._gpo['buttons'].append(b)

    def _add_settings(self):
        for name, value in SETTINGS.items():
            if name.startswith('out/') or name.startswith('enable/'):
                continue
            meta = Metadata(value)
            if 'hidden' not in meta.flags:
                self._add(name, meta)
            if name == 'current_range':
                pass  # todo add custom ranged slider for min/max selection

    def _add_str(self, name):
        w = QtWidgets.QLineEdit(self)
        topic = f'{get_topic_name(self._unique_id)}/settings/{name}'
        w.textChanged.connect(lambda s: pubsub_singleton.publish(topic, s))

        def on_change(v):
            block_state = w.blockSignals(True)
            w.setText(str(v))
            w.blockSignals(block_state)

        self._subscribe(topic, on_change)
        return w

    def _add_combobox(self, name, meta: Metadata):
        w = QtWidgets.QComboBox(self)

        options = meta.options
        option_values = [o[0] for o in options]
        option_strs = [o[1] for o in options]
        comboBoxConfig(w, option_strs)
        topic = f'{get_topic_name(self._unique_id)}/settings/{name}'
        w.currentIndexChanged.connect(lambda idx: pubsub_singleton.publish(topic, options[idx][0]))

        def lookup(v):
            try:
                idx = option_values.index(v)
            except ValueError:
                self._log.warning('Invalid value: %s not in %s', v, option_values)
                return
            block_state = w.blockSignals(True)
            w.setCurrentIndex(idx)
            w.blockSignals(block_state)

        self._subscribe(topic, lookup)
        return w

    def _add(self, name, meta: Metadata):
        tooltip = tooltip_format(meta.brief, meta.detail)
        lbl = QtWidgets.QLabel(meta.brief, self)
        lbl.setToolTip(tooltip)
        self._body_layout.addWidget(lbl, self._row, 0, 1, 1)
        self._widgets.append(lbl)

        w = None
        if meta.options is not None:
            w = self._add_combobox(name, meta)
        elif meta.dtype == 'str':
            w = self._add_str(name)
        else:
            pass

        if w is not None:
            w.setToolTip(tooltip)
            self._body_layout.addWidget(w, self._row, 1, 1, 1)
            self._widgets.append(w)
        self._row += 1

    def _add_footer(self):
        widget = QtWidgets.QWidget(self._body)
        self._body_layout.addWidget(widget, self._row, 0, 1, 2)
        self._widgets.append(widget)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        widget.setLayout(layout)

        b1 = QtWidgets.QPushButton(self._body)
        b1.setText(N_('Reset to defaults'))
        b1.setToolTip(_RESET_TO_DEFAULTS_TOOLTIP)
        b1.clicked.connect(self._reset_to_defaults)
        layout.addWidget(b1)

        b2 = QtWidgets.QPushButton(self._body)
        b2.setText(N_('Clear accum'))
        b2.setToolTip(_CLEAR_ACCUM_TOOLTIP)
        b2.clicked.connect(self._clear_accumulators)
        layout.addWidget(b2)
        self._row += 1
        self._footer = {
            'widget': widget,
            'layout': layout,
            'buttons': [b1, b2],
            'spacer': QtWidgets.QSpacerItem(0, 0,
                                            QtWidgets.QSizePolicy.Expanding,
                                            QtWidgets.QSizePolicy.Minimum),
        }
        layout.addItem(self._footer['spacer'])

    def _reset_to_defaults(self, checked):
        self._log.info('reset to defaults')
        topic_base = f'{get_topic_name(self._unique_id)}/settings'
        # disable all streaming
        for name in SETTINGS.keys():
            if name.startswith('enable/'):
                pubsub_singleton.publish(f'{topic_base}/{name}', False)
        for name, meta in SETTINGS.items():
            meta = Metadata(meta)
            value = meta.default
            if name == 'name':
                value = self._unique_id
            pubsub_singleton.publish(f'{topic_base}/{name}', value)

    def _clear_accumulators(self, checked):
        self._log.info('clear accumulators')
        # todo

    def clear(self):
        for topic, fn in self._unsub:
            pubsub_singleton.unsubscribe(topic, fn)
        while len(self._widgets):
            w = self._widgets.pop()
            self._grid.removeWidget(w)
            w.deleteLater()

    def closeEvent(self, event):
        self.clear()
        return super().closeEvent(event)

    def _on_blink(self, value):
        for b in self._buttons_blink:
            b.setProperty('blink', value)
            b.style().unpolish(b)
            b.style().polish(b)
