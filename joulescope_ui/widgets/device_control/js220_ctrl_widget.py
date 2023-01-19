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
from joulescope_ui.styles import styled_widget


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

        self._add_signal_buttons()
        self._add_settings()
        self._add_gpo()
        self._add_footer()

    def _subscribe(self, topic, update_fn):
        pubsub_singleton.subscribe(topic, update_fn, ['pub', 'retain'])
        self._unsub.append((topic, update_fn))

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
            'buttons': [],
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
        self._signals['buttons'].append(b)

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
        self._signals = {
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
        layout.addItem(self._signals['spacer'])
        self._row += 1

    def _add_gpo_button(self, signal, meta):
        topic = f'{get_topic_name(self._unique_id)}/settings/out/{signal}'
        b = QtWidgets.QPushButton(self._signals['widget'])
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
        self._signals['layout'].addWidget(b)
        self._signals['buttons'].append(b)

    def _add_settings(self):
        for name, value in SETTINGS.items():
            if name.startswith('out/') or name.startswith('enable/'):
                continue
            meta = Metadata(value)
            if 'hidden' not in meta.flags:
                self._add(name, meta)

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
        lbl = QtWidgets.QLabel(meta.brief, self)
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
            pubsub_singleton.publish(f'{topic_base}/{name}', meta.default)

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
