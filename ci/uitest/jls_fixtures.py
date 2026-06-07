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

"""Generate small JLS v2 fixtures for tests (single FSR signal + markers).

Shared by the harness unit tests and the open/verify tests so the JLS-writing
recipe lives in exactly one place.
"""

import numpy as np
import pyjls


# A fixed JLS-time base (time64 units) for fixtures: arbitrary but valid, so the
# file carries UTC like a real recording (the exporter needs UTC to map ranges).
_UTC_BASE = 300 * pyjls.time64.SECOND


def write_fsr_v2(path, *, signal_name='current', units='A', sample_rate=1000,
                 data=None, markers=0, model='JS220', serial_number='001234',
                 utc=True):
    """Write a minimal JLS v2 file with one FSR signal and ``markers`` VMARKERs.

    :param data: 1-D samples (default a 5000-point ramp 0..1).
    :param markers: Number of evenly-spaced vertical markers to add.
    :param utc: Write UTC sample<->time entries (default True).  Real recordings
        carry UTC, and the exporter requires it to resolve a range; fixtures
        without UTC cannot be exported.
    :return: The ``data`` array actually written (handy for round-trip asserts).
    """
    if data is None:
        data = np.linspace(0.0, 1.0, 5000, dtype=np.float32)
    data = np.asarray(data, dtype=np.float32)
    with pyjls.Writer(path) as w:
        w.source_def(source_id=1, name='dev', vendor='Jetperch', model=model,
                     version='1', serial_number=serial_number)
        w.signal_def(signal_id=1, source_id=1, signal_type=pyjls.SignalType.FSR,
                     data_type=pyjls.DataType.F32, sample_rate=sample_rate,
                     name=signal_name, units=units)
        if utc:
            last = len(data) - 1
            w.utc(1, 0, _UTC_BASE)
            w.utc(1, last, _UTC_BASE + int(round(last / sample_rate * pyjls.time64.SECOND)))
        w.fsr_f32(1, 0, data)
        for i in range(markers):
            sample = int((i + 1) * len(data) / (markers + 1))
            w.annotation(1, sample, 0.0, pyjls.AnnotationType.VMARKER, 0, f'm{i}')
    return data
