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

"""
Allow the user to configure the source devices displayed on the waveform.

WARNING: this widget and feature is still under development.
"""

from joulescope_ui import N_, tooltip_format, get_topic_name
from joulescope_ui.widget_tools import CallableAction, context_menu_show
from PySide6 import QtCore, QtGui, QtWidgets
import logging

log = logging.getLogger(__name__)
_BUTTON_SIZE = (20, 20)
_TOOLTIP_TRACE_BUTTON = tooltip_format(
    N_("Enable trace"),
    N_("""\
    Click to toggle this trace.
    
    When enabled, the waveform will display this trace.
    
    When disabled, the waveform will hide this trace."""))
_TOOLTIP_TRACE_SOURCE = tooltip_format(
    N_("Select the source"),
    N_("""\
    Select the source for this trace.
    
    "default" will use the default source which is normally configured
    using the Device Control widget."""))


class _Trace(QtWidgets.QFrame):

    def __init__(self, parent, index):
        self._index = index
        self._subsources = []
        self._subsource = None
        self._priority = None
        super().__init__(parent)
        self.setProperty('active', False)
        self.setObjectName(f'trace_widget_{index + 1}')
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformSourceTraceLayout")
        self._layout.setContentsMargins(10, 1, 10, 1)
        self._layout.setSpacing(5)

        trace = QtWidgets.QPushButton(self)
        self._trace = trace
        trace.setObjectName(f'trace_{index + 1}')
        trace.setToolTip(_TOOLTIP_TRACE_BUTTON)
        trace.setFixedSize(*_BUTTON_SIZE)
        trace.setCheckable(True)
        self._layout.addWidget(trace)
        trace.clicked.connect(self._on_clicked)

        name = QtWidgets.QLabel(self)
        self._name = name
        name.setToolTip(_TOOLTIP_TRACE_SOURCE)
        name.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        name.mousePressEvent = self._on_name_mousePressEvent
        self._layout.addWidget(name)

    @property
    def topic(self):
        return self.parent().topic

    @property
    def pubsub(self):
        return self.parent().pubsub

    @QtCore.Slot(bool)
    def _on_clicked(self, checked):
        self._on_enable(checked)

    def _name_menu_factory(self, subsource):
        topic = f'{self.topic}/settings/trace_subsources'
        def on_action(checked=False):
            value = self.pubsub.query(topic)
            if value[self._index] != subsource:
                value = list(value)
                value[self._index] = subsource
                self.pubsub.publish(topic, value)
        return on_action

    def _source_to_name(self, source):
        subsource = source.split('.')[-1]
        return self.pubsub.query(f'{get_topic_name(subsource)}/settings/name', default=subsource)

    def _update(self):
        if self._priority is None or self._subsource is None:
            self._name.setText(N_('off'))
        else:
            block_signals_state = self._trace.blockSignals(True)
            self._trace.setChecked(True)
            self._trace.blockSignals(block_signals_state)
            name = self._source_to_name(self._subsource)
            self._name.setText(name)
        self.setProperty('active', self._priority == 0)
        self.style().unpolish(self)
        self.style().polish(self)

    def on_subsources(self, subsources):
        self._subsources = list(subsources)
        self._update()

    def on_trace_subsource(self, subsource):
        self._subsource = subsource
        self._update()

    def on_trace_priority(self, priority):
        self._priority = priority
        self._update()

    def _on_enable(self, enabled):
        topic = f'{self.topic}/settings/trace_priority'
        value = list(self.pubsub.query(topic))
        if enabled:
            value = [None if x is None else x - 1 for x in value]
            value[self._index] = 0
        else:
            value[self._index] = None
        self.pubsub.publish(topic, value)

    def _on_name_mousePressEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton:
            self._on_enable(True)
        elif event.button() == QtCore.Qt.RightButton:
            menu = QtWidgets.QMenu(self)
            group = QtGui.QActionGroup(menu)
            group.setExclusive(True)
            for fullname in ['default'] + self._subsources:
                name = self._source_to_name(fullname)
                CallableAction(group, name, self._name_menu_factory(fullname),
                               checkable=True, checked=(fullname == self._subsource))
            context_menu_show(menu, event)


class WaveformSourceWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        self._traces = []
        self._subsources = []
        self._trace_subsources = ['default', None, None, None]
        self._trace_priorities = [0, None, None, None],
        QtWidgets.QWidget.__init__(self, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.setObjectName("WaveformSourceWidget")
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setObjectName("WaveformSourceLayout")
        self._layout.setContentsMargins(-1, 1, -1, 1)
        self._layout.setSpacing(10)

        self._spacer_l = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer_l)

        for i in range(4):
            t = _Trace(self, i)
            self._layout.addWidget(t)
            self._traces.append(t)

        self._spacer_r = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self._layout.addItem(self._spacer_r)

        self._visible_update()

    @property
    def topic(self):
        return self.parent().topic

    @property
    def pubsub(self):
        return self.parent().pubsub

    def _is_needed(self):
        if len(self._subsources) > 1:
            return True
        if not len(self._subsources):
            return False
        if self._trace_priorities[1:] != [None, None, None]:
            return True
        for self._trace_subsources[0] in ['default', self._subsources[0]]:
            return False
        return True

    def _visible_update(self):
        self.setVisible(self._is_needed())

    def _on_subsources(self, topic, value):
        self._subsources = value
        for idx, trace in enumerate(self._traces):
            trace.on_subsources(value)
        self._visible_update()

    def _on_trace_subsources(self, topic, value):
        self._trace_subsources = value
        for idx, trace in enumerate(self._traces):
            trace.on_trace_subsource(value[idx])
        self._visible_update()

    def _on_trace_priority(self, topic, value):
        self._trace_priorities = value
        for idx, trace in enumerate(self._traces):
            trace.on_trace_priority(value[idx])
        self._visible_update()

    def on_pubsub_register(self, pubsub):
        topic = self.topic
        pubsub.subscribe(f'{topic}/settings/subsources', self._on_subsources, ['pub', 'retain'])
        pubsub.subscribe(f'{topic}/settings/trace_subsources', self._on_trace_subsources, ['pub', 'retain'])
        pubsub.subscribe(f'{topic}/settings/trace_priority', self._on_trace_priority, ['pub', 'retain'])
