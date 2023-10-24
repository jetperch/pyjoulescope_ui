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
from joulescope_ui import N_, tooltip_format, pubsub_singleton, get_topic_name


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


class FuseWidget(QtWidgets.QWidget):

    def __init__(self, parent, unique_id, fuse_id):
        self._parent = parent
        self.unique_id = unique_id
        self.fuse_id = fuse_id
        self._widgets = []
        self._engaged_button = None
        self._enabled_button = None
        self._row = 0
        self._unsub = []  # (topic, fn)
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
        self._header_layout.addWidget(self._construct_engaged_button())
        self._header_layout.addWidget(self._construct_enable_button())
        self._expanding.header_ex_widget = self._header

        self._body = QtWidgets.QWidget()
        self._layout = QtWidgets.QGridLayout(self._body)
        self._expanding.body_widget = self._body

        t1 = self._add_field(N_('Threshold 1'), 'A', _THRESHOLD1_TOOLTIP, [0.01, 10, 0.001])
        t2 = self._add_field(N_('Threshold 2'), 'A', _THRESHOLD2_TOOLTIP, [0.01, 10, 0.001])
        d = self._add_field(N_('Duration'), 's', _DURATION_TOOLTIP, [0.001, 5, 0.001])

        # todo - add graph

        tau_label = QtWidgets.QLabel('τ', self)
        self._tau = QtWidgets.QLabel(self)
        tau_units = QtWidgets.QLabel('s', self)
        self._add_row([tau_label, self._tau, tau_units], _TIME_CONSTANT_TOOLTIP)

        self._subscribe('registry/ui/events/blink_slow', self._on_blink)

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

    def _subscribe(self, topic, update_fn):
        pubsub_singleton.subscribe(topic, update_fn, ['pub', 'retain'])
        self._unsub.append((topic, update_fn))

    def clear(self):
        for topic, fn in self._unsub:
            pubsub_singleton.unsubscribe(topic, fn)

    def closeEvent(self, event):
        self._log.info('closeEvent')
        self.clear()
        return super().closeEvent(event)

    def on_pubsub_unregister(self):
        self.clear()

    def _on_blink(self, value):
        b = self._engaged_button
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

    def _construct_engaged_button(self):
        #topic = f'{get_topic_name(self.unique_id)}/settings/target_power'
        #meta = pubsub_singleton.metadata(topic)
        b = self._construct_pushbutton('target_power')

        def update_from_pubsub(value):
            block_state = b.blockSignals(True)
            b.setChecked(bool(value))
            b.blockSignals(block_state)

        self._engaged_button = b
        #self._subscribe(topic, update_from_pubsub)
        #b.toggled.connect(lambda checked: pubsub_singleton.publish(topic, bool(checked)))
        return b

    def _construct_enable_button(self):
        self_topic = get_topic_name(self.unique_id)
        b = self._construct_pushbutton('open')
        if self.fuse_id >= 30:
            b.setChecked(True)
            b.setEnabled(False)

        #self._subscribe(state_topic, state_from_pubsub)
        #b.toggled.connect(on_toggle)
        return b