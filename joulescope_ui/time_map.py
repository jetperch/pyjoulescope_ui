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

from joulescope_ui import time64
import numpy as np


class TimeMap:
    """Define a time map."""

    def __init__(self):
        self.counter_offset = 0
        self._trel_offset = 0
        self.time_offset = 0
        self.time_to_counter_scale = 1.0
        self.counter_to_time_scale = 1.0

    def update(self, counter_offset, time_offset, scale):
        """Update the time mapping.

        :param counter_offset: The counter offset for zero.
        :param time_offset: The time offset time64 for zero.
        :param scale: The scale to convert time64 to counter.
        """
        self.counter_offset = counter_offset
        self.time_offset = time_offset
        if scale == 0:
            scale = 1.0
        self.time_to_counter_scale = scale
        self.counter_to_time_scale = 1.0 / scale

    @property
    def trel_offset(self):
        return self._trel_offset

    @trel_offset.setter
    def trel_offset(self, value):
        self.trel_offset_set(value)

    def trel_offset_set(self, value_time64, quantum=None):
        value_time64 = int(value_time64)
        if quantum in [0, None]:
            self._trel_offset = value_time64
            return
        if quantum < time64.SECOND:
            seconds = time64.SECOND * (value_time64 // time64.SECOND)
            fract = int(np.floor((value_time64 - seconds) / quantum) * quantum)
            value_time64 = seconds + fract
        else:
            value_time64 = int(np.floor(value_time64 / quantum) * quantum)
        self._trel_offset = value_time64

    def time64_to_counter(self, x_time, dtype=None):
        if isinstance(x_time, list):
            t = (np.array(x_time, np.int64) - self.time_offset).astype(float)
        else:
            t = (x_time - self.time_offset)
        v = self.counter_offset + t * self.time_to_counter_scale
        if dtype:
            v = np.rint(v)
            if isinstance(v, np.ndarray) or isinstance(v, np.number):
                v = v.astype(dtype)
        return v

    def counter_to_time64(self, counter):
        k = (counter - self.counter_offset) * self.counter_to_time_scale
        if isinstance(k, np.ndarray):
            k = np.rint(k).astype(np.int64)
        else:
            k = int(k)
        return self.time_offset + k

    def time64_to_trel(self, t64):
        dt = t64 - self.trel_offset
        if isinstance(dt, np.ndarray):
            dt = dt.astype(np.float64)
        else:
            dt = float(dt)
        return dt / time64.SECOND

    def trel_to_time64(self, trel):
        offset = self.trel_offset
        s = trel * time64.SECOND
        if isinstance(s, np.ndarray):
            s = s.astype(np.int64)
            s += np.int64(offset)
        else:
            s = int(s) + int(offset)
        return s

    def trel_to_counter(self, trel):
        t64 = self.trel_to_time64(trel)
        return self.time64_to_counter(t64)
