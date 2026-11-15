# Copyright 2026 Jetperch LLC
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

"""Mean-preserving anti-aliasing for zoomed-out Waveform plots.

A summary bin per pixel makes a sub-pixel pulse's average flicker as the view
scrolls (issue #356).  Request OVERSAMPLE sub-bins per pixel, then low-pass
filter and decimate the average for display.

The kernel is g = q ⊛ boxcar_N / N, with q a unit-sum Gaussian.  Every
polyphase component of g then sums to exactly 1 / N, so decimation preserves
the mean: away from the edges, sum(avg_aa) == sum(avg).
"""

from joulescope_ui import time64
import math
import numpy as np


OVERSAMPLE = 4
SIGMA_PIXELS = 1.0
PAD_PIXELS = int(math.ceil(3 * SIGMA_PIXELS))

# Sources return up to 2x the requested summary length due to integer sample
# increments.  Keep the response within the jsdrv buffer limit (16384).
REQUEST_LENGTH_MAX = 8000

# Sources return samples, not summaries, below 2 samples per entry.  The
# margin keeps rounding at the request edges from flipping the response type.
SUB_BIN_SAMPLES_MIN = 2.5


def kernel(oversample=None, sigma=None):
    """Construct the mean-preserving anti-aliasing kernel.

    :param oversample: The sub-bins per pixel, N.  None uses OVERSAMPLE.
    :param sigma: The Gaussian standard deviation in pixels.
        None uses SIGMA_PIXELS.
    :return: The symmetric kernel g with length 2H + N.
    """
    n = OVERSAMPLE if oversample is None else int(oversample)
    sigma = SIGMA_PIXELS if sigma is None else float(sigma)
    sigma_q = sigma * n
    h = int(math.ceil(3 * sigma_q))
    k = np.arange(-h, h + 1, dtype=np.float64)
    q = np.exp(-0.5 * (k / sigma_q) ** 2)
    q /= np.sum(q)
    return np.convolve(q, np.full(n, 1.0 / n))


def request_range(x_range, x_extent, width, sample_rate):
    """Compute the padded, oversampled request.

    :param x_range: The visible [x0, x1] in time64.
    :param x_extent: The available [e0, e1] in time64.  Padding never
        extends beyond the extent.
    :param width: The plot width in pixels.
    :param sample_rate: The signal sample rate in Hz, or None if unknown.
    :return: (start, end, length, pixels) where pixels is the width plus
        the whole pixels of padding added to each side.  Return None when
        anti-aliasing does not apply: too few samples per pixel for summary
        sub-bins, including zoomed in to one sample per pixel or less.
    """
    x0, x1 = int(x_range[0]), int(x_range[1])
    e0, e1 = int(x_extent[0]), int(x_extent[1])
    width = int(width)
    if width <= 0 or x1 <= x0 or not sample_rate:
        return None
    dt = (x1 - x0) / width
    samples_per_pixel = dt * sample_rate / time64.SECOND
    oversample = min(OVERSAMPLE, int(samples_per_pixel // SUB_BIN_SAMPLES_MIN))
    if oversample < 1:
        return None
    pad_l = int(min(PAD_PIXELS, max(0, math.floor((x0 - e0) / dt))))
    pad_r = int(min(PAD_PIXELS, max(0, math.floor((e1 - x1) / dt))))
    start = x0 - int(round(pad_l * dt))
    end = x1 + int(round(pad_r * dt))
    pixels = width + pad_l + pad_r
    oversample = max(1, min(oversample, REQUEST_LENGTH_MAX // pixels))
    return start, end, pixels * oversample, pixels


def decimate(data, pixels, x_range=None, sigma=None):
    """Reduce an oversampled summary response to about one entry per pixel.

    :param data: The summary dict with x, avg, std, min, max arrays.
    :param pixels: The requested pixels, including padding, from
        :func:`request_range`.  Sources may return more entries than
        requested, so the sub-bins per pixel is round(len(x) / pixels).
        Extra entries are dropped from the start to keep the newest data.
    :param x_range: The visible [x0, x1].  None keeps all pixels.
        Otherwise, keep only pixels with x inside this range.
    :param sigma: The Gaussian sigma in pixels.  None uses SIGMA_PIXELS.
    :return: The new dict with x, avg, std, min, max per pixel, plus
        avg_aa, the filtered average for display.  avg, std, min and max are
        the per-pixel statistics of the sub-bins, which assume equal sample
        counts per sub-bin.  Return None if there is less than one sub-bin
        per pixel.
    """
    x = np.asarray(data['x'])
    n = int(round(len(x) / pixels)) if pixels > 0 else 0
    if n < 1:
        return None
    n_pixels = len(x) // n
    k_start = len(x) - n_pixels * n
    shape = (n_pixels, n)
    s_avg = np.asarray(data['avg'], dtype=np.float64)[k_start:]
    avg_sub = s_avg.reshape(shape)
    std_sub = np.asarray(data['std'], dtype=np.float64)[k_start:].reshape(shape)
    x_sub = x[k_start:].reshape(shape)

    avg = np.mean(avg_sub, axis=1)
    var = np.mean(std_sub * std_sub + avg_sub * avg_sub, axis=1) - avg * avg
    std = np.sqrt(np.maximum(var, 0.0))
    v_min = np.min(np.asarray(data['min'])[k_start:].reshape(shape), axis=1)
    v_max = np.max(np.asarray(data['max'])[k_start:].reshape(shape), axis=1)
    x_px = x_sub[:, 0] + (x_sub[:, -1] - x_sub[:, 0]) // 2

    # normalized convolution: renormalize at the edges and NaN gaps
    g = kernel(n, sigma)
    h = (len(g) - n) // 2
    valid = np.isfinite(s_avg)
    num = np.convolve(np.where(valid, s_avg, 0.0), g)
    den = np.convolve(valid.astype(np.float64), g)
    idx = np.arange(n_pixels) * n + h + n - 1  # output centered on each pixel
    with np.errstate(invalid='ignore', divide='ignore'):
        avg_aa = num[idx] / den[idx]
    avg_aa[np.isnan(avg)] = np.nan

    rv = {
        'x': x_px,
        'avg': avg,
        'std': std,
        'min': v_min,
        'max': v_max,
        'avg_aa': avg_aa,
    }
    return rv if x_range is None else trim(rv, x_range)


def trim(data, x_range):
    """Keep only the entries with x inside the visible range.

    :param data: The dict with x and other per-entry arrays, or None.
    :param x_range: The visible [x0, x1].
    :return: The new dict with the padding removed.  Non-array values
        pass through unchanged.
    """
    x = data['x']
    k0 = int(np.searchsorted(x, x_range[0], side='left'))
    k1 = int(np.searchsorted(x, x_range[1], side='right'))
    rv = {}
    for key, value in data.items():
        if isinstance(value, np.ndarray) and len(value) == len(x):
            value = value[k0:k1]
        rv[key] = value
    return rv
