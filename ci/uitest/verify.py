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

"""Verify JLS recordings and exports produced by the UI under test.

The UI always *exports* and *records* JLS **v2**, so :class:`pyjls.Reader`
(v2-only) is the right tool for the "verify correct" assertions in the test
plan.  JLS **v1** appears only as an input fixture that the UI opens; the
:func:`jls_version` magic-byte sniff is provided to tell the two apart.

This module depends only on ``pyjls`` + numpy + stdlib (no PySide6), so it is
unit-testable without the UI installed.
"""

import contextlib
import numpy as np
import pyjls


#: First bytes of a JLS v1 file (``\xd3tagfmt``).
JLS_V1_MAGIC = b'\xd3tagfmt '
#: First bytes of a JLS v2 file.
JLS_V2_MAGIC = b'jlsfmt\r\n'


def jls_version(path):
    """Sniff the JLS major version from the file header.

    :param path: Path to a ``.jls`` file.
    :return: ``1``, ``2``, or ``None`` if unrecognized.
    """
    with open(path, 'rb') as f:
        head = f.read(8)
    if head.startswith(JLS_V2_MAGIC):
        return 2
    if head.startswith(JLS_V1_MAGIC):
        return 1
    return None


@contextlib.contextmanager
def open_reader(path):
    """Open a JLS **v2** file as a :class:`pyjls.Reader` context manager.

    :raises ValueError: If ``path`` is not a JLS v2 file (e.g. it is v1).
    """
    version = jls_version(path)
    if version != 2:
        raise ValueError(f'{path}: expected JLS v2, found {version!r}')
    reader = pyjls.Reader(path)
    try:
        yield reader
    finally:
        reader.close()


def data_signals(reader):
    """Return ``{signal_id: SignalDef}`` for real FSR data signals.

    Excludes the synthetic global-annotation signal (``signal_id == 0``,
    ``sample_rate == 0``).
    """
    out = {}
    for signal_id, sig in reader.signals.items():
        if signal_id == 0 or getattr(sig, 'sample_rate', 0) in (0, None):
            continue
        out[signal_id] = sig
    return out


def signal_by_name(reader, name):
    """Return the ``SignalDef`` whose ``name`` matches, else None."""
    for sig in data_signals(reader).values():
        if sig.name == name:
            return sig
    return None


def read_fsr(reader, signal_id, start=0, count=None):
    """Read fixed-sample-rate samples as a 1-D float numpy array.

    :param count: Number of samples; default reads to the end of the signal.
    """
    length = reader.signals[signal_id].length
    if count is None:
        count = length - start
    count = max(0, min(count, length - start))
    if count == 0:
        return np.empty(0, dtype=np.float64)
    return np.asarray(reader.fsr(signal_id, start, count)).ravel()


def summarize(path):
    """Return a structured summary of a JLS v2 file for diagnostics/asserts.

    :return: dict with ``sources`` (model/serial per non-global source) and
        ``signals`` (name/units/sample_rate/length/duration_s per data signal).
    """
    with open_reader(path) as reader:
        sources = {
            sid: {'model': s.model, 'serial_number': s.serial_number, 'name': s.name}
            for sid, s in reader.sources.items() if sid != 0
        }
        signals = {}
        for signal_id, sig in data_signals(reader).items():
            fs = float(sig.sample_rate)
            signals[signal_id] = {
                'name': sig.name,
                'units': sig.units,
                'sample_rate': fs,
                'length': int(sig.length),
                'duration_s': (sig.length / fs) if fs else 0.0,
            }
    return {'sources': sources, 'signals': signals}


def assert_recording(path, *, signal_names=None, min_duration_s=None,
                     finite=True, value_range=None, sample_check=4096):
    """Assert a JLS v2 recording/export is well-formed.

    :param signal_names: Iterable of signal names that must be present.
    :param min_duration_s: Minimum duration (samples / sample_rate) every data
        signal must meet.
    :param finite: When True, assert the (sampled) data contains no NaN/Inf.
    :param value_range: Optional ``(lo, hi)``; sampled data must lie within.
    :param sample_check: Max samples per signal to load for finite/range checks
        (keeps verification of multi-million-sample captures fast).
    :raises AssertionError: On any failed expectation.
    :return: The :func:`summarize` dict (handy for further assertions).
    """
    summary = summarize(path)
    present = {s['name'] for s in summary['signals'].values()}
    if signal_names is not None:
        missing = set(signal_names) - present
        assert not missing, f'{path}: missing signals {sorted(missing)} (have {sorted(present)})'

    with open_reader(path) as reader:
        for signal_id, sig in summarize_iter(reader):
            info = summary['signals'][signal_id]
            if min_duration_s is not None:
                assert info['duration_s'] + 1e-9 >= min_duration_s, \
                    f'{path}: signal {info["name"]} duration {info["duration_s"]:.3f}s ' \
                    f'< {min_duration_s}s'
            if finite or value_range is not None:
                n = info['length']
                count = min(n, sample_check)
                data = read_fsr(reader, signal_id, 0, count)
                if finite:
                    assert np.all(np.isfinite(data)), \
                        f'{path}: signal {info["name"]} has non-finite samples'
                if value_range is not None and data.size:
                    lo, hi = value_range
                    assert float(data.min()) >= lo and float(data.max()) <= hi, \
                        f'{path}: signal {info["name"]} range ' \
                        f'[{data.min():.4g}, {data.max():.4g}] outside [{lo}, {hi}]'
    return summary


def summarize_iter(reader):
    """Yield ``(signal_id, SignalDef)`` for data signals (helper for asserts)."""
    return list(data_signals(reader).items())


def count_annotations(path, signal_id=None, annotation_type=None):
    """Count annotations in a JLS v2 file.

    :param signal_id: Restrict to one signal; default counts across all
        signals that carry annotations (incl. the global signal 0).
    :param annotation_type: A :class:`pyjls.AnnotationType` to filter by
        (e.g. ``pyjls.AnnotationType.VMARKER`` for vertical time markers).
    :return: The matching annotation count.
    """
    want = None if annotation_type is None else int(annotation_type)
    total = [0]

    def _cb(timestamp, y, atype, group_id, data):
        if want is None or int(atype) == want:
            total[0] += 1
        return False  # continue iterating

    with open_reader(path) as reader:
        signal_ids = [signal_id] if signal_id is not None else list(reader.signals.keys())
        for sid in signal_ids:
            try:
                reader.annotations(sid, 0, _cb)
            except Exception:
                # signals without an annotation track raise; ignore them
                continue
    return total[0]


def assert_has_markers(path, n, *, dual=True):
    """Assert the export carries ``n`` vertical (time) markers.

    A "dual marker" pair is two ``VMARKER`` annotations, so a single dual
    marker => ``n == 2``.

    :param dual: Documentation hint only; ``n`` is the absolute marker count.
    """
    found = count_annotations(path, annotation_type=pyjls.AnnotationType.VMARKER)
    assert found == n, f'{path}: expected {n} vertical markers, found {found}'
    return found


def compare_subrange(reference_path, export_path, signal_name, *,
                     atol=1e-6, rtol=0.0, max_search=1_000_000):
    """Verify ``export`` is a contiguous sub-range of ``reference`` (round-trip).

    Used for the plan's "export to B, open B, verify correct": the exported
    signal must equal the corresponding slice of the source recording.  The
    export offset is discovered by matching the export's first samples within
    the reference.

    :param atol: Absolute tolerance for the sample comparison.
    :param rtol: Relative tolerance for the sample comparison.
    :param max_search: Max reference samples to scan when locating the offset.
    :raises AssertionError: If no aligned match is found.
    :return: The matched start offset (in samples) within the reference.
    """
    with open_reader(reference_path) as ref, open_reader(export_path) as exp:
        rsig = signal_by_name(ref, signal_name)
        esig = signal_by_name(exp, signal_name)
        assert rsig is not None, f'{reference_path}: signal {signal_name!r} not found'
        assert esig is not None, f'{export_path}: signal {signal_name!r} not found'
        assert esig.length > 0, f'{export_path}: signal {signal_name!r} is empty'

        exp_data = read_fsr(exp, esig.signal_id)
        probe_n = int(min(64, exp_data.size))
        probe = exp_data[:probe_n]

        scan = int(min(rsig.length, max_search))
        ref_head = read_fsr(ref, rsig.signal_id, 0, scan)
        offset = _find_offset(ref_head, probe, atol, rtol)
        assert offset is not None, \
            f'{export_path}: signal {signal_name!r} not found within first ' \
            f'{scan} samples of {reference_path}'

        ref_slice = read_fsr(ref, rsig.signal_id, offset, exp_data.size)
        assert ref_slice.size == exp_data.size, \
            f'{export_path}: export ({exp_data.size}) extends past reference at offset {offset}'
        assert np.allclose(ref_slice, exp_data, atol=atol, rtol=rtol), \
            f'{export_path}: signal {signal_name!r} samples differ from {reference_path}'
        return offset


def _find_offset(haystack, needle, atol, rtol):
    """Return the first index where ``needle`` aligns within ``haystack``."""
    n = needle.size
    if n == 0 or haystack.size < n:
        return None
    # Candidate offsets where the first sample matches, then verify the probe.
    first = needle[0]
    candidates = np.nonzero(np.isclose(haystack[:haystack.size - n + 1], first,
                                       atol=atol, rtol=rtol))[0]
    for off in candidates:
        if np.allclose(haystack[off:off + n], needle, atol=atol, rtol=rtol):
            return int(off)
    return None
