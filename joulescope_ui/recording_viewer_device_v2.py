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

from pyjls import Reader, DataType, AnnotationType, SignalType, SourceDef, SignalDef, SummaryFSR
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
        return None

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
        return 0

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

    def _get(self, start, stop, incr=None):
        """Get the statistics data.

        :param start: The starting sample id (inclusive).
        :param stop: The stop sample id (exclusive).
        :param incr: The increment for each returned value.
            None (default) is equivalent to 1.
        :return: A statistics data structure.
        """
        self._log.info('get: x_range=%r => (%s, %s, %s)', self._x_range, start, stop, incr)
        reader = self._reader
        fs = self.sampling_frequency
        self._log.info('update: x_range=%r => (%s, %s)', self._x_range, start, stop)
        if incr is None:
            incr = 1
        elif incr < 1:
            msg = f'incr {incr} < 1'
            self._log.warning(msg)
            raise RuntimeError(msg)
        if stop < (start + incr):
            msg = f'invalid range {start}, {stop}, {incr}'
            self._log.warning(msg)
            raise RuntimeError(msg)
        x_len = (stop - start) // incr
        stop = start + x_len * incr
        t_start = start / fs
        x = np.arange(x_len, dtype=np.float64)
        x *= incr / fs
        x += t_start
        dx = (x[-1] - x[0]) + (incr - 1) / fs

        result = {
            'time': {
                'x': {'value': x, 'units': 's'},
                'delta': {'value': dx, 'units': 's'},
                'samples': {'value': [start, stop], 'units': 'samples'},
                'limits': {'value': self.limits, 'units': 's'},
            },
            'state': {'source_type': 'buffer'},
            'signals': {},
        }

        for signal in reader.signals.values():
            signal_id = signal.signal_id
            if signal_id == 0:
                continue
            if signal.signal_type != SignalType.FSR:
                continue
            units = signal.units
            if incr > 1:
                data = reader.fsr_statistics(signal_id, start, incr, x_len)
                dmean = data[:, SummaryFSR.MEAN]
                s = {
                    'µ': {'value': dmean, 'units': units},
                    'σ2': {'value': data[:, SummaryFSR.STD] * data[:, SummaryFSR.STD], 'units': units},
                    'min': {'value': data[:, SummaryFSR.MIN], 'units': units},
                    'max': {'value': data[:, SummaryFSR.MAX], 'units': units},
                    'p2p': {'value': data[:, SummaryFSR.MAX] - data[:, SummaryFSR.MIN], 'units': units},
                    # '∫': {'value': 0.0, 'units': units},  # todo
                }
            else:
                data = reader.fsr(signal_id, start, x_len)
                zeros = np.zeros(len(data), dtype=np.float32)
                s = {
                    'µ': {'value': data, 'units': units},
                    'σ2': {'value': zeros, 'units': units},
                    'min': {'value': data, 'units': units},
                    'max': {'value': data, 'units': units},
                    'p2p': {'value': zeros, 'units': units},
                    # '∫': {'value': 0.0, 'units': units},  # todo
                }
            result['signals'][signal.name] = s
        return result

    def _update(self):
        reader = self._reader
        if not callable(self.on_update_fn) or reader is None:
            return
        self._refresh_requested = False
        if self._cache is not None:
            self.on_update_fn(self._cache)
            return
        fs = self.sampling_frequency
        start, stop = [int(x * fs) for x in self._x_range]
        self._cache = self._get(start, stop, self._samples_per)
        self.on_update_fn(self._cache)

    def _statistics_get(self, start=None, stop=None, units=None):
        """Get the statistics for the collected sample data over a time range.

        :param start: The starting time relative to the streaming start time.
        :param stop: The ending time.
        :param units: The units for start and stop.
            'seconds' or None is in floating point seconds relative to the view.
            'samples' is in stream buffer sample indices.
        :return: The statistics data structure.
        """
        self._log.info('_statistics_get(%s, %s, %s)', start, stop, units)
        if units == 'seconds':
            fs = self.sampling_frequency
            start = int(round(start * fs))
            stop = int(round(stop * fs + 1))  # make exclusive
        s = self._get(start, stop, stop - start)
        return s

    def _statistics_get_multiple(self, ranges, units=None):
        self._log.info('_statistics_get_multiple(%s, %s)', ranges, units)
        return [self._statistics_get(x[0], x[1], units=units) for x in ranges]

    def _samples_get(self, start=None, stop=None, units=None, fields=None):
        self._log.info('_samples_get(%s, %s, %s, %s)', start, stop, units, fields)
        r = self._reader
        if r is None:
            return None
        return r.samples_get(start, stop, units, fields)

    def open(self):
        fs = self.sampling_frequency
        sample_id_last = self._parent().sample_id_last
        x_lim = [0, sample_id_last / fs]
        self._span = span.Span(x_lim, 1.0 / fs, 100)
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
            'samples' is in stream buffer sample indices.
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


class RecordingViewerDeviceV2:
    """A user-interface-compatible device that displays previous recorded data

    :param filename: The filename path to the pre-recorded data.
    """
    def __init__(self, filename, cmdp=None):
        if isinstance(filename, str) and not os.path.isfile(filename):
            raise IOError('file not found')
        self._filename = filename
        self._cmdp = cmdp
        self._reader: Reader = None
        self._default_signal: SignalDef = None
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
        fs = self._default_signal.sample_rate
        if fs <= 0:
            raise RuntimeError('Invalid sampling_frequency')
        return fs

    @property
    def sample_id_last(self):
        return self._default_signal.length

    @property
    def calibration(self):
        return None

    @property
    def voltage_range(self):
        return 0

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
        except Exception:
            self._log.exception('While running command')
        if callable(cbk):
            try:
                cbk(rv)
            except Exception:
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
            except Exception:
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

    def _annotations_publish(self, reader):
        if self._cmdp is None:
            return
        for signal in reader.signals.values():
            dual_markers = {}

            def cbk(timestamp, annotation_type, data):
                if signal.signal_type == SignalType.FSR:
                    # convert to seconds
                    # todo make this respect UTC, when UTC is implemented
                    timestamp = timestamp / signal.sample_rate
                if annotation_type == AnnotationType.TEXT:
                    self._cmdp.invoke('!Widgets/Waveform/annotation/add', [signal.name, timestamp, data])
                elif annotation_type == AnnotationType.MARKER:
                    if data[-1] in 'ab':
                        name = data[:-1]
                        if name in dual_markers:
                            t2 = dual_markers.pop(name)
                            value = sorted([timestamp, t2])
                            self._cmdp.invoke('!Widgets/Waveform/Markers/dual_add', value)
                        else:
                            dual_markers[name] = timestamp
                    else:
                        self._cmdp.invoke('!Widgets/Waveform/Markers/single_add', timestamp)

            reader.annotations(signal.signal_id, 0, cbk)

    def _annotations_load(self):
        path = os.path.dirname(self._filename)
        fname = os.path.basename(self._filename)
        fbase, fext = os.path.splitext(fname)
        for filename in os.listdir(path):
            if filename.startswith(fbase) and filename != fname and filename.endswith(fext):
                with Reader(os.path.join(path, filename)) as r:
                    self._annotations_publish(r)

    def _open(self):
        self._log.info('RecordingViewerDevice.open')
        self._reader = Reader(self._filename)
        signals = self._reader.signals
        if len(signals) <= 1:
            raise RuntimeError('This JLS file is not currently supported')
        self._default_signal = signals[1]
        self._annotations_publish(self._reader)
        self._annotations_load()

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
