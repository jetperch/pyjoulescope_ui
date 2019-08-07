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
import logging
log = logging.getLogger(__name__)


class Worker(QtCore.QObject):
    sigProgress = QtCore.Signal(float)
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
            msg = self._invoker.range_tool_obj.run(self._invoker)
        except:
            log.exception('During range tool run()')
            msg = 'Error during range tool run()'
        self.sigProgress.emit(1.0)
        if msg is None:
            msg = ''
        self.sigFinished.emit(msg)


class RangeToolIterable:

    def __init__(self, parent, samples_per_iteration, progress):
        self._parent = parent
        self._x_start, self._x_stop = self._parent.sample_range
        self._x_next = self._x_start
        self._samples_per_iteration = int(samples_per_iteration)
        self._progress = progress

    def __iter__(self):
        return self

    def __next__(self):
        if self._x_next >= self._x_stop:
            self._progress(1.0)
            raise StopIteration()
        if self._parent.cancel:
            raise RuntimeError('')
        self._progress((self._x_next - self._x_start) / (self._x_stop - self._x_start))
        x_next = self._x_next + self._samples_per_iteration
        if x_next > self._x_stop:
            x_next = self._x_stop
        data = self._parent.view.samples_get(self._x_start, x_next)
        self._x_next = x_next
        return data


class RangeToolInvoke(QtCore.QObject):  # also implements RangeToolInvocation

    sigFinished = QtCore.Signal(object, str)  # range_tool, error message or ''

    def __init__(self, parent, range_tool, app_config, plugin_config):
        super().__init__(parent)
        self.range_tool = range_tool
        self.app_config = app_config
        self.plugin_config = plugin_config
        self.range_tool_obj = None
        self.sample_range = None
        self.view = None
        self._worker = None
        self._thread = None
        self._progress = None
        self.cancel = False

        self.sample_count = 0
        self.sample_frequency = 0
        self.calibration = None
        self._iterable = None

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
        return self.view.samples_get(*self.sample_range)

    def iterate(self, samples_per_iteration=None):
        if samples_per_iteration is None or samples_per_iteration <= 0:
            samples_per_iteration = self.sample_frequency
        if self._worker is not None:
            progress = self._worker.sigProgress.emit
        else:
            progress = self.progress
        return RangeToolIterable(self, samples_per_iteration, progress=progress)

    @QtCore.Slot(float)
    def progress(self, fraction):
        if self._progress is not None:
            self._progress.setValue(int(fraction * 1000))

    def run(self, view, x_start, x_stop):
        """Export data request.

        :param view: The view implementation with TBD API.
        :param x_start: The starting position in x-axis units.
        :param x_stop: The stopping position in x-axis units.
        """
        t1, t2 = min(x_start, x_stop), max(x_start, x_stop)
        log.info('range_tool %s(%s, %s)', self.range_tool.name, t1, t2)
        s1 = view.time_to_sample_id(x_start)
        s2 = view.time_to_sample_id(x_stop)
        if s1 is None or s2 is None:
            return 'time out of range'
        self.sample_range = (s1, s2)
        self.sample_count = s2 - s1
        self.sample_frequency = view.sampling_frequency
        self.view = view
        self.calibration = self.view.calibration

        self.range_tool_obj = self.range_tool.fn()
        try:
            if hasattr(self.range_tool_obj, 'run_pre'):
                self.range_tool_obj.run_pre(self)
        except:
            log.exception('During range tool run_pre()')
            return

        self._thread = QtCore.QThread()
        title = f'{self.range_tool.name} in progress...'
        self._progress = QtWidgets.QProgressDialog(title, 'Cancel', 0, 1000, self.parent())
        self._progress.setWindowModality(QtCore.Qt.WindowModal)
        self._worker = Worker(self)
        self._worker.sigProgress.connect(self.progress)
        self._worker.sigFinished.connect(self.on_finished)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._worker.deleteLater)
        self._progress.canceled.connect(self.on_cancel)
        self._thread.start()
        self._progress.forceShow()

    def on_cancel(self):
        self.cancel = True

    def on_finished(self, msg):
        self._thread.quit()
        self._thread.wait()
        self._progress.hide()
        self._progress.close()
        self._thread = None
        self._progress = None
        self._worker = None

        try:
            if hasattr(self.range_tool_obj, 'run_post'):
                self.range_tool_obj.run_post(self)
        except:
            log.exception('During range tool run_post()')
            return

        self.sigFinished.emit(self.range_tool, msg)
