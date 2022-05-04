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

import logging
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets
from .cdf_config_widget import Ui_Dialog
from . import plugin_helpers


log = logging.getLogger(__name__)


class CdfImpl:

    def __init__(self, name):
        if name not in ['cdf', 'ccdf']:
            raise ValueError(f'name={name}')
        self._name = name
        self._cfg = None
        self.hist = np.asarray([])
        self.bin_edges = np.asarray([])
        self._win = None
        self._label = None
        self._bg = None

    def run_pre(self, data):
        rv = CDFDialog().exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):
        signal = self._cfg['signal']
        if self._name == 'cdf':
            self.hist, bin_edges = plugin_helpers.cdf(data, signal)
        elif self._name == 'ccdf':
            self.hist, bin_edges = plugin_helpers.ccdf(data, signal)
        else:
            raise ValueError(f'name={self._name}')
        self.bin_edges = bin_edges[:-1]

    def run_post(self, data):
        if self.hist.size == 0 or self.bin_edges.size == 0:
            log.error('data is empty')
            return

        title = f'{self._cfg["signal"]} : {self._name}'
        self._win = pg.GraphicsLayoutWidget(show=True, title=title)
        p = self._win.addPlot(row=1, col=0)
        p.getAxis('left').setGrid(128)
        p.getAxis('bottom').setGrid(128)

        self._label = pg.LabelItem(justify='right')
        self._bg = pg.PlotDataItem(x=self.bin_edges, y=self.hist, pen='r')
        p.addItem(self._bg)
        self._win.addItem(self._label, row=0, col=0)

        p.setLabels(left='Probability', bottom=self._cfg['signal'])
        p.setXRange(self.bin_edges[0], self.bin_edges[-1], padding=0.05)
        p.setYRange(np.nanmin(self.hist), np.nanmax(self.hist), padding=0.05)

        def mouseMoved(evt):
            pos = evt[0]
            if p.sceneBoundingRect().contains(pos):
                mousePoint = p.vb.mapSceneToView(pos)
                xval = mousePoint.x()
                index = np.searchsorted(self.bin_edges, xval) - 1
                if index >= 0 and index < len(self.bin_edges):
                    self._label.setText(
                        "<span style='font-size: 12pt'>{}={:.5f}</span>,   <span style='color: yellow; font-size:12pt'>probability: {:.5f}</span>".format(
                            self._cfg['signal'], mousePoint.x(), self.hist[index])
                    )

        self.proxy = pg.SignalProxy(
            p.scene().sigMouseMoved, rateLimit=60, slot=mouseMoved)

        self._win.closeEvent = lambda evt: data.on_tool_finished()
        return True


class CDFDialog(QtWidgets.QDialog):
    def __init__(self):
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

    def exec_(self):
        if QtWidgets.QDialog.exec_(self) == 1:
            signal = str(self.ui.signal.currentText())
            return {
                'signal': signal,
            }
        else:
            return None

