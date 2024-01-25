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

import numpy as np
from joulescope_ui import time64
from joulescope_ui.units import unit_prefix, prefix_to_scale


_EXP_TABLE = ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹']
_SECOND = 1
_MINUTE = 60 * _SECOND
_HOUR = 60 * _MINUTE
_DAY = 24 * _HOUR
_X_TICK_SPACING = np.array([
    500e-9,                                                         # nanoseconds
    1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6, 100e-6, 200e-6, 500e-6,  # microseconds
    1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 100e-3, 200e-3, 500e-3,  # milliseconds
    1, 2, 5, 10, 20,                                                # seconds
    60, 120, 300, 600, 1200,                                        # minutes
    _HOUR, 2 * _HOUR, 4 * _HOUR, 8 * _HOUR,                         # hours
    _DAY, 2 * _DAY, 5 * _DAY,                                       # days
    10 * _DAY, 20 * _DAY, 50 * _DAY,                                # 10 x days (months?)
    100 * _DAY, 200 * _DAY, 500 * _DAY,                             # 100 x days (years?)
], dtype=float)
_X_OFFSET_SPACING = np.array([
    1e-6, 10e-6, 100e-6,
    1e-3, 10e-3, 100e-3,
    1, 10,
    60, 600,
    _HOUR,
    _DAY,
], dtype=float)


def _x_spacing(seconds, lookup):
    """Compute the next spacing larger than seconds.

    :param seconds: The time duration as float seconds.
    :param lookup: The lookup table, usually _X_TICK_SPACING or _X_OFFSET_SPACING.
    :return: (value, index)
    """
    if not np.isfinite(seconds) or lookup is None:
        return 0.0
    w = np.where(seconds < lookup)[0]
    if seconds < lookup[0]:
        idx = 0
    elif not len(w):
        idx = len(lookup) - 1
    else:
        idx = w[0]
    return lookup[idx], idx


def _minor_filt(minor, major):
    minor_idx = 0
    major_idx = 0
    minor_idx_max = len(minor)
    major_idx_max = len(major)
    a = []
    dt = (minor[-1] - minor[0]) / (10 * minor_idx_max)
    while minor_idx < minor_idx_max:
        if major_idx >= major_idx_max:
            a.append(minor[minor_idx])
        elif abs(minor[minor_idx] - major[major_idx]) < dt:
            major_idx += 1
        else:
            a.append(minor[minor_idx])
        minor_idx += 1
    return np.array(a)


def x_offset(x0, x1):
    """Compute the x-offset for the axis.

    :param x0: The left-most time64 to display.
    :param x1: The right-most time64 to display.
    :return: The (offset, quantization) for the entire x-axis display.
    """
    if x0 > x1:
        x0, x1 = x1, x0
    spacing = _x_spacing((x1 - x0) / time64.SECOND, _X_OFFSET_SPACING)[0]
    if spacing < 1:
        # Fractional seconds are not exactly represented in time64
        # Exactly determine seconds first to minimize error
        seconds = (x0 // time64.SECOND) * time64.SECOND
        remainder = (x0 - seconds) / time64.SECOND
        remainder = int(np.floor(remainder / spacing) * time64.SECOND * spacing)
        return seconds + remainder
    else:
        interval = time64.SECOND * int(spacing)
        return int(interval * (x0 // interval))


def tick_spacing(v_min, v_max, v_spacing_min):
    if v_spacing_min <= 0:
        return 0.0
    if not np.isfinite(v_min) or not np.isfinite(v_max):
        return 0.0
    target_spacing = v_spacing_min
    power10 = 10 ** np.floor(np.log10(v_spacing_min))
    intervals = np.array([1., 2., 5., 10., 20., 50., 100.]) * power10
    for interval in intervals:
        if interval >= target_spacing:
            return interval
    raise RuntimeError('tick_spacing calculation failed')
    return 0.0


def time_fmt(t, t_max, t_incr):
    p = None
    units = None
    intervals = [(_DAY, 'dd'), (_HOUR, 'hh'), (_MINUTE, 'mm'), (_SECOND, 'ss')]
    for interval, unit in intervals:
        v = int(np.floor(t / interval))
        t -= v * interval
        if p is None:
            if t_max >= interval:
                p = [str(v)]
                units = [unit]
        else:
            p.append(f'{v:02d}')
            units.append(unit)
        if p is not None and t < 1 and interval <= t_incr:
            break
    return ':'.join(p), (':'.join(units))[1:]


def x_ticks(x0, x1, major_count_max):
    if x1 < x0:
        x0, x1 = x1, x0
    dt = float(x1 - x0) / (time64.SECOND * int(major_count_max))
    major_interval, major_idx = _x_spacing(dt, _X_TICK_SPACING)
    k = x_offset(x0, x1)
    t0 = (x0 - k) / time64.SECOND
    t1 = (x1 - k) / time64.SECOND

    major_start = np.ceil(t0 / major_interval) * major_interval
    major = np.arange(major_start, t1, major_interval, dtype=np.float64)

    if major_idx > 0:
        minor_idx = max(major_idx - 2, 0)
        minor_interval = _X_TICK_SPACING[minor_idx]
        minor_start = np.ceil(t0 / minor_interval) * minor_interval
        minor = np.arange(minor_start, t1, minor_interval, dtype=np.float64)
        minor = _minor_filt(minor, major)
    else:
        minor = np.array([], dtype=float)
        minor_interval = major_interval

    labels = []
    if len(major):
        label_max = major[-1]
        if major_interval >= 1:
            for x in major:
                p = time_fmt(x, label_max, major_interval)
                labels.append(p[0])
                units = p[1]
        else:
            adjusted_value, prefix, scale = unit_prefix(label_max)
            scale = 1.0 / scale
            for v in major:
                v *= scale
                s = f'{v:g}'
                if s == '-0':
                    s = '0'
                labels.append(s)
            units = f'{prefix}s'
    else:
        units = ''

    return {
        'offset': k,
        'offset_str': time64.as_datetime(k).isoformat(),
        'major': major,
        'major_interval': major_interval,
        'minor': minor,
        'minor_interval': minor_interval,
        'labels': labels,
        'units': units,
    }


def ticks(v_min, v_max, v_spacing_min=None, major_max=None, logarithmic_zero=None, prefix_preferred=None):
    """Compute the axis tick locations.

    :param v_min: The minimum value (inclusive).
    :param v_max: The maximum value (exclusive).
    :param v_spacing_min: The minimum spacing between major intervals.
    :param major_max: The optional maximum number of major intervals
    :param logarithmic_zero: The power of 10 to use as zero for signed value support.
    :param prefix_preferred: The optional preferred prefix.
        Ignored when logarithmic_zero is provided.
    """
    v_diff = v_max - v_min
    if major_max is not None:
        v_lim = v_diff / major_max
        if v_spacing_min is not None:
            v_count = abs(v_max - v_min) / v_spacing_min
            if v_count > major_max:
                v_spacing_min = v_diff / major_max
        else:
            v_spacing_min = v_lim
    major_interval = tick_spacing(v_min, v_max, v_spacing_min)
    if major_interval <= 0:
        return None
    major_start = np.ceil(v_min / major_interval) * major_interval
    major = np.arange(major_start, v_max, major_interval, dtype=np.float64)
    minor_interval = major_interval / 10.0
    minor_start = major_start - major_interval
    minor = np.arange(minor_start, v_max, minor_interval, dtype=np.float64)
    if not len(minor):
        return None

    k = 0
    sel_idx = np.zeros(len(minor), dtype=bool)
    sel_idx[:] = True
    sel_idx[0::10] = False
    while minor_start < v_min and k < len(sel_idx):
        sel_idx[k] = False
        minor_start += minor_interval
        k += 1
    minor = minor[sel_idx]

    labels = []
    prefix = ''
    if len(major):
        if logarithmic_zero is not None:
            prefix = ''
            for v in major:
                if v == 0:
                    labels.append('0')
                    continue
                v_abs = int(abs(v) + logarithmic_zero)
                if v_abs < 0:
                    v_abs = abs(v_abs)
                    s = '10⁻'
                else:
                    s = '10'
                if v < 0:
                    s = '-' + s
                digits = []
                if v_abs == 0:
                    digits = [_EXP_TABLE[0]]
                while v_abs:
                    digits.append(_EXP_TABLE[v_abs % 10])
                    v_abs //= 10
                labels.append(s + ''.join(digits[-1::-1]))
        else:
            label_max = max(abs(major[0]), abs(major[-1]))
            adjusted_value, prefix, scale = unit_prefix(label_max)
            if prefix_preferred not in [None, 'auto']:
                p_scale = prefix_to_scale(prefix_preferred)
                p_label_max = label_max / p_scale
                if 0.001 <= p_label_max < 100_000:
                    prefix, scale = prefix_preferred, p_scale
            scale = 1.0 / scale
            zero_max = (label_max * scale) / 100_000.0
            for v in major * scale:
                if abs(v) < zero_max:
                    v = 0
                s = f'{v:g}'
                if s == '-0':
                    s = '0'
                labels.append(s)
    return {
        'major': major,
        'major_interval': major_interval,
        'minor': minor,
        'minor_interval': minor_interval,
        'labels': labels,
        'unit_prefix': prefix,
    }
    return np.arange(start, v_max, interval, dtype=np.float64), interval
