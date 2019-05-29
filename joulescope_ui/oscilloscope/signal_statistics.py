
from pyqtgraph.Qt import QtGui, QtCore
from joulescope.units import unit_prefix, three_sig_figs
import pyqtgraph as pg


class SignalStatistics(pg.GraphicsWidget):

    def __init__(self, parent=None, units=None):
        pg.GraphicsWidget.__init__(self, parent=parent)
        self._units = units
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        self._label = QtGui.QGraphicsTextItem(self)
        self._label.setVisible(True)
        self.style = 'color: #FFF; font-size: 8pt'
        self.data_update(-0.001, -0.001, -0.001, -0.01)
        b = self._label.boundingRect()
        self.setMinimumHeight(b.height())
        self.setMinimumWidth(b.width())
        pg.GraphicsWidget.show(self)

    def close(self):
        self.scene().removeItem(self._label)
        self._label = None

    def data_clear(self):
        self._label.setHtml(f'<html><body></body></html>')

    def data_update(self, v_mean, v_std, v_min, v_max):
        values = {
            'μ': v_mean,
            'σ': v_std,
            'min': v_min,
            'max': v_max,
            'p2p': v_max - v_min,
        }
        body = '<br/>'.join(['%s=%s' % (name, three_sig_figs(v, self._units)) for name, v in values.items()])
        self._label.setHtml(f'<html><body><span style="{self.style}">{body}</span></body></html>')
