# Copyright 2020 Jetperch LLC
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
from PySide2 import QtCore, QtWidgets


log = logging.getLogger(__name__)

PLUGIN = {
    'name': 'Frequency',
    'description': 'Plot the signal in the frequency domain',
}


class Frequency:

    def __init__(self):
        self._cfg = None
        self._win = None
        self._label = None
        self._bg = None

    def run_pre(self, data):
        rv = FrequencyDialog().exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):
        signal = self._cfg['signal']
        for data_chunk in data:
            pass  # todo

    def run_post(self, data):
        title = f'{self._cfg["signal"]} : Frequency Plot'
        self._win = pg.GraphicsLayoutWidget(show=True, title=title)

        x = np.arange(100)
        y = x
        p = self._win.addPlot(row=1, col=0)
        p.getAxis('left').setGrid(128)
        p.getAxis('bottom').setGrid(128)
        p.setLabels(left='Magnitude (dB)', bottom='Frequency (Hz)')
        bg = pg.PlotDataItem(x=x, y=x, pen='r')
        p.addItem(bg)
        p.setXRange(x[0], x[-1], padding=0.05)
        p.setYRange(np.nanmin(y), np.nanmax(y), padding=0.05)

        self._label = pg.LabelItem(justify='right')
        self._win.addItem(self._label, row=0, col=0)

        #p.setXRange(self.bin_edges[0], self.bin_edges[-1], padding=0.05)
        #p.setYRange(np.nanmin(self.hist), np.nanmax(self.hist), padding=0.05)

        def mouseMoved(evt):
            pos = evt[0]
            if p.sceneBoundingRect().contains(pos):
                mousePoint = p.vb.mapSceneToView(pos)
                xval = mousePoint.x()

        self.proxy = pg.SignalProxy(
            p.scene().sigMouseMoved, rateLimit=60, slot=mouseMoved)

        self._win.closeEvent = lambda evt: data.on_tool_finished()
        return True


class FrequencyDialog(QtWidgets.QDialog):

    def __init__(self):
        QtWidgets.QDialog.__init__(self)
        self.setObjectName('FrequencyDialog')
        self.setWindowTitle('Frequency')
        self.resize(259, 140)
        self.verticalLayout = QtWidgets.QVBoxLayout(self)
        self.verticalLayout.setObjectName("verticalLayout")
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setObjectName("formLayout")

        self.signalLabel = QtWidgets.QLabel(self)
        self.signalLabel.setObjectName("signalLabel")
        self.signalLabel.setText("Signal")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.signalLabel)

        self.signalComboBox = QtWidgets.QComboBox(self)
        self.signalComboBox.setObjectName("signalComboBox")
        self.signalComboBox.addItem("current")
        self.signalComboBox.addItem("voltage")
        self.signalComboBox.addItem("power")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.signalComboBox)

        self.verticalLayout.addLayout(self.formLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(self)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("accepted()"), self.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), self.reject)

    def exec_(self):
        if QtWidgets.QDialog.exec_(self) == 1:
            return {
                'signal': str(self.signalComboBox.currentText()),
            }
        else:
            return None


def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('Analysis/Frequency', Frequency)
    return True
