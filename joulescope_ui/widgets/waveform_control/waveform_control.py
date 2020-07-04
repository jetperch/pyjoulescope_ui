# Copyright 2019 Jetperch LLC
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

from PySide2 import QtCore, QtGui, QtWidgets
from joulescope_ui.preferences_ui import widget_factory
from joulescope_ui.widgets.waveform.signal_def import signal_def
import sys
import logging
log = logging.getLogger(__name__)


MARKER_REPOSITIION = """\
<p>To reposition the marker, left click on the marker, move the mouse to the new location,
and the left click again.</p>
"""


TOOLTIP_MARKER_SINGLE_ADD = f"""<html><body>
<p>Add a single marker to the waveform.</p>
{MARKER_REPOSITIION}
<p>You can also add a marker by right-clicking on the x-axis, 
then selecting <b>Annotations</b> → <b>Single Marker</b>.</p>
</body></html>
"""


TOOLTIP_MARKER_DUAL_ADD = f"""<html><body>
<p>Add a dual markers to the waveform.</p>
{MARKER_REPOSITIION}
<p>You can also add dual markers by right-clicking on the x-axis,
then selecting <b>Annotations</b> → <b>Dual Markers</b>.</p>
</body></html>
"""


TOOLTIP_MARKER_CLEAR = """<html><body>
<p>Clear all markers.</p>
</body></html>
"""


ZOOM_TIP = """\
<p>You can also zoom by positioning the mouse over the waveform and 
then using the scroll wheel.</p>"""


TOOLTIP_X_AXIS_ZOOM_IN = f"""<html><body>
<p>Zoom in on the x-axis.</p>
{ZOOM_TIP}
</body></html>
"""


TOOLTIP_X_AXIS_ZOOM_OUT = f"""<html><body>
<p>Zoom out on the x-axis.</p>
{ZOOM_TIP}
</body></html>
"""


TOOLTIP_X_AXIS_ZOOM_ALL = f"""<html><body>
<p>Zoom out to the full extents of the x-axis.</p>
</body></html>
"""


TOOLTIP_SIGNAL = """<html><body>
<p>Toggle the <b>{name}</b> signal display in the Waveform widget.</p>
</body></html>
"""


class WaveformControlWidget(QtWidgets.QWidget):

    def __init__(self, parent, cmdp, state_preference):
        QtWidgets.QWidget.__init__(self, parent)
        self._cmdp = cmdp
        self._buttons = []
        self.setObjectName("WaveformControlWidget")
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformControlLayout")
        self._layout.setContentsMargins(-1, 1, -1, 1)

        self._markers_label = QtWidgets.QLabel(self)
        self._markers_label.setText('Markers:')
        self._layout.addWidget(self._markers_label)

        self._add_button('Add Single', self._on_markers_single_add, TOOLTIP_MARKER_SINGLE_ADD)
        self._add_button('Add Dual', self._on_markers_dual_add, TOOLTIP_MARKER_DUAL_ADD)
        self._add_button('Clear', self._on_markers_clear, TOOLTIP_MARKER_CLEAR)

        self._x_axis_label = QtWidgets.QLabel(self)
        self._x_axis_label.setText('X-Axis:')
        self._layout.addWidget(self._x_axis_label)

        self._add_icon('zoom_in', self._on_x_axis_zoom_in, TOOLTIP_X_AXIS_ZOOM_IN)
        self._add_icon('zoom_out', self._on_x_axis_zoom_out, TOOLTIP_X_AXIS_ZOOM_OUT)
        self._add_icon('zoom_all', self._on_x_axis_zoom_all, TOOLTIP_X_AXIS_ZOOM_ALL)

        self._show_min_max_label = QtWidgets.QLabel(self)
        self._show_min_max_label.setText('Min/Max:')
        self._layout.addWidget(self._show_min_max_label)

        self._show_min_max = widget_factory(self._cmdp, 'Widgets/Waveform/show_min_max')
        self._show_min_max_widget = self._show_min_max.widget_construct(self)
        self._layout.addWidget(self._show_min_max_widget)

        self._signals_label = QtWidgets.QLabel(self)
        self._signals_label.setText('Signals:')
        self._layout.addWidget(self._signals_label)
        self._signals = {}
        for signal in signal_def:
            self._add_signal(signal)

        self._spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding,
                                             QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        h = self.minimumSizeHint().height()
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)
        self.updateGeometry()
        self._cmdp.subscribe('Widgets/Waveform/_signals', self._on_signals_active, update_now=True)

    def _add_button(self, label, callback, tooltip):
        button = QtWidgets.QPushButton(self)
        button.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        button.setText(label)
        button.setToolTip(tooltip)
        self._layout.addWidget(button)
        button.clicked.connect(callback)
        self._buttons.append((button, None))

    def _add_icon(self, resource_name, callback, tooltip):
        button = QtWidgets.QPushButton(self)
        button.setObjectName(resource_name)
        button.setToolTip(tooltip)
        button.setStyleSheet(f'image: url(":/style/{resource_name}.svg")')
        button.setFixedSize(24, 24)
        self._layout.addWidget(button)
        button.clicked.connect(callback)
        self._buttons.append(button)

    def _add_signal(self, signal):
        button = QtWidgets.QPushButton(self)
        button.setCheckable(True)
        button.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        name = signal['name']
        abbr = signal['abbreviation']
        button.setText(abbr)
        button.setToolTip(TOOLTIP_SIGNAL.format(name=name))
        if sys.platform == 'win32':
            width = button.fontMetrics().boundingRect(abbr).width()
            button.setMinimumWidth(width + 10)
            button.setMaximumWidth(width + 10)
        self._layout.addWidget(button)
        button.clicked.connect(lambda checked: self._on_signal_button(name, checked))
        self._signals[name] = button

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
        self._cmdp.invoke('!Widgets/Waveform/Markers/single_add', None)

    @QtCore.Slot(bool)
    def _on_markers_dual_add(self, checked):
        self._cmdp.invoke('!Widgets/Waveform/Markers/dual_add', None)

    @QtCore.Slot(bool)
    def _on_markers_clear(self, checked):
        self._cmdp.invoke('!Widgets/Waveform/Markers/clear', None)

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_in(self, checked):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/zoom', 1)

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_out(self, checked):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/zoom', -1)

    @QtCore.Slot(bool)
    def _on_x_axis_zoom_all(self, checked):
        self._cmdp.invoke('!Widgets/Waveform/x-axis/zoom_all', None)


def widget_register(cmdp):
    return {
        'name': 'Waveform Control',
        'brief': 'Controls for the Waveform Widget.',
        'class': WaveformControlWidget,
        'location': QtCore.Qt.RightDockWidgetArea,
        'singleton': True,
        'sizePolicy': ['expanding', 'minimum'],
    }
