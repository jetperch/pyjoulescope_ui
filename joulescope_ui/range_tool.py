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

from PySide2 import QtCore
import threading
import time
from queue import Queue, Empty
import logging
log = logging.getLogger(__name__)


SAMPLES_PER_ITERATION_DEFAULT_MIN = 1000
PROGRESS_COUNT = 1000
PROGRESS_UPDATE_RATE = 0.100  # seconds


class RangeToolIterable:

    def __init__(self, parent, samples_per_iteration):
        self._parent = parent
        self._x_start, self._x_stop = self._parent.sample_range
        self._x_next = self._x_start
        self._samples_per_iteration = int(samples_per_iteration)

    def __iter__(self):
        return self

    def __next__(self):
        if self._x_next >= self._x_stop or self._parent.is_cancelled:
            self._parent = None
            raise StopIteration()
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

    def __init__(self, parent, resync_handler, range_tool, cmdp):
        super().__init__(parent)
        self._parent = parent
        self._main_thread = threading.current_thread()
        self._qt_resync_handler = resync_handler
        self._range_tool = range_tool
        self.cmdp = cmdp
        self._range_tool_obj = None
        self.sample_range = None
        self._time_range = None
        self._view = None
        self._thread = None
        self._message_queue = Queue()
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

    @property
    def is_cancelled(self):
        return self._cancel

    def samples_get(self):
        return self._view.samples_get(*self.sample_range, units='samples')

    def _assert_worker_thread(self):
        assert (threading.current_thread() == self._thread)

    def _assert_main_thread(self):
        assert (threading.current_thread() == self._main_thread)

    def iterate(self, samples_per_iteration=None):
        self._assert_worker_thread()
        if samples_per_iteration is None or samples_per_iteration <= 0:
            if self.sample_frequency < SAMPLES_PER_ITERATION_DEFAULT_MIN:
                samples_per_iteration = SAMPLES_PER_ITERATION_DEFAULT_MIN
            else:
                samples_per_iteration = int(self.sample_frequency)
        else:
            samples_per_iteration = int(samples_per_iteration)
        return RangeToolIterable(self, samples_per_iteration)

    def _qt_resync(self, cmd, args):
        self._assert_worker_thread()
        self._message_queue.put((cmd, args))
        self._qt_resync_handler()  # causes self.on_resync()

    def progress(self, fraction):
        self._assert_worker_thread()
        current_time = time.time()
        if current_time - self._progress_time_last > PROGRESS_UPDATE_RATE:
            value = int(fraction * PROGRESS_COUNT)
            self._qt_resync('progress', value)
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

        :param view: The view implementation.
        :param statistics: The statistics (see :meth:`joulescope.driver.statistics_get`).
        :param x_start: The starting position in x-axis units.
        :param x_stop: The stopping position in x-axis units.
        """
        self._assert_main_thread()
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
                    log.warning('%s run_pre failed: %s', self._range_tool.name, rc)
                    self._finalize(f'{self._range_tool.name}: {rc}')
                    return
        except:
            log.exception('During range tool run_pre()')
            return
        self._thread = threading.Thread(target=self._thread_run)
        self._thread.start()

    def _thread_run(self):
        self._assert_worker_thread()
        try:
            rv = self._range_tool_obj.run(self)
            if self.is_cancelled:
                rv = f'{self._range_tool.name}: Cancelled'
        except Exception as ex:
            log.exception('range tool run exception')
            rv = f'{self._range_tool.name}: ERROR'
        self._qt_resync('done', rv)

    def on_resync(self):
        self._assert_main_thread()  # indirectly by self._qt_resync_callback
        while True:
            try:
                cmd, args = self._message_queue.get(timeout=0.0)
            except Empty:
                break
            except:
                log.exception('on_resync message_queue get')
            if cmd == 'progress':
                self.sigProgress.emit(args)
            elif cmd == 'done':
                self._on_finished(args)

    @QtCore.Slot()
    def on_cancel(self):
        log.info('range tool cancelled by user')
        self._cancel = True

    def _on_finished(self, msg):
        self._assert_main_thread()
        self.sigProgress.emit(1000)
        self.sigProgress.disconnect()
        self._thread.join()
        self._thread = None
        if not self.is_cancelled:
            try:
                if hasattr(self._range_tool_obj, 'run_post'):
                    self._range_tool_obj.run_post(self)
            except:
                log.exception('During range tool run_post()')
                return

            while not self.is_cancelled and len(self._commands):
                command = self._commands.pop(0)
                try:
                    command()
                except:
                    log.exception('During range tool command')
        self._finalize(msg)

    def _finalize(self, msg):
        self._assert_main_thread()
        log.info('range tool finalize')
        self.sigFinished.emit(self._range_tool, msg)
        self._range_tool_obj = None
        self._parent = None
        self._qt_resync_handler = None
        self._range_tool = None
        self.cmdp = None
