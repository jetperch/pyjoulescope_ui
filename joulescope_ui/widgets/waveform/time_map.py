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

    def __init__(self):
        self.pixel_offset = 0
        self.time64_label_offset = 0
        self.time64_zero_offset = 0
        self.time_to_pixel_scale = 1.0

    def update(self, pixel_offset, time64_label_offset, time64_zero_offset, time_to_pixel_scale):
        self.pixel_offset = pixel_offset
        self.time64_label_offset = time64_label_offset
        self.time64_zero_offset = time64_zero_offset
        self.time_to_pixel_scale = time_to_pixel_scale

    def trel_offset(self):
        offset = self.time64_label_offset
        offset = (offset // time64.SECOND) * time64.SECOND
        return offset

    def time64_to_pixel(self, x_time):
        if isinstance(x_time, list):
            t = (np.array(x_time, np.int64) - self.time64_zero_offset).astype(float)
        else:
            t = (x_time - self.time64_zero_offset)
        return self.pixel_offset + t * self.time_to_pixel_scale

    def pixel_to_time64(self, pixel):
        return self.time64_zero_offset + int((pixel - self.pixel_offset) * (1.0 / self.time_to_pixel_scale))

    def time64_to_trel(self, t64):
        offset = self.trel_offset()
        dt = t64 - offset
        if isinstance(dt, np.ndarray):
            dt = dt.astype(np.float64)
        else:
            dt = float(dt)
        return dt / time64.SECOND

    def trel_to_time64(self, trel):
        offset = self.trel_offset()
        s = trel * time64.SECOND
        if isinstance(s, np.ndarray):
            s = s.astype(np.int64)
            s += np.int64(offset)
        else:
            s = int(s) + int(offset)
        return s

    def trel_to_pixel(self, trel):
        t64 = self.trel_to_time64(trel)
        return self.time64_to_pixel(t64)
