# Copyright 2018-2023 Jetperch LLC
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

"""
Manage units and unit display.

For full handling of units, see the excellent quantities module
http://pythonhosted.org/quantities/.
"""


import re
import numpy as np
from joulescope_ui import N_, pubsub_singleton


# https://www.regular-expressions.info/floatingpoint.html
#RE_IS_NUMBER = re.compile(r'^([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+))')
RE_IS_NUMBER = re.compile(r'^\s*([-+]?[0-9]*\.?[0-9]+)\s*(.*)')
UNITS_SETTING = {
    'dtype': 'str',
    'brief': N_('The units to display.'),
    'options': [
        ['default', N_('Use the application defaults')],
        ['SI', N_('International System of Units (SI)')],
        ['Xh', N_('Customary units (Ah and Wh)')],
    ],
    'default': 'default',
}


_UNIT_PREFIX = [
    (1e24, 'Y'),
    (1e21, 'Z'),
    (1e18, 'E'),
    (1e15, 'P'),
    (1e12, 'T'),
    (1e9, 'G'),
    (1e6, 'M'),
    (1e3, 'k'),
    (1e0,  ''),
    (1e-3, 'm'),
    (1e-6, 'µ'),  # \u00B5 micro sign
    (1e-9, 'n'),
    (1e-12, 'p'),
    (1e-15, 'f'),
    (1e-18, 'a'),
    (1e-21, 'z'),
    (1e-24, 'y'),
]

_PREFIX_MAP = dict([(p, v) for v, p in _UNIT_PREFIX])
_PREFIX_MAP['u'] = _PREFIX_MAP['µ']  # common "misuse" of u
_PREFIX_MAP['μ'] = _PREFIX_MAP['µ']  # \u03BC greek small letter mu

FIELD_UNITS_SI = {
    'current': 'A',
    'charge': 'C',
    'voltage': 'V',
    'power': 'W',
    'energy': 'J',
}


FIELD_UNITS_INTEGRAL = {
    'current': 'charge',
    'power': 'energy',
}


def prefix_to_scale(prefix: str) -> float:
    """Convert a prefix character to the corresponding scale factor.

    :param prefix: The prefix string.
    :return: The scale factor for this prefix.
    """
    return _PREFIX_MAP[prefix]


def unit_prefix(value):
    """Get the unit prefix and adjust value.

    :param value: The value to convert to a power of 1000.
    :return: The tuple of (adjusted_value, prefix, scale)
        where value = scale * adjust_value
        Scale is always a power of 10 (10**k).
    """
    v = abs(value)
    for k, c in _UNIT_PREFIX:
        if v >= k:
            return value / k, c, k
    return 0.0, '', 1  # close enough to zero


def three_sig_figs(x, units=None, space1=None, space2=None):
    """Get the value x displayed to three significant figures.

    :param x: The value to convert to a string.
    :param units: The units for x.
    :param space1: The space to insert between the number and prefix.
        If None and units are provided, insert a single space, ' '.
        If None and units are not provide, insert nothing, ''.
    :param space2: The space to insert between the prefix and units.
        If None, insert nothing, ''.
    :return: The string formatted as 'value units'
    """
    units = '' if units is None else units
    if space1 is None:
        if len(units):
            space1 = ' '
        else:
            space1 = ''
    space2 = '' if space2 is None else space2
    x, prefix, _ = unit_prefix(x)
    z = abs(x)
    if z >= 100:
        s = '%.0f' % z
    elif z >= 10:
        s = '%.1f' % z
    elif z >= 1:
        s = '%.2f' % z
    else:
        s = '%.3f' % z
    if x < 0:
        s = '-' + s
    return '%s%s%s%s%s' % (s, space1, prefix, space2, units)


def str_to_number(s):
    if s is None:
        return s
    if not isinstance(s, str):
        float(s)
        return s
    match = RE_IS_NUMBER.match(s)
    if not match:
        raise ValueError(f'not a number: {s}')
    number = match.group(1)
    units = match.group(2)
    if '.' in number:
        number = float(number)
    else:
        number = int(number)
    if units.startswith('ppm'):
        pass
    elif len(units):
        v = _PREFIX_MAP.get(units[0])
        if v is not None:
            if v >= 1:
                v = int(v)
            number *= v
    return number


def convert_units(x, x_units, unit_setting):
    if x_units not in ['C', 'J']:
        return x, x_units
    if unit_setting == 'default':
        unit_setting = pubsub_singleton.query('registry/app/settings/units', default='SI')
    if unit_setting == 'Xh':
        x /= 3600
        y_units = 'Wh' if x_units == 'J' else 'Ah'
    else:
        y_units = x_units
    return x, y_units


def elapsed_time_formatter(seconds, fmt=None, precision=None, trim_trailing_zeros=None):
    """Format time in seconds to a string.

    :param seconds: The elapsed time in seconds.
    :param fmt: The optional format string containing:
        * 'seconds': Display time in seconds.
        * 'standard': Display time as D:hh:mm:ss.
    :param precision: The integer precision to display given in
        powers of 10.  This parameter determines the number of
        fractional seconds digits.
    :param trim_trailing_zeros: When True, trim any trailing fractional
        zero digits.  When False (default), keep full precision.
    :return: The tuple of elapsed time string and units string.
    """
    precision = 6 if precision is None else int(precision)
    x = float(seconds)
    x_pow = int(np.ceil(np.log10(abs(x) + 1e-15)))
    fract_digits = min(max(precision - x_pow, 0), precision)
    fract_fmt = '{x:.' + str(fract_digits) + 'f}'
    fmt = 'seconds' if fmt is None else str(fmt)
    if seconds >= 60 and fmt in ['D:hh:mm:ss', 'conventional', 'standard']:
        days = int(x / (24 * 60 * 60))
        x -= days * (24 * 60 * 60)
        hours = int(x / (60 * 60))
        x -= hours * (60 * 60)
        minutes = int(x / 60)
        x -= minutes * 60
        seconds_str = fract_fmt.format(x=x)
        if '.' in seconds_str:
            if seconds_str[1] == '.':
                seconds_str = '0' + seconds_str
        elif len(seconds_str) == 1:
            seconds_str = '0' + seconds_str
        time_parts = f'{days}:{hours:02d}:{minutes:02d}:{seconds_str}'.split(':')
        units_parts = 'D:hh:mm:ss'.split(':')
        while True:
            p = time_parts[0]
            p_zero = '0' * len(p)
            if p == p_zero:
                time_parts.pop(0)
                units_parts.pop(0)
            else:
                break
        time_str = ':'.join(time_parts)
        units_str = ':'.join(units_parts)
        while time_str[0] == '0':
            time_str = time_str[1:]
            if len(units_str) >= 2 and units_str[1] != ':':
                units_str = units_str[1:]
        return time_str, units_str
    else:
        units_str = 's'
        if fract_digits:
            time_str = fract_fmt.format(x=x)
        else:
            time_str = str(int(x))

    if bool(trim_trailing_zeros) and '.' in time_str:
        while time_str[-1] == '0':
            time_str = time_str[:-1]
        if time_str[-1] == '.':
            time_str = time_str[:-1]

    return time_str, units_str
