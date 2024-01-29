# Copyright 2024 Jetperch LLC
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

from joulescope_ui import N_
from joulescope_ui.units import unit_prefix, prefix_to_scale
import numpy as np


X_QUANTITY_OPTIONS = [
    ['avg', N_('avg')],
    ['std', N_('std')],
    ['rms', N_('rms')],
    ['min', N_('min')],
    ['max', N_('max')],
    ['p2p', N_('p2p')],
    ['integral', N_('∫')],
]
X_QUANTITY_TO_STR = dict([(k, x[0] if len(x) == 1 else x[1]) for x in X_QUANTITY_OPTIONS for k in x])
X_STR_TO_QUANTITY = dict([(k, x[0]) for x in X_QUANTITY_OPTIONS for k in x])
PRECISION_OPTIONS = [
    [6, '6'],
    [5, '5'],
    [4, '4'],
    [3, '3'],
]


def si_format(values, unit=None, prefix_preferred=None, precision=None):
    """Format a list of values to share the same prefix + units.

    :param values: The list of values to format.
    :param unit: The SI unit for values.
    :param prefix_preferred: The preferred scale prefix.
        None (default) autodetects.
    :param precision: The desired precision digits.
        None (default) uses 6.

    :return: The tuple of value_strs, prefix_units where
        * value_strs: the list of formatted value strings corresponding
          to each provided value.
        * prefix_units: The prefix + units string.
    """
    if not len(values):
        return [], unit
    value_strs = []
    unit = '' if unit is None else str(unit)
    precision = 6 if precision is None else int(precision)
    if precision < 1 or precision > 9:
        raise ValueError('unsupported precision')
    precision_min = 10 ** -(precision - 1)
    precision_max = 10 ** precision

    assert(1 <= precision <= 9)
    values = np.array(values)
    max_value = float(np.max(np.abs(values)))
    _, prefix, scale = unit_prefix(max_value)
    if prefix_preferred not in [None, 'auto']:
        p_scale = prefix_to_scale(prefix_preferred)
        if precision_min <= (max_value / p_scale) < precision_max:
            prefix, scale = prefix_preferred, p_scale

    scale = 1.0 / scale
    if len(unit) or len(prefix):
        unit_suffix = f'{prefix}{unit}'
    else:
        unit_suffix = ''
    for v in values:
        v *= scale
        if abs(v) < precision_min:  # minimum display resolution
            v = 0
        s = (f'%+{precision}f' % v)
        s1, s2 = s[:(precision + 2)], s[(precision + 2):]
        if s1[-1] == '.':
            s1 = s1[:-1]
        elif len(s2) and '.' in s2[1:]:
            s1 += s2.split('.')[0]
        value_strs.append(s1)
    return value_strs, unit_suffix


def quantities_format(quantities, values, prefix_preferred=None, precision=None):
    """Format statistics in a user-friendly format.

    :param quantities: The ordered list of quantities to display.
    :param values: The dict of quantity to (value, units).
    :param prefix_preferred: The preferred SI prefix scale.
    :param precision: The desired display precision.
    :return: [(name, value, units), ...]
    """
    units = {}
    quantities_filt = []
    for quantity in quantities:
        try:
            v, unit = values[quantity]
        except KeyError:
            continue
        if unit not in units:
            units[unit] = [[], []]
        q_list, v_list = units[unit]
        q_list.append(quantity)
        v_list.append(v)
        quantities_filt.append(quantity)

    z = {}
    for unit, (q_list, v_list) in units.items():
        value_strs, unit = si_format(v_list, unit=unit, prefix_preferred=prefix_preferred, precision=precision)
        for quantity, value in zip(q_list, value_strs):
            z[quantity] = (X_QUANTITY_TO_STR[quantity], value, unit)
    return [z[quantity] for quantity in quantities_filt]
