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

"""Export the Efficiency widget data as CSV."""

from joulescope_ui import time64
import csv
import math


_HISTORY_UNITS = {
    'efficiency': '',
    'p_in': 'W', 'p_out': 'W', 'p_loss': 'W',
    'v_in': 'V', 'i_in': 'A', 'v_out': 'V', 'i_out': 'A',
}


def _header(f, title, meta):
    f.write(f'# {title}\n')
    for key, value in meta.items():
        f.write(f'# {key}: {value}\n')


def _num(x):
    return '' if x is None or not math.isfinite(x) else repr(float(x))


def history_csv(f, t, columns, meta):
    """Write the time series.

    :param f: The text file, opened with newline=''.
    :param t: The window end time64 array.
    :param columns: The map of column name to array, see
        :meth:`WindowHistory.columns`.  Invalid values are NaN and written
        as empty fields.
    :param meta: The map of header comment key to value.
    """
    _header(f, 'Joulescope efficiency time series', meta)
    names = list(columns.keys())
    w = csv.writer(f)
    w.writerow(['utc', 't (s)'] + [f'{n} ({_HISTORY_UNITS[n]})' if _HISTORY_UNITS.get(n) else n
                                    for n in names])
    if not len(t):
        return
    t0 = int(t[0])
    for k, tk in enumerate(t):
        tk = int(tk)
        row = [time64.as_isostr(tk), f'{(tk - t0) / time64.SECOND:.6f}']
        row += [_num(columns[n][k]) for n in names]
        w.writerow(row)


def curve_csv(f, bins, x_name, x_units, meta):
    """Write the efficiency curve.

    :param f: The text file, opened with newline=''.
    :param bins: The bins from :meth:`Curve.bins`.
    :param x_name: The x quantity name, such as 'i_out'.
    :param x_units: The x units, such as 'A'.
    :param meta: The map of header comment key to value.
    """
    _header(f, 'Joulescope efficiency curve', meta)
    w = csv.writer(f)
    w.writerow([f'{x_name} ({x_units})', f'{x_name}_min ({x_units})', f'{x_name}_max ({x_units})',
                'efficiency', 'efficiency_min', 'efficiency_max',
                'windows', 'duration (s)', 'e_in (J)', 'e_out (J)'])
    for b in bins:
        w.writerow([_num(b['x']), _num(b['x_min']), _num(b['x_max']),
                    _num(b['efficiency']), _num(b['efficiency_min']), _num(b['efficiency_max']),
                    str(int(b['count'])), _num(b['duration']), _num(b['e_in']), _num(b['e_out'])])
