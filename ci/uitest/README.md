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
| Interactive (rendered) | `test_waveform_interactive` | a real display (`JS_UITEST_DISPLAY=1` makes it required) |
| Device | `test_multimeter`, `test_record_export` (marked `device`) | a connected Joulescope |

Tests marked `device` are selected/excluded with `-m`.  Interactive tests
**skip themselves** when there is no display or the plot is not rendering
(no GL), so the hardware-free command stays green in headless CI.  With
`JS_UITEST_DISPLAY=1`, which promises a display, they **fail** instead.

On Wayland (`WAYLAND_DISPLAY` and `DISPLAY` set), interactive tests run the
UI on XWayland (`QT_QPA_PLATFORM=xcb`).  Native Wayland cannot open popup
menus from synthetic clicks, which the y-axis and marker menu tests need.
Set `QT_QPA_PLATFORM` yourself to override.  On-screen Linux sessions
disable vsync (`vblank_mode=0`, `__GL_SYNC_TO_VBLANK=0`).  An unattended
bench blanks its screen, and each OpenGL swap would then stall the UI.

## Common commands

```bash
cd ~/repos/Jetperch/pyjoulescope_ui

# Qt-free unit tests only — fast, no UI, no hardware
pytest ci/uitest/test_harness_unit.py

# All hardware-free tests (what CI runs) — launches the UI offscreen
pytest ci/uitest -m "not device"

# Interactive waveform tests (pan, y-axis range/scale, marker move/remove,
# #352 fill) — require a real display; otherwise they fail
JS_UITEST_DISPLAY=1 pytest ci/uitest/test_waveform_interactive.py
```

## Device tests

The `device` tests parametrize per model, in one of two modes:

* **Auto-detect** (`JS_UITEST_DEVICES` unset, the default): every known model
  is a candidate; a model that is not attached **skips** at runtime.

  ```bash
  pytest ci/uitest -m device
  ```

* **Expectation** (`JS_UITEST_DEVICES` set): only the listed models run, and a
  listed model that is not connected **fails** the test — a missing expected
  device is a real bench fault, and keeps a dead bench from going green.

  ```bash
  JS_UITEST_DEVICES=JS220,JS320 pytest ci/uitest -m device   # release gate
  JS_UITEST_DEVICES= pytest ci/uitest                        # no device tests
  ```

Station configuration is owned by the `joulescope_ci` HIL farm: the
coordinator's `stations.yaml` is the single source of bench inventory, and its
runner exports the bench's DUT kinds as `JCI_DUTS`, which the farm's UI suite
passes here as `JS_UITEST_DEVICES` (parsing is case-insensitive).

## Everything (display + devices)

```bash
JS_UITEST_DISPLAY=1 pytest ci/uitest
```

## Handy variants

```bash
pytest ci/uitest/test_basics.py -v                        # one file, verbose
pytest "ci/uitest/test_waveform_interactive.py::test_pan"  # one test
JS_UITEST_DISPLAY=1 pytest ci/uitest -k marker             # select by name
```

## One-shot CLI (`cli.py`)

[`cli.py`](cli.py) is a standalone command-line client for interactive
automation (shell scripts, agents) against a UI already running with
`--tcp-server` — it auto-discovers `server.json`, performs one operation, and
prints one JSON object:

```bash
python ci/uitest/cli.py ping                       # connected? active view?
python ci/uitest/cli.py view multimeter           # switch view and wait
python ci/uitest/cli.py screenshot shot.png       # main window -> PNG
python ci/uitest/cli.py find --class WaveformWidget
python ci/uitest/cli.py devices
```

Exit codes: 0 success; 2 UI not running with `--tcp-server` (or stale
`server.json`); 3 request timeout; 4 server-reported error.  Run
`python ci/uitest/cli.py --help` for all subcommands.  Unlike `UiSession`,
the CLI never launches or closes the UI and never touches the config.

## Environment variables

| Var | Purpose |
| --- | --- |
| `JS_UITEST_DISPLAY=1` | Run the non-interactive tests on the real display too, and fail (not skip) interactive tests that cannot render.  Unset: non-interactive tests run offscreen, and interactive tests skip without a display |
| `JS_UITEST_DEVICES` | Comma-separated expected models (`JS220,JS320`); listed-but-missing fails.  Unset: auto-detect (missing skips).  Empty: no device tests |
| `JS_UITEST_EXECUTABLE` | Path to an installed `joulescope` binary to test (default: `python -m joulescope_ui`) |
| `JS_UITEST_DEVICE_TIMEOUT` | Seconds to wait for a device to enumerate (default 10) |
| `JS_UITEST_ARTIFACTS` | Directory for screenshot-on-failure PNGs (default `./uitest_artifacts`) |

## Notes

* Interactive tests each launch a fresh UI and need it to render, so they are
  slow (~7 s each); the Qt-free unit tests are near-instant.  The render
  check calls `WaveformWidget.plot_render_info()` and uses no input events.
  The fixture closes the attached-device waveforms so the file plot gets
  the window.
* Large JLS fixtures are fetched on demand and cached under `assets/`
  (git-ignored), not committed.
