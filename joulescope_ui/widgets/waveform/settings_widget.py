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

from PySide6 import QtGui, QtWidgets
import pyqtgraph as pg
import logging


log = logging.getLogger(__name__)


class SettingsWidget(pg.ViewBox):

    def __init__(self, cmdp):
        pg.ViewBox.__init__(self, enableMouse=False, enableMenu=False)
        self._cmdp = cmdp
        self.setToolTip('Click to adjust the waveform settings')
        self.setRange(xRange=[-1, 1], yRange=[-1, 1])
        self._text = pg.TextItem(html='<div><span style="color: #FFF; background-color: #448">Settings</span></div>',
                                 anchor=(0.5, 0.5))
        self.addItem(self._text, ignoreBounds=True)

        self._signals_available = []
        self._signals_visible = []

    def _signal_add_construct(self, name):
        def cbk():
            self._cmdp.publish('!Widgets/Waveform/Signals/add', name)
        return cbk

    def on_signalsAvailable(self, signals, visible=None):
        log.info('on_signalsAvailable(%s, %s)', [x['name'] for x in signals], visible)
        self._signals_available = signals
        self._signals_visible = visible

    def menu_exec(self, pos):
        menu = QtWidgets.QMenu()
        menu.setToolTipsVisible(True)
        signal_add = QtWidgets.QMenu()
        signal_add.setTitle('&Add')
        signal_add_actions = []

        for s in self._signals_available:
            if s['name'] not in self._signals_visible:
                a = QtGui.QAction(s['display_name'], signal_add)
                a.triggered.connect(self._signal_add_construct(s['name']))
                signal_add.addAction(a)
                signal_add_actions.append(a)
        if len(signal_add_actions):
            menu.addMenu(signal_add)
        menu.exec_(pos)

    def mouseClickEvent(self, event, axis=None):
        pos = event.scenePos()
        if self.geometry().contains(pos):
            event.accept()
            log.info('mouseClickEvent()')
            pos = event.screenPos().toPoint()
            self.menu_exec(pos)
