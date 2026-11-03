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

"""Spectrum widget stimulus validation: known signals in, checked numbers out.

Implements the automatable tests of docs/plans/spectrum.md stage 6b.  Each
test name starts with its plan ID.  Every test needs a Joulescope with an
ADP3450 wired as joulescope_ci doc/adp3450_connection.md describes, and
skips when the station's wiring cannot support it.

The amplitude reference is the device's own statistics (the std of a sine
is its rms), which cancels the device calibration.  Results and widget
screenshots go to the artifacts directory, spectrum_stimulus/.

    JS_UITEST_STIMULUS_FILE=stations.yaml JS_UITEST_STATION=<id> \\
        pytest ci/uitest/test_spectrum_stimulus.py -m stimulus
"""

import json
import math
import os
import re
import time

import numpy as np
import pytest

from uitest import discover, spectrum, verify
from uitest.stimulus import db, device_settings, signals_enable, statistics_rms, wirings

pytestmark = [
    pytest.mark.device,
    pytest.mark.stimulus,
    pytest.mark.skipif(not wirings(), reason='no stimulus wiring configured (JS_UITEST_STIMULUS)'),
]

_PPM = 100e-6            # combined crystal tolerance of the generator and the device
_DB_TOL_AMPLITUDE = 0.1
_DB_TOL_STEP = 0.2
_DB_TOL_HARMONIC = 0.3
_SETTLE = 0.5            # seconds for the generator and device statistics to settle
_RATES = {              # model: the device's signal_frequency options down to 1 kHz
    'JS320': [1_000_000, 200_000, 100_000, 50_000, 20_000, 10_000, 5_000, 2_000, 1_000],
    'JS220': [1_000_000, 500_000, 200_000, 100_000, 50_000, 20_000, 10_000, 5_000, 2_000, 1_000],
}
_CURRENT_RANGES = {     # model: [(code, full scale A)], fixed ranges
    'JS320': [(130, 0.18), (132, 0.018), (136, 0.0018), (144, 180e-6), (160, 18e-6)],
    'JS220': [(130, 0.18), (132, 0.018), (136, 0.0018), (144, 180e-6), (160, 18e-6)],
}
_ARTIFACTS = os.environ.get('JS_UITEST_ARTIFACTS', os.path.join(os.getcwd(), 'uitest_artifacts'))


def _models(*models):
    """The device models a test applies to; others skip before the UI starts."""
    return pytest.mark.models(*models)


def _full_rate(device):
    return discover.FULL_RATE[device.model]


@pytest.fixture
def bench(request, device_model):
    """(session, device, stimulus, widget, record) with the device streaming at full rate."""
    marker = request.node.get_closest_marker('models')
    if marker is not None and device_model not in marker.args:
        pytest.skip(f'{device_model}: not in this test\'s device set {marker.args}')
    ui_session = request.getfixturevalue('ui_session')
    device = request.getfixturevalue('device')
    stimulus = request.getfixturevalue('stimulus')
    ui_session.publish_and_wait('registry/app/settings/signal_stream_enable', True)
    ui_session.set_signal_frequency(device.unique_id, _full_rate(device))
    signals_enable(ui_session, device, 'i', 'v')
    widget = spectrum.open_widget(ui_session, device, signal='v', fft_window='flattop',
                                  average_mode='cumulative', peak_count=10, peak_excursion=6.0)
    results = {'test': request.node.name, 'device': device.unique_id,
               'wiring': stimulus.wiring.to_dict(), 'checks': []}

    def record(**kwargs):
        results['checks'].append(kwargs)

    yield ui_session, device, stimulus, widget, record
    stimulus.off()
    path = os.path.join(_ARTIFACTS, 'spectrum_stimulus')
    os.makedirs(path, exist_ok=True)
    name = re.sub(r'[^\w.-]', '_', request.node.name)
    with open(os.path.join(path, f'{name}.json'), 'wt') as f:
        json.dump(results, f, indent=1)
    try:
        with open(os.path.join(path, f'{name}.png'), 'wb') as f:
            f.write(ui_session.qt_screenshot(widget))
    except Exception:
        pass


def _measure(session, device, widget, f, field='voltage', count=20, search_bins=3, trace='average'):
    """Fresh spectra and statistics for the present stimulus.

    :return: (spectrum info, [bin f, dB] near f, statistics rms dB).
    """
    session.wait(_SETTLE)
    info = spectrum.fresh(session, widget, count=count, timeout=60.0)
    ref = db(statistics_rms(session, device, field))
    return info, spectrum.value_at(session, widget, f, trace, search_bins), ref


def _peak_near(info, f, tol):
    near = [p for p in info['peaks'] if abs(p[0] - f) <= tol]
    assert near, f'no peak within {tol:.3g} Hz of {f:.6g} Hz: {info["peaks"]}'
    return min(near, key=lambda p: abs(p[0] - f))


def _fft_length_for(fs, f, bins=8, n_max=1 << 20):
    """The smallest power-of-2 FFT that puts f at least bins bins from DC."""
    n = 1024
    while n < n_max and f < bins * fs / n:
        n *= 2
    return n


# ---- F: frequency --------------------------------------------------------

@_models('JS320', 'JS220', 'JS110')
def test_f1_frequency_accuracy(bench):
    session, device, stim, widget, record = bench
    fs = _full_rate(device)
    if device.model == 'JS110':
        freqs = [1_000.0, 100_000.0]
    else:   # the top tone stays in the passband: the JS220 FIR ends near 300 kHz
        top = 250_000.0 if device.model == 'JS220' else 400_000.0
        freqs = [10.0, 100.0, 1_000.0, 10_000.0, 100_000.0, top]
    for f in freqs:
        n = _fft_length_for(fs, f)
        spectrum.configure(session, widget, fft_length=n, fft_window='hann')
        stim.sine('voltage', f, 0.3)
        info, _, _ = _measure(session, device, widget, f, count=4 if n > 65536 else 10)
        tol = _PPM * f + 0.1 * fs / n
        peak = _peak_near(info, f, 10 * fs / n)
        record(id='F1', f=f, n=n, peak=peak, tol_hz=tol)
        assert abs(peak[0] - f) <= tol, f'{f} Hz read {peak[0]} Hz (tol {tol:.3g})'


@_models('JS320')
def test_f2_low_frequency_resolution(bench):
    session, device, stim, widget, record = bench
    fs = _full_rate(device)
    spectrum.configure(session, widget, fft_length=1 << 20, fft_window='hann', overlap=0.75)
    for f in (1.0, 5.0):
        stim.sine('voltage', f, 0.3)
        info, _, _ = _measure(session, device, widget, f, count=3)
        df = fs / (1 << 20)
        peak = _peak_near(info, f, 4 * df)
        record(id='F2', f=f, peak=peak)
        assert abs(peak[0] - f) <= 0.1 * df + _PPM * f


# ---- A: amplitude --------------------------------------------------------

@_models('JS320', 'JS220', 'JS110')
def test_a1_amplitude_flat_top(bench):
    session, device, stim, widget, record = bench
    levels = [1.0] if device.model == 'JS110' else [1.0, 0.1, 0.01]
    spectrum.configure(session, widget, fft_length=4096, fft_window='flattop')
    for rms in levels:
        for f in (1_000.0, 100_000.0):
            c = stim.sine('voltage', f, rms)
            _, (fb, level), ref = _measure(session, device, widget, f)
            scope = stim.monitor_rms(c.source)
            check = dict(id='A1', rms=rms, f=f, level_db=level, statistics_db=ref)
            if scope is not None and c.network in ('direct', 'divider'):
                check['scope_db'] = db(scope * c.gain)
            record(**check)
            assert abs(level - ref) <= _DB_TOL_AMPLITUDE, check
            if 'scope_db' in check:  # two instruments: allow 1%
                assert abs(check['scope_db'] - ref) <= 20 * math.log10(1.01), check


@_models('JS320', 'JS220')
def test_a2_amplitude_linearity(bench):
    session, device, stim, widget, record = bench
    f = 1_000.0
    spectrum.configure(session, widget, fft_length=4096, fft_window='flattop')
    errors = []
    for step in range(0, 7):
        rms = 10 ** (-step / 2)  # 1 V, then -10 dB steps
        if stim.source_vrms('voltage', rms) < 0.010:
            break  # the wavegen resolution floor
        stim.sine('voltage', f, rms)
        _, (_, level), ref = _measure(session, device, widget, f)
        errors.append(level - ref)
        record(id='A2', rms=rms, level_db=level, statistics_db=ref)
    assert len(errors) >= 4, f'only {len(errors)} steps fit the wavegen range'
    assert max(errors) - min(errors) <= 2 * _DB_TOL_AMPLITUDE, errors


@_models('JS320')
def test_a3_scalloping_per_window(bench):
    from joulescope_ui.spectrum_engine import WINDOWS, window
    session, device, stim, widget, record = bench
    fs, n, k = _full_rate(device), 4096, 41
    df = fs / n
    for name in WINDOWS:
        spectrum.configure(session, widget, fft_length=n, fft_window=name)
        levels = []
        for offset in (0.0, 0.5):
            f = (k + offset) * df
            stim.sine('voltage', f, 0.5)
            _, (_, level), ref = _measure(session, device, widget, f, search_bins=1)
            levels.append(level - ref)
        w = window(name, n)
        expect = 20 * math.log10(abs(np.sum(w * np.exp(-1j * np.pi * np.arange(n) / n))) / np.sum(w))
        loss = levels[1] - levels[0]
        record(id='A3', window=name, center_db=levels[0], loss_db=loss, expect_db=expect)
        assert abs(loss - expect) <= _DB_TOL_AMPLITUDE, (name, loss, expect)
        if name == 'flattop':
            assert abs(loss) < 0.1


# ---- H: harmonics and two-tone -------------------------------------------

@_models('JS320', 'JS220')
def test_h1_square_harmonics(bench):
    session, device, stim, widget, record = bench
    f = 1_000.0
    spectrum.configure(session, widget, fft_length=65536, fft_window='flattop')
    stim.square('voltage', f, vpp=2.0)
    _measure(session, device, widget, f, count=10)
    fundamental = spectrum.value_at(session, widget, f, 'average', 3)[1]
    for h in range(2, 16):
        level = spectrum.value_at(session, widget, h * f, 'average', 3)[1] - fundamental
        record(id='H1', harmonic=h, dbc=level)
        if h % 2:
            assert abs(level + 20 * math.log10(h)) <= _DB_TOL_HARMONIC, (h, level)
        else:
            assert level < -60, (h, level)


@_models('JS320')
def test_h2_two_tone(bench):
    session, device, stim, widget, record = bench
    n = 4096
    t = np.arange(n) / n
    small_dbc = -60.0
    samples = np.sin(2 * np.pi * 10 * t) + 10 ** (small_dbc / 20) * np.sin(2 * np.pi * 13 * t)
    spectrum.configure(session, widget, fft_length=65536, fft_window='blackman_harris')
    stim.custom('voltage', samples, 1_000.0, vpp=2.0)   # 10 kHz and 13 kHz
    _measure(session, device, widget, 10_000.0, count=20)
    big = spectrum.value_at(session, widget, 10_000.0, 'average', 3)[1]
    small = spectrum.value_at(session, widget, 13_000.0, 'average', 3)[1] - big
    tr = spectrum.trace(session, widget)
    dbs = np.array(tr['db'])
    f = tr['f0'] + tr['df'] * np.arange(len(dbs))
    mask = (f > 500) & (np.abs(f - 10_000) > 200) & (np.abs(f - 13_000) > 200)
    sfdr = big - float(np.max(dbs[mask]))
    record(id='H2', small_dbc=small, sfdr_db=sfdr)
    assert abs(small - small_dbc) <= 1.0, small


# ---- N: noise ------------------------------------------------------------

@_models('JS320', 'JS220')
def test_n1_psd_level(bench):
    session, device, stim, widget, record = bench
    stim.noise('voltage', vpp=1.0)
    levels = []
    for n in (1024, 4096, 65536):
        for name in ('hann', 'blackman_harris', 'flattop'):
            spectrum.configure(session, widget, scaling='psd', fft_length=n, fft_window=name)
            session.wait(_SETTLE)
            spectrum.fresh(session, widget, count=50 if n < 65536 else 20, timeout=60.0)
            variance = statistics_rms(session, device, 'voltage') ** 2
            tr = spectrum.trace(session, widget)
            p = 10 ** (np.array(tr['db']) / 10)
            f = tr['f0'] + tr['df'] * np.arange(len(p))
            integrated = float(np.sum(p[1:]) * tr['df'])
            band = float(10 * np.log10(np.mean(p[(f >= 10_000) & (f <= 200_000)])))
            levels.append(band)
            record(id='N1', n=n, window=name, integrated=integrated, variance=variance, band_db=band)
            assert abs(integrated / variance - 1) <= 0.05, (n, name, integrated, variance)
    assert max(levels) - min(levels) <= 1.0, levels   # ±0.5 dB


@_models('JS320', 'JS220')
def test_n2_noise_floor_baseline(bench):
    session, device, stim, widget, record = bench
    stim.off()
    for signal in ('v', 'i'):
        for n in (4096, 65536):
            spectrum.configure(session, widget, signal=signal, scaling='psd', fft_length=n, fft_window='hann')
            spectrum.fresh(session, widget, count=10, timeout=60.0)
            dbs = np.array(spectrum.trace(session, widget)['db'][1:])
            record(id='N2', signal=signal, n=n, median_db=float(np.median(dbs)),
                   max_db=float(np.max(dbs)), peaks=spectrum.info(session, widget)['peaks'])
            assert np.isfinite(dbs).all()


# ---- R: sample rates -----------------------------------------------------

@_models('JS320', 'JS220')
def test_r1_sample_rates(bench):
    session, device, stim, widget, record = bench
    for rate in _RATES[device.model]:
        session.set_signal_frequency(device.unique_id, rate)
        f = rate / 40   # the statistics are full rate: keep clear of the device decimator droop
        n = 4096 if rate >= 10_000 else 1024
        spectrum.configure(session, widget, fft_length=n, fft_window='flattop')
        stim.sine('voltage', f, 0.3)
        info, (_, level), ref = _measure(session, device, widget, f, count=5 if rate < 10_000 else 10)
        peak = _peak_near(info, f, 10 * rate / n)
        record(id='R1', rate=rate, fs=info['fs'], rbw=info['rbw'], peak=peak, level_db=level,
               statistics_db=ref, overruns=info['overruns'])
        assert info['fs'] == rate
        assert info['n'] == n
        assert abs(peak[0] - f) <= _PPM * f + 0.1 * rate / n
        assert abs(level - ref) <= _DB_TOL_STEP
        assert info['overruns'] == 0


@_models('JS320')
def test_r2_device_anti_alias(bench):
    """Characterize the device decimator for each Signal filter (sincN) order.

    Measures the passband droop at 0.75 x Nyquist and the alias of a tone at
    1.5 x Nyquist against the sincN response, N x 20 log10 |sinc(f / fs)|.
    sinc filters trade anti-aliasing for no ringing: sinc1, the default,
    rejects the alias by only 10.5 dB.
    """
    session, device, stim, widget, record = bench
    spectrum.configure(session, widget, fft_length=4096, fft_window='flattop')
    for rate in (100_000, 10_000):
        for order in (1, 2, 3):
            device_settings(session, device, signal_filter=order)
            for factor in (0.75, 1.5):   # passband edge, and above the new Nyquist
                f = factor * rate / 2
                alias = f if f < rate / 2 else rate - f
                stim.sine('voltage', f, 0.3)
                session.set_signal_frequency(device.unique_id, rate)
                _, (_, level), reference = _measure(session, device, widget, alias)   # statistics: full rate
                expect = order * db(abs(np.sinc(f / rate)))
                record(id='R2', rate=rate, signal_filter=order, f=f, read_at=alias,
                       dbc=level - reference, expect_dbc=expect)
                assert abs(level - reference - expect) <= 0.5, (rate, order, f, level - reference)   # 0.24 seen
    device_settings(session, device, signal_filter=1)


# ---- D: span (decimation) ------------------------------------------------

@_models('JS320', 'JS220')
def test_d1_span(bench):
    session, device, stim, widget, record = bench
    fs = _full_rate(device)
    rbw_prev = None
    for k in range(1, 11):
        d = 1 << k
        f = 0.5 * fs / 2 / d
        spectrum.configure(session, widget, decimate=d, fft_length=4096, fft_window='flattop')
        stim.sine('voltage', f, 0.3)
        info, (_, level), ref = _measure(session, device, widget, f, count=3 if d >= 64 else 10)
        record(id='D1', decimate=d, f=f, rbw=info['rbw'], level_db=level, statistics_db=ref)
        assert abs(level - ref) <= _DB_TOL_AMPLITUDE
        if rbw_prev is not None:
            assert info['rbw'] == pytest.approx(rbw_prev / 2, rel=1e-6)
        rbw_prev = info['rbw']


@_models('JS320', 'JS220')
def test_d2_decimator_aliasing(bench):
    session, device, stim, widget, record = bench
    fs, d = _full_rate(device), 4
    nyquist_d = fs / 2 / d
    spectrum.configure(session, widget, decimate=d, fft_length=4096, fft_window='blackman_harris')
    f = 1.2 * nyquist_d     # aliases to 0.8 x nyquist_d, inside the retained band
    stim.sine('voltage', f, 0.5)
    _, (_, alias), ref = _measure(session, device, widget, 0.8 * nyquist_d)
    record(id='D2', f=f, alias_dbc=alias - ref)
    assert alias - ref <= -80, alias - ref
    # Near the input Nyquist.  The generator and the device put spurs in the
    # retained band (-60 dBc measured), so compare against the undecimated
    # spectrum: the decimator must add nothing above it.
    stim.sine('voltage', 0.95 * fs / 2, 0.5)
    worst, worst_f = {}, {}
    for decimate in (1, d):
        spectrum.configure(session, widget, decimate=decimate)
        session.wait(_SETTLE)
        spectrum.fresh(session, widget, count=10)
        tr = spectrum.trace(session, widget)
        retained = int(0.9 * nyquist_d / tr['df'])   # the hidden roll-off band may hold aliases
        k = 4 + int(np.argmax(tr['db'][4:retained]))   # above the window main lobe at DC
        worst[decimate], worst_f[decimate] = tr['db'][k], k * tr['df']
    ref = db(statistics_rms(session, device, 'voltage'))
    record(id='D2', f=0.95 * fs / 2, input_worst_dbc=worst[1] - ref, input_worst_f=worst_f[1],
           worst_dbc=worst[d] - ref, worst_f=worst_f[d])
    assert worst[d] <= max(worst[1] + 1.0, ref - 80), (worst, ref)


# ---- C: current ----------------------------------------------------------

@_models('JS320', 'JS220')
def test_c1_current_fixed_ranges(bench):
    session, device, stim, widget, record = bench
    stim.require('current')
    f = 1_000.0
    spectrum.configure(session, widget, signal='i', fft_length=4096, fft_window='flattop')
    ran = []
    for code, full_scale in _CURRENT_RANGES[device.model]:
        rms = 0.2 * full_scale
        device_settings(session, device, current_range=code)
        gain = stim.current_gain(f)
        if rms / gain > 4.5 / math.sqrt(2) or rms / gain < 0.010:
            record(id='C1', range=code, gain=gain, skipped=f'needs {rms / gain:.3g} V rms from the source')
            continue
        steps = []
        for scale in (1.0, 10 ** (-10 / 20)):
            stim.sine('current', f, rms * scale, gain=gain)
            info, (_, level), ref = _measure(session, device, widget, f, field='current')
            peak = _peak_near(info, f, 10 * info['fs'] / info['n'])
            steps.append(level - ref)
            record(id='C1', range=code, rms_nominal=rms * scale, level_db=level, statistics_db=ref, peak=peak)
            assert abs(level - ref) <= _DB_TOL_STEP
        ran.append(code)
        assert abs(steps[1] - steps[0]) <= _DB_TOL_STEP
    device_settings(session, device, current_range=-1)
    assert ran, 'no fixed range fits the current wiring; see doc/adp3450_connection.md'


def _autorange_stimulus(stim, device, f):
    c = stim.require('current', networks=('series',))
    stim.sine('current', f, 4.0 / math.sqrt(2) * c.gain)   # 8 Vpp: crosses ranges every half cycle
    return c


@_models('JS320', 'JS220')
def test_c2_current_autoranging(bench):
    session, device, stim, widget, record = bench
    f = 10.0
    _autorange_stimulus(stim, device, f)
    device_settings(session, device, current_range=-1)
    spectrum.configure(session, widget, signal='i', fft_length=65536, fft_window='hann')
    session.wait(_SETTLE)
    spectrum.fresh(session, widget, count=10)
    session.wait(10.0)
    info = spectrum.info(session, widget)
    record(id='C2', info=info)
    assert info['overruns'] == 0 and info['gaps'] == 0, info
    _peak_near(info, f, 4 * info['fs'] / info['n'])


@_models('JS320')
def test_c3_current_range_signal(bench):
    session, device, stim, widget, record = bench
    f = 50.0
    _autorange_stimulus(stim, device, f)
    device_settings(session, device, current_range=-1)
    signals_enable(session, device, 'r')
    spectrum.configure(session, widget, signal='r', fft_length=65536, fft_window='hann')
    session.wait(_SETTLE)
    info = spectrum.fresh(session, widget, count=10)
    record(id='C3', peaks=info['peaks'])
    tol = 4 * info['fs'] / info['n']
    assert any(abs(p[0] - f) <= tol or abs(p[0] - 2 * f) <= tol for p in info['peaks']), info['peaks']


# ---- P, G: power and digital ---------------------------------------------

@_models('JS320', 'JS220')
def test_p1_power_products(bench):
    session, device, stim, widget, record = bench
    f1, f2 = 1_000.0, 1_300.0
    code, full_scale = _CURRENT_RANGES[device.model][2]   # 1.8 mA: fits series and divider wiring
    device_settings(session, device, current_range=code)
    stim.sine('current', f2, 0.25 * full_scale, gain=stim.current_gain(f2))
    stim.sine('voltage', f1, 1.0)
    signals_enable(session, device, 'p')
    spectrum.configure(session, widget, signal='p', fft_length=65536, fft_window='hann')
    session.wait(_SETTLE)
    spectrum.fresh(session, widget, count=10)
    floor = float(np.median(spectrum.trace(session, widget)['db'][1:]))
    for f in (f1 + f2, f2 - f1):
        level = spectrum.value_at(session, widget, f, 'average', 3)[1]
        record(id='P1', f=f, level_db=level, floor_db=floor)
        assert level - floor >= 20, (f, level, floor)


@_models('JS320')
def test_g1_digital_input(bench):
    session, device, stim, widget, record = bench
    connected = [t for t in ('gpi0', 'gpi1', 'gpi2', 'gpi3') if stim.wiring.connection(t)]
    if not connected:
        pytest.skip('no DIO wired to a gpi input')
    target = connected[0]
    signal = target[-1]
    device_settings(session, device, gpio_voltage=1)   # 3.3 V, as the ADP3450 DIO
    signals_enable(session, device, signal)
    f = stim.digital_square(target, 1_000.0)
    spectrum.configure(session, widget, signal=signal, fft_length=65536, fft_window='flattop')
    session.wait(_SETTLE)
    spectrum.fresh(session, widget, count=10)
    fundamental = spectrum.value_at(session, widget, f, 'average', 3)[1]
    third = spectrum.value_at(session, widget, 3 * f, 'average', 3)[1] - fundamental
    record(id='G1', target=target, f=f, fundamental_db=fundamental, third_dbc=third)
    assert abs(third + 20 * math.log10(3)) <= 1.0, third


# ---- W, T: waterfall and traces ------------------------------------------

@_models('JS320')
def test_w1_waterfall_sweep_timing(bench):
    session, device, stim, widget, record = bench
    f0, f1, period = 1_000.0, 100_000.0, 10.0
    spectrum.configure(session, widget, fft_length=4096, fft_window='hann', average_mode='off', peak_count=1)
    stim.sweep('voltage', f0, f1, period, vpp=1.0)
    session.wait(1.0)
    points = []
    t_end = time.monotonic() + period
    while time.monotonic() < t_end:
        peaks = spectrum.info(session, widget)['peaks']
        if peaks:
            points.append((time.monotonic(), peaks[0][0]))
        session.wait(0.2)
    # longest increasing run: the sweep wraps once per period
    runs, run = [], [points[0]]
    for p in points[1:]:
        if p[1] >= run[-1][1]:
            run.append(p)
        else:
            runs.append(run)
            run = [p]
    runs.append(run)
    run = max(runs, key=len)
    t, f = np.array(run).T
    slope = float(np.polyfit(t, f, 1)[0])
    expect = (f1 - f0) / period
    record(id='W1', slope_hz_per_s=slope, expect=expect, points=len(run))
    assert len(run) >= 10, run
    assert abs(slope / expect - 1) <= 0.05, (slope, expect)


@_models('JS320')
def test_w2_burst_detectors(bench):
    session, device, stim, widget, record = bench
    f = 10_000.0
    spectrum.configure(session, widget, fft_length=4096, fft_window='hann', waterfall_duration=10.0,
                       waterfall_rows=200)   # 50 ms rows
    stim.sine('voltage', f, 0.5)
    _, (_, steady), _ = _measure(session, device, widget, f)
    stim.burst('voltage', f, vpp=2 * math.sqrt(2) * 0.5, on_s=0.010, period_s=1.0)
    levels = {}
    for detector in ('max', 'average'):
        spectrum.configure(session, widget, waterfall_detector=detector)
        session.wait(4.0)
        column = [v for v in spectrum.waterfall_column(session, widget, f, 60) if v is not None]
        levels[detector] = max(column) - steady
    record(id='W2', steady_db=steady, **levels)
    assert levels['max'] >= -0.5, levels
    assert -10.5 <= levels['average'] <= -6.5, levels   # 10 ms of a 50 ms row, -7 dB, or split


@_models('JS320')
def test_t1_trace_modes(bench):
    session, device, stim, widget, record = bench
    # Hann, not flattop: flattop's negative lobes put a segment that straddles
    # an amplitude step outside the two levels (+0.15 / -0.3 dB measured).
    # The tone sits on bin 41, so Hann has no scalloping loss.
    n = 4096
    f = 41 * _full_rate(device) / n
    spectrum.configure(session, widget, fft_length=n, fft_window='hann', average_mode='exponential',
                       average_count=16, show_max=True, show_min=True)
    stim.sine('voltage', f, 0.5)
    _measure(session, device, widget, f)
    stim.amplitude('voltage', 1.0)   # a restart would drop out: min and max hold the glitch
    session.wait(2.0)
    stim.amplitude('voltage', 0.25)
    session.wait(3.0)   # >> 16 spectra
    value = {name: spectrum.value_at(session, widget, f, name, 3)[1] for name in ('max', 'min', 'average')}
    record(id='T1', **value)
    assert abs(value['max'] - db(1.0)) <= _DB_TOL_STEP, value
    assert abs(value['min'] - db(0.25)) <= _DB_TOL_STEP, value
    assert abs(value['average'] - db(0.25)) <= _DB_TOL_STEP, value
    session.publish(f'registry/{widget}/actions/!clear', None)
    spectrum.wait_info(session, widget, lambda i: i.get('count', 0) >= 5)
    assert abs(spectrum.value_at(session, widget, f, 'max', 3)[1] - db(0.25)) <= _DB_TOL_STEP


# ---- X: range tool parity ------------------------------------------------

@_models('JS320', 'JS220')
def test_x1_recording_parity(bench, tmp_capture):
    from joulescope_ui.spectrum_engine import SpectrumEngine, to_db
    session, device, stim, widget, record = bench
    f, n = 10_000.0, 4096
    spectrum.configure(session, widget, fft_length=n, fft_window='flattop')
    stim.sine('voltage', f, 0.5)
    _measure(session, device, widget, f)
    path = str(tmp_capture / 'x1.jls')
    record_id = session.record_start(path, source_ids=[device.unique_id])
    session.wait(3.0)
    widget_db = spectrum.value_at(session, widget, f, 'average', 3)[1]
    session.record_stop(record_id)
    with verify.open_reader(path) as r:
        signal = verify.signal_by_name(r, 'voltage')
        x = verify.read_fsr(r, signal.signal_id)
        e = SpectrumEngine({'fft_length': n, 'window': 'flattop', 'average_mode': 'cumulative',
                            'row_period': None})
        e.process(0, signal.sample_rate, x)
    db_file = float(np.max(to_db(e.average)[int(f * n / signal.sample_rate) - 3:][:7]))
    record(id='X1', widget_db=widget_db, recording_db=db_file)
    assert abs(widget_db - db_file) <= _DB_TOL_STEP


# ---- S: robustness -------------------------------------------------------

@_models('JS320', 'JS220')
def test_s1_two_devices(bench):
    session, device, stim, widget, record = bench
    stim.sine('voltage', 10_000.0, 0.5)
    others = [d for d in session.devices() if d.unique_id != device.unique_id]
    if not others:
        pytest.skip('needs a second device')
    widgets = [widget, spectrum.open_widget(session, device, signal='i')]
    for other in others:   # every other connected device, two widgets each
        signals_enable(session, other, 'i', 'v')
        widgets += [spectrum.open_widget(session, other, signal='v'),
                    spectrum.open_widget(session, other, signal='i')]
    session.wait(60.0)
    infos = [spectrum.info(session, w) for w in widgets]
    record(id='S1', infos=infos)
    for i in infos:
        assert i.get('count', 0) > 0 and i['overruns'] == 0 and i['gaps'] == 0, i


@_models('JS320')
def test_s2_worst_case_load(bench):
    session, device, stim, widget, record = bench
    stim.sine('voltage', 10_000.0, 0.5)
    spectrum.configure(session, widget, fft_length=1 << 20, overlap=0.9, waterfall_rows=1000)
    session.wait(60.0)
    t0 = time.monotonic()
    info = spectrum.info(session, widget)
    latency = time.monotonic() - t0
    record(id='S2', info=info, query_latency_s=latency)
    assert info.get('count', 0) > 0 and info['overruns'] == 0, info
    assert latency < 1.0


@_models('JS320', 'JS220')
@pytest.mark.slow
def test_s3_soak(bench):
    session, device, stim, widget, record = bench
    duration = float(os.environ.get('JS_UITEST_SOAK_S', '3600'))
    stim.sine('voltage', 10_000.0, 0.5)
    second = spectrum.open_widget(session, device, signal='i')
    try:
        import psutil
        proc = psutil.Process(session.ui_pid)
    except Exception:
        proc = None
    rss = []
    t_end = time.monotonic() + duration
    while time.monotonic() < t_end:
        if proc is not None:
            rss.append(proc.memory_info().rss)
        session.wait(60.0)
    infos = [spectrum.info(session, w) for w in (widget, second)]
    record(id='S3', rss=rss, infos=infos)
    for i in infos:
        assert i['overruns'] == 0 and i['gaps'] == 0, i
    if len(rss) > 5:   # flat after warm-up: allow 10% over the first 5 minutes' level
        assert max(rss[5:]) <= 1.10 * rss[5], rss
