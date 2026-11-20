<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
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
-->

# Event Analyzer (alpha) in Tools

## Status (2026-11-19)

Stages 0-2 are on main (`5c3a3a9`, `073b0c9`) and listed under 1.8.1 in
`CHANGELOG.md`; there is no `v1.8.1` tag yet.  The Stage 3 bench check is
done.  Remaining:

* The user's guide section (Stage 2).  joulescope_docs has no Event
  Analyzer page yet.
* The packaged-build checks in Stage 3: Windows and Linux with the network
  off, charts render, Cancel, and memory and time on a multi-hour capture.

## Context

[joulescope_event_analyzer](https://github.com/jetperch/joulescope_event_analyzer)
finds the wake-up events in a JLS capture, groups them into types, builds a
charge budget and writes a self-contained HTML report (plus CSV and summary
JSON).  It is a library with a command line; this plan adds an alpha front
end to the Joulescope UI so that customers can try it and give feedback.

This is a preview.  The UI-native energy analysis
(`docs/energy_analysis.md` on `feature/energy_analysis`) is the long-term
design and may replace it.

Branch: `feature/event_analyzer`.  Target: 1.8.1 if ready in time,
otherwise the next release.


## User flow

1. **Tools → Event Analyzer (alpha)** opens a dialog.
2. The user selects a JLS file.  The field defaults to the JLS open in the
   UI, else the most recent recording, else empty.
3. The user optionally changes a few options and the output directory, which
   defaults to `<capture>_events/` next to the JLS (same as the command
   line).
4. **Run** analyzes in a worker thread with a progress bar and Cancel.
5. On success, the UI opens `<capture>_events.html` in the browser with the
   existing `registry/ui/actions/!url_open` action.  On failure, it shows
   the error and logs the traceback.


## Options

Keep the dialog small.  Everything else uses the analyzer defaults.

| Dialog field | Config | Default |
|---|---|---|
| Sleep current | `sleep.level` | Auto (None) |
| Start threshold | `detect.start_threshold` | Auto (None) |
| Merge gap | `detect.merge_gap` | 200 µs |
| Match tolerance | `match.tolerance` | 0.30 |
| Battery capacity (mAh) | `report.battery_capacity_mAh` | none |
| Templates file | `analyze(templates=...)` | none |
| Output directory | — | `<capture>_events/` |

Remember the last-used values in the UI settings (not the file path).


## Design

* **No duplicated logic.**  The command line's `cmd_analyze` (analyze, then
  write CSV, summary JSON and HTML) moves into a library function in the
  analyzer, for example `analyze_file(path, outdir, config, templates,
  progress) -> list[str]`, and both the command line and the UI call it.
  This is done in the analyzer before its first release.
* **Worker thread.**  Run `analyze_file` on a `threading.Thread` (or
  `QThread`).  Marshal progress and completion to the Qt thread with a
  signal; never touch widgets from the worker.
* **Cancel.**  The progress callback raises a private exception when cancel
  is requested.  `analyze` does not catch exceptions from the callback, and
  the source is closed by its context manager.  Verify that no partial
  report is written (or delete the output files on cancel).
* **Output directory.**  Create it if missing.  If it already holds a
  report, ask before overwriting.  If it is not writable, show a clear
  error and let the user pick another directory.
* **Plotly.**  The report embeds plotly.js (JavaScript, not the Python
  package).  Bundle `plotly.min.js` (MIT) in the UI resources and point the
  analyzer at it, so that reports work offline from the first run with no
  download.  Add it to the credits.
* **Dependency.**  `joulescope_event_analyzer>=0.1.1,<1` is an
  `install_requires` entry.  0.1.1 fixes event tails biasing the sleep
  current, found in the Stage 3 hardware test.  The UI imports it
  lazily, inside the functions that use it.
* **Settings.**  The dialog's last-used values live in
  `registry/event_analyzer/settings/*`, flagged `hide`: they are dialog
  state, so the Settings widget and its Reset leave them alone.


## Stages

### Stage 0: Analyzer library entry point (analyzer repo) — DONE

`analyze_file` with `plotly=` and cancel through the progress callback;
joulescope_event_analyzer 0.1.0 released to PyPI 2026-11-16.

### Stage 1: Dialog, worker, menu item — DONE

* `joulescope_ui/event_analyzer.py`: dialog, option-to-`Config` mapping,
  worker, result handling.
* `main.py`: add the Tools menu entry.
* Unit tests: option-to-`Config` mapping, default output directory, worker
  success, error and cancel paths on a synthetic JLS (write one with
  `joulescope_event_analyzer.synthetic` and pyjls).
  (`joulescope_ui/test/test_event_analyzer.py`)

### Stage 2: Packaging — DONE except the user's guide

* Add the dependency to `setup.py`, `requirements.txt` and
  `flatpak/requirements-flatpak.txt`, and regenerate
  `flatpak/python3-modules.json`.  The regeneration also brought the
  Flatpak's stale pins up to `setup.py` (pyjls 0.17 → 0.19.2, driver
  2.2.9 → 2.5.7, joulescope 1.5.0 → 1.7.3, QtAds 4.5 → 5.0.0.2).  PySide6
  stays at 6.11 in the Flatpak: 6.12 adds PySide6_WebEngine and
  PySide6_Pdf, which flatpak-pip-generator cannot pin.
* PyInstaller finds the package through its imports; check the packaged
  build in Stage 3.
* Bundle plotly.js (`joulescope_ui/resources/plotly/`, with its MIT
  license; MANIFEST.in includes it) and add it and the analyzer to the
  credits.  A test checks that the bundled file matches the analyzer's
  pinned SHA-256, so bump both together.
* CHANGELOG entry; user's guide section on docs.joulescope.com marked
  alpha.

### Stage 3: Verification — hardware done; packaged builds open

ADP3450 W2 → 100 Ω → JS320 current, playing repeating waveforms with known
events (2026-11-16): one type, three interleaved types, amplitude jitter,
merge gap, 0.3 µC and 12 nC events, sleep dips, a 2 ms exponential tail,
at 1 MHz and 50 kHz.  The tail exposed a sleep-estimate bias, fixed in
analyzer 0.1.1; see the analyzer's CLAUDE.md "Hardware validation".  The
harness needs the private ADP3450 wrapper, so it belongs in joulescope_ci.


* Analyze a JS220 and a JS320 capture (1 MHz and a downsampled rate) from
  the packaged build on Windows and Linux with the network disabled; check
  that the report opens and that charts render.
* Cancel mid-run; analyze a multi-hour capture and check memory and time.


## Later

* **Compare** two JLS files from the same dialog (`compare_sources`).
* **Range tool** on the waveform dual markers, using an `ArraySource` over
  the marked samples, so that data in the streaming buffer can be analyzed
  without recording first.  Reuses the Stage 1 worker and options.
* Save and apply templates from the dialog.
