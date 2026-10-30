# Spectrum widget: real-time FFT and waterfall

## Context

Today, frequency analysis requires dual markers on the Waveform, then
**Analyze → Frequency** (`joulescope_ui/range_tools/frequency.py`).  That
range tool computes a one-shot Welch PSD over a fixed range from the signal
buffer and opens a static pyqtgraph plot.  It is useful for post-analysis
but not for live debugging: tuning a switching regulator, finding a
periodic wakeup, or watching a noise source change while you probe.

`docs/features_future.md` already lists "real-time FFT with max, min and
average" and "spectrogram" under **Frequency analysis**.  This plan adds a
new, independent **Spectrum** widget, opened from the **Widgets** menu, that
provides:

1. A live FFT with live/average/min/max traces, like a spectrum analyzer.
2. A spectrogram / waterfall history that shares the frequency axis.
3. Configurable span, bin count, and bin width (RBW), with the coupling
   between them made explicit.

The proposed layout is `docs/plans/spectrum.svg`.

References surveyed: Tektronix RSA/spectrum analyzer datasheets (RBW,
span, detector, trace modes), Signal Hound Spike (trace math, persistence,
peak table, linked waterfall), Red Pitaya (simple web SA: span, RBW,
window, min/max hold), Touchstone (waterfall + marker tables), and
Spectrum Lab (audio-rate FFT + waterfall, log frequency, color palettes).
The common denominator is what this plan targets; persistence (density)
displays, channel-power measurements, and trace math are future work.


## Review of the starting SVG

The layout is sound: FFT on top, waterfall below, controls in a bar that
follows the Waveform `control_location` setting.  Suggested refinements:

- **Real axes, not corner labels.**  The corner annotations (`f=0 Hz`,
  `f=max`, `intensity=max/min dB`) become a left dB axis with ticks and a
  bottom frequency axis with SI-prefixed ticks.  With a log frequency axis,
  the left edge is `f_min > 0`, not 0 Hz.
- **Pixel-exact column alignment.**  The FFT and waterfall must share the
  same plot-area left/right edges so a waterfall column sits under its
  FFT bin.  Both panes reserve the same left margin (dB axis width) and the
  same right margin (the waterfall's color bar).  Draw the frequency axis
  once, between the panes or at the bottom, not twice.
- **Color bar.**  The waterfall needs an intensity legend on the right.
  By default the color range tracks the FFT y-range (one "reference level"
  and "range" setting, like a spectrum analyzer).  An option decouples
  them.
- **Waterfall time axis.**  `t = now` at top flowing down matches Spike and
  Spectrum Lab.  This is the only orientation for now; other orientations
  can be added later.  Label it with relative time (`0 s`, `-10 s`, ...) using the
  existing `axis_ticks` relative formatting.
- **Splitter.**  Use a `QSplitter` between panes so the user can resize
  them, with settings to hide either pane.
- **Status / annotation line.**  Spectrum analyzers always show span, RBW,
  sample rate, FFT length, and average count.  Show these in the control
  bar (or a top-right overlay) so a screenshot is self-describing.  Also
  show an **overrun** indicator when processing falls behind (see
  [Threading](#threading-and-data-flow)).
- **Controls.**  The SVG shows only **Clear**.  The bar also needs
  **Run/Hold**, the signal selector, span, RBW (or bins), and average
  mode.  Less frequent settings stay in the right-click settings dialog.
- **Peak readout.**  Place the N-peak table as a translucent overlay in
  the FFT top-right corner (toggle), with peak markers drawn on the trace.


## Goals and non-goals

**Goals (v1)**

- Live spectrum of one signal from one signal stream source per widget
  instance.  Users open multiple Spectrum widgets to compare signals.  The widget
  is not added to any default view, and no "Spectrum" view preset is
  added yet.
- Traces: live (clear-write), average, max hold, min hold.  Each is
  individually shown/hidden.
- Waterfall with configurable duration.
- Frequency viewport (min/max, log/linear) shared by FFT and waterfall.
- Manual markers, delta marker, and automatic N-peak display.
- All settings persist with the view/profile like other widgets.
- Spectrum computation off the Qt event thread.

**Non-goals (v1)**

- Analysis of JLS files and paused buffers (planned as a later stage; see
  [Buffer source mode](#buffer-source-mode-later-stage)).
- Multi-signal overlay in one widget, trace math, persistence/density
  display, channel power, harmonic/THD analysis.
- Changing device sample rate from this widget.  The device
  `signal_frequency` setting is global and affects recording and the
  Waveform; the widget only displays it.


## Signal processing

### Input

Signal stream sources publish
`{device}/events/signals/{signal_id}/!data` with `sample_id`,
`sample_freq`, `utc`, `time_map`, `dtype`, `units`, and `data`
(see `CAPABILITIES.SIGNAL_STREAM_SOURCE`).  JS220 and JS320 output up to
1 MSPS for `i`, `v`, `p` (f32); JS110 outputs up to 2 MSPS.  Digital
signals (`0`–`3`, `T`, `r`) arrive packed (u1/u4) and are unpacked with
the same logic as `range_tool.rsp_as_f32` (refactor that into a shared
helper rather than copy it).

Per message the engine checks `sample_id` continuity and `sample_freq`:

- **Gap** (sample_id jump, stream restart, dropped message): discard the
  partial segment and restart segmentation.  Never FFT across a gap.
  Traces keep their history; the waterfall inserts a marker row.
- **Rate change** (user changed `signal_frequency`): full reset, because
  the frequency axis changed.

### Span, bin width, and bin count

These three are coupled: `bins = span / bin_width`.  With an FFT of
length `N` at (decimated) sample rate `fs_d`:

- span (Nyquist) = `fs_d / 2`
- bin spacing = `fs_d / N`
- RBW (equivalent noise bandwidth) = `ENBW_window × fs_d / N`
- displayed bins = `N / 2 + 1`

The control bar sets **span** (a power-of-2 decimation, labeled with the
resulting span) and **FFT length** `N` (any power of two in [64, 2^20],
matching the existing range tool's "FFT length").  The status line under
the frequency axis shows the resulting RBW and bin count.  As built, this
replaces the originally proposed RBW control: the two controls set span
and bins directly, and the RBW follows.  2^20 gives about 1 Hz RBW at
1 MSPS; narrower RBW comes from the analysis span (decimation), not a
longer FFT.

Span has two meanings and the plan keeps them separate:

- **Viewport** (`f_min`, `f_max`): which part of the computed spectrum is
  drawn.  Zoom/pan is free and does not reset averages.  Shared by both
  panes.
- **Analysis span**: reduces `fs_d` by decimating before the FFT
  (a "zoom FFT" in baseband).  For a fixed `N`, halving the span halves
  the RBW and roughly halves the compute.  Changing it resets traces.

Decimation uses a cascade of half-band FIR stages (power-of-2 factors)
implemented in numpy with block-to-block filter state.  `scipy` is not a
dependency and should not become one for this feature.  The filter must
achieve > 80 dB alias rejection over the retained band (tested).  The top
10% of the decimated band is roll-off that may hold aliases, so the
viewport excludes it whenever the span is decimated.

### Window, scaling, and units

Windows: rectangular, Hann (default), Hamming, Blackman, Blackman-Harris
(4-term), and flat-top.  numpy only provides some; define the others by
their published cosine coefficients in the engine module.  Each window
carries its coherent gain and ENBW (bins) for scaling and RBW display.

Scaling is user-selectable from the control bar:

- **Amplitude** (default): RMS amplitude per bin,
  `A[k] = sqrt(2) |X[k]| / sum(w)` (no `sqrt(2)` at DC and Nyquist).  A
  tone reads its true RMS amplitude at the peak; use flat-top for < 0.1 dB
  amplitude error.
- **PSD**: `2 |X[k]|^2 / (fs_d × sum(w^2))`, units²/Hz, matching the
  existing range tool.  Correct for noise; independent of RBW.

Y-axis: dB (default) or linear.  dB is relative to 1 signal unit, labeled
explicitly, for example `dB re 1 A` or `dB re 1 A²/Hz`.  Avoid `dBA`,
which reads as A-weighting.  Linear amplitude uses `units.py` SI
formatting (mA, µA).

**DC removal** (default on): subtract each segment's mean before
windowing.  Joulescope current usually has a large DC component whose
window leakage swamps the low-frequency bins.

### Segmentation, overlap, and averaging

Overlap is 0–90% (default 50%).  The engine accumulates input in a ring
and processes all complete segments in one batch using
`numpy.lib.stride_tricks.sliding_window_view(...)[::hop]` and a 2-D
`numpy.fft.rfft(..., axis=-1)`.  Batching keeps per-segment Python
overhead out of the hot path.

Traces:

- **Live**: the most recent segment (or the mean over the last display
  frame's segments; option), clear-write.
- **Average**: computed on linear power, never on dB (averaging dB biases
  noise by about -2.5 dB).  Modes: exponential with count `N` (after the
  first `N` segments, `a += (x - a) / N`), or cumulative until **Clear**.
- **Max hold / min hold**: elementwise on linear power.
- **Clear**: resets average, min, max, and the waterfall.

Peak search for N peaks: local maxima above a threshold, with a minimum
separation in bins, sorted by amplitude, with parabolic interpolation for
frequency and amplitude.  Plain numpy; no scipy.

### Waterfall rows

Waterfall row rate is decoupled from the FFT rate.  Each row aggregates
all segments within `row_period` (setting, default derived from duration
and pane height) using a detector: average (default) or max (peak, so
short bursts are not averaged away).  `duration = rows × row_period`.  Row
timestamps come from the input `time_map`, so time cursors can show both
relative and UTC time.


## Threading and data flow

The UI pubsub resynchronizes all callbacks onto the Qt thread, so stream
`!data` callbacks already arrive there.  The FFT work must not.

```
driver thread ─► pubsub (resync) ─► Qt thread: _on_data()
                                       │  enqueue (sample_id, fs, data)
                                       ▼  bounded, never blocks
                                 worker thread (threading.Thread)
                                       │  decimate, segment, rfft,
                                       │  traces, peaks, waterfall rows
                                       ▼  at most frame_rate (≈30 Hz)
                               Qt signal (queued) with immutable snapshot
                                       ▼
                         Qt thread: store + update(), paintEvent
```

Design points:

- **Engine is Qt-free.**  `spectrum_engine.py` is pure numpy: windows,
  scaling, decimator, segmenter, trace accumulators, peak search, waterfall
  row aggregation.  It is unit tested without a display.  The worker is a
  thin loop around it.
- **Worker: `threading.Thread`**, matching `RangeToolBase`, device threads,
  and `jls_source`.  `multiprocessing` is rejected: it adds IPC copies,
  PyInstaller `freeze_support` concerns, and slow spawn on macOS/Windows
  for no gain at these data rates.
- **Single input queue for data and commands.**  Configuration changes
  (window, N, span, Clear, Run/Hold) are posted into the same queue as data
  so ordering is guaranteed and the engine has no locks.  Each snapshot
  carries a configuration generation number; the widget drops stale
  snapshots.
- **Backpressure.**  The queue is bounded by sample count (about 1 s of
  data).  If full, the Qt-side handler drops the message (never blocks the
  Qt thread), flags a gap, and increments an overrun counter shown in the
  status line.  The engine treats the gap like any other gap.
- **Snapshots are handed off, not shared.**  The worker emits new arrays
  each frame and never mutates them afterward.  Waterfall data travels as
  deltas (new rows only); the widget owns the history.
- **Buffer ownership.**  Confirm in Stage 2 that stream `data` arrays are
  not reused by the driver after publish.  If they are, copy on enqueue
  (4 MB/s at 1 MSPS f32; negligible).
- **GIL.**  The worker shares the GIL with the Qt thread.  numpy releases
  the GIL inside large ufunc and FFT loops, so batched work leaves the Qt
  thread responsive; Python-level per-segment loops would not.  Stage 0
  benchmarks this with a GUI-thread latency probe, not just throughput.
  Free-threaded Python is not assumed.
- **Lifecycle.**  Start the worker in `on_pubsub_register`; stop it, join
  with timeout, and unsubscribe in `on_pubsub_unregister` and on close.
  The UI has had leaks from widgets that outlive their dock; add a test
  that opens/closes the widget repeatedly and checks that threads and
  subscriptions return to baseline.
- **Streaming pause.**  When `registry/app/settings/signal_stream_enable`
  goes false, the display freezes naturally (no data).  Run/Hold is a
  separate, per-widget freeze that keeps the last traces while the device
  keeps streaming.

### Compute budget

Worst case is JS110 at 2 MSPS, or 1 MSPS for JS220/JS320, with 75%
overlap.  At N = 4096, 2 MSPS, 75% overlap is about 1950 rfft/s, about
8 M points/s of FFT input.  numpy's pocketfft handles this in tens of ms
per second of data on a desktop CPU.  The budget to verify:

- < 15% of one core at 1 MSPS, N = 65536, 50% overlap on the slowest farm
  station (`ci_linux_arm`) and on a mid-range Windows laptop.
- Qt event-loop latency increase < 5 ms at the 99th percentile while the
  Waveform widget is also open and streaming.
- If the budget fails, fall back in order: reduce max overlap, cap
  segments per frame (skip segments, flag in status), then consider a C
  helper.  Do not start with C.

Measured on the dev machine (Intel Core Ultra 9 285H, Linux, Python 3.14,
numpy 2.5), `ci/spectrum_bench.py`, engine only, fraction of one core at
real time with 1000-sample messages:

| fs     | N      | overlap | decimate | load |
|--------|--------|---------|----------|------|
| 1 MSPS | 4096   | 50%     | 1        | 4.0% |
| 1 MSPS | 4096   | 75%     | 1        | 7.6% |
| 1 MSPS | 65536  | 50%     | 1        | 2.5% |
| 1 MSPS | 2^20   | 50%     | 1        | 2.5% |
| 1 MSPS | 4096   | 50%     | 16       | 2.0% |
| 2 MSPS | 4096   | 75%     | 1        | 15%  |
| 2 MSPS | 65536  | 50%     | 1        | 4.8% |

Qt event-loop latency with the worker running stayed at p99 0.21-0.23 ms
for every case, the same as without the worker.  In the widget, the Qt
thread costs about 18-20% of one core at 30 frames/s (1200 x 800,
offscreen raster, under the profiler), mostly painting.  Fixes made while
profiling:

- The segmenter re-copied its buffer on every message (24% at 2^20);
  it now appends into an amortized buffer.
- The exponential average used a matrix product, which woke OpenBLAS
  threads that spin-wait (about 20% system CPU); it is now elementwise.
- Grid lines are drawn with one `drawLines` call, and minor grid lines
  are skipped when closer than 6 px.
- Peak search evaluates at most max(64, 16 x count) candidates, which
  bounds its cost on noise.

The ARM farm station and Windows were not measured (out of scope for this
pass).


## Rendering

Use a custom `QPainter` plot, consistent with the Waveform widget, not
pyqtgraph:

- Uses `styled_widget` with its own `spectrum.*` color and font scheme
  (mirroring the Waveform colors) and reuses `axis_ticks.ticks` and
  `line_segments.PointsF` for fast polylines.
- Avoids the pyqtgraph import cost on the startup path (#206) and keeps
  the look consistent with the rest of the UI.
- OpenGL is not needed at these primitive counts.  Keep the paint code
  independent of the backing widget so `_PlotOpenGLWidget` can be adopted
  later if profiling shows a need.

FFT pane:

- Bins outnumber pixels (N = 65536 → 32769 bins vs ~1500 px).  Reduce per
  pixel column with `np.maximum.reduceat` (max for live/max traces, so
  narrow peaks never disappear) and `np.minimum.reduceat` for min hold.
  With log frequency, low-frequency bins are wider than a pixel; draw those
  as steps.
- Log frequency ticks need decade/sub-decade support in `axis_ticks`; add
  it there (shared), not in the widget.
- Y auto-scale option plus manual reference level/range.

Waterfall pane:

- History lives on the Qt thread as a ring of float32 dB rows at full bin
  resolution, capped by a memory setting (default 64 MB; e.g. 32769 bins ×
  ~500 rows).  Rows beyond the cap reduce duration, and the widget says so.
- Display image: `QImage.Format_Indexed8` with a 256-entry colormap table
  (default perceptual, e.g. viridis or inferno, plus grayscale).  New rows
  shift the image and map only the new rows: column map (precomputed for
  the viewport, linear or log) → per-pixel max → LUT index.
- Viewport, intensity range, colormap, or resize changes rebuild the image
  from history.  The rebuild is O(rows × bins) and may take ~100 ms for the
  largest N; acceptable because it only happens on user action.


## Widget and pubsub integration

New package `joulescope_ui/widgets/spectrum/`:

| File                    | Contents                                           |
|-------------------------|----------------------------------------------------|
| `__init__.py`           | exports `SpectrumWidget`                           |
| `spectrum_worker.py`    | thread + queue around the engine                   |
| `spectrum_widget.py`    | `@register @styled_widget` widget, settings, menus |
| `spectrum_plot.py`      | FFT and waterfall painters, axes, markers          |
| `spectrum_control.py`   | control bar                                        |
| `styles/`               | dark/light color schemes, fonts, qss               |
| `test/`                 | worker and widget tests                            |

The Qt-free DSP lives in `joulescope_ui/spectrum_engine.py` (tests in
`joulescope_ui/test/test_spectrum_engine.py`), not in the widget package:
`range_tool.py` and the Frequency range tool use it too, and importing the
widgets package from `range_tool.py` would create an import cycle.

Registered in `joulescope_ui/widgets/__init__.py` with
`CAPABILITIES = ['widget@']`, so it appears in the Widgets menu.  It is not
added to the default Multimeter or Oscilloscope views.

**Source and signal selection.**  Use `SourceSelector(self,
'signal_stream')` for the source (default follows
`registry/app/settings/defaults/signal_stream_source`, like other
widgets), plus a signal combobox populated from
`{source}/settings/signals/*`.  Both appear in the control bar and the
right-click menu (`SourceSelector.submenu_factory`).  Signal enable
behaves exactly like the Waveform widget: the widget lists only the
signals the source currently provides and never changes a device's
`settings/signals/{signal_id}/enable`.  If the selected signal is disabled
or the source disappears, the widget keeps the selection and shows no new
data, then resumes automatically when the signal returns.

**Settings** (`SETTINGS` dict, persisted, editable in the settings
dialog; control-bar items marked ★):

- `signal_stream_source` ★, `signal` ★
- `hold` ★ (tmp), `actions/!clear` ★
- `decimate` ★ (span), `fft_length` ★ (any power of two, 2^6 to 2^20)
- `fft_window` ★, `overlap`, `dc_remove`
- `scaling` ★ (amplitude/psd), `y_units` (dB/linear)
- `average_mode` ★ (off/exponential/cumulative), `average_count`
- `show_live`, `show_average`, `show_max`, `show_min`
- `x_log`, `f_range` (viewport, hidden), `y_autoscale`, `y_range` (hidden)
- `show_fft`, `show_waterfall`, `splitter` (hidden)
- `waterfall_duration`, `waterfall_rows`, `waterfall_detector`,
  `waterfall_memory`, `colormap`, `intensity_follows_y`, `intensity_min`,
  `intensity_max`
- `peak_count`, `peak_threshold`, `peak_excursion`
- `markers` (obj, hidden)
- `trace_width`, `frame_rate` (default 30 Hz)
- `control_location` (off/top/bottom), shared with the Waveform through
  `widget_tools.CONTROL_LOCATION_SETTING` and `control_location_apply`

pubsub installs a data descriptor on the class for each setting, so a
setting name must not collide with a QWidget method: the window setting is
`fft_window`, not `window`.

All user strings use `N_()`.  Settings are scriptable through pubsub and
therefore through the TCP server, which the UI release farm uses.

**Interaction.**  Mouse wheel zooms frequency about the cursor (both
panes), shift+wheel zooms the y-axis (and turns off autoscale), drag pans,
and double-click resets the viewport and y autoscale.  Hovering shows
frequency and each visible trace's value; over the waterfall it also shows
time and the row value.  Markers: right-click → add marker, add marker at
the nearest peak, remove, or clear; drag to move.  With two markers, a
delta line reads Δf and ΔdB.  Right-click also offers trace, view, y-units,
source, and signal submenus, Clear, and Settings, per `docs/plugin.md`.
Peaks use a spectrum analyzer's peak excursion (default 10 dB) so noise on
a tone's skirt is not listed, and they are limited to the viewport.

### Relationship to the Frequency range tool

The existing `FrequencyRangeTool` and the new engine compute the same
Welch PSD.  Per the "write once" rule, Stage 1 refactors the range tool to
call `spectrum_engine` for windowing, segmentation, and scaling.  The range
tool stays (it analyzes arbitrary marker ranges and JLS files).  A later
option could open its result in a Spectrum widget instead of the
pyqtgraph popup.


## Buffer source mode (later stage)

A second mode reads from a `signal_buffer` source via `!request`, like the
range tools, which works for JLS files and paused captures:

- **Range spectrogram**: compute the waterfall over the Waveform's
  visible x-range or dual-marker range, with the time axis in file time.
- **Follow**: poll the newest samples of a live buffer source, which
  would let one widget serve both live and paused data.

This mode needs a request/response path from the worker
(`RangeTool.request` already does this off-thread) and progress
reporting for long ranges.  It is deliberately after v1 so live mode is
proven first.


## Staged implementation

Work on a feature branch (`feature/spectrum`).  Each stage builds, passes
`python -m unittest`, and is reviewable alone.

Status (2026-10-30): stages 0-5 are implemented on `feature/spectrum`.
Stages 2-5 landed as one commit because they share the widget files.
Stage 6 ran partially on this machine (see Stage 6).

**Stage 0: engine and benchmark.**
`spectrum_engine.py` with windows (+ENBW, coherent gain), amplitude/PSD
scaling, batched segmentation with overlap, gap/rate-change handling, trace
accumulators, peak search, and waterfall row aggregation.  Tests:

- Tone at a bin center and between bins: amplitude within 0.1 dB with
  flat-top, and frequency within a bin after interpolation.
- White noise: mean PSD equals `σ² / (fs/2)` within tolerance (Parseval),
  for each window.
- Overlap segment counts, block-boundary invariance (same result
  regardless of how input is chunked), gap reset, DC removal.
- Average mode math on linear power; min/max holds.
- Peak finder: separation, threshold, ordering.

Add a benchmark script (`ci/` or `joulescope_ui/widgets/spectrum/bench`)
that reports throughput and Qt event-loop latency with a background
worker; record results in this plan.

**Stage 1: dedup range tool.**  Refactor `FrequencyRangeTool` onto the
engine and move the u1/u4 unpacking out of `rsp_as_f32` into a shared
helper.  Existing range tool tests must pass unchanged; add a test that
the refactored PSD matches the previous implementation numerically.

**Stage 2: worker and minimal widget.**  `spectrum_worker.py`, widget
registration, source/signal selection, live trace only, linear axes,
control bar with Run/Hold and Clear, `control_location`.  Tests: worker
start/stop/ordering/overflow with a synthetic feeder, widget open/close
leak test, and a widget test with a fake stream source publishing a tone.

**Stage 3: FFT pane complete.**  Average/min/max traces, dB/linear,
amplitude/PSD, log frequency (with `axis_ticks` extension and tests),
viewport zoom/pan, y autoscale, status line, manual and delta markers.

**Stage 4: waterfall.**  History ring, Indexed8 rendering, colormaps,
color bar, shared viewport, splitter, duration/detector/memory settings,
gap rows, time readout.  Tests for column mapping (linear/log), history
cap, and rebuild correctness.

**Stage 5: peaks and analysis span.**  N-peak overlay table and markers;
half-band decimator cascade with state; span/RBW-driven `N`.  Tests for
decimator alias rejection, passband flatness, and block-boundary
invariance.

**Stage 6: hardware verification (on-device).**  JS220 and JS320 at
1 MSPS, JS110 at 2 MSPS:

- ADP3450 W1 sine into voltage (and W2 through 100 Ω into current) at
  several frequencies and amplitudes; check peak frequency and amplitude
  against the generator.  Set ADP3450 attenuation, coupling, and range
  explicitly.
- Sample-rate change, stream pause/resume, device unplug/replug while
  open, two Spectrum widgets plus Waveform open simultaneously.
- CPU and UI responsiveness against the Stage 0 budget on the farm
  stations, including `ci_linux_arm`.
- 1-hour soak for memory growth.

**Stage 7: release integration.**  Add a UI release farm test (open
widget via TCP, publish settings, read peak results), user docs/help,
screenshots, changelog, and update `docs/features_future.md`.  Move this
plan to `docs/plans/completed/`.

**Stage 8 (optional): buffer source mode.**  See above.


## Decisions

Resolved with Matt on 2026-10-30:

1. **Scaling**: user-selectable in the control bar, amplitude or PSD.
   Amplitude is the default.
2. **Signal enable**: same as the Waveform widget.  List only the signals
   the source provides; never enable or disable device signals.
3. **One signal per widget** for v1.
4. **FFT length**: any power of two up to 2^20.
5. **Waterfall orientation**: newest at top only, for now.
6. **Default view**: no Spectrum view preset yet.
