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

"""Multimeter profile & widget: live statistics from a connected device.

Maps to the "Multimeter profile & widget" rows of the test plan:
* current, voltage, power, energy
* mean, stddev, min, max, p2p
* charge (C, Ah, s)

Verifies the statistics stream is well-formed and physically plausible -- NOT
calibrated accuracy (that is the PCTS/FTS domain).  Requires a connected device
under a stable known load.
"""

import math

import pytest

# Statistics fields present on every signal: avg(mean), std(stddev), min, max,
# p2p.  ``integral`` is additionally present only where it is meaningful:
# current -> charge (C), power -> energy (J).  Voltage has no integral.
_STAT_FIELDS = ['avg', 'std', 'min', 'max', 'p2p']
_INTEGRAL_SIGNALS = ('current', 'power')

# Broad physical sanity windows (functional check, not accuracy).
_SANITY = {
    'current': (-25.0, 25.0),     # A
    'voltage': (-30.0, 30.0),     # V
    'power': (-750.0, 750.0),     # W
}


def _value(field):
    """Extract the numeric ``value`` from a ``{'value':.., 'units':..}`` field."""
    assert isinstance(field, dict) and 'value' in field, f'malformed stat field: {field!r}'
    return float(field['value'])


@pytest.mark.device
def test_multimeter_statistics(ui_session, device):
    stats = ui_session.wait_for_statistics(device.unique_id)
    assert 'signals' in stats, f'no signals in statistics: {list(stats)}'
    signals = stats['signals']

    for name in ('current', 'voltage', 'power'):
        assert name in signals, f'{device.model}: missing signal {name!r}'
        sig = signals[name]
        fields = list(_STAT_FIELDS)
        if name in _INTEGRAL_SIGNALS:
            fields.append('integral')
        for field in fields:
            assert field in sig, f'{device.model}: {name} missing field {field!r}'
            v = _value(sig[field])
            assert math.isfinite(v), f'{device.model}: {name}.{field} not finite ({v})'

    # avg of each signal sits within a broad physical window.
    for name, (lo, hi) in _SANITY.items():
        avg = _value(signals[name]['avg'])
        assert lo <= avg <= hi, \
            f'{device.model}: {name} avg {avg:g} outside sane [{lo}, {hi}]'

    # min <= avg <= max and p2p >= 0 for current.
    cur = signals['current']
    assert _value(cur['min']) <= _value(cur['avg']) <= _value(cur['max'])
    assert _value(cur['p2p']) >= 0.0


@pytest.mark.device
def test_charge_and_energy_accumulate(ui_session, device):
    """current integral is charge (C); power integral is energy (J)."""
    stats = ui_session.wait_for_statistics(device.unique_id)
    signals = stats['signals']
    assert signals['current']['integral']['units'] in ('C', 'Ah')
    assert math.isfinite(_value(signals['current']['integral']))
    assert math.isfinite(_value(signals['power']['integral']))
