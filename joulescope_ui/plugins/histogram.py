import time
import logging
import numpy as np
import pyqtgraph as pg
from math import ceil
from typing import Callable
from joulescope_ui.histogram_config_widget import Ui_Dialog
from PySide2 import QtWidgets, QtGui, QtCore


log = logging.getLogger(__name__)
CHUNK_SIZE = 65536

PLUGIN = {
    'name': 'Histogram',
    'description': 'Histogram for current/voltage data',
}

_signal_index = {'current': 0, 'voltage': 1}


def _get_signal_index(signal: str):
    if signal not in _signal_index.keys():
        raise RuntimeError(
            'Invalid Signal Request; possible values: "voltage", "current"')
    return _signal_index[signal]


class Histogram:

    def __init__(self):
        self._cfg = None
        self.hist = np.asarray([])
        self.bin_edges = np.asarray([])

    def run_pre(self, data):
        rv = HistogramDialog().exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):
        norm = self._cfg['norm']
        signal = self._cfg['signal']
        num_bins = self._cfg['num_bins']

        hist, bin_edges = self._calculate_histogram(data, num_bins, signal)
        self.hist, _bin_edges = self._normalize_hist(hist, bin_edges, norm)
        self.bin_edges = _bin_edges[:-1]

    def run_post(self, data):
        if self.hist.size == 0 or self.bin_edges.size == 0:
            log.error('Histogram is empty')
            return

        self.win = pg.GraphicsLayoutWidget(show=True)
        p = self.win.addPlot(row=1, col=0)

        label = pg.LabelItem(justify='right')
        width = self.bin_edges[1] - self.bin_edges[0]
        bg = pg.BarGraphItem(
            x0=self.bin_edges, height=self.hist, width=width)

        p.addItem(bg)
        self.win.addItem(label, row=0, col=0)

        p.setLabels(left=(self._left_axis_label()),
                    bottom=(self._cfg['signal']))
        p.setXRange(self.bin_edges[0], self.bin_edges[-1], padding=0.05)
        p.setYRange(np.nanmin(self.hist), np.nanmax(self.hist), padding=0.05)

        def mouseMoved(evt):
            pos = evt[0]
            if p.sceneBoundingRect().contains(pos):
                mousePoint = p.vb.mapSceneToView(pos)
                xval = mousePoint.x()
                index = np.searchsorted(self.bin_edges, xval) - 1
                if index >= 0 and index < len(self.bin_edges):
                    label.setText(
                        "<span style='font-size: 12pt'>{}={:.5f}</span>,   <span style='color: yellow; font-size:12pt'>bin value: {:.5f}</span>".format(
                            self._cfg['signal'], mousePoint.x(), self.hist[index])
                    )
                    brushes = [(128, 128, 128)] * len(self.bin_edges)
                    brushes[index] = (213, 224, 61)
                    bg.opts['brushes'] = brushes
                    bg.drawPicture()

        self.proxy = pg.SignalProxy(
            p.scene().sigMouseMoved, rateLimit=60, slot=mouseMoved)

    def _calculate_histogram(self,
                             data,
                             bins: int,
                             signal: str):

        t0 = 0
        t1 = data.sample_count / data.sample_frequency

        stats = data.view.statistics_get(t0, t1)['signals'][signal]['statistics']
        maximum, minimum = stats['max'], stats['min']
        width = 3.5 * stats['σ'] / (data.sample_count)**(1. / 3)
        num_bins = bins if bins > 0 else ceil((maximum - minimum) / width)

        data_enum = enumerate(data)
        _, data_chunk = data_enum.__next__()

        # bin edges must be consistent, therefore calculate this first chunk to enforce standard bin edges
        hist, bin_edges = np.histogram(
            data_chunk[signal]['value'], range=(minimum, maximum), bins=num_bins)

        for _, data_chunk in data_enum:
            hist += np.histogram(data_chunk[signal]['value'], bins=bin_edges)[0]

        return hist, bin_edges

    def _normalize_hist(self, hist, bin_edges, norm: str = 'density'):
        if norm == 'density':
            db = np.array(np.diff(bin_edges), float)
            return hist/db/hist.sum(), bin_edges
        elif norm == 'unity':
            return hist/hist.sum(), bin_edges
        elif norm == 'count':
            return hist, bin_edges
        else:
            raise RuntimeWarning(
                '_normalize_hist invalid normalization; possible values are "density", "unity", or None')

    def _left_axis_label(self):
        if self._cfg['norm'] == 'density':
            return 'Probability Density'
        elif self._cfg['norm'] == 'unity':
            return 'Probability'
        else:
            return 'Sample Count'


class HistogramDialog(QtWidgets.QDialog):
    def __init__(self):
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

    def exec_(self):
        if QtWidgets.QDialog.exec_(self) == 1:
            num_bins = int(self.ui.num_bins.value())
            signal = str(self.ui.signal.currentText())
            norm = str(self.ui.normalization.currentText())
            return {
                'num_bins': num_bins,
                'signal': signal,
                'norm': norm
            }
        else:
            return None


def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('Histogram', Histogram)
    return True
