# Expand UI release-test coverage (2026-10)

## Goal

Automate every row of the JS320 tab of the manual release test plan
(`ui_test_1_7_3.xlsx`) on the joulescope_ci farm, then gate promotion on the
results.  The aim is a release that needs no manual test pass.  This plan
continues [`ui_release_test_automation.md`](ui_release_test_automation.md)
(M0-M2 done; M4 and M5 open) and builds on the farm described in
[`ui_hil_farm_requirements.md`](ui_hil_farm_requirements.md).

The device tests are parametrized by model, so the JS220 and JS110 tabs gain
the same coverage wherever those models are attached.

## CI station setup (2026-10-26)

Every Joulescope sits behind a USB Insight Hub port.  All of them are
production devices running production firmware, so no station has a firmware
limitation.

| Station | OS / arch | Port 1 | Port 2 | Port 3 |
| --- | --- | --- | --- | --- |
| ci_linux | Linux x86_64 | JS110-000552 | JS220-001062 | JS320-E8VA |
| ci_win | Windows 11 x86_64 | JS110-000494 | JS220-002557 | JS320-915C |
| ci_win_arm | Windows 11 ARM64 | - | JS220-001096 | JS320-S3C8 |
| ci_mac | macOS arm64 | JS110-000578 | JS220-001724 | JS320-Y0VA |
| ci_linux_arm | Linux arm64 (Pi) | - | JS220-001707 | JS320-X2VJ |

What the farm (joulescope_ci 0.3.15) gives a UI test:

- **Device list.**  `JS_UITEST_DEVICES` comes from the station's DUTs.  A listed
  model that is missing fails after 10 s; an unlisted model is skipped.  Every
  station has a JS320.
- **Cold devices.**  Each job closes any process holding a Joulescope, then
  power-cycles all hub ports and waits for every device to return to USB.
  Tests start with default device settings and no leftover state.
- **Port current.**  The runner reads each port's current about once a second
  and posts a `dut_current` event to the job (`/api/jobs/<id>/events`).
  A JS320 draws about 40 mA idle and 290-325 mA open.  Optional per-device
  `{min_mA, max_mA}` limits in `stations.yaml` fail the job when exceeded.
- **Results.**  `/api/results/<job>/files` lists `junit.xml` and `pytest.log`.
  A `ui_release` run takes about 4 minutes with `-m "not slow"`.

What a UI test must not do or cannot use yet:

- **Control the hub.**  The runner holds the hub's serial port for the whole
  job.  Ignore the `JCI_UIH_*` variables.  Hotplug, disconnect and power-loss
  tests need a runner hook that does not exist yet (see Out of scope).
- **Rely on a fixture.**  There is no GPO-to-GPI loopback, load, switchable
  target or signal source.  Tests can check function, data flow and round
  trips, but not that a measured value is correct.
- **Assume exclusive access.**  The UI opens every connected Joulescope.

## Coverage today (JS320 tab)

Two limits apply to every row:

1. **The installed app is not tested.**  The `ui` worker pip-installs the
   sdist into `~/venv/ui`.  `ci/uitest/installer.py` and
   `JS_UITEST_EXECUTABLE` exist but are not used.
2. **Most waveform, analysis and export tests use a generated 1 kHz
   single-signal JLS** (`jls_fixtures.write_fsr_v2`), not JS320 data.  Only
   the multimeter and record tests use the live device.

| Row | Today | Stage |
| --- | --- | --- |
| Executable starts | Partial: sdist, not the installer | 6 |
| (not on the tab) Device firmware update | Not covered | 0 |
| Help -> About version | Covered | - |
| Multimeter: current, voltage, power, energy | Partial: data only | 3 |
| Multimeter: mean, stddev, min, max, p2p | Partial: data only | 3 |
| Multimeter: charge C, Ah, s | Partial: unit name only | 3 |
| Waveform displays & scrolls | Partial: generated file | 2 |
| y-axis range manual/auto | Covered (generated file) | 2 |
| y-axis scale linear/log | Covered (generated file) | 2 |
| Add & remove signals | Not covered (see note) | 2 |
| Add, remove, move single marker | Covered (generated file) | - |
| Add, remove, move dual markers | Partial: add only | 2 |
| Record/export at 1 MHz (all legs) | Partial: record + rate only | 1 |
| Record/export at 10 kHz (all legs) | Partial: no live export, no C, no compare | 1 |
| View -> Oscilloscope / View -> File | Not covered | 1 |
| Open JLS v1 | Partial: opens only | 2 |
| v1: zoom/pan, dual markers, export, reopen | Not covered | 2 |
| Analysis: USB Inrush | Not covered (needs USBET) | Deferred |
| Analysis: Histogram, CDF, Frequency | Partial: widget appears, file data | 4 |
| Analysis: max window | Partial: does not raise | 4 |
| Preferences from previous release | Partial: same version only | 5 |
| File -> Clear config & Exit | Partial: action, not menu | 5 |
| Review CHANGELOG and test all changes | Not covered (manual) | 9 |
| Capture ~1 h at full rate / 10 kHz & open | Not covered | 7 |
| Run for 10 hours | Not covered | 7 |

Note: `test_waveform.test_add_remove_signals` clicks `trace_2`, a
`WaveformSourceWidget` source-trace toggle.  It does not add or remove a
signal, so the row is not covered.

## Status

| Stage | Status |
| --- | --- |
| 0 - Device firmware first | Done, local HW (no-op path); update path needs a stale bench |
| 1 - Record and export | Done, local HW; found and fixed 3 bugs (see Stage 1) |
| 2 - Waveform rows | Done, local HW; found and fixed a v1 export bug |
| 3 - Multimeter widget | Done, local HW; found and fixed a repaint bug |
| 4 - Analysis on live data | Done, local HW; found and fixed 4 bugs, 2 open |
| 5 - Preferences | Done, local |
| 6 - Installed app | Done, local (1.7.4 installer); workflow not yet run |
| 7 - Long-term tests | Done (shortened run on HW); run on demand from the jci Jobs page |
| 8 - Farm validation | jci 0.3.16 deployed 2026-10-27; runs when this branch reaches main |
| 9 - Release gate | Not started: needs decisions (see Stage 9) |

## Approach

- Work on a feature branch (`feature/expand_test_coverage`).  Each stage
  builds, passes `pytest ci/uitest -m "not device"` offscreen plus the unit
  tests, and is reviewable on its own.
- Device tests are validated with a farm run from the dashboard rerun button
  (a GitHub job rerun is ignored as a duplicate).  The full five-station
  validation is its own stage (Stage 8).
- Prefer the existing harness (`ci/uitest/harness.py`) and `verify.py`
  helpers.  Where a row needs a non-interactive UI hook, add it the way
  `!range_tool` and `!export` were added: a small action on the owning widget,
  with a unit test.

## Stage 0 - Determinism and external checks

Small fixes that make later stages reliable.

- **Update device firmware first, through the UI.**  At startup
  `main._device_update_check()` (`main.py:612`) opens `DeviceUpdateDialog`
  when a JS220 or JS320 runs firmware older than the firmware bundled with
  the UI.  The dialog becomes the active window and breaks `qt_inspect`
  lookups (the 1.7.2 `trace_2` failure on ci_win).  A new UI release can
  bundle newer production firmware than the benches carry, so this recurs.
  Instead of turning the check off, the first test updates the firmware:
  - New `ci/uitest/test_device_firmware.py`, marked `device` and a new
    `firmware` marker, parametrized by model.  A `pytest_collection_modifyitems`
    hook in `conftest.py` moves `firmware` tests to the front, so they run
    before any other test whatever the file order.
  - For each JS220 and JS320, read `registry/<dev>/settings/update_available`
    (`js320.py:876`; a `{name: (now, available)}` map) and check it with
    `device_update.is_update_available()`.  If no update is needed, the test
    passes and does nothing.
  - If an update is needed, drive the real dialog: wait for
    `DeviceUpdateDialog`, click OK, and wait for its status to reach
    `complete` (allow several minutes; a JS320 update includes the FPGA).
    Then wait for the device to return to USB, and check that
    `update_available` now reports `now == available` and the dialog closed.
    This also tests the UI's firmware update path, which has no test today.
  - JS110 has no UI firmware update (`device_update.py` handles JS220 and
    JS320 only), so its case is skipped.
  - In `UiSession.start()`, if a `DeviceUpdateDialog` is still showing (the
    firmware test failed or was deselected), fail the test with a clear
    "device firmware out of date" error instead of a later "widget not found".
- **Port-current limits.**  Set `max_mA` per model in the coordinator's
  `stations.yaml` as an over-current guard.  A whole-job `min_mA` cannot
  work, since devices idle at about 40 mA between tests.

ci_linux_arm already runs the full suite, including all six rendered tests:
its `ui_release` run on 8f3fe8d (2026-10-26) passed 103 of 103 with no skips.

Verify: unit tests for the ordering hook and the `update_available` check.
On the farm: one run where a bench is behind the bundled firmware (it updates
and the rest of the suite passes) and one where none is (the test does
nothing).

## Stage 1 - Record and export, as the manual plan does it

Rewrite `test_record_export.py` to follow the plan's legs, parametrized over
`(device, rate)` with rate in {full rate, 10 kHz}.  For the JS320 the full rate
is 1 MHz.

1. Select View -> Oscilloscope (`registry/view/settings/active`) and set the
   signal frequency.
2. Record A for 10 s (the plan's duration, up from 2 s), then stop.
3. In the **live** view, add dual markers and export B.  Today B is exported
   from reopened A after streaming stops.
4. Select View -> File, open A, and `verify.assert_recording`.
5. Open B and `verify.compare_subrange(A, B, ...)` for current, voltage and
   power.  The helper exists but no test calls it yet.
6. In the opened file's waveform, add dual markers and export C.  Open C and
   compare it with A.  Check the markers in the `.anno.jls` sidecars of B and C.

**Findings (2026-10-26, local JS110 + JS220 + JS320):**

- The exporter's fixed 5 s `request()` timeouts were not the problem: export
  from both the live view and a file works at 1 MHz.  The old test's 10 kHz
  limit came from waiting on file-size stability, which declared an export
  done between signals.  `UiSession.export_range` now waits for the
  exporter's own completion (it adds the path to the recent-files list).
- **Fixed, joulescope_driver 2.5.5**: after a sample rate decrease while
  streaming (1 MHz -> 10 kHz), the stream buffer dropped every new sample
  until streaming restarted, so the live view froze and a live export asked
  for samples the buffer did not hold.  The UI now requires 2.5.5.
- **Fixed, UI**: `RangeTool.request()` continued a partial *samples* answer to
  a summary request (`end` and `length=1`) with a negative length, got a
  summary back, and failed to concatenate 1-D and 2-D data.
- **Fixed, harness**: `verify.compare_subrange` aligned the export by
  matching sample values with `atol=1e-6`.  A quiet (no-load) current of about
  0.1 uA matches anywhere, so it aligned at the wrong place.  It now aligns by
  UTC and compares exactly.
- **Accepted, JS110**: an export from the live buffer is bit-exact, but its
  UTC disagrees with recording A by about 2 ms (3882 samples at 2 MHz), a
  known JS110 limitation.  JS220 and JS320 agree within 1 sample.  The test
  allows 5 ms for JS110.
- **Fixed, UI**: the driver sizes the buffer for the sample rate when
  streaming starts, so starting at 10 kHz and switching to 1 MHz left a
  0.13 s buffer.  The driver stays as is (a full redistribution is the only
  general fix); the UI's `Device._signal_frequency_request` now stops
  streaming, sets the rate and restores streaming (JS110, JS220, JS320).

Port current adds an external check here: a JS320 that is recording should
draw 290 mA or more for the 10 s window.  Record test timestamps in the JUnit
properties so Stage 9 can match them with the `dut_current` events.

Not done yet: JUnit timestamps for matching `dut_current` events (Stage 9).

Verify: local run green on JS110, JS220 and JS320 at both rates
(2026-10-26); farm run green for JS320 at both rates on all five stations.

## Stage 2 - Waveform rows on live and v1 data

- **Add & remove signals.**  Drive the real control (the per-plot signal menu,
  for example removing and then restoring the voltage plot) and check
  `plots[N].enabled` or the rendered plot count.  Rename the existing
  `trace_2` test to say what it tests (the source-trace toggle) and keep it.
- **Dual markers: move and remove.**  Extend `test_waveform_interactive.py`
  using `x_markers_info()`: drag each line of a dual marker and remove the
  pair through its context menu.
- **Live display and scroll on JS320.**  Add a `rendered_waveform` variant
  that uses the live device instead of a generated file.  Check that
  `x_range` advances while streaming, then pause and pan.  Pause streaming and
  clear `pin_left`/`pin_right` before driving the live waveform.
- **JLS v1.**  On `js110_evk1_10s_0_7_0.jls`: zoom in and out, pan, add dual
  markers, export A, reopen A, and `compare_subrange` against the source.
- Run the existing y-axis range and scale tests against the live device too.

**Done (2026-10-26):** `test_add_remove_signals` clicks the control bar's
`signal_button_v` (buttons now have unique names) and checks the plot's
`enabled` state; the old `trace_2` test is `test_source_trace_toggle`.
`test_dual_marker_move` / `_remove`, `test_live_display_and_scroll` and
`test_live_y_axis_menus` (new `rendered_live_waveform` fixture), and
`test_jls_v1_zoom_pan_export` (`compare_subrange` reads v1 references).

**Fixed, UI:** exporting a JLS v1 file's current range or GPI signals failed
with "Data type mismatch uint8 != float32": `JlsV1` reported every response
as `f32`.

Verify: rendered tests run (not skip) on all five stations.

## Stage 3 - Multimeter widget

Today the test reads the statistics data, not what the Multimeter view shows.

- Select the Multimeter view and inspect the `value_widget` fields
  (`widgets/value/value_widget.py`).  Check that current, voltage, power,
  charge and energy appear with mean, stddev, min, max and p2p, and that each
  shown value matches the statistics sample within display rounding.
- Switch the charge units between C and Ah and the energy units between J and
  Wh, using the widget's `units` setting through its context menu.  Check that
  the shown units change and that the values convert correctly.
- Check that the accumulation time (`accumulate_duration`, shown in s)
  increases between two samples.

**Done (2026-10-26):** `MultimeterWidget.displayed_text()` (test-support)
returns the painted strings.  `test_multimeter_widget_displays_statistics`
holds statistics and checks every field against the statistics sample the
widget shows, within one displayed digit.  `test_multimeter_units_and_duration`
switches `units` between `Xh` and `SI` and checks the accumulation time.
The units setting is changed through pubsub, not the settings dialog.

**Fixed, UI:** changing a Multimeter or Value display setting (units,
precision, divisor, sign, fields, titles) while statistics were held did not
repaint, so the widget kept showing the old units until the next sample.

Verify: farm run green for every attached model.

## Stage 4 - Analysis on live data, with computed values

- Run Histogram, CDF, Frequency and Max window over a dual-marker range of a
  JS320 recording (from Stage 1), not the generated file.
- **Check the results.**  Add a read-only way to get each tool's result data
  (for example the data the result widget already holds, such as
  `HistogramRangeToolWidget.data`).  Compare it with the same computation done
  in numpy on samples read with pyjls.  Max window must report its value
  instead of only "does not raise".
- **USB Inrush** is deferred (decision 2026-10-26).  It needs the external
  USBET library, and the row stays manual for now.

There is no known signal source, so these checks show the tool matches its
input data, not that the measurement is correct.

**Done (2026-10-26):** `test_analysis_on_recording` records 3 s at 10 kHz,
runs each tool over 30-70% of the opened recording, reads the result widget's
`data` setting, and compares with numpy on the same samples read with pyjls:
histogram and CDF within 3 samples, PSD within 0.1% (a numpy Welch reference;
scipy is not installed on the benches), and the Max window markers within 2
samples of the numpy maximum.  The tool's UTC-to-sample conversion can differ
by a sample, so each check accepts offsets of -2..2.

**Fixed, UI:**

- Max window never recorded a better window (`m = max_v` instead of
  `max_v = m`), so it always marked the start of the range.  It is now a
  vectorized moving sum (`max_window_index`), also fast for long ranges.
- The CDF result's `signal_name` was `signal[1]`, the second character of
  the signal id (a leftover from tuple signal ids).
- `tcp_client.Client.query` did not decode numpy arrays, and the client
  decoder did not recurse into dicts and lists.  A query response over 64 KiB
  overflowed the uint16 header; it now moves to the payload, as Qt responses
  already did.
- `qt_inspector` resolved paths only in the active window.  A floating range
  tool result window became the active window on a real display, so the main
  window's widgets were "not found".  Paths now fall back to the other
  top-level windows.

**Fixed, UI (2026-10-27):** `FrequencyRangeTool` plotted `20 * log10` of a
power and doubled the DC and Nyquist bins; it now plots the PSD in dB
(`10 * log10`).  Histogram, CDF and Frequency computed progress from absolute
sample ids, so the bar jumped to complete.

## Stage 5 - Preferences

- **Previous release's config.**  Commit a `joulescope_ui_config.json` saved by
  the previous release (and the one before it) under `ci/uitest/assets/`.  On
  each release, add the new one: it becomes the next release's fixture.  Start
  the UI with it and check that it starts cleanly, the preferences survive, and
  it was not reset to defaults.
- **File -> Clear config & Exit.**  Trigger it through the File menu
  (`menu_invoke`) instead of the `!close {config_clear}` action, then check the
  config file is gone and the next start uses defaults.

**Done (2026-10-27):** each GitHub Release carries a
`joulescope_ui_config.json` saved by that release with non-default units,
active view and Multimeter precision: `build_sdist` runs `config_fixtures.py`
and `publish` attaches it.  The test downloads the previous release's
config (the version from `index_v2.json`).  1.7.4 needs a one-time
backfill, generated from its tag.
`test_previous_release_config` checks those preferences survive; a truncated
config fails it.  `test_clear_config_resets_to_defaults` now uses
File -> Config -> Clear and exit and clicks Yes, through the new
`menubar_invoke` socket action (works with the native macOS menu bar) and
`click` by button text.

## Stage 6 - Test the installed app

- In the joulescope_ci `ui` worker, install the build under test with
  `ci/uitest/installer.py` and set `JS_UITEST_EXECUTABLE`.  Keep the sdist mode
  for branch pushes that have no published installer.
- Decide which build a tag push tests.  The tag build publishes to the alpha
  channel, so the worker must wait for that publish (or fetch the GitHub
  release asset) and check that the installed version matches the tag.
- **ci_linux_arm stays on the sdist** (decision 2026-10-26): it keeps
  pip-installing the UI into `~/venv/ui`.  There is no aarch64 Linux
  installer to test: `installer.platform_key()` maps aarch64 Linux to
  `ubuntu` (an x86_64 tarball), and aarch64 builds exist only as a Flatpak.
  The worker must therefore pick sdist mode on linux-arm64 even for a tag,
  and `platform_key()` should raise on aarch64 Linux instead of returning the
  x86_64 key.
- `test_executable_starts` then covers the real row on every platform.

**Done (2026-10-27):**

- joulescope_ci 0.3.16 (`d541141`, local) passes the job's build kind to
  the suite as `JS_UITEST_BUILD_KIND`.
- With `release`, `conftest._release_executable()` installs the published
  build of `joulescope_ui.__version__` (`installer.install_release`, polling
  `index_v2.json` up to 10 min) and every UI session launches it.  arm64
  Linux returns to the sdist (`platform_key()` now raises there).
- `packaging.yml` pushes the suite through the reusable
  `push_ui_suite.yml`: main after `build_sdist` (dev), release tags after
  `publish` (release), so the installer exists when the benches run.
- `locate_executable()` now finds the PyInstaller `joulescope_launcher`
  (macOS and Linux); it looked only for `joulescope`.
- `test_about_shows_versions` checks only the UI version for an installed
  app, which bundles its own driver and JLS versions.

Checked locally: the published 1.7.4 Ubuntu build installs and passes the
basics and preferences tests (except tests that need 1.7.5 features).  Not
checked: the workflow (YAML parses; needs a GitHub run), and the Windows and
macOS installs on the benches (Stage 8).

## Stage 7 - Long-term tests (M5)

- `ci/uitest/test_longterm.py`, marked `device` and `slow`: record about 1 h
  at full rate and open it; record about 1 h at 10 kHz and open it; run for
  10 h.  Verify with `assert_recording` (duration, sample count, no gaps) and
  open the file in the UI.
- Add a scheduled joulescope_ci suite (for example `ui_longterm`, markers
  `slow`), nightly or weekly, outside the release gate.  If the coordinator
  has no schedule trigger yet, add one there.
- Use the `dut_current` events as an outside check that the device streamed
  for the whole run.  A drop to idle current marks a stall even when the UI
  still looks normal.
- Watch disk use: a 1 h capture at 1 MHz is large.  Delete captures after
  they verify.

**Done (2026-10-27):** `test_longterm.py` (`device`, `slow`):
`test_long_capture` (full rate and 10 kHz) checks free disk first, checks
each minute that statistics arrive and the file grows, then verifies
duration, no missing samples (`verify.assert_no_gaps` scans for NaN, since
JLS summaries skip NaN) and opens the file.  `test_long_run` streams at full
rate and fails if UI memory grows more than 1 GiB (`rss_growth_mb` JUnit
property).  `JS_UITEST_CAPTURE_S` / `JS_UITEST_RUN_S` shorten them; a 90 s /
180 s run passed on the local JS320 (2 MB growth).

The long-term tests run with every connected Joulescope streaming at once
(decision 2026-10-27): the 10 h run is the live waveform widget, checked
each minute for statistics from every device and for repainting.  They run
on demand: the joulescope_ci Jobs page Run button with the `ui_longterm`
suite (worker `ui_longterm`, markers `slow`) on the newest cached UI build,
about 12 h per station.  A 1 h full-rate capture needs about 45 GB free per
JS220/JS320; the test fails up front without it.

## Stage 8 - Farm validation

Run the full `ui_release` suite on all five stations from a release-candidate
build, after Stages 0-7.  Every JS320 cell must pass with no skips caused by a
missing display.  Repeat enough times to measure the flake rate, and fix
flaky tests before the gate depends on them.

## Stage 9 - Release gate and VirusTotal (M4)

As in `ui_release_test_automation.md` M4: `ci/virustotal_scan.py` and
`ci/release_gate.py`.  The gate reads the joulescope_ci results
(`/api/results/<job>/files`) and passes only when every (station, model) cell
is green.  A skipped test counts as a failure unless it is on an explicit
allow-list (for example the JS110 case of the firmware test).  The gate
reports ci_linux_arm as sdist-tested and lists USB Inrush as manual.  On
pass it runs `ci/release_update.py <version> beta`; `stable` needs a second
approval.  Keep a manual override.

**Decisions (2026-10-27):** VirusTotal stays a manual upload: its personal
API key is not for business workflows and it publishes no pricing; OPSWAT
MetaDefender Cloud's commercial API is quote-only.  A free, automatable
partial check is Microsoft Defender (`MpCmdRun -Scan -ScanType 3 -File`) on
ci_win and ci_win_arm, against the installer the release run downloads.
Still open for the gate: the coordinator is LAN-only, so it runs on a LAN
machine, and joulescope_ci needs a JSON job listing (only `/api/jobs/<id>`
exists) to find a commit's `ui_release` jobs.

**CHANGELOG review** stays a human step.  To make it checkable, require each
CHANGELOG entry to name the test that covers it, or to say "manual".  The gate
then lists the manual entries for sign-off.

## Out of scope / blocked

- **Hotplug, USB disconnect, power loss.**  These need a runner-provided hub
  hook, because tests may not open the hub.  Not on the JS320 tab, but the
  past reconnect bugs (Linux resume, USB suspend) make these worth doing next.
- **Known-signal checks.**  These need a fixture (load, signal source or
  GPO-to-GPI loopback) on each station; see joulescope_ci
  `doc/plans/flexible_stations.md`.
- **Exclusive device access.**  The UI opens every connected Joulescope.  A
  future test that needs one device to itself must close the others first.
