# HIL Farm — capability requirements (M3) — ✅ COMPLETE

## Purpose

The Joulescope automated release tests (`pyjoulescope_ui/ci/uitest`, milestones
M1–M2, complete) drive the installed UI through its `--tcp-server` socket and
need to run **per platform on real hardware**.  That execution substrate — a
fleet of self-hosted runners with attached instruments and devices — is being
built as a **separate, shared HIL farm** because it serves more than the UI
(firmware HIL, PCTS, FTS, gateware bring-up).

This document specifies what that shared farm must provide so the UI suite (and
peers) can run on it.  It is written for the team/agent implementing the farm.
The UI side is already farm-ready: it ships `ci/uitest/installer.py` (download +
silent-install a published build) and a pytest suite gated by markers and
`JS_UITEST_*` env vars (see `pyjoulescope_ui/ci/uitest/README.md`).  Station
configuration lives in `joulescope_ci` (coordinator `stations.yaml`); the UI
suite takes only a `JS_UITEST_DEVICES` device expectation.

## Status (2026-10-27): complete

The farm is `joulescope_ci`.  It runs the UI suite as its `ui_release` suite
on five stations: on every main build (the sdist), and on every release tag
(the published installer).  UI 1.7.7 passed on all five with none skipped.
The release steps, including what stays manual, are in
[`docs/release.md`](../../release.md).

- **R1, met.**  Windows x64 and ARM64, macOS ARM64, Ubuntu x64, and Linux
  ARM64.  There is no macOS x64 station; macOS x64 is not retained.
- **R2, met.**  The coordinator `stations.yaml` owns the inventory; `JCI_DUTS`
  becomes `JS_UITEST_DEVICES`.
- **R3, met.**  Linux runs on Xvfb when it has no display.  Windows and macOS
  render on the desktop session with `JS_UITEST_DISPLAY=1`.
- **R4, met.**  A release run (`JS_UITEST_BUILD_KIND=release`) installs the
  published build: Windows per user with `/CURRENTUSER /NOLAUNCH`, macOS
  copied with `ditto` and checked with `codesign` and `spctl`, and Linux x64
  from the `.tar.gz`.  ci_linux_arm tests the sdist, since there is no Linux
  ARM64 installer.
- **R5, met with on-demand long-term runs.**  (a) Main and tag builds
  dispatch; (b) the long-term `ui_longterm` suite runs from the Jobs page Run
  button rather than on a schedule; (c) the dashboard reruns any job.
- **R6, met for manual review.**  Each job uploads JUnit XML, the pytest log
  and failure screenshots, and the release run is reviewed on the dashboard.
  An automated gate that aggregates the (station, model) cells is not built;
  see `docs/release.md`.
- **R7, met except the known load.**  Each job closes any process holding a
  Joulescope and power-cycles every DUT through the station's USB Insight
  Hub.  No station has a known load or loopback; that work belongs to
  joulescope_ci `doc/plans/flexible_stations.md`.
- **R8, met.**  A station runs one job at a time; others queue.
- **R9, met.**  Outbound access works.  VirusTotal stays a manual upload, so
  no `VT_API_KEY` is needed.

Acceptance (smoke) is met: each station installs the published release,
runs device and non-device tests (including the interactive waveform tests)
with none skipped for "no display", uploads its results, and recovers its
devices by power-cycle.

## Consumers (design for all, not just the UI)

- **UI release tests** — GUI app installed from `download.joulescope.com`, driven
  over a localhost TCP socket; needs a **rendering display** (see R3).
- **Firmware / gateware HIL** — drives `joulescope_driver` over USB; may need
  external instruments (ADP3450, Saleae) and device power control.
- **PCTS / FTS** — production/final test; calibration, known loads, fixtures.

## Required capabilities

### R1 — Heterogeneous runner fleet, one per platform/arch
Self-hosted runners covering at least: **Windows 11 x64, Windows 11 ARM64,
macOS ARM64, macOS x64 (if retained), Ubuntu LTS x64**.  A consumer must be able
to target a specific platform/arch.

### R2 — Capability advertising (don't assume)
Stations are heterogeneous; each runner **advertises** its platform and what is
attached rather than the job assuming it.  Advertised capabilities include
attached **device models** (JS220 / JS320 / JS110) and **instruments** (e.g.
Saleae, ADP3450, J-Link/programmer).  A job selects runners by required
capability and is skipped/withheld where the capability is absent.
*Resolved 2026-08-04: the farm owns the canonical inventory (`joulescope_ci`
coordinator `stations.yaml`); the runner exports the bench's DUT kinds as
`JCI_DUTS`, and the UI suite consumes them as `JS_UITEST_DEVICES`.  The UI-side
`stations.toml` mirror was removed.*

### R3 — Rendering display + working OpenGL  *(UI-critical, non-obvious)*
Runners that execute **UI tests must render the GUI, including the OpenGL
waveform plot** — a headless/offscreen session is **not** sufficient.  The
interactive waveform tests (pan, y-axis range/scale, marker move/remove) rely on
the plot actually painting to populate its hit-test geometry; a non-rendering
runner produces a blank plot (a grabbed plot widget is ~960 bytes) and those
tests **skip**.  Requirement: a real desktop session (X11/Wayland) with
functioning GL (GPU or a software-GL stack that genuinely renders), and the
ability to set a large window.  Tests are launched with `JS_UITEST_DISPLAY=1`.

### R4 — Install software-under-test
Runners must allow installing a downloaded, signed installer unattended:
- Windows: run the Inno Setup `.exe` with `/VERYSILENT /SUPPRESSMSGBOXES
  /NORESTART`.
- macOS: mount the `.dmg`, copy the `.app`, clear quarantine (`xattr -dr
  com.apple.quarantine`); handle Gatekeeper/notarization (possibly a one-time
  trust step per bench).
- Ubuntu: extract the `.tar.gz` and locate the binary.
`ci/uitest/installer.py` already implements download + sha256-verify + install.

### R5 — Job dispatch + matrix
Trigger a test job (a) after a publish event, (b) on a schedule (for long-term
runs), and (c) on demand (`workflow_dispatch` with a version).  Fan a job out as
a **matrix over runners by capability** (platform × advertised devices).

### R6 — Result + artifact collection
Collect per-job **JUnit XML** and **artifacts** (failure screenshots under
`JS_UITEST_ARTIFACTS`, logs).  Aggregate pass/fail per **(platform, device)
cell** so a release gate (UI M4) can require every required cell green.

### R7 — Clean state + device recovery between runs
- Reset host state between runs: kill stale app processes, clear app config.
- **Device power control** (programmable power-cycle) for attached Joulescopes.
  This is a hard requirement: a JS320 **wedges** if a stream is killed abruptly
  mid-capture and only recovers via power-cycle, and stream control can leak
  across a close.  The farm must be able to power-cycle a device to recover a
  bench without manual intervention.
- **Known, stable DUT load** per UI/PCTS bench so recordings carry real,
  repeatable signal (a fixed resistor / programmable load; optionally GPO→GPI
  loopback).  UI tests check function + round-trip, not calibrated accuracy.

### R8 — Single-instance / port serialization  *(UI-specific)*
The UI's TCP server binds a **fixed port (21861)** and writes one `server.json`
per host app dir.  Only **one UI test process per host** can run at a time;
the farm must serialize UI jobs on a host (or give each its own host).  Stale
`server.json` / orphan UI processes must be cleaned between jobs.

### R9 — Network + secrets
Runners need outbound access to `download.joulescope.com` (installers +
`index_v2.json`), GitHub (runner registration, artifacts), and — for the gate —
the VirusTotal API.  Provide secrets (signing, `VT_API_KEY`, AWS for publish) to
the appropriate jobs only.

## Interface contract the UI relies on

As built, the farm sets `JS_UITEST_BUILD_KIND=release` instead of
running `installer.py` itself: the suite's `conftest.py` installs the
published release for the version under test and launches it.  The design
contract was:

Given a farm runner with the above, the UI job is simply:

```bash
python ci/uitest/installer.py <channel>        # download + verify + install alpha
JS_UITEST_DISPLAY=1 \
JS_UITEST_DEVICES=$JCI_DUTS \
JS_UITEST_EXECUTABLE=<installed joulescope path> \
  pytest ci/uitest --junitxml=results.xml       # device + non-device per caps
# upload results.xml + uitest_artifacts/
```

So the farm must expose, per runner: the bench's **device set** (→
`JCI_DUTS` → `JS_UITEST_DEVICES`), the **installed executable path** (→
`JS_UITEST_EXECUTABLE`), and a **rendering display** (→ `JS_UITEST_DISPLAY=1`).

## Out of scope here (owned by the UI, already done or planned)
- The UI test harness, suites, and `installer.py` (done, M1–M2).
- The release **gate** that consumes the farm's aggregated results + VirusTotal
  (UI **M4**, `ci/release_gate.py` + `ci/virustotal_scan.py`).
- Long-term capture tests scheduled on the farm (UI **M5**, `test_longterm.py`).

## Acceptance (smoke)
A single Ubuntu runner with a rendering display and a JS220 + JS320 attached can:
install the published alpha build, run `JS_UITEST_DISPLAY=1 pytest ci/uitest`
(non-device **and** device + the interactive waveform tests all execute, none
skipped for "no display"), and upload JUnit XML + any failure screenshots; and a
mid-capture abort followed by a power-cycle leaves the devices usable for the
next job.
