# HIL Farm — capability requirements (M3)

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
silent-install a published build), `ci/uitest/stations.py` + `stations.toml`
(capability advertising), and a pytest suite gated by markers and `JS_UITEST_*`
env vars (see `pyjoulescope_ui/ci/uitest/README.md`).

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
*The UI mirrors this in `stations.toml`; the farm should own the canonical,
machine-readable station inventory that the UI registry can be generated from or
aligned to.*

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

Given a farm runner with the above, the UI job is simply:

```bash
python ci/uitest/installer.py <channel>        # download + verify + install alpha
JS_UITEST_DISPLAY=1 \
JS_UITEST_STATION=<this-runner> \
JS_UITEST_EXECUTABLE=<installed joulescope path> \
  pytest ci/uitest --junitxml=results.xml       # device + non-device per caps
# upload results.xml + uitest_artifacts/
```

So the farm must expose, per runner: a **stable station name** (→
`JS_UITEST_STATION`), the **installed executable path** (→
`JS_UITEST_EXECUTABLE`), a **rendering display** (→ `JS_UITEST_DISPLAY=1`), and
the advertised **device set** (so the station registry matches reality).

## Out of scope here (owned by the UI, already done or planned)
- The UI test harness, suites, and `installer.py` / `stations.py` (done, M1–M2).
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
