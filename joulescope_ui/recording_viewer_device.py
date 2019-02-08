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
from joulescope_ui.data_view_api import DataViewApi
from joulescope import span
import os
import numpy as np
import logging
log = logging.getLogger(__name__)


class RecordingViewerDevice:
    """A user-interface-compatible device that displays previous recorded data

    :param filename: The filename path to the pre-recorded data.
    """
    def __init__(self, filename):
        self._filename = filename
        self.reader = None
        self.ui_action = None
        self.view = None  # type: DataViewApi
        self.x_range = [0.0, 1.0]
        self.span = None
        self.x = None
        self.samples_per = 1
        self.changed = True

    def __str__(self):
        return os.path.basename(self._filename)

    def __len__(self):
        return self.span.length

    def open(self):
        self.view = self
        self.reader = DataReader().open(self._filename)
        f = self.reader.sampling_frequency
        r = self.reader.sample_id_range
        x_lim = [x / f for x in r]
        self.span = span.Span(x_lim, 1/f, 100)
        self.x_range, self.samples_per, self.x = self.span.conform_discrete(x_lim)
        self.changed = True
        log.info('RecordingViewerDevice.open: %s => %s, %s', r, self.x_range, self.samples_per)

    def close(self):
        if self.reader is not None:
            self.reader.close()
            self.reader = None
            if self.on_close is not None:
                self.on_close()
            self.view = None

    def on_x_change(self, cmd, kwargs):
        x_range = self.x_range
        if cmd == 'resize':  # {pixels: int}
            length = kwargs['pixels']
            if length is not None and length != self.span.length:
                log.info('resize %s', length)
                self.span.length = length
                self.changed = True  # invalidate
            x_range, self.samples_per, self.x = self.span.conform_discrete(x_range)
        elif cmd == 'span_absolute':  # {range: (start: float, stop: float)}]
            x_range, self.samples_per, self.x = self.span.conform_discrete(kwargs.get('range'))
        elif cmd == 'span_relative':  # {pivot: float, gain: float}]
            x_range, self.samples_per, self.x = self.span.conform_discrete(
                x_range, gain=kwargs.get('gain'), pivot=kwargs.get('pivot'))
        elif cmd == 'span_pan':
            delta = kwargs.get('delta', 0.0)
            x_range = [x_range[0] + delta, x_range[-1] + delta]
            x_range, self.samples_per, self.x = self.span.conform_discrete(x_range)
        elif cmd == 'refresh':
            self.changed = True
            return
        else:
            log.warning('on_x_change(%s) unsupported', cmd)
            return

        self.changed |= self.x_range != x_range
        self.x_range = x_range
        log.info('changed=%s, length=%s, span=%s, range=%s, samples_per=%s',
                 self.changed, len(self), self.x_range,
                 self.x_range[1] - self.x_range[0], self.samples_per)

    def update(self):
        if not self.changed:
            return False, (None, None)
        f = self.reader.sampling_frequency
        log.info('update: x_range=%r', self.x_range)
        start, stop = [int(x * f) for x in self.x_range]
        log.info('update: x_range=%r => (%s, %s)', self.x_range, start, stop)
        data = self.reader.get(start, stop, self.samples_per)
        t_start = start / self.reader.sampling_frequency
        t_stop = stop / self.reader.sampling_frequency
        x = np.linspace(t_start, t_stop, len(data), dtype=np.float64)
        try:
            log.info('update: len=%d, x_range=>(%s, %s)', len(data), x[0], x[-1])
        except:
            print(x.shape)
        return True, (x, data)


