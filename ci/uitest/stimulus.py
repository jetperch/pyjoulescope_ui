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

"""Drive a stimulus instrument (an ADP3450) into the device under test.

The wiring comes from the station inventory, so a test asks for what it
needs and skips, with the reason, when the station is wired differently:

* On the HIL farm, the runner sets ``JS_UITEST_STIMULUS`` from the
  station's ``stations.yaml`` and puts ``jci_instruments`` on the path.
* On a bench, set ``JS_UITEST_STIMULUS_FILE`` to a ``stations.yaml`` and
  ``JS_UITEST_STATION`` to the station id (or to a JSON/YAML mapping of
  device spec to stimulus).  ``jci_instruments`` comes from a sibling
  ``joulescope_ci`` checkout when it is not installed.

See joulescope_ci doc/adp3450_connection.md and docs/plans/completed/spectrum.md.
"""

import json
import math
import os
import sys
import time

import pytest


ENV = 'JS_UITEST_STIMULUS'
ENV_FILE = 'JS_UITEST_STIMULUS_FILE'
ENV_STATION = 'JS_UITEST_STATION'

VPP_MAX = 9.0           # stay inside the ADP3450 wavegen ±5 V
VRMS_MIN = 0.010        # below this the 14-bit wavegen quantization dominates


def instruments():
    """Import jci_instruments, from a sibling joulescope_ci checkout if needed."""
    try:
        import jci_instruments  # noqa: F401  (presence check)
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        sibling = os.path.normpath(os.path.join(here, '..', '..', '..', 'joulescope_ci'))
        sys.path.insert(0, sibling)
    from jci_instruments import adp3450, stimulus
    return adp3450, stimulus


def _load_file(path, station):
    with open(path, 'rt', encoding='utf-8') as f:
        text = f.read()
    if path.endswith(('.yaml', '.yml')):
        import yaml  # bench-only: the farm passes JSON in ENV
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if 'stations' not in data:
        return data
    stations = data['stations'] or {}
    if station is None:
        wired = [s for s, body in stations.items()
                 if any('stimulus' in d for d in (body or {}).get('duts', []))]
        if len(wired) != 1:
            raise ValueError(f'set {ENV_STATION} to one of {wired}')
        station = wired[0]
    out = {}
    for d in stations[station].get('duts', []):
        if 'stimulus' in d:
            out[d.get('serial') or d['kind']] = d['stimulus']
    return out


def wirings():
    """{device spec: Wiring} for this station, empty when none.

    Also empty without jci_instruments, which is private to joulescope_ci and
    so absent from public CI: the stimulus tests skip.
    """
    path = os.environ.get(ENV_FILE)
    if not os.environ.get(ENV) and not path:
        return {}
    try:
        _, stimulus = instruments()
    except ImportError:
        return {}
    if os.environ.get(ENV):
        return stimulus.decode(os.environ[ENV])
    data = _load_file(os.path.expanduser(path), os.environ.get(ENV_STATION))
    return {spec: stimulus.Wiring.from_dict(d) for spec, d in data.items()}


def wiring_for(device):
    """The Wiring for device by its unique id (JS320-8W2A) or kind (js320)."""
    w = wirings()
    for key in (device.unique_id, device.model.lower()):
        for spec, wiring in w.items():
            if spec.lower() == key.lower():
                return wiring
    return None


class Stimulus:
    """The instrument wired to one device, addressed by DUT input.

    Amplitudes are at the DUT input: volts for voltage and gpi targets,
    nominal amps for current (source volts / series ohms; the device's own
    statistics are the reference, see :func:`statistics_rms`).
    """

    def __init__(self, session, device, wiring, adp):
        self.session = session
        self.device = device
        self.wiring = wiring
        self.adp = adp

    def require(self, target, networks=None):
        """The connection to target, or pytest.skip with the reason."""
        _, stimulus = instruments()
        try:
            return self.wiring.require(target, networks)
        except stimulus.Incompatible as ex:
            pytest.skip(str(ex))

    def _source_vpp(self, c, vpp_at_input, gain=None):
        vpp = vpp_at_input / (c.gain if gain is None else gain)
        if vpp > VPP_MAX:
            pytest.skip(f'{c.target} needs {vpp:.3g} Vpp from {c.source}, above {VPP_MAX} Vpp')
        return vpp

    def source_vrms(self, target, rms_at_input):
        """The source amplitude for rms_at_input, in V rms."""
        return rms_at_input / self.require(target).gain

    def sine(self, target, freq_hz, rms, offset=0.0, gain=None):
        """Output a sine of rms at the DUT input.

        :param gain: The input per source volt, for a connection with no
            defined gain (a divider into current): see :meth:`current_gain`.
        """
        c = self.require(target)
        gain = c.gain if gain is None else gain
        vpp = self._source_vpp(c, 2 * math.sqrt(2) * rms, gain)
        if vpp / (2 * math.sqrt(2)) < VRMS_MIN:
            pytest.skip(f'{c.source} at {vpp:.3g} Vpp is below the {VRMS_MIN} V rms resolution floor')
        self.adp.wavegen_sine(c.channel, freq_hz, vpp=vpp, offset=offset / gain)
        return c

    def amplitude(self, target, rms):
        """Change the running sine on target to rms without a restart glitch."""
        c = self.require(target)
        self.adp.wavegen_amplitude(c.channel, self._source_vpp(c, 2 * math.sqrt(2) * rms))

    def current_gain(self, freq_hz=1_000.0, source_vrms=0.05):
        """The current per source volt on the present fixed current range.

        Through a series resistor this is nominal (1 / ohms).  Through a
        divider it depends on the range shunt, so measure it with a small
        sine.  The caller must select a fixed current range first.
        """
        c = self.require('current')
        if c.network == 'series':
            return c.gain
        self.adp.wavegen_sine(c.channel, freq_hz, vpp=2 * math.sqrt(2) * source_vrms)
        self.session.wait(0.5)
        return statistics_rms(self.session, self.device, 'current') / source_vrms

    def square(self, target, freq_hz, vpp, duty_percent=50.0):
        c = self.require(target)
        self.adp.wavegen_square(c.channel, freq_hz, self._source_vpp(c, vpp), duty_percent=duty_percent)
        return c

    def noise(self, target, vpp, bandwidth_hz=1_000_000.0):
        c = self.require(target)
        self.adp.wavegen_noise(c.channel, self._source_vpp(c, vpp), bandwidth_hz=bandwidth_hz)
        return c

    def sweep(self, target, f_start_hz, f_stop_hz, period_s, vpp):
        c = self.require(target)
        self.adp.wavegen_sweep(c.channel, f_start_hz, f_stop_hz, period_s, self._source_vpp(c, vpp))
        return c

    def burst(self, target, freq_hz, vpp, on_s, period_s):
        c = self.require(target)
        self.adp.wavegen_burst(c.channel, freq_hz, self._source_vpp(c, vpp), on_s, period_s)
        return c

    def custom(self, target, samples, freq_hz, vpp):
        c = self.require(target)
        self.adp.wavegen_custom(c.channel, samples, freq_hz, self._source_vpp(c, vpp))
        return c

    def digital_square(self, target, freq_hz):
        c = self.require(target)
        return self.adp.digital_square(c.channel, freq_hz)

    def off(self):
        self.adp.outputs_off()

    def monitor_rms(self, source, duration_s=0.1, sample_rate_hz=10_000_000.0):
        """The AC rms of source measured by its monitor scope channel, or None."""
        m = self.wiring.monitor(source)
        if m is None:
            return None
        x = self.adp.capture(channels=(m.scope_channel,), duration_s=duration_s,
                             sample_rate_hz=sample_rate_hz, channel_range=10.0)[m.scope_channel]
        n = len(x)
        mean = sum(x) / n
        return math.sqrt(sum((v - mean) ** 2 for v in x) / n)


def device_settings(session, device, **settings):
    """Apply device settings, each confirmed."""
    for name, value in settings.items():
        session.publish_and_wait(f'{device.topic}/settings/{name}', value)


def signals_enable(session, device, *signals):
    for s in signals:
        session.publish_and_wait(f'{device.topic}/settings/signals/{s}/enable', True)


def statistics_rms(session, device, field, seconds=2.0):
    """The AC rms of a signal from the device's own statistics.

    The statistics std of a signal is its AC rms over each statistics
    window.  This combines the windows received over ``seconds``.

    :param field: current, voltage, or power.
    """
    samples = []
    topic = f'{device.topic}/events/statistics/!data'
    session.subscribe(topic, lambda t, v: samples.append(v['signals'][field]['std']['value']), ['pub'])
    session.publish('registry/app/settings/statistics_stream_enable', True)
    deadline = time.monotonic() + seconds + 5.0
    t_end = time.monotonic() + seconds
    while time.monotonic() < deadline and (time.monotonic() < t_end or not samples):
        session.wait(0.1)
    session.unsubscribe(topic)
    if not samples:
        raise TimeoutError(f'no statistics from {device.unique_id}')
    return math.sqrt(sum(v * v for v in samples) / len(samples))


def db(rms):
    return 20.0 * math.log10(rms)
