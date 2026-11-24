<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# Range tools fail on JLS v1 files

Status: found 2026-11-24 by the display audit.  Not fixed.

## Symptom

Open the uitest asset `js110_evk1_10s_0_7_0.jls`, a JS110 recording in the
JLS v1 format.  Add dual markers on the Waveform and run Histogram, CDF,
or Frequency.  Each shows "Range tool failed":

- Histogram and CDF: `IndexError: too many indices for array: array is
  1-dimensional, but 2 were indexed` in `calculate_histogram()`
  (`joulescope_ui/range_tools/plugin_helpers.py`), at
  `d['data'][0, :]`.
- Frequency: `ValueError: invalid fft_length 0`.

It reproduces on `origin/main` at 16099f7, before the 2026-11 translation
work, for marker ranges of 10 % and 40 % of the file.

## Likely cause

`calculate_histogram()` requests one summary point over the marker range
(`time_type='utc'`, `length=1`) and expects a `(1, 4)` summary array.
`JlsV1._req()` (`joulescope_ui/jls_v1.py`) returns a summary only when
`length <= interval // 2`.  Otherwise it returns 1-D samples.  So the UTC
range converts to an interval of 0 or 1 samples for this file.  That
points at the v1 UTC-to-sample time map, which the Frequency tool's
zero-length FFT also suggests.

## Plan

1. Add a unit test that opens the asset with `JlsV1` and requests the
   UTC range of the middle 10 % with `length=1`.  Assert a `(1, 4)`
   summary.
2. Fix the time map, or the request, so that the interval is correct.
3. Make `calculate_histogram()` and the Frequency tool report a clear error
   when they get samples instead of a summary, rather than an IndexError.
4. Add a hardware-free uitest that runs each range tool on the v1 asset.
   The current `test_analysis` only covers JLS v2 recordings from a device.
