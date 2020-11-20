# Copyright 2018 Jetperch LLC
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

from joulescope.data_recorder import DataReader
from joulescope.view import data_array_to_update
from joulescope_ui.data_view_api import DataViewApi
from joulescope import span
import os
import numpy as np
import threading
import queue
import weakref
import logging


TIMEOUT = 10.0


class RecordingView:
    """A user-interface-compatible device that displays previous recorded data"""
    def __init__(self, parent):
        self._parent = weakref.ref(parent)
        self._x_range = [0.0, 1.0]
        self._span = None
        self._x = None
        self._samples_per = 1
        self._refresh_requested = False
        self._cache = None
        self.on_update_fn = None  # callable(data)
        self._log = logging.getLogger(__name__)

    def __str__(self):
        return f'RecordingView()'

    def __len__(self):
        if self._span is None:
            return 0
        return self._span.length

    @property
    def sampling_frequency(self):
        return self._parent().sampling_frequency

    @property
    def calibration(self):
        return self._parent().calibration

    @property
    def limits(self):
        """Get the (x_min, x_max) limits for the view."""
        if self._span is not None:
            return list(self._span.limits)
        return None

    @property
    def _reader(self):
        return self._parent()._reader

    @property
    def voltage_range(self):
        return self._reader.voltage_range

    def _on_x_change(self, cmd, kwargs):
        x_range = self._x_range
        if cmd == 'resize':  # {pixels: int}
            length = kwargs['pixels']
            if length is not None and length != self._span.length:
                self._log.info('resize %s', length)
                self._span.length = length
                self._cache = None  # invalidate
            x_range, self._samples_per, self._x = self._span.conform_discrete(x_range)
        elif cmd == 'span_absolute':  # {range: (start: float, stop: float)}]
            x_range, self._samples_per, self._x = self._span.conform_discrete(kwargs.get('range'))
        elif cmd == 'span_relative':  # {pivot: float, gain: float}]
            x_range, self._samples_per, self._x = self._span.conform_discrete(
                x_range, gain=kwargs.get('gain'), pivot=kwargs.get('pivot'))
        elif cmd == 'span_pan':
            delta = kwargs.get('delta', 0.0)
            x_range = [x_range[0] + delta, x_range[-1] + delta]
            x_range, self._samples_per, self._x = self._span.conform_discrete(x_range)
        elif cmd == 'refresh':
            self._cache = None  # invalidate
            self._refresh_requested = True
            return
        else:
            self._log.warning('on_x_change(%s) unsupported', cmd)
            return

        if self._x_range != x_range:
            self._cache = None  # invalidate
        self._x_range = x_range
        self._refresh_requested = True
        self._log.info('cmd=%s, changed=%s, length=%s, span=%s, range=%s, samples_per=%s',
                 cmd, self._cache is None, len(self), self._x_range,
                 self._x_range[1] - self._x_range[0], self._samples_per)

    def _update(self):
        if not callable(self.on_update_fn) or self._reader is None:
            return
        self._refresh_requested = False
        if self._cache is not None:
            self.on_update_fn(self._cache)
            return
        f = self._reader.sampling_frequency
        self._log.info('update: x_range=%r', self._x_range)
        start, stop = [int(x * f) for x in self._x_range]
        self._log.info('update: x_range=%r => (%s, %s)', self._x_range, start, stop)
        data = self._reader.data_get(start, stop, self._samples_per)
        t_start = start / self._reader.sampling_frequency
        t_stop = stop / self._reader.sampling_frequency
        x = np.linspace(t_start, t_stop, len(data), dtype=np.float64)
        if not len(x):
            self._log.info('update: empty')
        else:
            self._log.info('update: len=%d, x_range=>(%s, %s)', len(data), x[0], x[-1])
        self._cache = data_array_to_update(self.limits, x, data)
        self.on_update_fn(self._cache)

    def time_to_sample_id(self, t):
        if self._reader is None:
            return None
        return self._reader.time_to_sample_id(t)

    def sample_id_to_time(self, t):
        if self._reader is None:
            return None
        return self._reader.sample_id_to_time(t)

    def _statistics_get(self, start=None, stop=None, units=None):
        """Get the statistics for the collected sample data over a time range.

        :param start: The starting time relative to the streaming start time.
        :param stop: The ending time.
        :param units: The units for start and stop.
            'seconds' or None is in floating point seconds relative to the view.
            'samples' is in stream buffer sample indices.
        :return: The statistics data structure.
        """
        if self._reader is None:
            return None
        return self._reader.statistics_get(start=start, stop=stop, units=units)

    def _statistics_get_multiple(self, ranges, units=None):
        return [self._statistics_get(x[0], x[1], units=units) for x in ranges]

    def _samples_get(self, start=None, stop=None, units=None, fields=None):
        r = self._reader
        if r is None:
            return None
        return r.samples_get(start, stop, units, fields)

    def open(self):
        f = self._reader.sampling_frequency
        if f <= 0:
            self._log.warning('Invalid sampling_frequency %r, assume 1 Hz', f)
            f = 1.0
        r = self._reader.sample_id_range
        x_lim = [x / f for x in r]
        self._span = span.Span(x_lim, 1 / f, 100)
        self._x_range, self._samples_per, self._x = self._span.conform_discrete(x_lim)
        self._cache = None  # invalidate

    def close(self):
        if self._parent()._thread is not None:
            return self._parent()._post_block('view_close', None, self)

    def refresh(self, force=None):
        return self._parent()._post('refresh', self, {'force': force})

    def on_x_change(self, cmd, kwargs):
        self._parent()._post('on_x_change', self, (cmd, kwargs))

    def samples_get(self, start=None, stop=None, units=None, fields=None):
        """Get exact samples over a range.

        :param start: The starting time.
        :param stop: The ending time.
        :param units: The units for start and stop.
            'seconds' or None is in floating point seconds relative to the view.
            'samples' is in stream buffer sample indicies.
        :param fields: The list of field names to get.
        """
        args = {'start': start, 'stop': stop, 'units': units, 'fields': fields}
        return self._parent()._post_block('samples_get', self, args)

    def statistics_get(self, start=None, stop=None, units=None, callback=None):
        """Get statistics over a range.

        :param start: The starting time.
        :param stop: The ending time.
        :param units: The units for start and stop.
            'seconds' or None is in floating point seconds relative to the view.
            'samples' is in stream buffer sample indicies.
        :param callback: The optional callable.  When provided, this method will
            not block and the callable will be called with the statistics
            data structure from the view thread.
        :return: The statistics data structure or None if callback is provided.
        """
        args = {'start': start, 'stop': stop, 'units': units}
        if callback is None:
            return self._parent()._post_block('statistics_get', self, args)
        else:
            self._parent()._post('statistics_get', self, args, callback)
            return

    def statistics_get_multiple(self, ranges, units=None, callback=None, source_id=None):
        args = {'ranges': ranges, 'units': units, 'source_id': source_id}
        if callback is None:
            return self._parent()._post_block('statistics_get_multiple', self, args)
        else:
            self._parent()._post('statistics_get_multiple', self, args, callback)
            return

    def ping(self, *args, **kwargs):
        return self._parent()._post_block('ping', self, (args, kwargs))


class RecordingViewerDevice:
    """A user-interface-compatible device that displays previous recorded data

    :param filename: The filename path to the pre-recorded data.
    """
    def __init__(self, filename, current_ranging_format=None):
        if isinstance(filename, str) and not os.path.isfile(filename):
            raise IOError('file not found')
        self._filename = filename
        self._current_ranging_format = current_ranging_format
        self._reader = None
        self._views = []
        self._coalesce = {}
        self._thread = None
        self._cmd_queue = queue.Queue()  # tuples of (command, args, callback)
        self._response_queue = queue.Queue()
        self._quit = False
        self._log = logging.getLogger(__name__)

    def __str__(self):
        return os.path.basename(self._filename)

    @property
    def filename(self):
        return self._filename

    @property
    def sampling_frequency(self):
        if self._reader is None:
            return None
        return self._reader.sampling_frequency

    @property
    def calibration(self):
        if self._reader is None:
            return None
        return self._reader.calibration

    @property
    def voltage_range(self):
        return self._reader.voltage_range

    def _cmd_process(self, cmd, view, args, cbk):
        rv = None
        try:
            # self._log.debug('_cmd_process %s - start', cmd)
            if cmd == 'refresh':
                view._refresh_requested = True
            elif cmd == 'on_x_change':
                rv = view._on_x_change(*args)
            elif cmd == 'samples_get':
                rv = view._samples_get(**args)
            elif cmd == 'statistics_get':
                rv = view._statistics_get(**args)
            elif cmd == 'statistics_get_multiple':
                rv = view._statistics_get_multiple(**args)
            elif cmd == 'view_factory':
                self._views.append(args)
                rv = args
            elif cmd == 'view_close':
                if args in self._views:
                    self._views.remove(args)
            elif cmd == 'open':
                rv = self._open()
            elif cmd == 'close':
                rv = self._close()
            elif cmd == 'ping':
                rv = args
            else:
                self._log.warning('unsupported command %s', cmd)
        except:
            self._log.exception('While running command')
        if callable(cbk):
            try:
                cbk(rv)
            except:
                self._log.exception('in callback')

    def run(self):
        cmd_count = 0
        timeout = 1.0
        self._log.info('RecordingViewerDevice.start')
        while not self._quit:
            try:
                cmd, view, args, cbk = self._cmd_queue.get(timeout=timeout)
            except queue.Empty:
                timeout = 1.0
                for value in self._coalesce.values():
                    self._cmd_process(*value)
                self._coalesce.clear()
                for view in self._views:
                    if view._refresh_requested:
                        view._update()
                cmd_count = 0
                continue
            cmd_count += 1
            timeout = 0.0
            try:
                source_id = args.pop('source_id')
            except:
                source_id = None
            if source_id is not None:
                key = f'{view}_{cmd}_{source_id}'  # keep most recent only
                self._coalesce[key] = (cmd, view, args, cbk)
            else:
                self._cmd_process(cmd, view, args, cbk)
        self._log.info('RecordingViewerDevice.run done')

    def _post(self, command, view=None, args=None, cbk=None):
        if self._thread is None:
            self._log.info('RecordingViewerDevice._post(%s) when thread not running', command)
        else:
            self._cmd_queue.put((command, view, args, cbk))

    def _post_block(self, command, view=None, args=None, timeout=None):
        timeout = TIMEOUT if timeout is None else float(timeout)
        # self._log.debug('_post_block %s start', command)
        while not self._response_queue.empty():
            self._log.warning('response queue not empty')
            try:
                self._response_queue.get(timeout=0.0)
            except queue.Empty:
                pass
        if self._thread is None:
            raise IOError('View thread not running')
        self._post(command, view, args, lambda rv_=None: self._response_queue.put(rv_))
        try:
            rv = self._response_queue.get(timeout=timeout)
        except queue.Empty as ex:
            self._log.error('RecordingViewerDevice thread hung: %s - FORCE CLOSE', command)
            self._post('close', None, None)
            self._thread.join(timeout=TIMEOUT)
            self._thread = None
            rv = ex
        except Exception as ex:
            rv = ex
        if isinstance(rv, Exception):
            raise IOError(rv)
        # self._log.debug('_post_block %s done', command)  # rv
        return rv

    def _open(self):
        self._reader = DataReader()
        if self._current_ranging_format is not None:
            self._reader.raw_processor.suppress_mode = self._current_ranging_format
        self._reader.open(self._filename)  # todo progress bar updates
        self._log.info('RecordingViewerDevice.open')

    def _close(self):
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        self._quit = True

    def view_factory(self):
        view = RecordingView(self)
        return self._post_block('view_factory', None, view)

    def open(self, event_callback_fn=None):
        self.close()
        self._log.info('open')
        self._thread = threading.Thread(name='view', target=self.run)
        self._thread.start()
        self._post_block('open')

    def close(self):
        if self._thread is not None:
            self._log.info('close')
            try:
                self._post_block('close')
            except Exception:
                self._log.exception('while attempting to close')
            self._thread.join(timeout=TIMEOUT)
            self._thread = None
