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
import time


class ProcessMonitor(QtCore.QObject):
    update = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pid = os.getpid()
        self._process = psutil.Process(self._pid)

        # state
        self._time = time.time()
        self._process_time_ns = time.process_time_ns()
        self._cpu_count = psutil.cpu_count()
        psutil.cpu_times_percent(0)

        self._timer = QtCore.QTimer(self)
        self._timer.setTimerType(QtGui.Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(1000)  # = 1 / render_frame_rate

    @QtCore.Slot()
    def _on_timer(self):
        time_now = time.time()
        process_time_ns = time.process_time_ns()
        dt = time_now - self._time

        process_time_self = (process_time_ns - self._process_time_ns) / (1e9 * dt * self._cpu_count) * 100
        process_time_all = 100 - psutil.cpu_times_percent(0).idle
        mem = self._process.memory_info().rss
        vm = psutil.virtual_memory()

        data = {
            'cpu_utilization': {
                'self': process_time_self,
                'all': process_time_all,
                'units': '%',
            },
            'memory_utilization': {
                'self': mem,
                'available': vm.available,
                'total': vm.total,
                'units': 'B',
            },
            'memory_utilization_percent': {
                'self': mem / vm.total * 100,
                'used': vm.percent,
                'available': 100 - vm.percent,
                'units': '%',
            },
        }
        self.update.emit(data)
        self._time = time_now
        self._process_time_ns = process_time_ns
