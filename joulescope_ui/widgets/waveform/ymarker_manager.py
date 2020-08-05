# Copyright 2019-2020 Jetperch LLC
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

from .signal import Signal
from .marker import Z_MARKER_NORMAL, Z_MARKER_ACTIVE
from typing import Dict
import copy
import logging


log = logging.getLogger(__name__)


class YMarkerManager:

    def __init__(self, cmdp, signals: Dict[str, Signal]):
        self._cmdp = cmdp
        self._signals = signals

        cmdp.register('!Widgets/Waveform/YMarkers/single_add', self._cmd_single_add,
                      brief='Add a single marker to the waveform widget.',
                      detail='Value is [signal, ypos]')
        cmdp.register('!Widgets/Waveform/YMarkers/dual_add', self._cmd_dual_add,
                      brief='Add a dual marker pair to the waveform widget.',
                      detail='Value is a list containing:\n' +
                             'signal: The signal name\n' +
                             'y1: The initial y-axis coordinate for the bottom marker.\n' +
                             'y2: The initial y-axis coordinate for the top marker.\n')
        cmdp.register('!Widgets/Waveform/YMarkers/remove', self._cmd_remove,
                      brief='Remove a single marker or dual marker pair from the waveform widget.',
                      detail='Value is [[signal, name], ...]')
        cmdp.register('!Widgets/Waveform/YMarkers/clear', self._cmd_clear,
                      brief='Remove all markers.',
                      detail='[signal, ...]')
        cmdp.register('!Widgets/Waveform/YMarkers/activate', self._cmd_activate,
                      brief='Activate the list of markers',
                      detail='[[signal, name], ...]')
        cmdp.register('!Widgets/Waveform/YMarkers/restore', self._cmd_restore,
                      brief='Restore removed markers (for undo support)',
                      detail='[state, ...].')
        cmdp.register('!Widgets/Waveform/YMarkers/move', self._cmd_move,
                      brief='Move list of markers.',
                      detail='[[signal, name, new_pos, old_pos], ...]')

    def _axis(self, signal_name):
        return self._signals[signal_name].y_axis

    def _cmd_single_add(self, topic, value):
        signal, ypos = value
        marker = self._axis(signal).marker_single_add(ypos)
        return '!Widgets/Waveform/YMarkers/remove', [[signal, marker.name]]

    def _cmd_dual_add(self, topic, value):
        signal, y1, y2 = value
        m1, m2 = self._axis(signal).marker_dual_add(y1, y2)
        return '!Widgets/Waveform/YMarkers/remove', [[signal, m1.name]]

    def _cmd_remove(self, topic, value):
        restore = []
        for signal, name in value:
            ax = self._axis(signal)
            states = ax.marker_remove(name)
            restore.extend(states)
        log.info('_cmd_remove: %s', restore)
        return '!Widgets/Waveform/YMarkers/restore', restore

    def _cmd_clear(self, topic, value):
        markers = []
        for signal in value:
            ax = self._axis(signal)
            markers.extend([[signal, name] for name in ax.markers.keys()])
        return self._cmd_remove(topic, markers)

    def _cmd_activate(self, topic, value):
        active = []
        signals = {s for s, _ in value}
        for signal in signals:
            ax = self._axis(signal)
            for name, marker in ax.markers.items():
                if marker.zValue() >= Z_MARKER_ACTIVE:
                    active.append([signal, name])
            if [signal, name] in value:
                z_value = Z_MARKER_ACTIVE
            else:
                z_value = Z_MARKER_NORMAL
            marker.setZValue(z_value)
        return '!Widgets/Waveform/YMarkers/activate', active

    def _cmd_restore(self, topic, value):
        remove = []
        log.info('_cmd_restore %s', value)
        for state in value:
            state = copy.deepcopy(state)
            name = state['name']
            signal = state.pop('signal')
            ax = self._axis(signal)
            ax.marker_restore(state)
            remove.append([signal, name])
        return '!Widgets/Waveform/YMarkers/remove', remove

    def _cmd_move(self, topic, value):
        undo = []
        for signal, name, new_pos, old_pos in value:
            undo.append([signal, name, old_pos, new_pos])
            self._axis(signal).markers[name].set_pos(new_pos)
        return '!Widgets/Waveform/YMarkers/move', undo

