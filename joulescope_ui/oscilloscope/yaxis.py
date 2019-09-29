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

from PySide2 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import logging


log = logging.getLogger(__name__)


class YAxisMenu(QtGui.QMenu):

    def __init__(self, log_enable=None):
        QtGui.QMenu.__init__(self)
        self.setTitle('Y Axis')

        # range
        self.range = QtGui.QMenu()
        self.range.setTitle('Range')
        self.range_group = QtGui.QActionGroup(self)
        self.range_group.setExclusive(True)
        self.range_auto = QtGui.QAction(
            '&Auto', self.range_group,
            checkable=True,
            toolTip='Automatically adjust the y-axis range to show all visible data.'
        )
        self.range_auto.setChecked(True)
        self.range.addAction(self.range_auto)
        self.range_group.addAction(self.range_auto)
        self.range_manual = QtGui.QAction(
            '&Manual', self.range_group,
            checkable=True,
            toolTip='Manually zoom and pan the y-axis range.'
        )
        self.range.addAction(self.range_manual)
        self.range_group.addAction(self.range_manual)
        self.addMenu(self.range)

        self.scale = QtGui.QMenu()
        self.scale.setTitle('Scale')
        self.scale_group = QtGui.QActionGroup(self)
        self.scale_group.setExclusive(True)

        self.scale_linear = QtGui.QAction(
            '&Linear', self.scale_group,
            checkable=True,
            toolTip='Use a "normal" linear y-axis scale.'
        )
        self.scale_linear.setChecked(True)
        self.scale.addAction(self.scale_linear)
        self.scale_group.addAction(self.scale_linear)

        self.scale_logarithmic = QtGui.QAction(
            'Lo&garithmic', self.scale_group,
            checkable=True,
            toolTip='Use a logarithmic y-axis scale.'
        )
        self.scale.addAction(self.scale_logarithmic)
        self.scale_group.addAction(self.scale_logarithmic)
        if log_enable:
            self.addMenu(self.scale)

        self.hide_request = QtGui.QAction('&Hide', self)
        self.hide_request.setToolTip('Hide this signal.')
        self.addAction(self.hide_request)

    def range_set(self, value):
        if value == 'manual':
            self.range_auto.setChecked(False)
            self.range_manual.setChecked(True)
        else:
            self.range_auto.setChecked(True)
            self.range_manual.setChecked(False)

    def scale_set(self, value):
        if value == 'logarithmic':
            self.scale_linear.setChecked(False)
            self.scale_logarithmic.setChecked(True)
        else:
            self.scale_linear.setChecked(True)
            self.scale_logarithmic.setChecked(False)


class YAxis(pg.AxisItem):

    sigConfigEvent = QtCore.Signal(object)
    """Indicate a potential configuration event change.
    
    :param configuration: The dict of parameter-value pairs which include:
        * autorange: True - automatically determine min/max extents to display.
          False - allow the user to manually pan and zoom.
        * scale: 
          * 'linear': display in a "normal" linear scale
          * 'logarithmic': Display the y-axis in logarithmic scale.
    """

    sigWheelZoomYEvent = QtCore.Signal(float, float)
    """A scroll wheel zoom event.

     :param y: The y-axis location in axis coordinates. 
     :param delta: The scroll wheel delta.
     """

    sigPanYEvent = QtCore.Signal(object, float)
    """A pan y event.

    :param command: One of ['start', 'drag', 'finish', 'abort']
    :param y: The y-axis delta from the start in axis coordinates. 
    """

    sigHideRequestEvent = QtCore.Signal(str)
    """Request to hide this signal.
    
    :param name: The name of the signal to hide.
    """

    def __init__(self, name, log_enable=None):
        pg.AxisItem.__init__(self, orientation='left')
        self._name = name
        self.log = logging.getLogger(__name__ + '.' + name)
        self._pan = None
        self.menu = YAxisMenu(log_enable=log_enable)
        self.config = {
            'range': 'auto',
            'scale': 'linear',
        }
        self.menu.range_auto.triggered.connect(lambda: self._config_update(range='auto'))
        self.menu.range_manual.triggered.connect(lambda: self._config_update(range='manual'))
        self.menu.scale_linear.triggered.connect(lambda: self._config_update(scale='linear'))
        self.menu.scale_logarithmic.triggered.connect(lambda: self._config_update(scale='logarithmic'))
        self.menu.hide_request.triggered.connect(lambda: self.sigHideRequestEvent.emit(self._name))
        self._markers = {}
        self._proxy = None
        self._popup_menu_pos = None

    def _config_update(self, **kwargs):
        log.info('config update: %s', str(kwargs))
        self.config.update(**kwargs)
        self.sigConfigEvent.emit(self.config.copy())

    def range_set(self, value):
        self.config['range'] = value
        self.menu.range_set(value)

    def mouseClickEvent(self, event, axis=None):
        if self.linkedView() is None:
            return
        pos = event.scenePos()
        if self.geometry().contains(pos):
            self.log.info('mouseClickEvent(%s)', event)
            event.accept()
            if event.button() == QtCore.Qt.RightButton:
                self._popup_menu_pos = self.linkedView().mapSceneToView(pos)
                # self.scene().addParentContextMenus(self, self.menu, event)
                self.menu.popup(event.screenPos().toPoint())

    def mouseDragEvent(self, event, axis=None):
        vb = self.linkedView()
        if vb is None:
            return
        pos = event.scenePos()
        if self.geometry().contains(pos):
            self.log.info('mouseDragEvent(%s)', event)
            event.accept()
            if self.config['range'] == 'manual':
                [x_min, x_max], [y_min, y_max] = vb.viewRange()
                pmin = vb.mapViewToScene(pg.Point(x_min, y_min))
                pmax = vb.mapViewToScene(pg.Point(x_max, y_max))

                yview_range = y_max - y_min
                yscene_range = pmax.y() - pmin.y()
                pnow_y = event.scenePos().y()

                if self._pan is not None:
                    dx = (pnow_y - self._pan[1]) * yview_range / yscene_range
                    self._pan[0] += dx
                    self._pan[1] = pnow_y

                if event.button() & QtCore.Qt.LeftButton:
                    if event.isFinish():
                        if self._pan is not None:
                            pan_x, self._pan = self._pan[0], None
                            self.sigPanYEvent.emit('finish', pan_x)
                    elif self._pan is None:
                        self._pan = [0.0, pnow_y]
                        self.sigPanYEvent.emit('start', 0.0)
                    else:
                        self.sigPanYEvent.emit('drag', self._pan[0])

    def wheelEvent(self, event, axis=None):
        vb = self.linkedView()
        if vb is None:
            return
        pos = event.scenePos()
        if self.geometry().contains(pos):
            self.log.info('wheelEvent(%s)', event)
            event.accept()
            if self.config['range'] == 'manual':
                p = vb.mapSceneToView(event.scenePos())
                self.sigWheelZoomYEvent.emit(p.y(), event.delta())
        else:
            event.setAccepted(False)
        # p = self.mapSceneToView(ev.scenePos())
        # self.sigWheelZoomXEvent.emit(p.x(), ev.delta())
