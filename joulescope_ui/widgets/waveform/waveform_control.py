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
from joulescope_ui.widget_tools import CallableSlotAdapter
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

_TOOLTIP_PIN_LEFT = tooltip_format(
    N_("Pin left"),
    N_("""\
    Pin the waveform display to the left side.
    When enabled, the left side (oldest) data 
    always remains in view."""))

_TOOLTIP_PIN_RIGHT = tooltip_format(
    N_("Pin right"),
    N_("""\
    Pin the waveform display to the right side.
    When enabled, the right side (newest) data 
    always remains in view."""))

_TOOLTIP_Y_AXIS_ZOOM_ALL = tooltip_format(
    N_("Y zoom all"),
    N_("""\
    Click to reset the y-axis of all plots to auto ranging mode.
    
    This operation does not affect the fixed range plots such
    as the general purpose inputs."""))

_TOOLTIP_MIN_MAX = tooltip_format(
    N_("Show min/max extents"),
    N_("""\
    Change how the waveform shows the min/max extents.
    When zoomed out, each pixel may represent many samples.
    Displaying the min/max can allow you to see events
    that may be missed with just the average.
    
    "off" only displays the average.
    
    "lines" displays the minimum and maximum as separate line traces.
    
    "fill 1" displays a filled color between the minimum and maximum.
    
    "fill 2" also displays an additional fill for standard deviation."""))

_TOOLTIP_SIGNAL = tooltip_format(
    N_("Show/hide signals"),
    N_("""\
    Click to toggle the signal axis display in the Waveform widget."""))

_SIGNALS = ['i', 'v', 'p', 'r', '0', '1', '2', '3', 'T']


class WaveformControlWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        self.pubsub = None
        self.topic = ''
        self._min_max_topic = None
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._buttons = []
        self.setObjectName("WaveformControlWidget")
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformControlLayout")
        self._layout.setContentsMargins(-1, 1, -1, 1)
        self._layout.setSpacing(5)

        # non-expanding to left-justify
        self._spacer_l = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer_l)

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
        self._pin_left = self._add_button('pin_left', self._on_pin_left_click, _TOOLTIP_PIN_LEFT)
        self._pin_left.setCheckable(True)
        self._pin_right = self._add_button('pin_right', self._on_pin_right_click, _TOOLTIP_PIN_RIGHT)
        self._pin_right.setCheckable(True)
        self._add_button('y_zoom_all', self._on_y_axis_zoom_all, _TOOLTIP_Y_AXIS_ZOOM_ALL)

        self._show_min_max_label = QtWidgets.QLabel(self)
        self._show_min_max_label.setText('Min/Max:')
        self._show_min_max_label.setToolTip(_TOOLTIP_MIN_MAX)
        self._layout.addWidget(self._show_min_max_label)

        self._min_max_sel = QtWidgets.QComboBox(self)
        self._min_max_sel.setToolTip(_TOOLTIP_MIN_MAX)
        self._layout.addWidget(self._min_max_sel)
        self._min_max_sel.currentIndexChanged.connect(self._on_min_max_sel)

        self._signals_label = QtWidgets.QLabel(self)
        self._signals_label.setText('Signals:')
        self._layout.addWidget(self._signals_label)

        self._signal_holder = QtWidgets.QWidget(self)
        self._layout.addWidget(self._signal_holder)
        self._signal_layout = QtWidgets.QHBoxLayout(self._signal_holder)
        self._signal_layout.setContentsMargins(3, 0, 3, 0)
        self._signal_layout.setSpacing(3)

        self._signals = {}
        for signal in _SIGNALS:
            self._add_signal(signal)

        self._spacer_r = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer_r)

    @property
    def is_file_mode(self):
        return self._source_filter is not None and 'JlsSource' in self._source_filter

    def on_pubsub_register(self, pubsub, topic, source_filter):
        self.pubsub = pubsub
        self.topic = topic
        self._source_filter = source_filter

        self._min_max_topic = f'{self.topic}/settings/show_min_max'
        meta = self.pubsub.metadata(self._min_max_topic)
        comboBoxConfig(self._min_max_sel, [x[1] for x in meta.options])
        pubsub.subscribe(self._min_max_topic, self._on_min_max, ['pub', 'retain'])
        pin_mode = ['pub'] if self.is_file_mode else ['pub', 'retain']
        pubsub.subscribe(f'{self.topic}/settings/pin_left', self._on_pin_left, pin_mode)
        pubsub.subscribe(f'{self.topic}/settings/pin_right', self._on_pin_right, pin_mode)
        pubsub.subscribe(f'{self.topic}/settings/state', self._on_waveform_state, ['pub', 'retain'])
        if self.is_file_mode:
            self._on_pin_left_click(False)
            self._on_pin_right_click(False)
        else:
            pubsub.subscribe('registry/app/settings/signal_stream_enable',
                             self._on_signal_stream_enable, ['pub', 'retain'])

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        return super().closeEvent(event)

    def _on_waveform_state(self, value):
        for plot in value['plots']:
            name = plot['quantity']
            try:
                b = self._signals[name]
            except KeyError:
                return
            block_signals_state = b.blockSignals(True)
            b.setChecked(plot['enabled'])
            b.blockSignals(block_signals_state)

    def _on_signal_stream_enable(self, value):
        self._on_pin_left_click(value)
        self._on_pin_right_click(value)

    def _on_min_max(self, value):
        block_signals_state = self._min_max_sel.blockSignals(True)
        self._min_max_sel.setCurrentIndex(value)
        self._min_max_sel.blockSignals(block_signals_state)

    def _on_pin_left(self, value):
        block_signals_state = self._pin_left.blockSignals(True)
        self._pin_left.setChecked(bool(value))
        self._pin_left.blockSignals(block_signals_state)

    def _on_pin_right(self, value):
        block_signals_state = self._pin_right.blockSignals(True)
        self._pin_right.setChecked(bool(value))
        self._pin_right.blockSignals(block_signals_state)

    @QtCore.Slot(bool)
    def _on_pin_left_click(self, value):
        self.pubsub.publish(f'{self.topic}/settings/pin_left', bool(value))

    @QtCore.Slot(bool)
    def _on_pin_right_click(self, value):
        self.pubsub.publish(f'{self.topic}/settings/pin_right', bool(value))

    @QtCore.Slot(int)
    def _on_min_max_sel(self, index):
        self.pubsub.publish(self._min_max_topic, index)

    def _add_button(self, name, callback, tooltip):
        b = QtWidgets.QPushButton(self)
        b.setObjectName(name)
        b.setToolTip(tooltip)
        b.setFixedSize(*_BUTTON_SIZE)
        self._layout.addWidget(b)
        b.clicked.connect(callback)
        self._buttons.append(b)
        return b

    def _add_signal(self, signal):
        b = QtWidgets.QPushButton(self)
        b.setText(signal)
        b.setObjectName(f'signal_button')
        b.setCheckable(True)
        b.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        b.setToolTip(_TOOLTIP_SIGNAL)
        b.setFixedSize(*_BUTTON_SIZE)
        self._signal_layout.addWidget(b)
        self._signals[signal] = b
        adapter = CallableSlotAdapter(b, lambda checked: self._on_signal_button(signal, checked))
        b.toggled.connect(adapter.slot)
        return b

    def _on_signal_button(self, name, checked):
        self.pubsub.publish(f'{self.topic}/actions/!plot_show', [name, checked])

    def _on_signals_active(self, topic, value):
        for name, button in self._signals.items():
            checked = name in value
            if checked != button.isChecked():
                block_signals_state = button.blockSignals(True)
                button.setChecked(checked)
                button.blockSignals(block_signals_state)

    @QtCore.Slot(bool)
    def _on_markers_single_add(self, checked):
        self.pubsub.publish(f'{self.topic}/actions/!x_markers', 'add_single')

    @QtCore.Slot(bool)
    def _on_markers_dual_add(self, checked):
        self.pubsub.publish(f'{self.topic}/actions/!x_markers', 'add_dual')

    @QtCore.Slot(bool)
    def _on_markers_clear(self, checked):
        self.pubsub.publish(f'{self.topic}/actions/!x_markers', 'clear_all')

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_in(self, checked):
        self.pubsub.publish(f'{self.topic}/actions/!x_zoom', [1, None])

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_out(self, checked):
        self.pubsub.publish(f'{self.topic}/actions/!x_zoom', [-1, None])

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_all(self, checked):
        self.pubsub.publish(f'{self.topic}/actions/!x_zoom_all', None)

    @QtCore.Slot(bool)
    def _on_pin_oldest(self, checked):
        pass

    @QtCore.Slot(bool)
    def _on_pin_newest(self, checked):
        pass

    @QtCore.Slot(bool)
    def _on_y_axis_zoom_all(self, checked):
        self.pubsub.publish(f'{self.topic}/actions/!y_zoom_all', None)
