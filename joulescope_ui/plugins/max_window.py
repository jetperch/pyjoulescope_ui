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

import logging
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets
from .max_window_config_widget import Ui_Dialog
from . import plugin_helpers


log = logging.getLogger(__name__)

PLUGIN = {
    'name': 'Max Window',
    'description': 'Maximum sum of voltage/current/power samples in a given time window',
}


class MaxWindow:

    def __init__(self):
        self._cfg = None
        self.data = None

    def run_pre(self, data):
        max_time_len = data.time_range[1] - data.time_range[0]
        rv = MaxWindowDialog(max_time_len).exec_()
        if rv is None:
            return 'Cancelled'
        self._cfg = rv

    def run(self, data):
        time_len = self._cfg['time_len']
        signal = self._cfg['signal']

        max_sum, start, end = plugin_helpers.max_sum_in_window(data, signal, time_len)

        self.data = {
            'max_sum': max_sum,
            'start': start,
            'end': end
        }

    def run_post(self, data):
        if not self.data:
            log.exception('Max Window function failed to produce data')
            return

        start_time = self.data['start'] / data.sample_frequency
        end_time = self.data['end'] / data.sample_frequency

        data.marker_dual_add(start_time, end_time)


class MaxWindowDialog(QtWidgets.QDialog):
    def __init__(self, max_time_len):
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.ui.signal.addItem("current")
        self.ui.signal.addItem("voltage")
        self.ui.signal.addItem("power")
        self.ui.time_len.setMaximum(max_time_len)
        starting_value = 10 ** np.round(np.log10(max_time_len / 1000))
        value = min(max_time_len, max(0.00001, starting_value))
        self.ui.time_len.setValue(value)

    def exec_(self):
        if QtWidgets.QDialog.exec_(self) == 1:
            time_len = float(self.ui.time_len.value())
            signal = str(self.ui.signal.currentText())
            return {
                'time_len': time_len,
                'signal': signal,
            }
        else:
            return None


def plugin_register(api):
    """Register the example plugin.

    :param api: The :class:`PluginServiceAPI` instance.
    :return: True on success any other value on failure.
    """
    api.range_tool_register('Analysis/Max Window', MaxWindow)
    return True
