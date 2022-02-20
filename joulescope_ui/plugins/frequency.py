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


_WINDOWS = {
    'bartlett': np.bartlett,
    'blackman': np.blackman,
    'hamming': np.hamming,
    'hanning': np.hanning,
    'rectangular': np.ones
}

_FFT_LENGTHS = [64, 128, 256, 512, 1024, 2048, 4096, 8192]


class Frequency:

    def __init__(self):
        self._cfg = None
        self._win = None
        self._label = None
        self._bg = None
        self._f = None
        self._y = None

    def run_pre(self, data):
        rv = FrequencyDialog().exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):
        signal = self._cfg['signal']
        window = self._cfg['window']
        nfft = self._cfg['nfft']
        overlap = self._cfg['overlap']

        if nfft > data.sample_count:
            nfft = data.sample_count & 0xfffffffe  # make even

        overlap = int(min(1.0, max(0.0, overlap)) * nfft)
        sample_jump = nfft - overlap
        window = _WINDOWS[window](nfft)
        x = np.zeros(nfft)
        y = np.zeros(nfft // 2 + 1)
        k = 0
        x_offset = 0

        fs = data.sample_frequency
        window_factor = np.sum(window * window)
        fft_factor = 2.0 / (fs * window_factor)
        self._f = np.arange(nfft // 2 + 1) * (fs / nfft)

        # Video explaining periodogram: https://www.youtube.com/watch?v=Qs-Zai0F2Pw
        # Example: https://github.com/matplotlib/matplotlib/blob/d7feb03da5b78e15b002b7438779068a318a3024/lib/matplotlib/mlab.py#L405

        for data_chunk in data:
            d = data_chunk['signals'][signal]['value']
            data_offset = 0
            d_len = len(d)
            while (d_len + x_offset) >= nfft:
                d_len_this = nfft - x_offset
                x[x_offset:] = d[data_offset:(data_offset + d_len_this)]
                z = np.fft.rfft(x * window)
                y += np.real((z * np.conj(z))) * fft_factor
                k += 1
                d_len -= d_len_this
                data_offset += d_len_this
                x[:overlap] = x[sample_jump:]
                x_offset = overlap
            x[x_offset:(x_offset + d_len)] = d[data_offset:]
            x_offset += d_len

        y *= (1.0 / k)  # average
        y = 20 * np.log10(y)  # convert to dB
        self._y = y

    def run_post(self, data):
        title = f'{self._cfg["signal"]} : Frequency Plot'
        self._win = pg.GraphicsLayoutWidget(show=True, title=title)
        self._label = pg.LabelItem(justify='right')
        self._win.addItem(self._label)

        x = self._f
        y = self._y
        p = self._win.addPlot(row=1, col=0)
        p.getAxis('left').setGrid(128)
        p.getAxis('bottom').setGrid(128)
        p.setLabels(left='Magnitude (dB)', bottom='Frequency (Hz)')
        bg = pg.PlotDataItem(x=x, y=y, pen='r')
        p.addItem(bg)
        x_min, x_max = [x[0], x[-1]]
        y_min, y_max = [np.nanmin(y), np.nanmax(y)]
        y_over = 0.025 * (y_max - y_min)
        y_min, y_max = y_min - y_over, y_max + y_over
        p.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)
        p.setXRange(x_min, x_max, padding=0.0)
        p.setYRange(y_min, y_max, padding=0.0)

        self._label = pg.LabelItem(justify='right')
        self._win.addItem(self._label, row=0, col=0)

        # cross hair
        self._vLine = pg.InfiniteLine(angle=90, movable=False)
        self._hLine = pg.InfiniteLine(angle=0, movable=False)
        p.addItem(self._vLine, ignoreBounds=True)
        p.addItem(self._hLine, ignoreBounds=True)

        def mouseMoved(evt):
            pos = evt[0]
            if p.sceneBoundingRect().contains(pos):
                mousePoint = p.vb.mapSceneToView(pos)
                xval = mousePoint.x()
                idx = np.searchsorted(self._f, xval)
                xval = self._f[idx]
                yval = self._y[idx]
                self._label.setText(f'x={xval:.1f} Hz, y={yval:.3f} dB')
                self._vLine.setPos(xval)
                self._hLine.setPos(yval)

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
        self._layout = QtWidgets.QGridLayout()
        self._layout.setObjectName("gridLayout")

        self.signalLabel = QtWidgets.QLabel(self)
        self.signalLabel.setObjectName("signalLabel")
        self.signalLabel.setText("Signal")
        self._layout.addWidget(self.signalLabel, 0, 0, 1, 1)

        self.signalComboBox = QtWidgets.QComboBox(self)
        self.signalComboBox.setObjectName("signalComboBox")
        self.signalComboBox.addItem("current")
        self.signalComboBox.addItem("voltage")
        self.signalComboBox.addItem("power")
        self._layout.addWidget(self.signalComboBox, 0, 1, 1, 1)

        self._windowLabel = QtWidgets.QLabel(self)
        self._windowLabel.setText("Window")
        self._layout.addWidget(self._windowLabel, 1, 0, 1, 1)

        self._windowComboBox = QtWidgets.QComboBox(self)
        self._windowComboBox.setObjectName("windowComboBox")
        for key in _WINDOWS.keys():
            self._windowComboBox.addItem(key)
        self._windowComboBox.setCurrentIndex(2)  # hamming
        self._layout.addWidget(self._windowComboBox, 1, 1, 1, 1)

        self._fftLengthLabel = QtWidgets.QLabel(self)
        self._fftLengthLabel.setText('FFT Length')
        self._layout.addWidget(self._fftLengthLabel, 2, 0, 1, 1)

        self._fftLengthComboBox = QtWidgets.QComboBox(self)
        self._fftLengthComboBox.setObjectName('fftLengthComboBox')
        for pow2 in range(6, 22):
            self._fftLengthComboBox.addItem(str(2**pow2))
        self._fftLengthComboBox.setCurrentIndex(6)
        self._layout.addWidget(self._fftLengthComboBox, 2, 1, 1, 1)

        self._overlapLabel = QtWidgets.QLabel(self)
        self._overlapLabel.setText('Overlap %')
        self._layout.addWidget(self._overlapLabel, 3, 0, 1, 1)

        self._overlapSpin = QtWidgets.QSpinBox(self)
        self._overlapSpin.setRange(0, 50)
        self._overlapSpin.setValue(25)
        self._layout.addWidget(self._overlapSpin, 3, 1, 1, 1)

        self.verticalLayout.addLayout(self._layout)
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
                'signal': self.signalComboBox.currentText(),
                'window': self._windowComboBox.currentText(),
                'nfft': int(self._fftLengthComboBox.currentText()),
                'overlap': self._overlapSpin.value() / 100.0,
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
