# Copyright 2023 Jetperch LLC
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
from joulescope_ui import N_, tooltip_format, get_topic_name
from joulescope_ui.devices.jsdrv.js220_fuse import fuse_to_config, fuse_curve
import pyqtgraph as pg
import numpy as np


FUSE_ID = {
    0: N_('Fuse 1'),
    1: N_('Fuse 2'),
    30: N_('Range fuse'),
    31: N_('Max fuse')
}

_BUTTON_SIZE = (20, 20)

_THRESHOLD1_TOOLTIP = tooltip_format(
    N_('Fuse trip threshold'),
    N_('Any current above this threshold will eventually trip the fuse.')
)

_THRESHOLD2_TOOLTIP = tooltip_format(
    N_('Fuse speed threshold'),
    N_('The fuse trips in Duration at this constant current.')
)

_DURATION_TOOLTIP = tooltip_format(
    N_('Fuse duration'),
    N_('The fuse trips in this Duration at Threshold 2 current.')
)

_TIME_CONSTANT_TOOLTIP = tooltip_format(
    N_('Fuse dissipation time constant'),
    N_("""\
    The exponential decay time constant.
    The fuse dissipates 63.2% of accumulated energy in this duration.\
    """)
)

_FUSE_STATE = N_("Fuse state indicator.  When enabled and engaged, click to clear.")


class FuseSubWidget(QtWidgets.QWidget):

    def __init__(self, parent, unique_id, fuse_id, pubsub):
        self.unique_id = unique_id
        self.fuse_id = fuse_id
        self.pubsub = pubsub
        self._value_prev = None
        self._widgets = []
        self._engaged_button = None
        self._row = 0
        super().__init__(parent)
        self._top_layout = QtWidgets.QVBoxLayout(self)
        self._top_layout.setContentsMargins(0, 0, 0, 0)
        self._top_layout.setSpacing(0)
        self._expanding = ExpandingWidget(self)
        self._expanding.title = FUSE_ID[fuse_id]
        self._top_layout.addWidget(self._expanding)

        self._header = QtWidgets.QWidget()
        self._header_layout = QtWidgets.QHBoxLayout(self._header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._engaged_button = parent.construct_engaged_button(fuse_id)
        self._header_layout.addWidget(self._engaged_button)
        self._enabled_button = self._construct_enable_button()
        self._header_layout.addWidget(self._enabled_button)
        self._expanding.header_ex_widget = self._header

        self._body = QtWidgets.QWidget()
        self._layout = QtWidgets.QGridLayout(self._body)
        self._expanding.body_widget = self._body

        self._t1 = self._add_field(N_('Threshold 1'), 'A', _THRESHOLD1_TOOLTIP, [0.01, 10, 0.001])
        self._t2 = self._add_field(N_('Threshold 2'), 'A', _THRESHOLD2_TOOLTIP, [0.01, 10, 0.001])
        self._d = self._add_field(N_('Duration'), 's', _DURATION_TOOLTIP, [0.001, 5, 0.001])
        for w in [self._t1, self._t2, self._d]:
            w.valueChanged.connect(self._on_value_changed)
        topic = get_topic_name(self.unique_id)

        tau_label = QtWidgets.QLabel('τ', self)
        self._tau = QtWidgets.QLabel(self)
        tau_units = QtWidgets.QLabel('s', self)
        self._add_row([tau_label, self._tau, tau_units], _TIME_CONSTANT_TOOLTIP)

        # add plot
        self._i = np.arange(0, 10.001, 0.001)
        self._p = pg.PlotWidget(parent=self._body, title=N_('Fuse response'))
        self._p.setLabel('left', N_('Time (s)'))
        self._p.setLabel('bottom', N_('Current (A)'))
        self._p.showGrid(True, True, alpha=0.8)
        self._p.setMinimumHeight(200)
        self._p.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._curve = self._p.plot()
        self._p_threshold1_line = pg.InfiniteLine(angle=90, movable=False)
        self._p.addItem(self._p_threshold1_line)
        self._p_threshold2_line = pg.InfiniteLine(angle=90, movable=False)
        self._p.addItem(self._p_threshold2_line)
        self._layout.addWidget(self._p, self._row, 0, 1, 3)
        self._row += 1

        self.pubsub.subscribe(f'{topic}/settings/fuse/{self.fuse_id}/config', self._on_config, ['pub', 'retain'])
        self.pubsub.subscribe('registry/ui/events/blink_slow', self._on_blink, ['pub', 'retain'])

    def _on_config(self, topic, value):
        if value is self._value_prev:
            return
        for w, v_name in [[self._t1, 'threshold1'], [self._t2, 'threshold2'], [self._d, 'duration']]:
            block_state = w.blockSignals(True)
            w.setValue(value[v_name])
            w.blockSignals(block_state)
        self._value_prev = value
        self._update()

    def _on_value_changed(self, d):
        self._value_prev = fuse_to_config(self._t1.value(), self._t2.value(), self._d.value())
        topic = get_topic_name(self.unique_id)
        topic = f'{topic}/settings/fuse/{self.fuse_id}/config'
        self.pubsub.publish(topic, self._value_prev)
        self._update()

    def _update(self):
        if self._value_prev is None:
            return
        v = self._value_prev
        tau = v['tau']
        self._tau.setText(f'{tau:.3f}')
        self._p_threshold1_line.setPos(v['threshold1'])
        self._p_threshold2_line.setPos(v['threshold2'])
        self._y = fuse_curve(v['T'], v['K'], self._i)
        idx = np.isfinite(self._y)
        i, y = self._i[idx], self._y[idx]
        self._curve.setData(i, y)
        self._p.setYRange(0, min(2, y[0]))
        self._p.setXRange(0, min(10, v['threshold2'] * 2))

    def _add_field(self, name, units, tooltip, spinbox_limits):
        label = QtWidgets.QLabel(name)
        value = QtWidgets.QDoubleSpinBox()
        units = QtWidgets.QLabel(units)
        value.setRange(spinbox_limits[0], spinbox_limits[1])
        value.setSingleStep(spinbox_limits[2])
        value.setDecimals(3)
        value.setStepType(QtWidgets.QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._add_row([label, value, units], tooltip)
        return value

    def _add_row(self, widgets, tooltip):
        for idx, w in enumerate(widgets):
            self._layout.addWidget(w, self._row, idx, 1, 1)
            w.setToolTip(tooltip)
        self._widgets.append(widgets)
        self._row += 1

    def _on_blink(self, value):
        for b in [self._engaged_button]:
            b.setProperty('blink', value)
            b.style().unpolish(b)
            b.style().polish(b)

    def _construct_pushbutton(self, name, tooltip=None):
        b = QtWidgets.QPushButton()
        b.setObjectName(name)
        b.setProperty('blink', False)
        b.setCheckable(True)
        b.setFixedSize(*_BUTTON_SIZE)
        b.setToolTip(tooltip)
        self._widgets.append(b)
        return b

    def _construct_enable_button(self):
        if self.fuse_id >= 30:
            return
        topic = get_topic_name(self.unique_id)
        topic = f'{topic}/settings/fuse/{self.fuse_id}/enable'
        b = self._construct_pushbutton('open')

        def update_from_pubsub(value):
            block_state = b.blockSignals(True)
            b.setChecked(value)
            b.blockSignals(block_state)
            self._engaged_button.setEnabled(value)

        def on_toggled(checked):
            self.pubsub.publish(topic, checked)
            self._engaged_button.setEnabled(checked)

        self.pubsub.subscribe(topic, update_from_pubsub, ['pub', 'retain'])
        b.toggled.connect(on_toggled)
        return b


class FuseWidget(QtWidgets.QWidget):

    def __init__(self, parent, unique_id, pubsub):
        self.unique_id = unique_id
        self.pubsub = pubsub
        self._widgets = []
        self._blink_buttons = []
        self._row = 0
        super().__init__(parent)
        self._top_layout = QtWidgets.QVBoxLayout(self)
        self._top_layout.setContentsMargins(0, 0, 0, 0)
        self._top_layout.setSpacing(0)
        self._expanding = ExpandingWidget(self)
        self._expanding.title = N_('Fuse')
        self._top_layout.addWidget(self._expanding)

        self._header = QtWidgets.QWidget()
        self._header_layout = QtWidgets.QHBoxLayout(self._header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.addWidget(self.construct_engaged_button(0))
        self._header_layout.addWidget(self.construct_engaged_button(1))
        self._header_layout.addWidget(self.construct_engaged_button(30))
        self._header_layout.addWidget(self.construct_engaged_button(31))
        self._expanding.header_ex_widget = self._header

        self._body = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._body)
        self._fuse1 = FuseSubWidget(self, unique_id, 0, self.pubsub)
        self._layout.addWidget(self._fuse1)
        self._fuse2 = FuseSubWidget(self, unique_id, 1, self.pubsub)
        self._layout.addWidget(self._fuse2)
        self._expanding.body_widget = self._body

        self.pubsub.subscribe('registry/ui/events/blink_slow', self._on_blink, ['pub', 'retain'])

    def _on_blink(self, value):
        for b in self._blink_buttons:
            b.setProperty('blink', value)
            b.style().unpolish(b)
            b.style().polish(b)

    def _construct_pushbutton(self, name, tooltip=None):
        b = QtWidgets.QPushButton()
        b.setObjectName(name)
        b.setProperty('blink', False)
        b.setCheckable(True)
        b.setFixedSize(*_BUTTON_SIZE)
        b.setToolTip(tooltip)
        self._widgets.append(b)
        return b

    def construct_engaged_button(self, fuse_id):
        topic = get_topic_name(self.unique_id)
        b = self._construct_pushbutton('fuse', tooltip=tooltip_format(FUSE_ID[fuse_id], _FUSE_STATE))
        mask = 1 << fuse_id

        def update_from_pubsub(value):
            value = bool(value & mask)
            block = b.blockSignals(True)
            b.setChecked(value)
            b.blockSignals(block)

        def enable_from_pubsub(value):
            b.setEnabled(value)

        def on_toggled(checked):
            if bool(checked):
                block = b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(block)
            else:
                self.pubsub.publish(f'{topic}/actions/!fuse_clear', fuse_id)

        self._blink_buttons.append(b)
        self.pubsub.subscribe(f'{topic}/settings/fuse_engaged', update_from_pubsub, ['pub', 'retain'])
        b.toggled.connect(on_toggled)
        if fuse_id < 30:
            b.setEnabled(False)
            self.pubsub.subscribe(f'{topic}/settings/fuse/{fuse_id}/enable', enable_from_pubsub, ['pub', 'retain'])

        return b
