# Efficiency widget: two-instrument DC-DC efficiency measurement

## Context

Customers measure converter efficiency (DC-DC, LDO, charger, PMIC rail) with
two Joulescopes: one on the input and one on the output.  Today they must
read two Multimeter widgets and divide by hand, or export two JLS files and
align them offline.  The two instruments have free-running sample clocks and
separate statistics windows, so a ratio of two statistics values pairs
mismatched time windows and gives wrong numbers when the load changes.

This plan adds:

1. **A documented wiring method** that removes Joulescope burden voltage from
   the result, with a figure, on docs.joulescope.com.
2. **An Efficiency widget** (Widgets menu, not in any default view) with:
   - an instantaneous efficiency readout at the statistics rate;
   - an optional efficiency-vs-time plot;
   - an optional efficiency-vs-output-current curve, built up over time from
     whatever load points the user exercises.

The layout mockup is [efficiency.svg](efficiency.svg).


## Measurement setup (customer documentation)

### Wiring that removes burden voltage

The regulator's efficiency is `η = P_out / P_in`, where both powers are
measured **at the regulator pins**.  Each Joulescope adds a burden voltage
across its current path.  If each voltmeter is connected at the regulator
pins (Kelvin connection), the burden voltage falls outside both measured
powers and does not affect η:

```
Supply -> [A: I+ -> I-] -> VIN +-----------+ VOUT -> [B: I+ -> I-] -> Load
                            |  | Regulator |  |
                A V+ -------+  |           |  +------- B V+
                A V- ------ GND+-----------+GND ------ B V-
```

- **Input instrument (A)**: current path between the supply and the
  regulator input; voltage measured *after* the Joulescope, at VIN/GND.
- **Output instrument (B)**: current path between the regulator output and
  the load; voltage measured *before* the Joulescope, at VOUT/GND.
- Both measured currents are the regulator's input and output currents, and
  both voltages are at the pins, so `P_in` and `P_out` are exactly the
  regulator's.  The shunt losses appear only in the supply and load voltages,
  which affect the operating point slightly but not the measurement.

The docs also cover:

- **Model support.**  JS220 and JS320 are the primary instruments: separate
  V+/V- inputs and isolated (sensor ground referenced to Current+), so they
  work on either side and in high- or low-side placement.  JS110 gets a
  short caveats section: its voltmeter measures between IN+ and IN-, before
  its shunt.  It is therefore correct as the **output** instrument (IN at the
  regulator output), but as the **input** instrument its own burden voltage
  is included in `P_in`, so η reads slightly low.  JS110 is also isolated.
- **Ground.**  Both regulator grounds are common.  Link to
  `theory/ground_loops.md` for USB and debugger loops.
- **Null test** ("wire test"): replace the regulator with a wire.  Both
  instruments then measure the same node and current, so the widget must read
  100% (within instrument accuracy).  This verifies wiring and source
  assignment before measuring the real converter.
- **Resistor test**: a series resistor R as the "regulator" with load R_L
  gives `η = V_out / V_in = R_L / (R + R_L)`, since the currents are equal.
- **Accuracy.**  Error in η is roughly the sum of both instruments' power
  gain errors plus current offset at light load.  Light-load efficiency
  needs the instruments' low current ranges; state this with the datasheet
  values per model.
- **Time alignment.**  Two instruments have independent clocks.  Residual
  misalignment after host time sync is about ±160 µs (measured below), which
  matters only for windows containing load steps at high update rates.
- **Energy storage.**  Regulator capacitance stores energy, so η over a short
  window during a transient can exceed 100%.
- **Settings.**  Both instruments need the `p` signal enabled (the widget
  shows a status and offers an Enable action, see below).  Sample rates need
  not match between instruments.

### Where it lives

- **Theory page** `joulescope_docs/source/theory/efficiency.md` (label
  `theory-efficiency`): general knowledge independent of the UI: wiring
  that removes burden voltage, model support (JS110 caveat), ground, null
  test, resistor test, accuracy, energy storage in regulator capacitance,
  why two free-running instruments must be time aligned, and steady-state
  load points for an efficiency curve.
- **UI guide page**
  `joulescope_docs/source/software/joulescope_ui/efficiency.md`, linked from
  the UI guide index next to `multiple_instruments.md`: opening the widget,
  selecting input/output, Enable p, the readout, the two plots, settings,
  CSV export, status messages, and implementation details (UTC window grid,
  rate follows the input instrument, steady filter).  It links to the Theory
  page rather than repeating it.
- **Figure**: SVG generated by a script in `joulescope_docs/scripts/` using
  the existing matplotlib helpers in `theory_diagrams.py` (`_box`, `_wire`,
  `_arrow`).  Refactor those helpers into a shared `scripts/diagram_util.py`
  rather than copy them.  The figure shows both instruments' terminal labels
  for JS220/JS320, with colored current and voltage paths.
- Screenshots of the widget are added after Stage 5.


## Goals and non-goals

**Goals (v1)**

- One input and one output signal-stream source per widget instance, each
  any connected JS110/JS220/JS320 (selected independently; both must be
  different devices).
- Correct time alignment between two free-running instruments.
- Readout: η, P_in, P_out, P_loss (= P_in − P_out), and cumulative η since
  Clear (`ΣE_out / ΣE_in`), at the statistics rate.
- Efficiency-vs-time plot (toggle).
- Efficiency-vs-output-current curve (output power optional) accumulated over
  time (toggle).
- CSV export of the time series and the curve.
- Settings persist with the view/profile like other widgets.  The curve
  itself does not persist.
- Processing off the Qt thread, following the Spectrum widget pattern.

**Non-goals (v1)**

- JLS file / paused buffer analysis (later stage; the engine is designed so
  a buffer source can feed it).
- More than two instruments (multi-rail PMIC, multiple outputs).  The engine
  keeps "input" and "output" as lists internally so this can be added.
- Uncertainty bands computed from datasheet accuracy.
- Controlling the load (e.g. driving an electronic load sweep).
- Additional readouts (loss as % of P_out, thermal); add later if needed.


## Signal processing

### Why sample data, not statistics

Each device emits statistics on its own clock, so windows from A and B start
at different instants and have slightly different lengths.  The sample stream
carries `sample_id`, `sample_freq`, and a `time_map` (all three models, see
`devices/jsdrv/js320.py` `_signal_forward_factory`), which maps each device's
sample counter to host UTC including clock drift.  Using samples lets the
widget integrate both instruments over the **same UTC interval**.

The widget uses the device-computed `p` signal (computed at the full rate
before decimation, so it is exact even when `i` and `v` vary within a
decimated sample).  `i` and `v` are not needed for η.  The output `i` is
subscribed for the default curve x-axis (output current); the others are
subscribed only when the optional V/I readout is shown.

### Per-instrument energy integrator

`EnergyIntegrator` (Qt-free, in a new `joulescope_ui/efficiency_engine.py`):

- Per chunk: check `sample_id` continuity (gap → mark the interval invalid,
  same rule as `spectrum_engine`), convert the chunk's start and end
  sample_id to UTC with the chunk's `time_map`, and append the chunk's
  cumulative energy `cumsum(p) / fs`.  The `time_map` counter is the
  *origin* sample_id (`origin_sample_id`, at `counter_rate`), not the
  decimated one.
- Query `energy(t0, t1)`: map UTC to fractional sample index through the
  time map, and interpolate the cumulative sum linearly at both edges.  This
  makes windows exact to a fraction of a sample, independent of each
  device's sample rate.
- The same integrator handles any signal, so mean `I_out` (and optional V/I)
  per window come from the same code.
- Retains only a few seconds of history (bounded memory); chunks older than
  the oldest pending window are dropped.

Packed digital signals are never needed; reuse `sample_count` from
`spectrum_engine.py` for message length.

### Window grid and pairing

All engine times are float seconds relative to `t_ref`, an integer UTC
second (exact in time64) taken from the first message.  Absolute UTC in
float64 only resolves about 30 ns, which cost about 1e-7 relative accuracy
in the first engine tests.  Windows report `t0`/`t1` relative to `t_ref`
plus `utc` (time64 of `t0`).

- Windows are aligned to a common UTC grid: `[k·T, (k+1)·T)`, with
  `T = 1 / statistics_frequency`.
- **Rate source:** the widget follows the **input** instrument's
  `settings/statistics_frequency` (1–100 Hz), so η updates exactly when the
  Multimeter does.  No override.  A rate change restarts the grid (traces
  keep their history).  JS110 exposes the same setting.
- Window k is emitted when both integrators cover `(k+1)·T` plus a small
  guard.  Each emitted window carries: `t`, `E_in`, `E_out`, `P_in`,
  `P_out`, `I_out`, `η`, `valid`, `steady`, and optional mean V/I.
- A window with a gap on either instrument is emitted as invalid (shown as a
  break in the time plot, excluded from the curve and the cumulative η).
- If one instrument stops (unplug, closed), windows stall; after a timeout
  the status line shows which instrument is missing.  When both overlap
  again, the engine emits one invalid window spanning the discarded data,
  then continues on the grid.
- A configuration change never re-emits a window: each grid keeps the end
  of its last emitted window across period changes.

### Alignment error budget

Residual misalignment δ comes only from the host time sync of each device
and any model-dependent signal latency.  For a load step ΔP inside a window,
the energy error is about `δ·ΔP`, so the relative error is about `δ/T`, and
zero for steady loads.  Measured values are in [Stage 0 results](#stage-0-results).

### Energy storage caveat

Regulator input/output capacitance stores energy.  Over a short window during
a load transient, η can read above 100% or swing low.  This is physically
correct for that window.  The readout and time plot show raw values; the
curve uses only steady windows (below).  The docs explain this.

### Efficiency vs output current curve

- X-axis: output current (default, as in converter datasheets) or output
  power (option), log scale by default, linear optional.  The default needs
  the output instrument's `i` signal, so the widget subscribes `p` on both
  instruments and `i` on the output instrument.
- Log-spaced bins (setting: bins per decade, default 20), auto-extending as
  new load levels appear.  Bins are centered on `10^(k / bins_per_decade)`,
  so round loads such as 10 mA land in a bin center, not on an edge.
- Each accepted window adds to its bin: `ΣE_in`, `ΣE_out`, duration, window
  count, η min/max.  The bin's η is `ΣE_out / ΣE_in` (energy-weighted, so
  noisy light-load windows do not bias it).
- **Steady-state filter:** a window is accepted only if both the input and
  output power are steady within it.  The engine splits each window into 10
  sub-windows; accept when `(max − min) / mean` of the sub-window power is
  below a threshold (setting, default 5%) for both instruments.  Rejected
  windows are counted in the status line.
- **Curve window:** the curve uses the same window T by default; a setting
  allows a shorter curve window (e.g. 10 ms) for fast load sweeps.
- Clear resets the curve; the curve can be frozen (Hold) while the time plot
  continues.  The curve is not persisted; CSV export saves it.
- Display: points with min/max whiskers (toggle), and a line through bin
  means.  Bins with fewer than N windows (setting) drawn faded.


## Widget design

### Layout (mockup in [efficiency.svg](efficiency.svg))

- **Top: readout**: large η, then P_in, P_out, P_loss, cumulative η, and
  optionally V/I.  Styled like the Value widget (`widgets/value/`), using its
  font and color scheme files.
- **Middle: efficiency vs time** (toggle), y = η in %, x = relative time,
  configurable duration (default 10 min), ring buffer of window results.
- **Bottom: efficiency vs output current** (toggle).
- `QSplitter` between panes, as in Spectrum.
- **Control bar** (follows the Waveform `control_location` setting, as in
  Spectrum): input source, output source, Swap, Run/Hold, Clear, status
  (rate, window count, rejected windows, gaps, missing instrument).
- Right-click menu and settings dialog for the less frequent settings.

### Sources

- Two `SourceSelector(self, 'signal_stream')` instances
  (`joulescope_ui/source_selector.py`) with settings `input_source` and
  `output_source`.  Neither defaults to `default`: on first open with exactly
  two instruments, input = the app default device, output = the other.
- Same device for both → status error, no computation.
- Swap button exchanges them.  If η stays above 105% for several valid
  windows, the status suggests Swap.
- **JS110:** no extra controls.  When a JS110 is the **input** instrument,
  the status line shows a warning (burden voltage included in P_in) with a
  link to the Theory page; as the output instrument it needs no warning.
  The JS220/JS320 path is unchanged by JS110 support.
- If `p` is disabled on either device (or `i` on the output device), show
  the status and an **Enable** action that publishes
  `settings/signals/{signal}/enable` (same enable-topic subscription pattern
  as `spectrum_widget.py` `_enable_unsubscribe`).
- Respect `registry/app/settings/signal_stream_enable`: the widget drops data
  itself when paused (stream sinks must, per the Spectrum findings).

### Plots

Both plots are custom `QPainter` plots like Spectrum, reusing
`widgets/waveform/axis_ticks.py`, `line_segments.PointsF`, and `units.py`.
Stage 2 moved the shared drawing into `joulescope_ui/widgets/plot_base.py`:
`style_vars`/`style_build` (common pens and font from `{prefix}.*` style
variables), `draw_x_axis`, `draw_y_axis`, grid lines, `draw_v_line`,
`draw_text_box`, and `draw_border`.  Spectrum now uses them, and renders
pixel-identical to before.  Spectrum's `_PlotBase` mouse handling stayed in
Spectrum: it is built around frequency markers and the frequency viewport,
so sharing it would only rename Spectrum concepts.  The Efficiency plots
implement their own small mouse handling (hover, and zoom on the time plot).
No copied plot code.

pyqtgraph (already a dependency, used by the range tools, timesync, and
fuse widgets) was considered.  Matt prefers the look of the custom
Waveform/Spectrum plots, so v1 uses QPainter; pyqtgraph is the fallback if
the custom plots don't work out.

### Threading

Same pattern as Spectrum (`widgets/spectrum/spectrum_worker.py`): Qt-thread
`_on_data` enqueues `(instrument, signal, sample_id, fs, time_map, data)`
into one bounded queue with config commands; a `threading.Thread` runs the
engine and emits immutable window results via a queued Qt signal.  The data
rate is low (about 3 × 1 MSPS f32), and the engine work is one `cumsum` per
chunk.  Stage 2 factored the generic loop (command queue, backpressure in
seconds of queued data, frame-rate snapshots, start/stop) out of
`SpectrumWorker` into `joulescope_ui/stream_worker.py` `StreamWorker`; the
efficiency worker subclasses it with `queue_seconds` sized for three
streams.

### Settings (persisted)

`input_source`, `output_source`, `show_vi`, `time_plot_enable`,
`time_plot_duration`, `curve_enable`, `curve_x` (current (default) /
power), `curve_x_scale` (log / linear), `curve_bins_per_decade`,
`curve_window`, `steady_threshold`, `curve_min_count`, `curve_whiskers`.
No setting named `window` (pubsub installs a descriptor that would clobber
`QWidget.window()`).

### Automation

`efficiency_info()` callable via `qt_action('call', ...)` returning the last
window, cumulative η, curve bins, and counters, matching `spectrum_info`.


## Stages

Each stage builds, passes `pytest --pyargs joulescope_ui`, and is reviewable
on its own.  Run `python ci/translations.py --preserve-create-date
--error-if-changed` before pushing.

0. **Plan + mockup + measurements.**  DONE 2026-11-15: this plan,
   `efficiency.svg`, JS110 voltage point verified from its guide, null test
   and alignment measured (see [Stage 0 results](#stage-0-results)).
1. **Engine** DONE 2026-11-15 (`joulescope_ui/efficiency_engine.py`,
   Qt-free; `joulescope_ui/test/test_efficiency_engine.py`, 20 tests) with
   unit tests:
   integrator edge interpolation; two synthetic devices at different rates
   (e.g. 1 MHz and 999,950 Hz with drift in the time map) produce η = known
   value exactly; gaps; window grid; steady filter; curve binning; cumulative
   η; bounded memory.
2. **Refactor** DONE 2026-11-15: `widgets/plot_base.py` and `stream_worker.py`
   with tests (`test_plot_base.py`, `test_stream_worker.py`); Spectrum moved
   onto both.  Spectrum tests unchanged and passing; FFT and waterfall
   renders (markers, hover, text boxes) are pixel-identical before and after.
   The farm test is not needed for a pixel-identical refactor.
3. **Widget, readout only** DONE 2026-11-15: sources, Swap, Enable, pause
   handling, worker, status, settings, `efficiency_info`; open/close leak
   test (threads and subscriptions) like Spectrum's.  17 widget tests.
   Also in this stage:
   - `widgets/control_bar.py` `ControlBar`: the combo/toggle/button helpers
     from Spectrum's control bar, shared by both (object names unchanged).
   - `StreamWorker.update(config)`: in-place engine reconfiguration, so a
     statistics rate change keeps the cumulative totals.
   - Engine `signals` config: each display window waits for every
     subscribed stream, not just `p`.  Streams arrive in any order, so the
     optional V/I means were empty when computed on `p` coverage alone.
     The engine drops integrators for removed signals so they can't stall.
   - The readout uses height-for-width: the table moves below the main
     value when the dock is narrow.
   - Live on the bench (UI offscreen, JS220 input, JS320 output, ADP3450):
     DC null test η = 99.988%, cumulative 99.987% over 16 windows; 10 Hz
     square-wave load (10 steps per window) η = 99.976 to 99.990% over 40
     windows, cumulative 99.982%; no invalid windows or overruns; all 40
     square-wave windows correctly rejected from the curve as unsteady.
4. **Efficiency vs time plot** DONE 2026-11-15: `efficiency_plot.py`
   `TimePlot` in a splitter under the readout; `WindowHistory` ring buffer
   (Qt-free, in `efficiency_engine.py`) sized to the duration setting
   (10 s to 1 h, default 10 min) at the current rate; invalid windows are
   gaps; y autoscales with `plot_base.autoscale_hysteresis` (moved from
   Spectrum); more points than pixels reduce to a min/max pair per column
   with `spectrum_engine.column_map`/`column_reduce`; hover snaps to the
   nearest window; mouse wheel zooms into recent history, double-click
   resets.
5. **Efficiency vs output current curve** plus CSV export DONE 2026-11-15:
   `CurvePlot` (log or linear x, output current or power, min/max
   whiskers, faded under-sampled bins, hover bin details, "Waiting for
   steady load" when empty); curve settings map to the engine config and
   clear the curve when changed; Curve hold freezes the displayed curve
   while the readout and time plot continue; Export → Efficiency vs time
   (CSV) and Efficiency curve (CSV), with `export_history(path)` and
   `export_curve(path)` for automation.  `WindowHistory` now keeps P/V/I
   columns for the time series export.  Live on the bench (JS220 input,
   JS320 output, ADP3450 load steps from about 9 µA to 13 mA, 5 s each):
   every level got its own bin with 9 steady windows; step transitions
   were rejected as unsteady; bin efficiency 99.987% to 100.023%, the
   instruments' relative gain and offset.
   - Open for Stage 7: the time plot shows windows spanning a load step
     off by up to +0.18%, above the ~0.06% that time alignment alone
     predicts.  Likely the two instruments switching current ranges at
     different moments; investigate with a slower step and fixed ranges.
6. **Documentation** DONE 2026-11-15: joulescope_docs branch
   `feature/efficiency` (local, unpushed; pushing `main` deploys the live
   site): `source/theory/efficiency.md` with the wiring figure from
   `scripts/theory_efficiency_figures.py` (block diagram helpers moved to
   `scripts/diagram_util.py`, now byte-stable); UI guide revision 1.8 with
   a new chapter 6 Widgets (Matt, 2026-11-16): Meet the Joulescope UI
   keeps the basics, and `software/joulescope_ui/widgets/` documents
   Multimeter, Waveform, Trigger, Spectrum (previously undocumented) and
   Efficiency, whose screenshot is rendered from an example converter loss
   model; CHANGELOG entry here.
   Merge the docs branch only once the UI release with the widget is out.
7. **Hardware verification** (on the agent bench):
   - Null test: the bench ADP3450 drives JS220 and JS320 with currents in
     series and voltages in parallel, so η = 100% within instrument
     accuracy, both steady and with a square-wave load.
   - Resistor as the "regulator": compare to `R_L / (R + R_L)` across load
     steps.
   - Real DC-DC module swept with a load (ADP3450 or electronic load): curve
     shape vs the module datasheet.
   - Unplug/replug either instrument; 1 h soak with both streaming.
   - Farm uitest: automated null test needs a station with two instruments;
     if none exists, run it on the agent bench and record it.


## Stage 0 results

Bench (2026-11-15): ADP3450 W1 → 50 Ω termination → JS220 and JS320 voltage
inputs in parallel; W2 → series path (about 153 Ω total) through the JS220
and JS320 current inputs.  Both at 1 MSPS, autoranging.  Scripts were ad hoc
(pyjoulescope_driver + `jci_instruments.adp3450`); Stage 7 turns them into a
repeatable test.

**Null test** (1 s means, W1 = W2 = 1 V DC):

| Instrument     | I (mA)  | V (V)   | P (mW)  |
|----------------|---------|---------|---------|
| JS220-000049   | 6.51083 | 0.49782 | 3.24123 |
| JS320-8W2A     | 6.51064 | 0.49776 | 3.24073 |

`P_JS320 / P_JS220 = 0.99984` (η = 99.98%), well within instrument accuracy.

**Alignment** (W2 = 10 Hz square, 0–2 V; rising-edge UTC times from each
device's stream `time_map`, 1200 edge pairs over 120 s):

- δ(JS320 − JS220) = 24 to 162 µs, mean 105 µs, std 34 µs.
- δ wanders slowly (about a 120 s period): the host time-sync servo.  A
  30 s run showed −54 to +42 µs, so the mean is not a fixed model offset.
- Worst-case relative energy error for a full-scale step inside a window is
  about `δ/T`: 0.03% at 2 Hz (default), 0.3% at 20 Hz, 1.6% at 100 Hz.
  Steady loads are unaffected.  The steady-state filter keeps step windows
  out of the curve, so this affects only the readout and time plot.
- No per-model latency correction is planned for v1.

**JS110:** its guide (`products/js110/guide/theory.md`) states the voltmeter
measures between IN+ and IN-, before the shunt, and that the JS110 is
isolated.  The JS110 caveat therefore applies to the input position (see
[Model support](#wiring-that-removes-burden-voltage)).


## Verification summary

- Unit: `pytest joulescope_ui/test/test_efficiency_engine.py` and the full
  `pytest --pyargs joulescope_ui`.
- Interactive: run the UI with two instruments, open Widgets → Efficiency,
  confirm the readout updates at the input's statistics rate and matches
  `P_out_mean / P_in_mean` from the two Multimeter widgets for a steady load.
- Hardware tests in Stage 7, results recorded in this plan.


## Review decisions (2026-11-15)

1. **Update rate:** follow the input instrument's `statistics_frequency`.
   No widget-owned rate override.
2. **JS110:** allowed, with a warning and caveats in the status line and
   docs.  JS220/JS320 are the primary target; JS110 guidance must not add
   controls or complexity to the JS220/JS320 path.
3. **Curve x-axis:** output current is the default; output power is an
   option.
4. **Curve persistence:** none in the widget; CSV export only.
5. **Readout extras:** η, P_in, P_out, P_loss, cumulative η for now; more
   later if needed.
6. **Docs:** general knowledge in a Theory page; UI-specific guidance and
   implementation details in the UI guide page.
