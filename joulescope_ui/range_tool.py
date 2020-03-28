# Copyright 2018-2019 Jetperch LLC
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

"""Run a tool that operates over a data range.

The tool is executed from a separate thread.
"""

from PySide2 import QtWidgets, QtCore
import threading
import time
import logging
log = logging.getLogger(__name__)


SAMPLES_PER_ITERATION_DEFAULT_MIN = 1000
PROGRESS_COUNT = 1000
PROGRESS_UPDATE_RATE = 0.100  # seconds


class Worker(QtCore.QObject):
    sigFinished = QtCore.Signal(str)

    def __init__(self, invoker):
        super().__init__()
        self._invoker = invoker
        self._cancel = False

    @QtCore.Slot()
    def cancel(self):
        self._invoker.stop()

    def run(self):
        try:
            msg = self._invoker._thread_run()
        except:
            log.exception('During range tool run()')
            msg = 'Error during range tool run()'
        if msg is None:
            msg = ''
        self.sigFinished.emit(msg)


class RangeToolIterable:

    def __init__(self, parent, samples_per_iteration):
        self._parent = parent
        self._x_start, self._x_stop = self._parent.sample_range
        self._x_next = self._x_start
        self._samples_per_iteration = int(samples_per_iteration)

    def __iter__(self):
        return self

    def __next__(self):
        if self._x_next >= self._x_stop:
            raise StopIteration()
        if self._parent._cancel:
            raise RuntimeError('Range tool canceled by user')
        self._parent.progress((self._x_next - self._x_start) / (self._x_stop - self._x_start))
        x_next = self._x_next + self._samples_per_iteration
        if x_next > self._x_stop:
            x_next = self._x_stop
        data = self._parent._view.samples_get(self._x_next, x_next, units='samples')
        self._x_next = x_next
        return data


class RangeToolInvoke(QtCore.QObject):  # also implements RangeToolInvocation
    sigProgress = QtCore.Signal(int)
    sigFinished = QtCore.Signal(object, str)  # range_tool, error message or ''

    def __init__(self, parent, range_tool, cmdp):
        super().__init__(parent)
        self._parent = parent
        self._range_tool = range_tool
        self.cmdp = cmdp
        self._range_tool_obj = None
        self.sample_range = None
        self._time_range = None
        self._view = None
        self._worker = None
        self._thread = None
        self._progress = None
        self._cancel = False
        self._progress_time_last = time.time()

        self.sample_count = 0
        self.sample_frequency = 0
        self.calibration = None
        self.statistics = None
        self._iterable = None
        self._commands = []

        cmdp.define('Plugins/#state/voltage_range', dtype=int, default=0)  # for file export

    def __iter__(self):
        self._iterable = self.iterate()
        return self._iterable

    def __next__(self):
        try:
            return self._iterable.__next__()
        except StopIteration:
            self._iterable = None
            raise

    def samples_get(self):
        return self._view.samples_get(*self.sample_range, units='samples')

    def iterate(self, samples_per_iteration=None):
        if samples_per_iteration is None or samples_per_iteration <= 0:
            if self.sample_frequency < SAMPLES_PER_ITERATION_DEFAULT_MIN:
                samples_per_iteration = SAMPLES_PER_ITERATION_DEFAULT_MIN
            else:
                samples_per_iteration = int(self.sample_frequency)
        else:
            samples_per_iteration = int(samples_per_iteration)
        return RangeToolIterable(self, samples_per_iteration)

    def progress(self, fraction):
        current_time = time.time()
        if current_time - self._progress_time_last > PROGRESS_UPDATE_RATE:
            self.sigProgress.emit(int(fraction * PROGRESS_COUNT))
            self._progress_time_last = current_time

    def _x_map_to_parent(self, x):
        t1, t2 = self._time_range
        if x < 0.0:
            raise ValueError('x too small')
        if x >= (t2 - t1):
            raise ValueError('x too big')
        return t1 + x

    def marker_single_add(self, x):
        x = self._x_map_to_parent(x)
        self._commands.append(lambda: self.cmdp.publish('!Widgets/Waveform/Markers/single_add', x))

    def marker_dual_add(self, x1, x2):
        x1 = self._x_map_to_parent(x1)
        x2 = self._x_map_to_parent(x2)
        self._commands.append(lambda: self.cmdp.publish('!Widgets/Waveform/Markers/dual_add', (x1, x2)))

    def run(self, view, statistics, x_start, x_stop):
        """Export data request.

        :param view: The view implementation with TBD API.
        :param statistics: The statistics (see :meth:`joulescope.driver.statistics_get`).
        :param x_start: The starting position in x-axis units.
        :param x_stop: The stopping position in x-axis units.
        """
        self.statistics = statistics
        t1, t2 = min(x_start, x_stop), max(x_start, x_stop)
        log.info('range_tool %s(%s, %s)', self._range_tool.name, t1, t2)
        self._time_range = (t1, t2)
        s1 = view.time_to_sample_id(t1)
        s2 = view.time_to_sample_id(t2)
        if s1 is None or s2 is None:
            return 'time out of range'
        self.sample_range = (s1, s2)
        self.sample_count = s2 - s1
        self.sample_frequency = view.sampling_frequency
        self.calibration = view.calibration
        self._view = view

        self._range_tool_obj = self._range_tool.fn()
        try:
            if hasattr(self._range_tool_obj, 'run_pre'):
                rc = self._range_tool_obj.run_pre(self)
                if rc is not None:
                    log.info('%s run_pre failed: %s', self._range_tool.name, rc)
                    return
        except:
            log.exception('During range tool run_pre()')
            return

        title = f'{self._range_tool.name} in progress...'
        self._progress = QtWidgets.QProgressDialog(title, 'Cancel', 0, PROGRESS_COUNT, self._parent)
        self._progress.setWindowTitle('Progress')
        self._progress.setWindowModality(QtCore.Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._worker = Worker(self)
        self._worker.sigFinished.connect(self._on_finished, type=QtCore.Qt.QueuedConnection)
        self._worker.moveToThread(self._thread)
        self._thread = threading.Thread(target=self._worker.run)
        self._progress.canceled.connect(self._on_cancel, type=QtCore.Qt.QueuedConnection)
        self.sigProgress.connect(self._progress.setValue, type=QtCore.Qt.QueuedConnection)
        self._thread.start()

    def _thread_run(self):
        return self._range_tool_obj.run(self)

    def _on_cancel(self):
        self._cancel = True

    def _on_finished(self, msg):
        self._thread.join()
        self.sigProgress.disconnect()
        self._progress.hide()
        self._progress.close()
        time.sleep(0.0)  # yield to let progress window close
        self._thread = None
        self._progress = None
        self._worker = None

        try:
            if hasattr(self._range_tool_obj, 'run_post'):
                self._range_tool_obj.run_post(self)
        except:
            log.exception('During range tool run_post()')
            return

        while len(self._commands):
            command = self._commands.pop(0)
            try:
                command()
            except:
                log.exception('During range tool command')

        self.sigFinished.emit(self._range_tool, msg)
