# Automated Joulescope UI Release Testing (HIL farm + release gating)

## Context

Today the Joulescope UI release test plan (`~/doc/ui_test_1_3_4.xlsx`, v1.3.4) is run **by
hand**. It has three tabs:

- **JS220** / **JS110** — the same ~40-step functional checklist, executed manually on each
  platform column (Windows 11 x64, macOS x64, macOS ARM64, Ubuntu LTS).
- **Release** — the build/publish/promote checklist.

Two things have changed since that plan was written:

1. **The build→publish path is already automated.** A tag push runs
   `pyjoulescope_ui/.github/workflows/packaging.yml`, which builds per-platform installers and runs
   `ci/publish.py` to upload to S3 (`download.joulescope.com`), updating `index_v2.json` and pointing
   the **alpha** channel at the new build. Promotion alpha→beta→stable is done by
   `ci/release_update.py <version> <maturity>` (the replacement for the legacy `js220_mfg publish`).
2. **The UI now exposes a control socket.** Launching `joulescope --tcp-server` starts a TCP server
   (`joulescope_ui/tcp_server/`) that bridges the UI's pubsub bus and the Qt widget tree to external
   clients, with a ready-made Python client (`joulescope_ui/tcp_client.py`).

**Goal of this work:** automate the JS220/JS110 functional checklist — and add **JS320** — by driving
the installed UI through the socket on a **multi-platform HIL farm** (one bench per OS, with real
devices attached), and **gate** the alpha→beta→stable promotion (plus a VirusTotal scan) on those
tests passing. All new code lives under `pyjoulescope_ui/ci/`.

### User decisions (already made)

- **Data source:** multi-platform **HIL farm** — real JS220/JS320 (JS110 where present) attached to
  one machine per OS. (The driver's emulated backend `joulescope_driver/src/emu.c` + `emulated.c` is a
  disabled, Windows-only stub — `#emu.c` in `src/CMakeLists.txt`, `// todo add device`,
  `// todo BACKEND_INIT(... emulation ...)` in `src/jsdrv.c` — so it is **not** used.)
- **Harness home:** everything in `pyjoulescope_ui/ci/` (a new `ci/uitest/` package).
- **Release gating:** **yes** — smoke-gate promotion + automate the VirusTotal scan.
- **Scope:** full, detailed plan for all milestones.

---

## Building blocks to reuse (do not reinvent)

| Need | Reuse | Path |
| --- | --- | --- |
| Drive UI externally | `Client` (query/publish/subscribe/enumerate/qt_inspect/qt_action/qt_screenshot) | `joulescope_ui/tcp_client.py` |
| Start server + creds | `--tcp-server` flag → `run(tcp_server=True)`; writes `server.json {token, port}` to `app_path` | `joulescope_ui/entry_points/ui.py:42`, `joulescope_ui/main.py:996-1010` |
| Wire protocol | frame + msg types (incl. `MSG_QT_*`) | `joulescope_ui/tcp_server/protocol.py` |
| Qt actions available | `click`, `key`, `set_property`, `get_property`, `inspect`, `screenshot` | `joulescope_ui/tcp_server/qt_inspector.py:234-302` |
| Discovery pattern | wildcard subscribe + view switch example | `examples/tcp_server/change_views.py` |
| Installer index + sha256 download | `software_update.py` (`_URL_BASE`, index parse, hash verify) | `joulescope_ui/software_update.py` |
| JLS verification | `pyjls.Reader` (sources, signals, samples, annotations) | `jls/pyjls/` |
| Publish / promote | `publish.py`, `release_update.py`, `_publish_common.py` (channels alpha/beta/stable) | `pyjoulescope_ui/ci/` |
| CI matrix + pytest hook | `packaging.yml` already runs `pytest --pyargs joulescope_ui` and `pytest ci/test_publish.py` | `.github/workflows/packaging.yml` |

### Key pubsub topics / actions the harness drives

- Device discovery: enumerate `registry_manager/capabilities/statistics_stream.source/list`
  (and `.../signal_stream.source/list`) — see `joulescope_ui/capabilities.py:166,176`.
- Per device `registry/<id>/...` where `<id>` ∈ `js220`, `js320`, `js110` (auto-numbered):
  `actions/!open`, `actions/!close`, `settings/state`, `settings/info`, `settings/signal_frequency`
  (`js220.py:144`), `events/statistics/!data`, `events/signals/{i,v,p,r}/!data`.
- App: `registry/app/settings/signal_stream_enable`, `.../signal_stream_record`,
  `.../statistics_stream_enable`, `registry/app/settings/mode`.
- Views/widgets: `registry/view/settings/active`; waveform plot `.../settings/plots[N]/signals`,
  y-axis `range_mode`/`range`/`scale`; marker actions (`add_single`/`add_dual`/`clear_all`) —
  `widgets/waveform/waveform_widget.py:144`.
- Export: `registry/ui/actions/!export_waveform` (`exporter.py:109`).
- About/version: `registry/help_html/actions/!show` = `'about'`; versions sourced from
  `about.py:16-19` (`ui_version`, `jsdrv_version`, `jls_version`).
- Config: `registry/ui/actions/!close` with `{'config_clear': True}` (`pubsub.py:1604`); config file
  `joulescope_ui_config.json` under the platform app dir.

---

## Architecture

```
pyjoulescope_ui/ci/
  uitest/
    __init__.py
    harness.py        # UiSession: launch installed app --tcp-server, connect Client, helpers, teardown
    discover.py       # server.json location per-OS; device enumeration -> Device objects
    installer.py      # per-OS download (reuse software_update) + silent install/uninstall + locate exe
    verify.py         # pyjls.Reader helpers: open & assert recording/export contents, round-trip compare
    stations.py       # load stations config; advertise capabilities (platform, attached devices)
    conftest.py       # pytest fixtures: ui_session, device (parametrized), tmp_capture, screenshot-on-fail
    stations.toml     # one entry per HIL bench: platform, host, devices[], display
    assets/
      evk1_10s_0_7_0.jls   # JLS v1 fixture (sourced)  -- see "Test assets"
      sample_v2.jls        # JLS v2 fixture (recorded once on a bench, checked in)
    test_basics.py        # exe starts, Help->About version
    test_multimeter.py    # multimeter values + statistics fields            [device]
    test_waveform.py      # display/scroll, y-axis range/scale, signals, markers [device]
    test_record_export.py # live record+export matrix @ full-rate & 10 kHz    [device]
    test_open_jls.py      # open v1/v2, zoom/pan, markers, export, reopen
    test_analysis.py      # USB Inrush / Histogram / CDF / Frequency / max-window
    test_preferences.py   # config persists across restart; clear config
    test_longterm.py      # 1 hr @ full & 10 kHz, 10 hr run                  [device][slow]
    test_harness_unit.py  # unit tests for verify.py/installer.py/discover.py (no UI, no HW)
  virustotal_scan.py  # submit installers to VirusTotal API, poll, fail on detections
  release_gate.py     # read test-result artifacts; allow/deny release_update promotion
```

```
GitHub Actions
  packaging.yml (tag push)            release_test.yml (after publish OR workflow_dispatch <version>)
   build -> publish alpha  ───────────►  matrix over self-hosted HIL runners (one per platform):
                                            installer.py: download alpha build, silent install
                                            run pytest ci/uitest -m "device or not device"
                                            upload junit xml + screenshots as artifacts
                                          gate job: release_gate.py + virustotal_scan.py
                                            on all-pass -> release_update.py <ver> beta (then stable)
```

The same pytest suite runs in two contexts: hardware-free tests (`-m "not device"`) also run inside
`packaging.yml`'s `build_sdist` job under `QT_QPA_PLATFORM=offscreen`; device tests (`-m device`) run
only on HIL benches that advertise the matching device.

---

## Milestone 0 — Foundations (`ci/uitest/` harness)

**Create** `ci/uitest/harness.py`:

- `class UiSession` (context manager). `__enter__`: spawn the app
  (`[<exe>] --tcp-server` for installed builds, or `python -m joulescope_ui ui --tcp-server` in dev),
  poll for `server.json` (path from `discover.py`), read `{token, port}`, open a `tcp_client.Client`,
  wait until `registry/app` is responsive (`query`). `__exit__`: publish
  `registry/ui/actions/!close` (optionally `{'config_clear': True}`), join process, delete `server.json`.
- High-level helpers wrapping the client: `set_view(name)`, `open_device(unique_id)`,
  `set_signal_frequency(dev, hz)`, `record_start/stop(path)`, `add_dual_markers(...)`,
  `export_waveform(path, ...)`, `screenshot(path='')`, `wait_for(topic, predicate, timeout)`.
- A clean-shutdown + force-kill fallback so a hung UI never wedges the bench.

**Create** `ci/uitest/discover.py`:

- `server_json_path()` — per-OS app dir: Windows `%LOCALAPPDATA%/joulescope`, macOS
  `~/Library/Application Support/joulescope`, Linux `~/.joulescope` (mirror `main.py` `app_path`;
  confirm the exact value at implementation time and centralize it).
- `enumerate_devices(client)` → list of `Device(unique_id, model, serial)` from the capability list
  topics; `Device.model` ∈ {JS220, JS320, JS110}.

**Create** `ci/uitest/verify.py` (reuses `pyjls.Reader`):

- `assert_recording(path, *, signals, min_duration_s, finite=True, ranges=None)` — open, check the
  expected sources/signals exist, sample count ≈ duration×fs, data finite and within broad windows.
- `assert_has_annotations(path, n_markers)` — confirm exported markers landed in the JLS.
- `compare(src, exp)` — round-trip: exported range matches the source samples it was cut from.

**Create** `ci/uitest/stations.py` + `stations.toml` — load the bench registry; each station advertises
`platform` and attached `devices` so tests skip/xfail when a device is absent
(reuses the HIL capability model: *advertise capabilities, don't assume*).

**Create** `ci/uitest/conftest.py` — pytest fixtures: `ui_session`, `device` (parametrized over the
station's advertised devices), `tmp_capture` (temp dir for A/B/C captures), and a
`pytest_runtest_makereport` hook that calls `UiSession.screenshot()` on failure and attaches it.

**Unit tests** (`test_harness_unit.py`, no UI/HW): exercise `verify.py` against the checked-in JLS
fixtures, `discover.py` path logic, and `installer.py` filename/URL resolution with a mocked index.
Follow the existing `joulescope_ui/tcp_server/test/test_integration.py` pattern (spin a `TcpServer`
on a bare `PubSub` for client-level tests).

**Verify:** `pytest ci/uitest/test_harness_unit.py` green; `UiSession` launches a dev UI locally and
`query('registry/app/...')` returns.

---

## Milestone 1 — Hardware-free smoke suite (runs on every platform, incl. CI runners)

These need no device, so they also run in `packaging.yml` under `QT_QPA_PLATFORM=offscreen`.

- `test_basics.py`: app starts (server.json appears, `registry/app` responds); **Help→About** —
  publish `registry/help_html/actions/!show='about'`, `qt_inspect` the dialog, assert it contains
  `ui_version` (== `joulescope_ui.__version__`, currently `1.5.1`), `jsdrv_version`, `jls_version`.
  *If dialog scraping proves brittle, add a small read-only `registry/app/actions/!version` query
  returning the same dict — one-file change in `about.py`/`app.py` — and assert on that instead.*
- `test_open_jls.py`: open the v1 and v2 fixtures (set `registry/app/settings/mode='file_viewer'` /
  MRU-load), zoom/pan via waveform actions, add dual markers, export to A, reopen A and
  `verify.compare`.
- `test_analysis.py`: over a dual-marker range on an opened file, invoke each range tool
  (`range_tools/usb_inrush.py`, `histogram.py`, `cdf.py`, `frequency.py`, max-window) and assert the
  result widget appears (`qt_inspect`) + screenshot. USB Inrush requires USBET — mark `xfail` where
  unavailable.
- `test_preferences.py`: set a preference, restart `UiSession`, assert retained; then
  `!close {'config_clear': True}`, restart, assert defaults restored.

**Verify:** `pytest ci/uitest -m "not device"` green locally (offscreen) and add the same invocation
to `build_sdist` in `packaging.yml`.

---

## Milestone 2 — Live device suite (HIL, parametrized per device)

Marked `@pytest.mark.device`; the `device` fixture parametrizes over JS220 / JS320 / JS110 present on
the bench. Each device row uses a per-device parameter table:

| Device | full-rate | reduced-rate | unique_id |
| --- | --- | --- | --- |
| JS220 | 1 MHz | 10 kHz | `js220` |
| JS110 | 2 MHz | 10 kHz | `js110` |
| JS320 | (confirm max) | 10 kHz | `js320` |

- `test_multimeter.py`: open device, multimeter view, `statistics_stream_enable=True`, subscribe
  `registry/<dev>/events/statistics/!data`; assert current/voltage/power/energy/charge present and the
  mean/stddev/min/max/p2p fields are finite and within a broad expected window (functional, **not**
  calibrated-accuracy — accuracy is PCTS/FTS's job).
- `test_waveform.py`: oscilloscope view; assert live signal data flows; exercise y-axis
  range auto/manual and scale linear/log; add/remove signals (assert `plots[N].signals` length);
  add/remove/move single and dual markers (assert marker state); scroll/pan.
- `test_record_export.py`: the spreadsheet's record/export matrix, parametrized over
  (device, {full-rate, 10 kHz}): set `signal_frequency`; record to **A** (10 s); stop; add dual
  markers; export to **B**; open **A** and verify; open **B** and verify; add markers to opened file,
  export to **C**, verify. Uses `verify.assert_recording` / `assert_has_annotations` / `compare`.
- Live analysis (USB Inrush / Histogram / CDF / Frequency / max-window) over a live dual-marker range.

**Known-DUT fixture (hardware, per bench):** each Joulescope must measure a **stable, known load** so
recordings contain real non-zero signal — e.g. a fixed resistor / programmable load giving steady
current in a known range, and GPO0/1 looped to a GPI for digital-signal coverage. Tests assert
values are finite, stable (low variance), and within a broad window — they verify **function**, not
calibration. (The existing ADP3450 HIL wiring is for firmware bring-up; the UI bench needs only a
simple deterministic load — to be wired by the bench owner.)

**Verify:** `pytest ci/uitest -m device` green on a JS220 bench, then JS320, then JS110.

---

## Milestone 3 — HIL farm orchestration

- Stand up one **self-hosted GitHub Actions runner per platform** (Windows 11 x64, macOS ARM64,
  macOS x64 if retained, Ubuntu LTS), labeled by platform **and** advertised device capability
  (e.g. `[self-hosted, windows, js220, js320]`), matching `stations.toml`.
- **Create** `ci/uitest/installer.py`: resolve the alpha installer for `(platform, arch)` from
  `index_v2.json` (reuse `software_update.py` URL/hash logic), download + sha256-verify, then
  silent-install:
  - Windows (Inno Setup): `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`.
  - macOS: mount `.dmg`, copy `.app`, `xattr -dr com.apple.quarantine`.
  - Ubuntu: extract `.tar.gz`, locate the binary.
  Plus `uninstall()` / `locate_executable()` and a CLI entry for the workflow.
- **Create** `.github/workflows/release_test.yml`: triggered after publish (or `workflow_dispatch`
  with a version); matrix over the self-hosted runners; steps = install alpha build →
  `pytest ci/uitest` (device + non-device, per advertised caps) → upload JUnit XML + failure
  screenshots as artifacts.

**Verify:** dispatch `release_test.yml` against the current alpha; confirm each bench installs, runs,
and uploads artifacts.

---

## Milestone 4 — Release gating + VirusTotal

- **Create** `ci/virustotal_scan.py`: submit each installer (esp. `joulescope.exe`) to the VirusTotal
  API (`VT_API_KEY` secret), poll, fail on detections — automating the spreadsheet's manual scan step.
- **Create** `ci/release_gate.py`: read the `release_test.yml` JUnit artifacts (+ VirusTotal result);
  pass only if every required (platform, device) cell is green. On pass, drive
  `ci/release_update.py <version> beta` (then `stable` on a second approval).
- Wire a `promote` job (or `workflow_dispatch`) that runs `release_gate.py` before
  `release_update.py`, so promotion is **blocked** unless the farm + VirusTotal passed. Keep a manual
  override for emergencies.

**Verify:** force one failing cell → `release_gate.py` blocks promotion; all-green → promotes alpha→beta.

---

## Milestone 5 — Long-term tests (nightly, not per-release)

- `test_longterm.py` (`@pytest.mark.device @pytest.mark.slow`): ~1 hr capture at full rate & open;
  ~1 hr at 10 kHz & open; 10 hr run. Scheduled nightly/weekly on the farm, not in the release gate.

**Verify:** scheduled workflow runs to completion and the long capture opens + verifies.

---

## Test assets

- `evk1_10s_0_7_0.jls` (JLS **v1**) is referenced by the plan but **not** in the repo (only
  `joulescope_ui/test/anno1.anno.jls` exists). Source the canonical file and commit it under
  `ci/uitest/assets/` (or fetch from S3 in CI if size is a concern).
- `sample_v2.jls` (JLS **v2**): record once on a bench during M2 and commit a short clip as the
  open/verify fixture.

## Status (implemented so far)

Done and validated live on a JS220 + JS320 bench:
- M0 harness (`ci/uitest/`): `UiSession`, `discover`, `verify`, `installer`,
  `stations`, `qt`, `assets`, `jls_fixtures`, `conftest`.
- Suites: `test_basics`, `test_preferences`, `test_multimeter` (device),
  `test_open_jls`, `test_record_export` (device record→reopen), `test_waveform`
  (display), plus the Qt-free unit tests.
- Socket fixes found while building the tests (all in `tcp_server/bridge.py`,
  with regression tests): Qt response id correlation; nested-numpy
  serialization. Harness suppresses the first-run "Getting Started" dialog.

### Analysis tools — DONE (added a non-interactive UI affordance)

`WaveformWidget.on_action_range_tool` (`registry/<wf>/actions/!range_tool`) runs
a named range tool over an explicit `x_range` + `signals` list, building the
`!run` value the way the Analysis menu does. `_signals_get()` is empty headless
(it depends on the live render/data cycle), so the action accepts an explicit
`signals` list (`source.device.quantity`); range tools request data from the
buffer source directly, so that works. The harness `run_analysis` helper drives
it, accepts the tool's config dialog (Return), and waits for the result widget.
Covered by `test_analysis` (Histogram / CDF / Frequency create result widgets;
MaxWindow runs). USB Inrush needs the external USBET lib and is out of scope.

### Still blocked: export-with-markers, marker/y-axis assertions

- **Export** is blocked deeper than the save dialog. A non-interactive entry
  point is straightforward (the exporter already runs directly when
  `value['kwargs']['path']` is set, mirroring `ExporterDialog._on_finished`), but
  the export then **pull-requests** sample data from the file buffer source via
  `RangeToolBase.request(...)`, and that request **times out** against a
  `JlsSource` in automation — reproduced both offscreen and on a real display
  (`TimeoutError: request timed out for JlsSource:...`). The file opens and
  displays (summary path works), but sample-level pull requests do not complete.
  Fixing this needs the file-buffer-source request pipeline to serve data in the
  socket-driven flow; until then export-with-markers cannot be verified, so the
  speculative affordance was reverted. Recording coverage is provided instead by
  `test_record_export` (push-based streaming + file-level pyjls verification).
  NOTE: the same pull-request path underlies the analysis tools; `test_analysis`
  asserts the result widget is created (the tool launches end-to-end) but does
  not assert on computed values, for the same reason.
- **Markers** are added with `!x_markers ['add_dual', ...]`, but the resulting
  marker set is internal state with no queryable readback; verify them via the
  exported JLS annotations once export is automatable.

## Risks / open items

- **app_path for `server.json`**: confirm the exact per-OS directory `main.py` uses and centralize it
  in `discover.py` (don't hard-code three guesses).
- **JS320 sample rates** and any JS320-only signals (dual current ranges, built-in UART) — confirm and
  extend the per-device table; reuse `devices/jsdrv/js320.py`.
- **JS110 deprecation** (per project notes) — keep JS110 tests but allow benches to omit the device.
- **Marker/export action payloads** — pin exact shapes from `waveform_widget.py` and `exporter.py`
  when implementing M1/M2.
- **macOS notarization/Gatekeeper** on silent install — handle quarantine; may need a one-time
  bench trust step.

## Incremental delivery (per CLAUDE.md: small, testable steps)

Land in this order, each as its own reviewed change with tests: **M0** (harness + unit tests) →
**M1** (hardware-free suite, wired into `build_sdist`) → **M2** (device suite on one JS220 bench) →
**M3** (installer + one self-hosted runner) → **M4** (gate + VirusTotal) → **M5** (long-term).
Do not bundle milestones; each milestone touches a bounded set of files and ships green tests.
