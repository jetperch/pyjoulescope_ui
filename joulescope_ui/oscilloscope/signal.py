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

from .signal_statistics import SignalStatistics, si_format
from .signal_viewbox import SignalViewBox
from joulescope.units import unit_prefix, three_sig_figs
from .yaxis import YAxis
import pyqtgraph as pg
import numpy as np
import logging


log = logging.getLogger(__name__)
CURVE_WIDTH = 1
AUTO_RANGE_FRACT = 0.45  # autorange when current range smaller than existing range by this fractional amount.


INTEGRATION_UNITS = {
    'A': 'C',
    'W': 'J'
}


class Signal:

    def __init__(self, name, units=None, y_limit=None):
        self.text_item = None
        self.name = name
        self.units = units
        self.vb = SignalViewBox(name=self.name)
        if y_limit is not None:
            y_min, y_max = y_limit
            self.vb.setLimits(yMin=y_min, yMax=y_max)
            self.vb.setYRange(y_min, y_max)
        self.y_axis = YAxis(name)
        self.y_axis.linkToView(self.vb)
        self.y_axis.setGrid(128)
        self._most_recent_data = None
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

    def removeFromLayout(self, layout):
        rows = layout.ci.layout.rowCount()
        for row in range(rows):
            if layout.getItem(row, 1) == self.vb:
                layout.removeItem(self.y_axis)
                layout.removeItem(self.vb)
                if self.text_item:
                    layout.removeItem(self.text_item)
                return row

    def yaxis_autorange(self, v_min, v_max):
        _, (vb_min, vb_max) = self.vb.viewRange()
        if not np.isfinite(v_min):
            v_min = vb_min
        if not np.isfinite(v_max):
            v_max = vb_max
        vb_range = vb_max - vb_min
        v_range = v_max - v_min
        update_range = (v_max > vb_max) or (v_min < vb_min)
        if vb_range > 0:
            update_range |= (v_range / vb_range) < AUTO_RANGE_FRACT
        if update_range:
            self.vb.setYRange(v_min, v_max)

    def data_clear(self):
        self._most_recent_data = None
        self.curve_mean.clear()
        self.curve_mean.update()
        self._min_max_disable()

    def _min_max_enable(self):
        if not self.curve_min.isVisible():
            self.curve_max.show()
            self.curve_min.show()

    def _min_max_disable(self):
        if self.curve_min.isVisible():
            self.curve_max.clear()
            self.curve_max.update()
            self.curve_max.hide()
            self.curve_min.clear()
            self.curve_min.update()
            self.curve_min.hide()

    def update(self, x, value):
        """Update the signal data.

        :param x: The length N array of x-axis time in seconds.
        :param value: The y-axis data which can be:
            * length N array
            * length Nx4 array of [mean, var, min, max].  Note that
              var, min, max may be NaN when not available.
        """
        self.text_item.data_clear()
        if x is None or value is None or not len(x):
            self.data_clear()
            return
        x_range = x[-1] - x[0]

        # get the mean value regardless of shape
        shape_len = len(value.shape)
        if shape_len == 1:
            z_mean = value
        elif shape_len == 2:
            z_mean = value[:, 0]
        else:
            log.warning('Unsupported value shape: %s', str(value.shape))

        # get the valid mean values regardless of shape
        z_valid = np.isfinite(z_mean)
        x = x[z_valid]
        z_mean = z_mean[z_valid]
        if not len(z_mean):
            self.data_clear()
            return

        self._most_recent_data = [x, z_mean, None, None, None]
        z_var, z_min, z_max = None, None, None
        if shape_len == 2 and value.shape[1] == 4:
            z_min = value[z_valid, 2]
            if np.isfinite(z_min[0]):
                z_var = value[z_valid, 1]
                z_max = value[z_valid, 3]
                self._most_recent_data = [x, z_mean, z_var, z_min, z_max]
            else:
                z_min = None

        # compute statistics over the visible window
        z = z_mean
        self.curve_mean.setData(x, z)
        if z_min is None:
            self._min_max_disable()
            v_mean = np.mean(z)
            v_std = np.std(z)
            v_max = np.max(z)
            v_min = np.min(z)
        else:
            self._min_max_enable()
            self.curve_min.setData(x, z_min)
            self.curve_max.setData(x, z_max)

            v_mean = np.mean(z_mean)
            v_min = np.min(z_min)
            v_max = np.max(z_max)
            mean_delta = z_mean - v_mean
            # combine variances across the combined samples
            v_std = np.sqrt(np.sum(np.square(mean_delta, out=mean_delta) + z_var) / len(z_mean))

        if self.text_item is not None:
            labels = {'μ': v_mean, 'σ': v_std, 'min': v_min, 'max': v_max, 'p2p': v_max - v_min}
            txt_result = si_format(labels, units=self.units)
            integration_units = INTEGRATION_UNITS.get(self.units)
            if integration_units is not None:
                txt_result += si_format({'∫': v_mean * x_range}, units=integration_units)
            self.text_item.data_update(txt_result)

        self.yaxis_autorange(v_min, v_max)

    def statistics_at(self, x):
        """Get the statistics at the provided x value.

        :param x: The x-axis value in seconds.
        :return: The dict mapping parameter name to float value.
        """
        if self._most_recent_data is None:
            return {}
        z_x, z_mean, z_var, z_min, z_max = self._most_recent_data
        if not z_x[0] <= x <= z_x[-1]:
            return {}
        idx = np.argmax(z_x >= x)
        y_mean = float(z_mean[idx])
        if z_min is not None:
            y_var = float(z_var[idx])
            y_min = float(z_min[idx])
            y_max = float(z_max[idx])
            labels = {'μ': y_mean, 'σ': np.sqrt(y_var), 'min': y_min, 'max': y_max, 'p2p': y_max - y_min}
        else:
            labels = {'μ': y_mean}
        return labels

