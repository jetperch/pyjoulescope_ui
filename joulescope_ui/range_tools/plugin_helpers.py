# Copyright 2019-2023 Jetperch LLC
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

import logging
import numpy as np
from math import ceil


_log = logging.getLogger(__name__)


def calculate_histogram(range_tool, range_tool_value, signal, num_bins: int = 0):
    d = range_tool.request(signal, 'utc', *range_tool_value['x_range'], 1)
    s_now = d['info']['time_range_samples']['start']
    s_end = d['info']['time_range_samples']['end'] + 1  # +1 for inclusive to exclusive

    length = s_end - s_now
    _, v_std, v_min, v_max = s_data = d['data'][0, :]
    width = 3.5 * v_std / (length ** (1. / 3))
    if num_bins <= 0:
        num_bins = ceil((v_max - v_min) / width)
    hist = None
    bin_edges = None

    while True:
        if s_now >= s_end:
            break
        length = min(100_000, s_end - s_now)
        d_iter = range_tool.request(signal, 'samples', s_now, 0, length)
        y = d_iter['data']
        if bin_edges is None:
            hist, bin_edges = np.histogram(y, range=(v_min, v_max), bins=num_bins)
        else:
            hist += np.histogram(y, bins=bin_edges)[0]
        s_now += length
        range_tool.progress(s_now / s_end)

    return hist, bin_edges


def normalize_hist(hist, bin_edges, norm: str = None):
    if norm == 'density':
        db = np.array(np.diff(bin_edges), float)
        gain = 1.0 / (db * hist.sum())
        return hist * gain, bin_edges
    elif norm == 'count':
        return hist, bin_edges
    elif norm not in ['unity', None]:
        _log.error('_normalize_hist invalid normalization: %s', norm)
    gain = 1 / hist.sum()
    return hist * gain, bin_edges
