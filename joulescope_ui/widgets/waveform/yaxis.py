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
import pyqtgraph as pg
import logging


log = logging.getLogger(__name__)


class YAxisMenu(QtWidgets.QMenu):

    def __init__(self, log_enable=None):
        QtWidgets.QMenu.__init__(self)
        self.setTitle('Y Axis')

        # range
        self.range = QtWidgets.QMenu()
        self.range.setTitle('Range')
        self.range_group = QtWidgets.QActionGroup(self)
        self.range_group.setExclusive(True)
        self.range_auto = QtWidgets.QAction(
            '&Auto', self.range_group,
            checkable=True,
            toolTip='Automatically adjust the y-axis range to show all visible data.'
        )
        self.range_auto.setChecked(True)
        self.range.addAction(self.range_auto)
        self.range_group.addAction(self.range_auto)
        self.range_manual = QtWidgets.QAction(
            '&Manual', self.range_group,
            checkable=True,
            toolTip='Manually zoom and pan the y-axis range.'
        )
        self.range.addAction(self.range_manual)
        self.range_group.addAction(self.range_manual)
        self.addMenu(self.range)

        self.scale = QtWidgets.QMenu()
        self.scale.setTitle('Scale')
        self.scale_group = QtWidgets.QActionGroup(self)
        self.scale_group.setExclusive(True)

        self.scale_linear = QtWidgets.QAction(
            '&Linear', self.scale_group,
            checkable=True,
            toolTip='Use a "normal" linear y-axis scale.'
        )
        self.scale_linear.setChecked(True)
        self.scale.addAction(self.scale_linear)
        self.scale_group.addAction(self.scale_linear)

        self.scale_logarithmic = QtWidgets.QAction(
            'Lo&garithmic', self.scale_group,
            checkable=True,
            toolTip='Use a logarithmic y-axis scale.'
        )
        self.scale.addAction(self.scale_logarithmic)
        self.scale_group.addAction(self.scale_logarithmic)
        if log_enable:
            self.addMenu(self.scale)

        self.hide_request = QtWidgets.QAction('&Hide', self)
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

    def __init__(self, name, cmdp, log_enable=None):
        pg.AxisItem.__init__(self, orientation='left')
        self._name = name
        self._cmdp = cmdp
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
        self.menu.hide_request.triggered.connect(self._on_hide)
        self._markers = {}
        self._proxy = None
        self._popup_menu_pos = None

    def _on_hide(self):
        self._cmdp.publish('!Widgets/Waveform/Signals/remove', self._name)

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

    def _pan_finish(self):
        if self._pan is not None:
            self.log.info('_pan_finish')
            pan_x, self._pan = self._pan[0], None
            self.sigPanYEvent.emit('finish', pan_x)

    def _pan_start(self, pnow_y):
        self._pan_finish()
        self._pan = [0.0, pnow_y]
        self.sigPanYEvent.emit('start', 0.0)

    def hoverEvent(self, event):
        vb = self.linkedView()
        if vb is None:
            return
        if event.exit:
            self._pan_finish()
        try:
            pos = event.scenePos()
        except:
            return  # no problem, not a mouse move event
        if not self.geometry().contains(pos):
            self._pan_finish()

    def mouseDragEvent(self, event, axis=None):
        vb = self.linkedView()
        if vb is None:
            return
        pos = event.scenePos()
        if self.geometry().contains(pos):
            self.log.debug('mouseDragEvent(%s)', event)
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
                        self._pan_finish()
                    elif self._pan is None:
                        self._pan_start(pnow_y)
                    else:
                        self.sigPanYEvent.emit('drag', self._pan[0])
        else:
            self._pan_finish()

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
