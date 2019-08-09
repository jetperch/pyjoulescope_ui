import time
import logging
import numpy as np
import pyqtgraph as pg
from math import ceil
from PySide2 import QtWidgets, QtGui, QtCore
from joulescope_ui.histogram_config_widget import Ui_Dialog
from .plugin_helpers import plugin_helpers


log = logging.getLogger(__name__)

PLUGIN = {
    'name': 'Histogram',
    'description': 'Histogram for current/voltage data',
}


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
        norm = _shorten_norm_name(self._cfg['norm'])
        signal = self._cfg['signal']
        num_bins = self._cfg['num_bins']

        hist, bin_edges = plugin_helpers.calculate_histogram(data, num_bins, signal)
        self.hist, _bin_edges = plugin_helpers.normalize_hist(hist, bin_edges, norm)
        self.bin_edges = _bin_edges[:-1]

    def run_post(self, data):
        if self.hist.size == 0 or self.bin_edges.size == 0:
            log.exception('Histogram is empty')
            return

        self.win = pg.GraphicsLayoutWidget(show=True)
        p = self.win.addPlot(row=1, col=0)

        label = pg.LabelItem(justify='right')
        width = self.bin_edges[1] - self.bin_edges[0]
        brushes = [(128, 128, 128)] * len(self.bin_edges)
        bg = pg.BarGraphItem(
            x0=self.bin_edges, height=self.hist, width=width, brushes=brushes)
        self.prev_hover_index = 0

        p.addItem(bg)
        self.win.addItem(label, row=0, col=0)

        p.setLabels(left=(_left_axis_label(self._cfg['norm'])),
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
                        "<span style='font-size: 12pt'>{}={:.5f}</span>,   <span style='color: yellow; font-size:12pt'>{}: {:.5f}</span>".format(
                            self._cfg['signal'], mousePoint.x(), _left_axis_label(self._cfg['norm']), self.hist[index])
                    )
                    bg.opts['brushes'][self.prev_hover_index] = (128, 128, 128)
                    bg.opts['brushes'][index] = (213, 224, 61)
                    self.prev_hover_index = index
                    bg.drawPicture()

        self.proxy = pg.SignalProxy(
            p.scene().sigMouseMoved, rateLimit=60, slot=mouseMoved)


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


def _shorten_norm_name(norm_name):
    if norm_name == 'Probability Density Distribution':
        return 'density'
    elif norm_name == 'Discrete Probability Distribution':
        return 'unity'
    elif norm_name == 'Frequency Distribution':
        return 'count'
    else:
        log.exception('Invalid normalization')
        return


def _left_axis_label(norm_name):
        if norm_name == 'Probability Density Distribution':
            return 'Probability Density'
        elif norm_name == 'Discrete Probability Distribution':
            return 'Probability'
        elif norm_name == 'Frequency Distribution':
            return 'Sample Count'
        else:
            log.exception('Invalid normalization')
            return

def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('Histogram', Histogram)
    return True
