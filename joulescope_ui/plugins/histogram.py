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

from PySide6 import QtCore, QtWidgets
from joulescope_ui import register, N_, pubsub_singleton
from joulescope_ui.range_tool import RangeToolBase
import logging
import numpy as np
import pyqtgraph as pg
from .plugin_helpers import calculate_histogram, normalize_hist
from joulescope_ui.styles import styled_widget


_NAME = N_('Histogram')
_NORMALIZATIONS = {
    'Discrete Probability Distribution': ('unity', 'Probability'),
    'Frequency Distribution': ('count', 'Sample Count'),
    'Probability Density Distribution': ('density', 'Probability Density'),
}


class HistogramRangeToolDialog(QtWidgets.QDialog):

    def __init__(self, value):
        self._value = value
        parent = pubsub_singleton.query('registry/ui/instance')
        super().__init__(parent=parent)
        self._log = logging.getLogger(f'{__name__}.dialog')
        self.setObjectName('histogram_range_tool_dialog')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._form = QtWidgets.QFormLayout()

        self._signal_label = QtWidgets.QLabel(N_('Signal'), self)
        self._form.setWidget(0, QtWidgets.QFormLayout.LabelRole, self._signal_label)
        self._signal = QtWidgets.QComboBox(self)
        self._form.setWidget(0, QtWidgets.QFormLayout.FieldRole, self._signal)
        for idx, signal_id in enumerate(value['signals']):
            signal_name = '.'.join(signal_id.split('.')[-2:])
            self._signal.addItem(signal_name)

        self._num_bins_label = QtWidgets.QLabel(N_('Number of bins (0 for auto)'), self)
        self._form.setWidget(1, QtWidgets.QFormLayout.LabelRole, self._num_bins_label)
        self._num_bins = QtWidgets.QSpinBox(self)
        self._num_bins.setMaximum(1000)
        self._form.setWidget(1, QtWidgets.QFormLayout.FieldRole, self._num_bins)

        self._type_label = QtWidgets.QLabel(N_('Histogram type'), self)
        self._form.setWidget(2, QtWidgets.QFormLayout.LabelRole, self._type_label)
        self._normalization = QtWidgets.QComboBox(self)
        self._form.setWidget(2, QtWidgets.QFormLayout.FieldRole, self._normalization)
        for name in _NORMALIZATIONS.keys():
            self._normalization.addItem(name)

        self._layout.addLayout(self._form)
        self._buttons = QtWidgets.QDialogButtonBox(self)
        self._buttons.setOrientation(QtCore.Qt.Horizontal)
        self._buttons.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok)
        self._layout.addWidget(self._buttons)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self.finished.connect(self._on_finished)

        self.resize(400, 173)
        self.setWindowTitle(N_('Histogram configuration'))
        self._log.info('open')
        self.open()

    @QtCore.Slot(int)
    def _on_finished(self, value):
        self._log.info('finished: %d', value)

        if value == QtWidgets.QDialog.DialogCode.Accepted:
            self._log.info('finished: accept - start histogram')
            self._value['kwargs'] = {
                'signal': self._value['signals'][self._signal.currentIndex()],
                'num_bins': int(self._num_bins.value()),
                'norm': str(self._normalization.currentText()),
            }
            w = HistogramRangeTool(self._value)
            pubsub_singleton.register(w)
        else:
            self._log.info('finished: reject - abort histogram')  # no action required
        self.close()


@register
@styled_widget(_NAME)
class HistogramRangeToolWidget(QtWidgets.QWidget):

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
        self._hist = None
        self._bin_edges = None
        self._bg = None
        super().__init__()
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._win = pg.GraphicsLayoutWidget(parent=self, title=_NAME)
        self._win.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._layout.addWidget(self._win)
        p = self._win.addPlot(row=1, col=0)
        self._p = p
        p.getAxis('left').setGrid(128)
        p.getAxis('bottom').setGrid(128)
        self._label = pg.LabelItem(justify='right')
        self.prev_hover_index = 0
        self._win.addItem(self._label, row=0, col=0)

        self.proxy = pg.SignalProxy(p.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

    def on_pubsub_register(self):
        if self._data is not None:
            self.data = self._data

    @QtCore.Slot(object)
    def _on_mouse_moved(self, evt):
        pos = evt[0]
        if self._hist is None or self.data is None:
            return
        p = self._p
        if p.sceneBoundingRect().contains(pos):
            mouse_point = p.vb.mapSceneToView(pos)
            xval = mouse_point.x()
            index = np.searchsorted(self._bin_edges, xval) - 1
            signal_name = self.data['signal_name']
            axis_label = self.data['axis_label']
            if index >= 0 and index < len(self._bin_edges):
                self._label.setText(
                    "<span style='font-size: 12pt'>{}={:.5f}</span>,   <span style='color: yellow; font-size:12pt'>{}: {:.5f}</span>".format(
                        signal_name, xval, axis_label, self._hist[index])
                )
                self._brushes[self.prev_hover_index] = (128, 128, 128)
                self._brushes[index] = (213, 224, 61)
                self._bg.setOpts(brushes=self._brushes)
                self.prev_hover_index = index

    def on_setting_data(self, value):
        if value is None:
            self._hist = None
            self._bin_edges = None
            return
        self._hist = np.array(value['hist'], dtype=float)
        self._bin_edges = np.array(value['bin_edges'], dtype=float)
        signal_name = value['signal_name']
        axis_label = value['axis_label']

        if self._bg is not None:
            self._p.removeItem(self._bg)
        self._bg = pg.BarGraphItem(
            x0=self._bin_edges,
            height=self._hist,
            width=self._bin_edges[1] - self._bin_edges[0],
            brushes=[(128, 128, 128)] * len(self._bin_edges),
        )
        self._brushes = [(128, 128, 128)] * len(self._bin_edges)
        self._p.addItem(self._bg)
        self._p.setXRange(self._bin_edges[0], self._bin_edges[-1], padding=0.05)
        self._p.setYRange(np.nanmin(self._hist), np.nanmax(self._hist), padding=0.05)
        self._p.setLabels(left=axis_label, bottom=signal_name)
        value['hist'] = self._hist.tolist()  # json-serializable
        value['bin_edges'] = self._bin_edges.tolist()  # json-serializable


@register
class HistogramRangeTool(RangeToolBase):
    NAME = _NAME
    BRIEF = N_('Compute histogram over the range')
    DESCRIPTION = N_("""\
        Compute a histogram of the signal's data values over the
        selected range.""")

    def __init__(self, value):
        super().__init__(value)

    def _run(self):
        kwargs = self.kwargs
        num_bins = kwargs['num_bins']
        signal_id = kwargs['signal']
        norm, norm_label = _NORMALIZATIONS[kwargs['norm']]

        hist, bin_edges = calculate_histogram(self, self.value, signal_id, num_bins)
        hist, bin_edges = normalize_hist(hist, bin_edges, norm)
        bin_edges = bin_edges[:-1]
        if hist.size == 0 or bin_edges.size == 0:
            self._log.error('Histogram is empty')
            return

        self.pubsub.publish('registry/view/actions/!widget_open', {
            'value': 'HistogramRangeToolWidget',
            'kwargs': {
                'data': {
                    'hist': hist,
                    'bin_edges': bin_edges,
                    'signal_name': signal_id,
                    'axis_label': norm_label,
                },
            },
            'floating': True,
        })

    @staticmethod
    def on_cls_action_run(value):
        HistogramRangeToolDialog(value)
