# UI release-test automation (`ci/uitest`)

Automated execution of the Joulescope UI release test plan
(`doc/ui_test_1_3_4.xlsx`) by driving the running UI through its TCP control
socket (`joulescope --tcp-server`).  See
[`docs/plans/ui_release_test_automation.md`](../../docs/plans/ui_release_test_automation.md)
for the design and status.

Run everything with `pytest` from the **`pyjoulescope_ui/`** directory.

## Prerequisites

* `pytest`, plus the UI's runtime dependencies importable in the same
  environment (PySide6, pyjoulescope_driver, pyjls, numpy) — i.e. the env the UI
  itself runs in.
* For **device** tests: a Joulescope (JS220 / JS320 / JS110) attached, ideally
  measuring a stable known load.
* For **interactive** waveform tests: a real display that renders the OpenGL
  plot (see `JS_UITEST_DISPLAY` below).

## Test tiers

| Tier | Files | Needs |
| --- | --- | --- |
| Qt-free unit tests | `test_harness_unit.py` | nothing (no UI) |
| Hardware-free UI | `test_basics`, `test_preferences`, `test_open_jls`, `test_waveform`, `test_analysis` | the UI (runs offscreen) |
| Interactive (rendered) | `test_waveform_interactive` | a real display (`JS_UITEST_DISPLAY=1`) |
| Device | `test_multimeter`, `test_record_export` (marked `device`) | a connected Joulescope + a station that advertises it |

Tests marked `device` are selected/excluded with `-m`.  Interactive tests
**skip themselves** when the plot is not rendering (offscreen / no GL), so the
hardware-free command stays green in headless CI.

## Common commands

```bash
cd ~/repos/Jetperch/pyjoulescope_ui

# Qt-free unit tests only — fast, no UI, no hardware
pytest ci/uitest/test_harness_unit.py

# All hardware-free tests (what CI runs) — launches the UI offscreen
pytest ci/uitest -m "not device"

# Interactive waveform tests (pan, y-axis range/scale, marker move/remove)
# — require a real display; otherwise they skip
JS_UITEST_DISPLAY=1 pytest ci/uitest/test_waveform_interactive.py
```

## Device tests

The `device` tests parametrize over the models the active **station** advertises.
Describe your bench in a stations file and select it:

```bash
cat > /tmp/stations.toml <<'TOML'
[stations.localdev]
platform = "ubuntu"
devices = ["JS220", "JS320"]     # exactly what is plugged in
TOML

JS_UITEST_STATIONS_FILE=/tmp/stations.toml JS_UITEST_STATION=localdev \
  pytest ci/uitest -m device
```

A device advertised by the station but not connected **fails** the test (a
missing advertised device is a real bench fault), so list only what is attached.

The committed [`stations.toml`](stations.toml) holds a no-device `default` plus
example benches; edit it (or point `JS_UITEST_STATIONS_FILE` elsewhere) to match
real hardware and the self-hosted runner labels.

## Everything (display + devices)

```bash
JS_UITEST_DISPLAY=1 JS_UITEST_STATIONS_FILE=/tmp/stations.toml JS_UITEST_STATION=localdev \
  pytest ci/uitest
```

## Handy variants

```bash
pytest ci/uitest/test_basics.py -v                        # one file, verbose
pytest "ci/uitest/test_waveform_interactive.py::test_pan"  # one test
JS_UITEST_DISPLAY=1 pytest ci/uitest -k marker             # select by name
```

## Environment variables

| Var | Purpose |
| --- | --- |
| `JS_UITEST_DISPLAY=1` | Render on the real display (needed for `test_waveform_interactive`; otherwise the UI runs offscreen and those tests skip) |
| `JS_UITEST_STATION` | Station name from the registry (selects which device models are advertised) |
| `JS_UITEST_STATIONS_FILE` | Path to your own stations TOML (instead of the committed `stations.toml`) |
| `JS_UITEST_EXECUTABLE` | Path to an installed `joulescope` binary to test (default: `python -m joulescope_ui`) |
| `JS_UITEST_DEVICE_TIMEOUT` | Seconds to wait for an advertised device to enumerate (default 10) |
| `JS_UITEST_ARTIFACTS` | Directory for screenshot-on-failure PNGs (default `./uitest_artifacts`) |

## Notes

* Interactive tests each launch a fresh UI and need it to render, so they are
  slow (~30 s each); the Qt-free unit tests are near-instant.
* Large JLS fixtures are fetched on demand and cached under `assets/`
  (git-ignored), not committed.
