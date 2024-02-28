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

from joulescope_ui import register, N_, pubsub_singleton
from joulescope_ui.range_tool import RangeToolBase, rsp_as_f32
import logging
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets
from joulescope_ui.styles import styled_widget


_NAME = N_('Frequency')


_WINDOWS = {
    'bartlett': np.bartlett,
    'blackman': np.blackman,
    'hamming': np.hamming,
    'hanning': np.hanning,
    'rectangular': np.ones,
}


@register
class FrequencyRangeTool(RangeToolBase):
    NAME = _NAME
    BRIEF = N_('Compute frequency spectrum over the range')
    DESCRIPTION = N_("""\
        Compute the frequency spectrum to analyze the frequency
        content of the signal's data values over the
        selected range.""")

    def __init__(self, value):
        super().__init__(value)

    def _run(self):
        kwargs = self.kwargs
        signal = kwargs['signal']
        window = kwargs['window']
        nfft = kwargs['nfft']
        overlap = kwargs['overlap']

        d = self.request(signal, 'utc', *self.x_range, 1)
        fs = d['info']['time_map']['counter_rate']
        s_now = d['info']['time_range_samples']['start']
        s_end = d['info']['time_range_samples']['end'] + 1
        sample_count = s_end - s_now

        if nfft > sample_count:
            nfft = sample_count & 0xfffffffe  # make even

        overlap = int(min(1.0, max(0.0, overlap)) * nfft)
        sample_jump = nfft - overlap
        window = _WINDOWS[window](nfft)
        x = np.zeros(nfft)
        y = np.zeros(nfft // 2 + 1)
        k = 0
        x_offset = 0

        window_factor = np.sum(window * window)
        fft_factor = 2.0 / (fs * window_factor)

        # Video explaining periodogram: https://www.youtube.com/watch?v=Qs-Zai0F2Pw
        # Example: https://github.com/matplotlib/matplotlib/blob/d7feb03da5b78e15b002b7438779068a318a3024/lib/matplotlib/mlab.py#L405
        while s_now < s_end:
            length = min(int(fs), s_end - s_now)
            rsp = self.request(signal, 'samples', s_now, 0, length)
            d = rsp_as_f32(rsp)
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
            s_now += length
            self.progress(s_now / (length + 1))

        y *= (1.0 / k)  # average
        y = 20 * np.log10(y)  # convert to dB

        self.pubsub.publish('registry/view/actions/!widget_open', {
            'value': 'FrequencyRangeToolWidget',
            'kwargs': {
                'data': {
                    'x': np.arange(nfft // 2 + 1) * (fs / nfft),
                    'y': y,
                },
            },
            'floating': True,
        })

    @staticmethod
    def on_cls_action_run(value):
        FrequencyRangeToolDialog(value)


@register
@styled_widget(_NAME)
class FrequencyRangeToolWidget(QtWidgets.QWidget):

    SETTINGS = {
        'data': {
            'dtype': 'obj',
            'brief': 'Hold the histogram data',
            'default': None,
            'flags': ['hide'],
        }
    }

    def __init__(self, data=None):
        self._data = data
        self._bg = None
        self._f = None
        self._y = None
        super().__init__()
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._win = pg.GraphicsLayoutWidget(parent=self, title=_NAME)
        self._win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._label = pg.LabelItem(justify='right')
        self._win.addItem(self._label)
        self._layout.addWidget(self._win)

        self._p = self._win.addPlot(row=1, col=0)
        p = self._p
        p.getAxis('left').setGrid(128)
        p.getAxis('bottom').setGrid(128)
        p.setLabels(left='Magnitude (dB)', bottom='Frequency (Hz)')

        self._label = pg.LabelItem(justify='right')
        self._win.addItem(self._label, row=0, col=0)

        # cross hair
        self._vLine = pg.InfiniteLine(angle=90, movable=False)
        self._hLine = pg.InfiniteLine(angle=0, movable=False)
        p.addItem(self._vLine, ignoreBounds=True)
        p.addItem(self._hLine, ignoreBounds=True)

        self.proxy = pg.SignalProxy(
            p.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

    def on_pubsub_register(self):
        if self._data is not None:
            self.data = self._data

    @QtCore.Slot(object)
    def _on_mouse_moved(self, evt):
        pos = evt[0]
        p = self._p
        if p.sceneBoundingRect().contains(pos):
            mousePoint = p.vb.mapSceneToView(pos)
            xval = mousePoint.x()
            idx = np.searchsorted(self._f, xval)
            idx = min(max(0, idx), len(self._f) - 1)
            xval = self._f[idx]
            yval = self._y[idx]
            self._label.setText(f'x={xval:.1f} Hz, y={yval:.3f} dB')
            self._vLine.setPos(xval)
            self._hLine.setPos(yval)

    def on_setting_data(self, value):
        if value is None:
            self._f = None
            self._y = None
            return
        self._data = value
        self._f = self._data['x']
        self._y = self._data['y']
        x, y = self._f, self._y
        p = self._p
        if self._bg is not None:
            p.removeItem(self._bg)
        self._bg = pg.PlotDataItem(x=x, y=y, pen='r')
        p.addItem(self._bg)
        x_min, x_max = [x[0], x[-1]]
        y_min, y_max = [np.nanmin(y), np.nanmax(y)]
        y_over = 0.025 * (y_max - y_min)
        y_min, y_max = y_min - y_over, y_max + y_over
        p.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)
        p.setXRange(x_min, x_max, padding=0.0)
        p.setYRange(y_min, y_max, padding=0.0)


class FrequencyRangeToolDialog(QtWidgets.QDialog):

    def __init__(self, value):
        self._value = value
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self._log = logging.getLogger(f'{__name__}.dialog')
        self.setObjectName('FrequencyRangeToolDialog')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(N_('Frequency configuration'))
        self.resize(259, 140)
        self.verticalLayout = QtWidgets.QVBoxLayout(self)
        self.verticalLayout.setObjectName("verticalLayout")
        self._layout = QtWidgets.QGridLayout()

        self._signal_label = QtWidgets.QLabel(self)
        self._signal_label.setText("Signal")
        self._layout.addWidget(self._signal_label, 0, 0, 1, 1)

        self._signal = QtWidgets.QComboBox(self)
        self._signal.setObjectName("signalComboBox")
        for signal_id in value['signals']:
            signal_name = '.'.join(signal_id.split('.')[-2:])
            self._signal.addItem(signal_name)
        self._layout.addWidget(self._signal, 0, 1, 1, 1)

        self._windowLabel = QtWidgets.QLabel(self)
        self._windowLabel.setText("Window")
        self._layout.addWidget(self._windowLabel, 1, 0, 1, 1)

        self._window = QtWidgets.QComboBox(self)
        self._window.setObjectName("windowComboBox")
        for key in _WINDOWS.keys():
            self._window.addItem(key)
        self._window.setCurrentIndex(2)  # hamming
        self._layout.addWidget(self._window, 1, 1, 1, 1)

        self._fftLengthLabel = QtWidgets.QLabel(self)
        self._fftLengthLabel.setText('FFT Length')
        self._layout.addWidget(self._fftLengthLabel, 2, 0, 1, 1)

        self._fft_length = QtWidgets.QComboBox(self)
        self._fft_length.setObjectName('fftLengthComboBox')
        for pow2 in range(6, 22):
            self._fft_length.addItem(str(2 ** pow2))
        self._fft_length.setCurrentIndex(6)
        self._layout.addWidget(self._fft_length, 2, 1, 1, 1)

        self._overlapLabel = QtWidgets.QLabel(self)
        self._overlapLabel.setText('Overlap %')
        self._layout.addWidget(self._overlapLabel, 3, 0, 1, 1)

        self._overlapSpin = QtWidgets.QSpinBox(self)
        self._overlapSpin.setRange(0, 50)
        self._overlapSpin.setValue(25)
        self._layout.addWidget(self._overlapSpin, 3, 1, 1, 1)

        self.verticalLayout.addLayout(self._layout)
        self._buttons = QtWidgets.QDialogButtonBox(self)
        self._buttons.setOrientation(QtCore.Qt.Horizontal)
        self._buttons.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        self._buttons.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self._buttons)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self.finished.connect(self._on_finished)
        self._log.info('open')
        self.open()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        self._log.info('finished: %d', value)

        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._log.info('finished: accept - start frequency')
            self._value['kwargs'] = {
                'signal': self._value['signals'][self._signal.currentIndex()],
                'window': self._window.currentText(),
                'nfft': int(self._fft_length.currentText()),
                'overlap': self._overlapSpin.value() / 100.0,
            }
            w = FrequencyRangeTool(self._value)
            pubsub_singleton.register(w)
        else:
            self._log.info('finished: reject - abort frequency')  # no action required
        self.close()
