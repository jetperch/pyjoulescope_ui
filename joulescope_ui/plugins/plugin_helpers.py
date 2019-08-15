# Copyright 2019 Jetperch LLC
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
from collections import deque

log = logging.getLogger(__name__)


def calculate_histogram(data, bins: int, signal: str):
    stats = data.statistics['signals'][signal]['statistics']
    maximum, minimum = stats['max'], stats['min']
    width = 3.5 * stats['σ'] / (data.sample_count ** (1. / 3))
    num_bins = bins if bins > 0 else ceil((maximum - minimum) / width)
    hist = None
    bin_edges = None

    for data_chunk in data:
        if bin_edges is None:
            hist, bin_edges = np.histogram(data_chunk[signal]['value'], range=(minimum, maximum), bins=num_bins)
        else:
            hist += np.histogram(data_chunk[signal]['value'], bins=bin_edges)[0]

    return hist, bin_edges


def normalize_hist(hist, bin_edges, norm: str = 'density'):
    if norm == 'density':
        db = np.array(np.diff(bin_edges), float)
        return hist/db/hist.sum(), bin_edges
    elif norm == 'unity':
        return hist/hist.sum(), bin_edges
    elif norm == 'count':
        return hist, bin_edges
    else:
        log.exception(
            '_normalize_hist invalid normalization; possible values are "density", "unity", or None')
        return


def cdf(data, signal):
    hist, bin_edges = calculate_histogram(data, bins=0, signal=signal)
    normed, bin_edges = normalize_hist(hist, bin_edges, norm='unity')
    _cdf = np.zeros(len(normed))
    for i, hist_val in enumerate(normed):
        _cdf[i] = _cdf[i - 1] + hist_val
    return _cdf, bin_edges


def ccdf(data, signal):
    _cdf, bin_edges = cdf(data, signal=signal)
    return 1 - _cdf, bin_edges

def max_sum_in_window(data, signal, time_window_len):
    window_len = int(time_window_len * data.sample_frequency)
    queue = deque(np.zeros(window_len), maxlen=window_len)

    start = end = 0
    max_sum = cur_sum = 0
    j = 0

    for data_chunk in data:
        for v in data_chunk[signal]['value']:
            j += 1
            old_val = queue.popleft()
            cur_sum += v - old_val
            queue.append(v)
            if cur_sum > max_sum:
                max_sum = cur_sum
                start = max(0, j - window_len)
                end   = j

    return max_sum, start, end
