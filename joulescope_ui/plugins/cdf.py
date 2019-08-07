import time
import logging
import numpy as np
import pyqtgraph as pg
from math import ceil
from PySide2 import QtWidgets, QtGui, QtCore
from joulescope_ui.cdf_config_widget import Ui_Dialog
from .plugin_helpers import plugin_helpers


log = logging.getLogger(__name__)
CHUNK_SIZE = 65536

PLUGIN = {
    'name': 'Cumulative Distribution Function',
    'description': 'Cumulative Distribution Function for current/voltage data',
}

_signal_index = {'current': 0, 'voltage': 1}


def _get_signal_index(signal: str):
    if signal not in _signal_index.keys():
        raise RuntimeError(
            'Invalid Signal Request; possible values: "voltage", "current"')
    return _signal_index[signal]


class CDF:

    def __init__(self):
        self._cfg = None
        self.hist = np.asarray([])
        self.bin_edges = np.asarray([])

    def run_pre(self, data):
        rv = CDFDialog().exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):
        signal = self._cfg['signal']

        self.hist, bin_edges = plugin_helpers.cdf(data, signal)
        self.bin_edges = bin_edges[:-1]

    def run_post(self, data):
        if self.hist.size == 0 or self.bin_edges.size == 0:
            log.error('CDF data is empty')
            return

        self.win = pg.GraphicsLayoutWidget(show=True)
        p = self.win.addPlot(row=1, col=0)

        label = pg.LabelItem(justify='right')
        bg = pg.PlotDataItem(x=self.bin_edges, y=self.hist, pen='r')

        p.addItem(bg)
        self.win.addItem(label, row=0, col=0)

        p.setLabels(left=('Probability'), bottom=(self._cfg['signal']))
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
                        "<span style='font-size: 12pt'>{}={:.5f}</span>,   <span style='color: yellow; font-size:12pt'>probability: {:.5f}</span>".format(
                            self._cfg['signal'], mousePoint.x(), self.hist[index])
                    )

        self.proxy = pg.SignalProxy(
            p.scene().sigMouseMoved, rateLimit=60, slot=mouseMoved)


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


def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('CDF', CDF)
    return True
