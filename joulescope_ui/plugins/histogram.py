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


class histogram:

    def __init__(self):
        self._cfg = None

    def run_pre(self, data):
        rv = HistogramDialog().exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):
        norm = self._cfg['norm']
        signal = self._cfg['signal']
        num_bins = self._cfg['num_bins']

        _num_bins = num_bins if num_bins > 0 else ceil(
            data.sample_count ** (1/3))

        hist, bin_edges = self._calculate_histogram(data, _num_bins, signal)
        self.hist, self.bin_edges = self._normalize_hist(hist, bin_edges, norm)

    def run_post(self, data):
        win = pg.plot()
        win.setWindowTitle('Booga Booga Booga')

        width = self.bin_edges[1] - self.bin_edges[0]
        bg = pg.BarGraphItem(x=self.bin_edges[:-1], height=self.hist, width=width)
        win.addItem(bg)
        win.setXRange(self.bin_edges[0], self.bin_edges[-1], padding=0.05)
        win.setYRange(np.amin(self.hist), np.amax(self.hist), padding=0.05)

    def _calculate_histogram(self,
                             data,
                             bins: int,
                             signal: str):

        t0 = 0
        t1 = data.sample_count / data.sample_frequency

        stats = data.view.statistics_get(
            t0, t1)['signals'][signal]['statistics']
        maximum, minimum = stats['max'], stats['min']

        data_enum = enumerate(data)
        _, data_chunk = data_enum.__next__()

        # bin edges must be consistent, therefore calculate this first chunk to enforce
        # standard bin edges
        hist, bin_edges = np.histogram(
            data_chunk[signal]['value'], range=(minimum, maximum), bins=bins)

        for _, data_chunk in data_enum:
            hist += np.histogram(data_chunk[signal]['value'], bins=bin_edges)[0]

        return hist, bin_edges

    def _normalize_hist(self, hist, bin_edges, norm: str = 'density'):
        if norm == 'density':
            db = np.array(np.diff(bin_edges), float)
            return hist/db/hist.sum(), bin_edges
        elif norm == 'unity':
            return hist/hist.sum(), bin_edges
        elif norm == None:
            return hist, bin_edges
        else:
            raise RuntimeWarning(
                '_normalize_hist invalid normalization; possible values are "density", "unity", or None')


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
    api.range_tool_register('histogram', histogram)
    return True
