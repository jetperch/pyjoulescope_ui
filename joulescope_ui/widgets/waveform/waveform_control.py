# Copyright 2019-2023 Jetperch LLC
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

from joulescope_ui import pubsub_singleton, N_, get_topic_name, tooltip_format
from joulescope_ui.ui_util import comboBoxConfig
from PySide6 import QtCore, QtGui, QtWidgets
import sys
import logging
log = logging.getLogger(__name__)

_BUTTON_SIZE = (20, 20)

_MARKER_REPOSITIION = tooltip_format(
    N_(""),
    N_("""\
    When selected, prevent the display from updating.

    The UI also includes a global statistics hold button
    on the sidebar.  When the global statistics hold button
    is selected, this button is disabled and has no effect.

    The displayed values normally update with each new statistics
    data computed by the device.  When this button is selected,
    the display will not be updated.  However, the statistics
    will continue accumulate and accrue (if selected)."""))


MARKER_REPOSITIION = """\
<p>To reposition the marker, left click on the marker, move the mouse to the new location,
and the left click again.</p>
"""


_TOOLTIP_MARKER_SINGLE_ADD = tooltip_format(
    N_("Add single marker"),
    N_("""\
    Click to add a single marker to the waveform.
    
    To reposition the marker, left click on the marker, 
    move the mouse to the new location,
    and the left click again.
    
    You can also add a marker by right-clicking on the x-axis
    or in the plot area."""))

_TOOLTIP_MARKER_DUAL_ADD = tooltip_format(
    N_("Add dual markers"),
    N_("""\
    Click to add a dual markers to the waveform.

    To reposition the marker, left click on the marker, 
    move the mouse to the new location,
    and the left click again.

    You can also add a dual markers by right-clicking on the x-axis
    or in the plot area."""))

_TOOLTIP_MARKER_CLEAR = tooltip_format(
    N_("Clear all markers"),
    N_("""\
    Click to clear all markers from the waveform.
    This operation removes both single markers
    and dual markers."""))

_TOOLTIP_X_AXIS_ZOOM_IN = tooltip_format(
    N_("Zoom in"),
    N_("""\
    Click to zoom in along the time x-axis.
    
    You can also zoom by positioning the mouse over the waveform and 
    then using the scroll wheel."""))

_TOOLTIP_X_AXIS_ZOOM_OUT = tooltip_format(
    N_("Zoom out"),
    N_("""\
    Click to zoom out along the time x-axis.

    You can also zoom by positioning the mouse over the waveform and 
    then using the scroll wheel."""))

_TOOLTIP_X_AXIS_ZOOM_ALL = tooltip_format(
    N_("Zoom all"),
    N_("""\
    Click to display the full extents of the x-axis."""))

_TOOLTIP_SIGNAL = tooltip_format(
    N_("Show/hide signals"),
    N_("""\
    Click to toggle the signal axis display in the Waveform widget."""))

_SIGNALS = ['i', 'v', 'p', 'r', '0', '1', '2', '3', 'T']


class WaveformControlWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        self._pubsub = None
        self._topic = ''
        self._min_max_topic = None
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._buttons = []
        self.setObjectName("WaveformControlWidget")
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformControlLayout")
        self._layout.setContentsMargins(-1, 1, -1, 1)

        self._markers_label = QtWidgets.QLabel(self)
        self._markers_label.setText('Markers:')
        self._layout.addWidget(self._markers_label)

        self._add_button('marker_add1', self._on_markers_single_add, _TOOLTIP_MARKER_SINGLE_ADD)
        self._add_button('marker_add2', self._on_markers_dual_add, _TOOLTIP_MARKER_DUAL_ADD)
        self._add_button('marker_clear', self._on_markers_clear, _TOOLTIP_MARKER_CLEAR)

        self._x_axis_label = QtWidgets.QLabel(self)
        self._x_axis_label.setText('X-Axis:')
        self._layout.addWidget(self._x_axis_label)

        self._add_button('zoom_in', self._on_x_axis_zoom_in, _TOOLTIP_X_AXIS_ZOOM_IN)
        self._add_button('zoom_out', self._on_x_axis_zoom_out, _TOOLTIP_X_AXIS_ZOOM_OUT)
        self._add_button('zoom_all', self._on_x_axis_zoom_all, _TOOLTIP_X_AXIS_ZOOM_ALL)

        self._show_min_max_label = QtWidgets.QLabel(self)
        self._show_min_max_label.setText('Min/Max:')
        self._layout.addWidget(self._show_min_max_label)

        self._min_max_sel = QtWidgets.QComboBox(self)
        self._layout.addWidget(self._min_max_sel)
        self._on_min_max_fn = self._on_min_max
        self._min_max_sel.currentIndexChanged.connect(self._on_min_max_sel)

        self._signals_label = QtWidgets.QLabel(self)
        self._signals_label.setText('Signals:')
        self._layout.addWidget(self._signals_label)

        self._signal_holder = QtWidgets.QWidget(self)
        self._layout.addWidget(self._signal_holder)
        self._signal_layout = QtWidgets.QHBoxLayout(self._signal_holder)
        self._signal_layout.setContentsMargins(3, 0, 3, 0)
        self._signal_layout.setSpacing(3)
        self._signal_holder.setLayout(self._signal_layout)

        for signal in _SIGNALS:
            self._add_signal(signal)
#
        self._spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding,
                                             QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer)

    def on_pubsub_register(self, pubsub, topic):
        self._pubsub = pubsub
        self._topic = topic

        self._min_max_topic = f'{self._topic}/settings/show_min_max'
        meta = self._pubsub.metadata(self._min_max_topic)
        comboBoxConfig(self._min_max_sel, [x[1] for x in meta.options])
        self._pubsub.subscribe(self._min_max_topic, self._on_min_max, ['pub', 'retain'])

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._pubsub.unsubscribe(self._min_max_topic, self._on_min_max_fn)
        return super().closeEvent(event)

    def _on_min_max(self, value):
        block_signals_state = self._min_max_sel.blockSignals(True)
        self._min_max_sel.setCurrentIndex(value)
        self._min_max_sel.blockSignals(block_signals_state)

    def _on_min_max_sel(self, index):
        self._pubsub.publish(self._min_max_topic, index)

    def _add_button(self, name, callback, tooltip):
        b = QtWidgets.QPushButton(self)
        b.setObjectName(name)
        b.setToolTip(tooltip)
        b.setFixedSize(*_BUTTON_SIZE)
        self._layout.addWidget(b)
        b.clicked.connect(callback)
        self._buttons.append(b)

    def _add_signal(self, signal):
        b = QtWidgets.QPushButton(self)
        b.setText(signal)
        b.setObjectName(f'signal_button')
        b.setCheckable(True)
        b.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        b.setToolTip(_TOOLTIP_SIGNAL)
        b.setFixedSize(*_BUTTON_SIZE)
        self._signal_layout.addWidget(b)
        #button.clicked.connect(lambda checked: self._on_signal_button(name, checked))
        #self._signals[name] = button

    def _on_signal_button(self, name, checked):
        if checked:
            self._cmdp.invoke('!Widgets/Waveform/Signals/add', name)
        else:
            self._cmdp.invoke('!Widgets/Waveform/Signals/remove', name)

    def _on_signals_active(self, topic, value):
        for name, button in self._signals.items():
            checked = name in value
            if checked != button.isChecked():
                block_signals_state = button.blockSignals(True)
                button.setChecked(checked)
                button.blockSignals(block_signals_state)

    @QtCore.Slot(bool)
    def _on_markers_single_add(self, checked):
        self._pubsub.publish(f'{self._topic}/actions/!markers', 'add_single')

    @QtCore.Slot(bool)
    def _on_markers_dual_add(self, checked):
        self._pubsub.publish(f'{self._topic}/actions/!markers', 'add_dual')

    @QtCore.Slot(bool)
    def _on_markers_clear(self, checked):
        self._pubsub.publish(f'{self._topic}/actions/!markers', 'clear_all')

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_in(self, checked):
        self._pubsub.publish(f'{self._topic}/actions/!x_zoom', 1)

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_out(self, checked):
        self._pubsub.publish(f'{self._topic}/actions/!x_zoom', -1)

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_all(self, checked):
        self._pubsub.publish(f'{self._topic}/actions/!x_zoom_all', None)
