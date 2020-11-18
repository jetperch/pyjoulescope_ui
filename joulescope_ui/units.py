# Copyright 2020 Jetperch LLC
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


UNIT_CONVERTER = {
    # (from, to): conversion function
    ('C', 'Ah'): lambda x: x / 3600.0,
    ('Ah', 'C'): lambda x: x * 3600.0,
    ('J', 'Wh'): lambda x: x / 3600.0,
    ('Wh', 'J'): lambda x: x * 3600.0,
}


def convert_units(value, input_units, output_units):
    key = (input_units, output_units)
    fn = UNIT_CONVERTER.get(key)
    if fn is not None:
        return {
            'value': fn(value),
            'units': output_units}
    return {
        'value': value,
        'units': input_units}


def elapsed_time_formatter(seconds, cmdp=None, fmt=None):
    """Format time in seconds to a string.

    :param seconds: The elapsed time in seconds.
    :param cmdp: The optional CommandProcessor containing the time formatting options.
    :param fmt: The optional format string containing:
        * 'seconds': Display time in seconds.
        * 'standard': Display time as D:hh:mm:ss.
    :return: The elapsed time string.
    """
    seconds = int(seconds)  # drop fractions
    fmt = 'seconds' if fmt is None else str(fmt)
    if cmdp is not None:
        if isinstance(cmdp, str):
            fmt = cmdp
        else:
            fmt = cmdp['Units/elapsed_time']
    if seconds >= 60 and fmt in ['D:hh:mm:ss', 'conventional', 'standard']:
        days = seconds // (24 * 60 * 60)
        seconds -= days * (24 * 60 * 60)
        hours = seconds // (60 * 60)
        seconds -= hours * (60 * 60)
        minutes = seconds // 60
        seconds -= minutes * 60
        time_parts = f'{days}:{hours:02d}:{minutes:02d}:{seconds:02d}'.split(':')
        while True:
            p = time_parts[0]
            p_zero = '0' * len(p)
            if p == p_zero:
                time_parts.pop(0)
            else:
                break
        time_str = ':'.join(time_parts)
        while time_str[0] == '0':
            time_str = time_str[1:]
        return time_str
    else:
        return f'{seconds} s'
