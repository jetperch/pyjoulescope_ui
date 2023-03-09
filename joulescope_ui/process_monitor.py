# Copyright 2023 Jetperch LLC
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


from PySide6 import QtCore, QtGui
import numpy as np
import os
import psutil


class ProcessMonitor(QtCore.QObject):
    update = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = os.getpid()
        self._process = psutil.Process(self._pid)

        self._idx = 0
        self._utilization = np.zeros((10, 4), dtype=float)

        self._timer = QtCore.QTimer()
        self._timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(100)  # = 1 / render_frame_rate

    def _on_timer(self):
        vm = psutil.virtual_memory()
        self._utilization[self._idx, 0] = self._process.cpu_percent() / psutil.cpu_count()
        self._utilization[self._idx, 1] = psutil.cpu_percent()
        self._utilization[self._idx, 2] = self._process.memory_info().rss
        self._utilization[self._idx, 3] = vm.used
        self._idx += 1
        if self._idx >= 10:
            v = np.mean(self._utilization, axis=0)
            data = {
                'cpu_utilization': {
                    'self': v[0],
                    'all': v[1],
                    'units': '%',
                },
                'memory_utilization': {
                    'self': v[2],
                    'all': v[3],
                    'total': vm.total,
                    'units': 'B',
                },
            }
            self.update.emit(data)
            self._idx = 0


