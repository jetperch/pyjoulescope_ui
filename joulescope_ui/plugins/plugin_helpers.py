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
from collections import deque

log = logging.getLogger(__name__)


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
        log.error('_normalize_hist invalid normalization: %s', norm)
    gain = 1 / hist.sum()
    return hist * gain, bin_edges


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
    """Compute the maximum sum over a data window.

    :param data: The :class:`RangeToolInvocation` instance.
    :param signal: The name of the signal to process.
    :param time_window_len: The length of the window used to evaluate each
        sample.  The time_window_len span with the maximum value will
        be returned.
    :return: (max_sum, start, end) where:
        * max_sum is the computed value over the best span.
        * start is the starting sample index.
        * end is the ending sample index.
    """
    window_len = int(time_window_len * data.sample_frequency)
    if window_len >= data.sample_count:
        window_len = data.sample_count - 1
    queue = deque(np.zeros(window_len), maxlen=window_len)

    start = end = -1
    max_sum = -np.Infinity
    cur_sum = 0.0
    j = 0

    for data_chunk in data:
        for v in data_chunk['signals'][signal]['value']:
            j += 1
            old_val = queue.popleft()
            cur_sum += v - old_val
            queue.append(v)
            if cur_sum > max_sum:
                max_sum = cur_sum
                start = max(0, j - window_len)
                end = max(j, start + window_len)
                if end >= data.sample_count:
                    end = data.sample_count - 1
                    start = end - window_len

    if start < 0:
        raise RuntimeError('Span not found')
    log.info('max_sum_in_window found (%s, %s): max_sum=%g', start, end, max_sum)

    return max_sum, start, end
