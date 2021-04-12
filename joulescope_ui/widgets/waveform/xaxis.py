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

from PySide2 import QtCore, QtWidgets
from .marker import Marker, Z_MARKER_NORMAL, Z_MARKER_ACTIVE
from .marker_area import MarkerArea
import numpy as np
from typing import Dict, List, Tuple
import pyqtgraph as pg
from . axis_item_patch import AxisItemPatch
import logging


log = logging.getLogger(__name__)


class AxisMenu(QtWidgets.QMenu):

    def __init__(self):
        QtWidgets.QMenu.__init__(self)
        self.annotations = self.addMenu('&Annotations')

        self.single_marker = QtWidgets.QAction('&Single marker')
        self.annotations.addAction(self.single_marker)

        self.dual_markers = QtWidgets.QAction('&Dual markers')
        self.annotations.addAction(self.dual_markers)

        self.clear_all_markers = QtWidgets.QAction('&Clear all')
        self.annotations.addAction(self.clear_all_markers)


def int_to_alpha(i):
    result = ''
    while True:
        k = i % 26
        result = chr(ord('A') + k) + result
        i = (i // 26)
        if i <= 0:
            return result
        i = i - 1


class XAxis(AxisItemPatch):
    sigMarkerMoving = QtCore.Signal(str, float)

    def __init__(self, cmdp):
        pg.AxisItem.__init__(self, orientation='top')
        self._cmdp = cmdp
        self.menu = AxisMenu()
        self.menu.single_marker.triggered.connect(self.on_singleMarker)
        self.menu.dual_markers.triggered.connect(self.on_dualMarkers)
        self.menu.clear_all_markers.triggered.connect(self.on_clearAllMarkers)
        self._markers: Dict[str, Marker] = {}
        self._marker_area = MarkerArea(self)
        self._proxy = None
        self._popup_menu_pos = None

        cmdp.subscribe('Widgets/Waveform/grid_x', self._on_grid_x, update_now=True)

        cmdp.register('!Widgets/Waveform/Markers/single_add', self._cmd_waveform_marker_single_add,
                      brief='Add a single marker to the waveform widget.',
                      detail='value is x-axis time coordinate in seconds for the marker.')
        cmdp.register('!Widgets/Waveform/Markers/dual_add', self._cmd_waveform_marker_dual_add,
                      brief='Add a dual marker pair to the waveform widget.',
                      detail='value is a list containing:\n' +
                             'x1: The initial x-axis time coordinate in seconds for the left marker.\n' +
                             'x2: The initial x-axis time coordinate in seconds for the right marker.\n')
        cmdp.register('!Widgets/Waveform/Markers/remove', self._cmd_waveform_marker_remove,
                      brief='Remove a single marker or dual marker pair from the waveform widget.',
                      detail='The value is the list of marker names lists to remove which is either length 1' +
                             'for single markers and length 2 for dual markers.')
        cmdp.register('!Widgets/Waveform/Markers/clear', self._cmd_waveform_marker_clear,
                      brief='Remove all markers.')
        cmdp.register('!Widgets/Waveform/Markers/activate', self._cmd_waveform_marker_activate,
                      brief='Activate the list of markers')
        cmdp.register('!Widgets/Waveform/Markers/restore', self._cmd_waveform_marker_restore,
                      brief='Restore removed markers (for undo support).')
        cmdp.register('!Widgets/Waveform/Markers/move', self._cmd_waveform_marker_move,
                      brief='Move list of markers given as [name, new_pos, old_pos].')

    def add_to_scene(self):
        self._marker_area.add_to_scene()

    def _on_grid_x(self, topic, value):
        self.setGrid(128 if bool(value) else 0)

    def _find_first_unused_marker_index(self):
        idx = 1
        while True:
            name = str(idx)
            name1 = name + 'a'
            if name not in self._markers and name1 not in self._markers:
                return idx
            idx += 1

    def _marker_color(self, idx):
        idx = 1 + ((idx - 1) % 6)  # have 6 colors
        colors = self._cmdp['Appearance/__index__']['colors']
        color = f'waveform_marker{idx}'
        return colors.get(color, '#808080')

    def _position_markers(self, positions):
        """Position markers to avoid overlaying existing markers.

        :param positions: The list of desired marker locations.
        :return: The list of actual marker locations.
        """
        positions_start = [k for k in positions]
        m = np.array([m.get_pos() for m in self._markers.values()])
        x1, x2 = self.range
        incr = (x2 - x1) / 80
        while max(positions) < x2:
            if all([np.all(np.abs(m - p) > incr) for p in positions]):
                return positions
            positions = [k + incr for k in positions]
        return positions_start

    def _cmd_waveform_marker_single_add(self, topic, value):
        log.info('marker_single_add(%s)', value)
        x1, x2 = self.range
        if value is None:
            x = self._position_markers([(x1 + x2) / 2])[0]
        else:
            x = value
            x = min(max(x, x1), x2)
        idx = self._find_first_unused_marker_index()
        name = str(idx)
        color = self._marker_color(idx)
        self._marker_add(name, shape='full', pos=x, color=color, statistics='right')
        self.marker_moving_emit(name, x)
        self._cmd_waveform_marker_activate(None, [name])
        self._cmdp.publish('Widgets/Waveform/#requests/refresh_markers', [name])
        return '!Widgets/Waveform/Markers/remove', [[name]]

    def _cmd_waveform_marker_dual_add(self, topic, value):
        log.info('marker_dual_add(%s)', value)
        if value is None:
            x1, x2 = self.range
            xc = (x1 + x2) / 2
            xs = (x2 - x1) / 10
            x1, x2 = xc - xs, xc + xs
            x1, x2 = self._position_markers([x1, x2])
        elif len(value) == 1:
            x = value[0]
            xa, xb = self.range
            xr = (xb - xa) * 0.05
            x1, x2 = x - xr, x + xr
        elif len(value) == 2:
            x1, x2 = value
        else:
            raise ValueError(f'unsupported dual marker value: {value}')
        idx = self._find_first_unused_marker_index()
        name = str(idx)
        name1, name2 = name + 'a', name + 'b'
        color = self._marker_color(idx)
        mleft = self._marker_add(name1, shape='left', pos=x1, color=color, statistics='off')
        mright = self._marker_add(name2, shape='right', pos=x2, color=color, statistics='right')
        mleft.pair = mright
        mright.pair = mleft
        self.marker_moving_emit(name1, x1)
        self.marker_moving_emit(name2, x2)
        self._cmd_waveform_marker_activate(None, [name1, name2])
        self._cmdp.publish('Widgets/Waveform/#requests/refresh_markers', [name1, name2])
        return '!Widgets/Waveform/Markers/remove', [[name1, name2]]

    def _cmd_waveform_marker_remove(self, topic, value):
        log.info('marker_remove(%s)', value)
        states = []
        for v in value:
            states.append(self.marker_remove(*v))
        self._cmdp.publish('Widgets/Waveform/#requests/refresh_markers', None)
        return '!Widgets/Waveform/Markers/restore', states

    def _cmd_waveform_marker_restore(self, topic, value):
        log.info('marker_restore(%s)', value)
        names = []
        for state in value:
            if state is None or len(state) != 2:
                continue
            markers = [self._marker_add(**s) for s in state if s is not None]
            if len(markers) == 2:
                markers[0].pair = markers[1]
                markers[1].pair = markers[0]
            for m in markers:
                self.marker_moving_emit(m.name, m.get_pos())
            names.append([x.name for x in markers])
        return '!Widgets/Waveform/Markers/remove', names

    def _cmd_waveform_marker_clear(self, topic, value):
        log.info('marker_clear(%s)', value)
        removal = []
        for marker in self._markers.values():
            if marker.pair is not None:
                if marker.is_left:
                    removal.append([marker, marker.pair])
            else:
                removal.append([marker])
        return self._cmd_waveform_marker_remove(None, removal)

    def _cmd_waveform_marker_activate(self, topic, value):
        active = []
        for name, marker in self._markers.items():
            if marker.zValue() >= Z_MARKER_ACTIVE:
                active.append(name)
            z = Z_MARKER_ACTIVE if name in value else Z_MARKER_NORMAL
            marker.setZValue(z)
        return '!Widgets/Waveform/Markers/activate', active

    def _cmd_waveform_marker_move(self, topic, value):
        undo = []
        for name, new_pos, old_pos in value:
            self._markers[name].set_pos(new_pos)
            undo.append([name, old_pos, new_pos])
        return '!Widgets/Waveform/Markers/move', undo

    def on_singleMarker(self):
        x = self._popup_menu_pos.x()
        self._cmdp.invoke('!Widgets/Waveform/Markers/single_add', x)

    def on_dualMarkers(self):
        x = self._popup_menu_pos.x()
        self._cmdp.invoke('!Widgets/Waveform/Markers/dual_add', [x])

    def on_clearAllMarkers(self):
        self._cmdp.invoke('!Widgets/Waveform/Markers/clear', None)

    def linkedViewChanged(self, view, newRange=None):
        pg.AxisItem.linkedViewChanged(self, view=view, newRange=newRange)
        for marker in self._markers.values():
            marker.viewTransformChanged()

    def _marker_add(self, name, **state):
        if name in self._markers:
            raise RuntimeError('_marker_add internal error: name %s already exists', name)
        marker = Marker(cmdp=self._cmdp, name=name, x_axis=self, state=state)
        for item in [marker] + marker.graphic_items:
            item.setParentItem(self._marker_area)
        self._markers[name] = marker
        marker.show()
        if self._proxy is None:
            self._proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._mouseMoveEvent)
        return marker

    def marker_get(self, name):
        if name is None:
            return None
        elif isinstance(name, Marker):
            name = name.name
        return self._markers.get(name)

    def _marker_remove_one(self, m):
        if m is None:
            return None
        self._markers.pop(m.name)
        m.setVisible(False)
        state = m.remove()
        # marker.prepareGeometryChange()
        # self.scene().removeItem(marker)  # removing from scene causes crash... ugh
        # ViewBox has crash workaround for this case - incorporate here?
        return state

    def marker_remove(self, m1, m2=None):
        m1 = self.marker_get(m1)
        m2 = self.marker_get(m2)
        if m1 is not None and m2 is not None:
            if m1.pair is not None and m1.pair != m2:
                log.error('dual marker mismatch')
                self._marker_remove_one(m1.pair)
            if m2.pair is not None and m2.pair != m1:
                log.error('dual marker mismatch')
                self._marker_remove_one(m2.pair)
        return [self._marker_remove_one(m1),
                self._marker_remove_one(m2)]

    @property
    def markers(self) -> Dict[str, Marker]:
        # WARNING: for reference only
        return self._markers

    def markers_single(self) -> List[Marker]:
        return [m for m in self._markers.values() if m.is_single]

    def markers_dual(self) -> List[Tuple[Marker, Marker]]:
        return [(m.pair, m) for m in self._markers.values() if m.is_right]

    def markers_clear(self):
        while self._markers:
            m = next(iter(self._markers.values()))
            self.marker_remove(m)

    def marker_moving_emit(self, marker_name, marker_pos):
        self.sigMarkerMoving.emit(marker_name, marker_pos)

    def _mouseMoveEvent(self, ev):
        """Handle mouse movements for every mouse movement within the widget"""
        pos = ev[0]
        b1 = self.geometry()
        if pos.y() < b1.top():
            return
        p = self.linkedView().mapSceneToView(pos)
        x = p.x()
        x_min, x_max = self.range
        if x < x_min:
            x = x_min
        elif x > x_max:
            x = x_max

        for marker in self._markers.values():
            if marker.moving:
                marker.set_pos(x + marker.moving_offset)

    def mouseClickEvent(self, event):
        if self.linkedView() is None:
            return
        pos = event.scenePos()
        if self.geometry().contains(pos):
            log.info('mouseClickEvent(%s)', event)
            if event.button() == QtCore.Qt.RightButton:
                self._popup_menu_pos = self.linkedView().mapSceneToView(pos)
                event.accept()
                # self.scene().addParentContextMenus(self, self.menu, event)
                self.menu.popup(event.screenPos().toPoint())

    def wheelEvent(self, event, axis=None):
        pos = event.scenePos()
        vb = self.linkedView()
        if vb is not None and self.geometry().contains(pos):
            vb.process_wheel_event(event)
        else:
            event.setAccepted(False)

