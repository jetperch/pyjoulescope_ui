# Copyright 2019-2023 Jetperch LLC
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
from joulescope_ui.range_tool import RangeToolBase
from .plugin_helpers import calculate_histogram, normalize_hist
import logging
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets
from joulescope_ui.styles import styled_widget


@register
class CdfRangeTool(RangeToolBase):
    NAME = 'CDF'
    BRIEF = N_('Compute the Cumulative Distribution Function')
    DESCRIPTION = N_("""\
        The Cumulative Distribution Function (CDF) value is the probability
        that a signal's value is less than or equal to the x-axis value.
        
        When use to analyze current or power, this graphically indicates the
        time spent below in each current mode.  Compared to a histogram,
        the CDF makes it easier to compare the amount of time in each mode
        by simply measuring the change in the y-axis value.""")

    def __init__(self, value):
        super().__init__(value)

    def _run(self):
        kwargs = self.kwargs
        signal = kwargs['signal']
        num_bins = kwargs['num_bins']
        complimentary = kwargs['complimentary']
        hist, bin_edges = calculate_histogram(self, self.value, signal, num_bins)
        hist, bin_edges = normalize_hist(hist, bin_edges, 'unity')
        y = np.cumsum(hist)
        if complimentary:
            y = 1 - y

        self.pubsub.publish('registry/view/actions/!widget_open', {
            'value': 'CdfRangeToolWidget',
            'kwargs': {
                'data': {
                    'x': bin_edges,
                    'y': y,
                    'signal_name': signal[1],
                    'type': 'CCDF' if complimentary else 'CDF'
                },
            },
            'floating': True,
        })

    @staticmethod
    def on_cls_action_run(value):
        CdfRangeToolDialog(value)


@register
@styled_widget(None)
class CdfRangeToolWidget(QtWidgets.QWidget):

    SETTINGS = {
        'data': {
            'dtype': 'obj',
            'brief': 'Hold the data',
            'default': None,
            'flags': ['hide'],
        }
    }

    def __init__(self, data=None):
        self._data = data
        self._plot_item = None
        super().__init__()
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._win = pg.GraphicsLayoutWidget(parent=self)
        self._win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._label = pg.LabelItem(justify='right')
        self._win.addItem(self._label)
        self._layout.addWidget(self._win)

        self._p = self._win.addPlot(row=1, col=0)
        p = self._p
        p.getAxis('left').setGrid(128)
        p.getAxis('bottom').setGrid(128)

        self._label = pg.LabelItem(justify='right')
        self._win.addItem(self._label, row=0, col=0)

        # cross hair
        self._vLine = pg.InfiniteLine(angle=90, movable=False)
        self._hLine = pg.InfiniteLine(angle=0, movable=False)
        p.addItem(self._vLine, ignoreBounds=True)
        p.addItem(self._hLine, ignoreBounds=True)

        self.proxy = pg.SignalProxy(p.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

    def on_pubsub_register(self):
        if self._data is not None:
            self.data = self._data
            self.name = self._data['type']

    @QtCore.Slot(object)
    def _on_mouse_moved(self, evt):
        if self._data is None:
            return
        pos = evt[0]
        p = self._p
        if p.sceneBoundingRect().contains(pos):
            mousePoint = p.vb.mapSceneToView(pos)
            xval = mousePoint.x()
            x_i = self._data['x'][1:]
            idx = np.searchsorted(x_i, xval)
            idx = min(max(0, idx), len(x_i) - 1)
            xval = x_i[idx]
            yval = self._data['y'][idx]
            self._label.setText(
                "<span style='font-size: 12pt'>{:.5f}</span>,   <span style='color: yellow; font-size:12pt'>probability: {:.5f}</span>".format(
                    xval, yval)
            )
            self._vLine.setPos(xval)
            self._hLine.setPos(yval)

    def on_setting_data(self, value):
        p = self._p
        if self._plot_item is not None:
            p.removeItem(self._plot_item)
        if value is None:
            return
        self._data = value
        left_label = N_('Probability')
        if value['type'] == 'CCDF':
            left_label = f'1 - {left_label}'
        p.setLabels(left=left_label, bottom=value['signal_name'])
        x, y = value['x'], value['y']

        self._plot_item = pg.PlotDataItem(x=x[1:], y=y, pen='r')
        p.addItem(self._plot_item)
        p.setXRange(x[0], x[-1], padding=0.05)
        p.setYRange(0, 1, padding=0.05)


class CdfRangeToolDialog(QtWidgets.QDialog):

    def __init__(self, value):
        self._value = value
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self._log = logging.getLogger(f'{__name__}.dialog')
        self.setObjectName('CdfRangeToolDialog')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(N_('CDF configuration'))
        self.resize(350, 180)
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

        self._num_bins_label = QtWidgets.QLabel(N_('Number of bins (0 for auto)'), self)
        self._layout.addWidget(self._num_bins_label, 1, 0, 1, 1)
        self._num_bins = QtWidgets.QSpinBox(self)
        self._num_bins.setMaximum(1000)
        self._layout.addWidget(self._num_bins, 1, 1, 1, 1)

        self._complimentary_label = QtWidgets.QLabel(N_('Complimentary'), self)
        self._layout.addWidget(self._complimentary_label, 2, 0, 1, 1)
        self._complimentary = QtWidgets.QCheckBox(self)
        self._complimentary.setCheckable(True)
        self._layout.addWidget(self._complimentary, 2, 1, 1, 1)

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
            self._log.info('finished: accept - start cdf')
            self._value['kwargs'] = {
                'signal': self._value['signals'][self._signal.currentIndex()],
                'num_bins': int(self._num_bins.value()),
                'complimentary': self._complimentary.isChecked(),
            }
            w = CdfRangeTool(self._value)
            pubsub_singleton.register(w)
        else:
            self._log.info('finished: reject - abort cdf')  # no action required
        self.close()
