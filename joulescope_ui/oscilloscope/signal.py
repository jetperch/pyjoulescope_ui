from .signal_statistics import SignalStatistics
import pyqtgraph as pg
import numpy as np

CURVE_WIDTH = 1
AUTO_RANGE_FRACT = 0.45  # autorange when current range smaller than existing range by this fractional amount.


class Signal:

    def __init__(self, name, units=None, y_limit=None):
        self.text_item = None
        self.name = name
        self.units = units
        self.vb = pg.ViewBox(enableMenu=False, enableMouse=False)
        if y_limit is not None:
            y_min, y_max = y_limit
            self.vb.setLimits(yMin=y_min, yMax=y_max)
            self.vb.setYRange(y_min, y_max)
        self.y_axis = pg.AxisItem(orientation='left')
        self.y_axis.linkToView(self.vb)
        self.y_axis.setGrid(128)
        if name is not None:
            self.y_axis.setLabel(text=name, units=units)
            if units is not None:
                self.text_item = SignalStatistics(units=units)

        self._pen_min_max = pg.mkPen(color=(255, 64, 64), width=CURVE_WIDTH)
        self._brush_min_max = pg.mkBrush(color=(255, 64, 64, 32))
        self._pen_mean = pg.mkPen(color=(255, 255, 64), width=CURVE_WIDTH)

        self.curve_mean = pg.PlotDataItem(pen=self._pen_mean)
        self.curve_max = pg.PlotDataItem(pen=self._pen_min_max)
        self.curve_min = pg.PlotDataItem(pen=self._pen_min_max)
        self.vb.addItem(self.curve_mean)
        self.vb.addItem(self.curve_max)
        self.vb.addItem(self.curve_min)
        # self.curve_range = pg.FillBetweenItem(self.curve_min, self.curve_max, brush=self._brush_min_max)
        # self.vb.addItem(self.curve_range)

    def set_xlimits(self, x_min, x_max):
        self.vb.setLimits(xMin=x_min, xMax=x_max)

    def addToLayout(self, layout, row):
        layout.addItem(self.y_axis, row=row, col=0)
        layout.addItem(self.vb, row=row, col=1)
        if self.text_item:
            layout.addItem(self.text_item, row=row, col=2)
            layout.ci.layout.setRowStretchFactor(row, 150)
        else:
            layout.ci.layout.setRowStretchFactor(row, 10)

    def yaxis_autorange(self, v_min, v_max):
        if True:  # self.ui.zoomAutoYButton.isChecked():
            _, (vb_min, vb_max) = self.vb.viewRange()
            vb_range = vb_max - vb_min
            v_range = v_max - v_min
            update_range = (v_max > vb_max) or (v_min < vb_min)
            if vb_range > 0:
                update_range |= (v_range / vb_range) < AUTO_RANGE_FRACT
            if update_range:
                self.vb.setYRange(v_min, v_max)

    def update(self, x, value):
        self.text_item.data_clear()
        if x is None or value is None:
            self.curve_mean.clear()
            self.curve_mean.update()
            self.curve_max.clear()
            self.curve_max.update()
            self.curve_min.clear()
            self.curve_min.update()

        elif len(value.shape) == 1:
            self.curve_mean.setData(x, value)
            self.curve_max.clear()
            self.curve_max.update()
            self.curve_min.clear()
            self.curve_min.update()

            if self.text_item is not None:
                z_valid = np.isfinite(value)
                z = value[z_valid]
                if len(z):
                    z_mean = np.mean(z)
                    z_std = np.std(z)
                    z_max = np.max(z)
                    z_min = np.min(z)
                    self.text_item.data_update(z_mean, z_std, z_max, z_min)
                    self.yaxis_autorange(np.min(z_min), np.max(z_max))

        elif len(value.shape) == 2 and value.shape[-1] > 1:
            z_mean = value[:, 0]
            self.curve_mean.setData(x, z_mean)
            self.curve_min.setData(x, value[:, 2])
            self.curve_max.setData(x, value[:, 3])

            if self.text_item is not None:
                z_valid = np.isfinite(z_mean)
                z_mean = value[z_valid, 0]
                z_var = value[z_valid, 1]
                z_min = value[z_valid, 2]
                z_max = value[z_valid, 3]
                if len(z_mean):
                    v_mean = np.mean(z_mean)
                    v_min = np.min(z_min)
                    if not np.isfinite(v_min):
                        v_min = np.min(z_mean)
                    v_max = np.max(z_max)
                    if not np.isfinite(v_max):
                        v_max = np.max(z_mean)
                    mean_delta = z_mean - v_mean
                    # combine variances across the combined samples
                    v_std = np.sqrt(np.sum(np.square(mean_delta, out=mean_delta) + z_var) / len(z_mean))
                    self.text_item.data_update(v_mean, v_std, v_max, v_min)
                    self.yaxis_autorange(v_min, v_max)

