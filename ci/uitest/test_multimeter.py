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


_BASE_UNITS = {'current': 'A', 'voltage': 'V', 'power': 'W'}
_PREFIX = {'': 1.0, 'k': 1e3, 'm': 1e-3, 'µ': 1e-6, 'n': 1e-9, 'p': 1e-12}


def _parse(text, base_units):
    """Parse a displayed ``'+1.23456 mA [field]'`` into ``(value, lsb)`` in base units."""
    number, units = text.split()[:2]
    assert units.endswith(base_units), f'{text!r}: units are not {base_units}'
    scale = _PREFIX[units[:-len(base_units)]]
    decimals = len(number.split('.')[1]) if '.' in number else 0
    return float(number) * scale, 10.0 ** -decimals * scale


def _multimeter(ui_session, device):
    """Show the Multimeter view for ``device``; return the widget id."""
    ui_session.set_view('multimeter')
    mm = [i for i in ui_session.enumerate('registry') if i.startswith('MultimeterWidget:')]
    assert mm, 'no Multimeter widget'
    ui_session.publish(f'registry/{mm[0]}/settings/statistics_stream_source', device.unique_id)
    return mm[0]


def _hold(ui_session, device):
    """Stream statistics briefly, then hold; return the recent statistics samples.

    The device keeps publishing after the hold, so the widget shows one of the
    samples received around the hold, not necessarily the last.
    """
    samples = []
    ui_session.subscribe(f'registry/{device.unique_id}/events/statistics/!data',
                         lambda t, v: samples.append(v), ['pub'])
    ui_session.wait_for_statistics(device.unique_id)
    ui_session.wait(1.5)
    ui_session.publish('registry/app/settings/statistics_stream_enable', False)
    ui_session.wait(1.0)   # the widget repaints with the last sample
    return samples[-8:]


def _displayed(ui_session, mm):
    rsp = ui_session.qt_action('call', path=mm, method='displayed_text')
    assert rsp.get('ok'), f'displayed_text failed: {rsp}'
    return rsp['result']


@pytest.mark.device
def test_multimeter_widget_displays_statistics(ui_session, device):
    """The Multimeter widget shows each signal's fields, matching the statistics."""
    mm = _multimeter(ui_session, device)
    recent = _hold(ui_session, device)
    shown = _displayed(ui_session, mm)

    def matches(stats, name, field):
        value, lsb = _parse(shown[f'{name}.{field}'], _BASE_UNITS[name])
        return abs(value - _value(stats['signals'][name][field])) <= 1.01 * lsb

    for name in _BASE_UNITS:
        for field in _STAT_FIELDS:
            assert f'{name}.{field}' in shown, \
                f'{device.model}: Multimeter does not show {name}.{field}: {sorted(shown)}'
    shown_sample = [s for s in recent if matches(s, 'current', 'avg')]
    assert shown_sample, f'{device.model}: current.avg {shown["current.avg"]!r} matches ' \
                         f'no recent statistics sample'
    stats = shown_sample[-1]
    for name in _BASE_UNITS:
        for field in _STAT_FIELDS:
            assert matches(stats, name, field), \
                f'{device.model}: {name}.{field} shows {shown[f"{name}.{field}"]!r}, ' \
                f'statistics {_value(stats["signals"][name][field]):g}'
    for name in ['charge', 'energy']:
        assert f'{name}.avg' in shown and f'{name}.duration' in shown, \
            f'{device.model}: Multimeter does not show {name}: {sorted(shown)}'


@pytest.mark.device
def test_multimeter_units_and_duration(ui_session, device):
    """Charge/energy switch between C/J and Ah/Wh; the accumulation time advances."""
    mm = _multimeter(ui_session, device)
    _hold(ui_session, device)
    for units, charge, energy in [('Xh', 'Ah', 'Wh'), ('SI', 'C', 'J')]:
        ui_session.publish(f'registry/{mm}/settings/units', units)
        ui_session.wait(0.5)
        shown = _displayed(ui_session, mm)
        assert shown['charge.avg'].endswith(charge), f'{units}: charge {shown["charge.avg"]!r}'
        assert shown['energy.avg'].endswith(energy), f'{units}: energy {shown["energy.avg"]!r}'

    duration = _displayed(ui_session, mm)['charge.duration']
    _hold(ui_session, device)
    assert _displayed(ui_session, mm)['charge.duration'] != duration, \
        f'{device.model}: accumulation time did not advance from {duration!r}'
