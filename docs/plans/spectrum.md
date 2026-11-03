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
- **Streaming pause.**  Devices keep streaming when
  `registry/app/settings/signal_stream_enable` goes false; only the stream
  buffers hold.  The widget subscribes to it and drops data while paused,
  so it freezes with the Waveform.  Hold is a separate, per-widget freeze.
  The widget counts upstream gaps from sample ids before it drops any data
  (hold, pause, overrun), so its own drops never count; the engine only
  resyncs at a discontinuity.

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

Status (2026-10-30): stages 0-5 and 7 are implemented on
`feature/spectrum`, and stage 6 ran on the dev machine with the limits
listed under Stage 6.  Next phase: Stage 6b, stimulus validation with the
ADP3450, exhaustive on the JS320.  Stages 2-5 landed as one commit because they share
the widget files.

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

Results 2026-10-30, dev machine (JS220 000415 and JS320 8W2A, UI offscreen
through the TCP server, nothing connected to the inputs):

- Pass: live streaming on both devices with no overruns or gaps; JS220
  sample-rate change to 100 kHz (RBW 36.6 Hz) and back; global pause and
  resume; Hold; JS320 close (source disappears, "No signal") and reopen
  (resumes on the kept selection); Oscilloscope view plus two Spectrum
  widgets.
- CPU: the UI used 17-27% of one core with the Oscilloscope view and
  41-47% with two Spectrum widgets added (about 12-15% per widget at
  30 frames/s, mostly painting).
- 10-minute soak with both widgets: RSS flat at 695 MB after the first
  30 s, zero overruns.
- Found and fixed: a source change counted the new stream as a gap; the
  widget ignored global pause (devices keep streaming).
- Not done here: ADP3450 tone accuracy (the generator was not reachable,
  so accuracy rests on the engine unit tests), JS110, USB unplug/replug
  (the hub controller was in its ROM bootloader), the 1-hour soak, and
  the ARM and Windows farm stations.

**Stage 6b: stimulus validation (next phase).**  The Stage 6 run
proved the plumbing but not the numbers: nothing was connected to the
inputs.  This phase drives known signals into the instruments and checks
what the widget reports.  It is exhaustive on the JS320, covers the JS220
in the same format, and is a quick check on the JS110.

*Equipment and wiring*

The wiring, and how to describe it in `stations.yaml`, is in joulescope_ci
`doc/adp3450_connection.md`.  In short, the standard wiring for the JS320
and JS220 is:

- W1 direct → voltage V+.
- W2 → 100 Ω series resistor → current +.
- ADP3450 ground → V− and current −.
- DIO0 → GPI0 (JS320).
- Scope CH1 and CH2 monitor W1 and W2.

The JS110 needs only W1 → V+.  The tests read each station's wiring and
skip, with the reason, whatever it cannot support.  The USB Insight Hub
provides unplug/replug, which stays a manual step.

*Prerequisites (blocking)*

- [ ] ADP3450 reachable from the test host.  On 2026-10-30 `FDwfEnum`
  found no devices from the dev machine.
- [ ] Bench wired per the connection guide, and its `stations.yaml` entry
  added (`duts[].stimulus`), then the station updated from the dashboard.
- [ ] Current path: the 100 Ω series resistor makes the current nominally
  V/100, less the shunt and path.  The current checks compare against the
  device's own current statistics, so they do not need the absolute
  scaling.  100 Ω covers the 18 mA and 1.8 mA ranges; a second run with
  10 kΩ covers the µA ranges.
- [ ] USB Insight Hub controller back in its application firmware.  On
  2026-10-30 it enumerated as the ESP32 ROM bootloader.
- [ ] Set every ADP3450 scope channel explicitly: attenuation 1, DC
  coupling, range, and offset (dwf keeps stale settings).  Slice captures
  to `FDwfAnalogInStatusSamplesValid`.

*Amplitude references*

Compare against two independent references:

- The **device's own statistics**: the multimeter `std` of a pure sine is
  its RMS.  This is the primary amplitude reference because it cancels
  device calibration error.
- The **ADP3450 scope** reading of the generator output.  This one is
  subject to both instruments' accuracy, so allow ±1%.

Frequency accuracy is bounded by the two crystal oscillators (assume
±100 ppm combined) plus a tenth of a bin after interpolation.

*JS320 test matrix (exhaustive)*

Unless noted: voltage signal, 1 MSPS, Hann, N = 4096, amplitude scaling.

- **F1 Frequency accuracy.**  Stimulus: W1 sine 1 V rms at 10, 100, 1k, 10k,
  100k, 400 kHz.  Pass: peak f within 100 ppm + 0.1 bin.
- **F2 Low-frequency resolution.**  Stimulus: 1 Hz and 5 Hz sines, N = 2^20.
  Pass: resolved; peak within 0.1 bin.
- **A1 Amplitude, flat top.**  Stimulus: 1 V, 100 mV, 10 mV rms at 1 kHz and
  100 kHz.  Pass: peak within 0.1 dB of statistics RMS, 1% of scope.
- **A2 Amplitude linearity.**  Stimulus: 1 kHz sine stepped down from 1 V
  rms in 10 dB steps while the wavegen stays at or above 10 mV rms (-40 dB
  direct; deeper through a divider).  Pass: the spectrum tracks the
  statistics within ±0.1 dB at every step, at least four steps.
- **A3 Scalloping per window.**  Stimulus: tone at bin center and half-bin,
  all windows.  Pass: half-bin loss matches window theory ±0.1 dB; flat top <
  0.1 dB.
- **H1 Harmonics.**  Stimulus: 1 kHz square, 50% duty.  Pass: odd harmonics at
  20·log10(1/n) ±0.3 dB to n = 15; even < -60 dBc.
- **H2 Two-tone dynamic range.**  Stimulus: 10 kHz plus 13 kHz at -60 dBc
  (one custom waveform; -80 dBc is below the 14-bit wavegen's own spurs).
  Pass: small tone at -60 ±1 dBc; spur-free range recorded.
- **N1 PSD level.**  Stimulus: ADP noise, statistics std as reference.  Pass:
  integrated PSD = variance ±5%; level within ±0.5 dB across N = 1k..64k and
  every window.
- **N2 Noise floor.**  Stimulus: inputs shorted / no stimulus.  Pass: floor
  recorded per N and range as a baseline; no unexplained spurs.
- **R1 Sample rates.**  Stimulus: tone at fs/8 for each `signal_frequency`
  1 MHz..1 kHz.  Pass: fs, RBW, bin count, and peak correct after each change;
  no overruns.
- **R2 Device anti-alias.**  Stimulus: tone at 0.75·fs/2 and 1.5·fs/2 at
  100 kHz and 10 kHz rates.  Pass: records the device downsampler response
  (informational).
- **D1 Span (decimation).**  Stimulus: tone at 0.5·span for ÷2..÷1024.  Pass:
  amplitude ±0.1 dB; RBW halves per step.
- **D2 Decimator aliasing.**  Stimulus: tone just above the retained band and
  near the old Nyquist.  Pass: alias ≤ -80 dBc; roll-off band hidden.
- **C1 Current path, fixed range.**  Stimulus: W2 sine at 20% of full scale
  for each fixed range the series resistor reaches.  Pass: peak f correct;
  level within ±0.2 dB of the current statistics; 10 dB step ±0.2 dB.
- **C2 Current autoranging.**  Stimulus: W2 sine swept across range
  boundaries.  Pass: waterfall shows the switching; no crash, overrun, or gap;
  artifacts documented.
- **C3 Current range signal.**  Stimulus: as C2, signal `r`.  Pass: u4/u8 path
  shows the range-switching rate.
- **P1 Power signal.**  Stimulus: W1 at f1, W2 at f2.  Pass: `p` shows f1 ± f2
  products.
- **G1 Digital signal.**  Stimulus: GPO → GPI square at 1 kHz.  Pass: `0`..`3`
  (u1) show 1 kHz and odd harmonics.
- **W1 Waterfall timing.**  Stimulus: ADP sweep 1 kHz → 100 kHz over 10 s.
  Pass: slope matches the sweep rate ±5%; time axis labels correct.
- **W2 Burst capture.**  Stimulus: 10 ms tone burst every 1 s, 50 ms
  waterfall rows.  Pass: max detector shows the full burst level; average
  detector shows it diluted by 10/50 (-7 dB ±0.5 dB).
- **T1 Trace modes.**  Stimulus: amplitude stepped up then down.  Pass:
  max/min hold track the extremes; exponential average settles in ~N spectra;
  Clear resets.
- **X1 Range tool parity.**  Stimulus: record a JLS while the widget runs;
  Analyze → Frequency on it.  Pass: range tool PSD matches the cumulative
  average ±0.2 dB.
- **S1 Robustness.**  Stimulus: hub unplug/replug; rate change while
  streaming; JS320 + JS220 with two widgets each.  Pass: resumes on the kept
  selection; no leaks, overruns, or exceptions in the log.
- **S2 Worst case load.**  Stimulus: N = 2^20, 90% overlap, plus waterfall
  1000 rows.  Pass: no overruns; UI stays responsive.
- **S3 Soak.**  Stimulus: 1 hour with two widgets (8 hours optional).  Pass:
  RSS flat after warm-up; zero overruns; gaps only when stimulus or device
  changes.

*JS220 matrix*

Run F1, A1, A2, H1, N1, N2, R1, D1, D2, C1, C2, P1, X1, S1, and S3 with
the same criteria.

*JS110 quick check*

- Streaming at 2 MSPS with no overruns at N = 4096 and 75% overlap.
- F1 and A1 at 1 kHz and 100 kHz on voltage only.
- `ci/uitest/test_spectrum.py` passes.

*UI and platforms*

- On a real display (not offscreen), check:
  - wheel zoom, pan, and shift+wheel;
  - marker add, drag, and remove, plus the delta readout;
  - the context menus;
  - the light theme, and HiDPI scaling.
- Run `test_spectrum.py` on the Windows, macOS, and `ci_linux_arm` farm
  stations.  Record the per-widget CPU against the Stage 0 budget.

*Automation (staged 2026-10-30)*

Everything below is in place, so a wired station runs the tests with no
further work:

- `ci/uitest/test_spectrum_stimulus.py`: one test per automatable ID
  above (F1, F2, A1-A3, H1, H2, N1, N2, R1, R2, D1, D2, C1-C3, P1, G1, W1,
  W2, T1, X1, S1-S3).  Each test is marked `device` and `stimulus`, with a
  `models` marker for the devices it applies to (JS320 all, JS220 the
  subset above, JS110 F1 and A1).  The module skips at once without a
  stimulus wiring.  The S3 soak is also `slow` (`JS_UITEST_SOAK_S`, default
  3600).
- `ci/uitest/stimulus.py`: loads the wiring (`JS_UITEST_STIMULUS` from
  the runner, or `JS_UITEST_STIMULUS_FILE` + `JS_UITEST_STATION` on a
  bench) and drives the ADP3450 in DUT units.  `ci/uitest/spectrum.py`:
  widget helpers, shared with `test_spectrum.py`.
- Widget automation methods: `spectrum_info`, `value_at`,
  `spectrum_trace`, `waterfall_column`.
- joulescope_ci 0.3.23: the `jci_instruments` package (the ADP3450
  wrapper, moved out of js320/gateware/hil, and the wiring rules),
  `duts[].stimulus` in `stations.yaml`, the `stimulus` capability axis,
  and the on-demand `ui_stimulus` suite.
- Each test writes a JSON result and a widget screenshot to
  `spectrum_stimulus/` in the artifacts directory.
- Manual: hub unplug/replug (UI tests must not touch the hub) and the
  real-display UI checks.

Dry-run on 2026-10-30 (no ADP3450 reachable):

- Without wiring, all 75 parametrizations skip in 0.07 s.
- With wiring but no instrument, the JS320 test fails at setup with "adp3450
  wired to JS320-8W2A but not available: ... No connected device found".
  That path goes through the real Waveforms runtime.  The JS220, which had
  no wiring, skips.

*First hardware run (2026-11-03, agent machine, JS320-8W2A, ADP3450
SN:210018BB6E2C)*

Bench wiring: W1 into a 50 Ω terminator across V+/V− (`divider, ratio:
0.5`, measured 0.498); W2 into a 50 Ω terminator, then 49.5 Ω over 0.5 Ω
with the 0.5 Ω across the current inputs (`divider, ratio: 0.005`).
Polarity checked with DC: +1 V on W1 reads +0.498 V, on W2 reads +4.49 µA
(autorange).  DIO0 drives GPI0 (IN0).  A JS110 (001612) and a JS220
(002122) share the hub for S1.  C2 and C3 need a defined current, which a divider does not give: they ran
after the series rewire below.

Result: all 23 runnable JS320 tests pass, including the S3 one-hour soak.
Measured:

| Test | Result |
|------|--------|
| A1, A2 | spectrum vs statistics within 0.003 dB, 1 V to 10 mV rms, 1 kHz and 100 kHz |
| A3 | scalloping loss within 0.005 dB of theory for all 7 windows |
| C1 | 18 mA, 1.8 mA, 180 µA, 18 µA ranges within 0.003 dB; 180 mA skips (needs 6 V rms) |
| D1 | decimate 2 to 1024 within 0.03 dB; RBW halves each step |
| D2 | alias at 1.2 x Nyquist(d=4): -97 dBc |
| H1 | odd harmonics at 1/k; even harmonics -84 dBc |
| H2 | -60 dBc tone resolved; SFDR 87 dB |
| N1 | integrated PSD equals variance for 3 lengths x 3 windows |
| R1 | all 9 JS320 rates within 0.01 dB; fs and RBW correct; no overruns |
| T1 | max, min, average within 0.04 dB after a 0.5, 1.0, 0.25 V rms sequence |
| W1 | sweep slope 9884 to 9907 Hz/s vs 9900 expected |
| W2 | burst max hold 0.0 dB; average detector -8.2 dB |
| X1 | widget and recording agree within 0.001 dB |
| G1 | 1 kHz DIO square on GPI0: third harmonic -9.54 dBc (1/3) |
| S1 | 6 widgets on JS320, JS220, JS110 for 60 s: 0 overruns, 0 gaps |
| R2 | sinc1/2/3 droop and alias within 0.25 dB of N x 20 log10 \|sinc(f/fs)\| |
| S3 | 1 h, two widgets (v, i): 0 overruns, 0 gaps; RSS flat at 683 MiB after 5 min |

Found and fixed by this run:

- UI: the JS320 offered 500 kHz, which the firmware rejects (decimate
  factors 2 and 3 were removed).  The rejected setting ended the device
  thread and left streaming off.  Removed the option; a saved JS320 500
  kHz loads as 200 kHz (no config version change: 500 kHz never worked); a
  rejected command is now logged and the thread continues; a failed rate
  change restores streaming.
- jci_instruments: the sweep ramped for half its period, then held (the FM
  node's default 50 % symmetry).  Reconfiguring an output restarted it,
  a dropout that min hold caught; `wavegen_amplitude` changes a running
  output instead.
- Tests: R1 tests at fs/40, since the statistics are full rate and the
  JS320 decimator droops 0.22 dB at fs/8.  D2 near the input Nyquist now
  compares against the undecimated spectrum: the generator and the device
  put spurs in the retained band (a 52 kHz spur at -43 dBc from a 475 kHz
  tone, also in a raw pyjoulescope capture).  T1 uses Hann on a bin:
  flattop's negative lobes put a segment straddling an amplitude step
  outside the two levels (+0.15/-0.3 dB).  The current tests run on fixed
  ranges and measure the divider gain on each.

*JS320 series-current run (2026-11-03)*: W2 rewired through a 100 Ω
series resistor (no terminator; 1 V reads 6.587 mA, so 152 Ω with the
wavegen's 50 Ω: `series, ohms: 150`).  All 24 non-soak tests pass, none
skipped.  C1 18 mA and 1.8 mA within 0.003 dB (µA ranges need 10 kΩ).  C2
at 100 Hz (2000 range switches in 10 s): 0 overruns, 0 gaps, level within
0.002 dB of the statistics.  It first ran at 10 Hz on a 15 Hz bin, so it
found only DC-adjacent energy; it now sizes the FFT like F1.  C3: the range
signal peaks at 2f.  Full rerun with this wiring, including the S3 soak:
25 of 25 pass in 69 min.  S3: two widgets for 1 h, 0 overruns, 0 gaps,
RSS flat at 759 MiB from minute 5 to the end.

*JS220 run (2026-11-03, JS220-000049, same ADP3450 and wiring moved
over)*: 13 of 13 runnable tests pass (C2 deferred; the S3 soak was not
run).  A1/A2 within 0.004 dB; 100 kHz is flat (-0.07 dB) where the JS320
sinc1 droops 0.75 dB.  C1 18 mA to 18 µA within 0.003 dB.  R1 all 10 rates,
including 500 kHz, within 0.01 dB.  F1 tops out at 250 kHz: the JS220 FIR
passband ends near 300 kHz, so 400 kHz is below -60 dB.  The bring-up
found `outputs_off` leaving a DC output at its level (stop before reset):
fixed in jci_instruments.  Sine tests were unaffected: their idle level is
0 V.

*JS110 quick check (2026-11-03, JS110-001612, W1 moved over)*: F1 and A1
pass; A1 within 0.002 dB at 1 kHz and 100 kHz.  A1 first read 0.13 dB low:
at the JS110's 2 MHz, n = 4096 put 1 kHz on bin 2, inside the flattop main
lobe of its negative-frequency image.  A1 now keeps the tone at least 8
bins from DC, like F1 (the JS320 and JS220 then use n = 8192 at 1 kHz; not
rerun, since the change only moves the tone away from DC).

Device behavior, by design: the JS320 decimates with sinc filters, which
do not ring, at the cost of anti-aliasing.  The Signal filter setting
(Device Control) selects the order.  At 0.75 x Nyquist the droop is
-2.1, -4.2, and -6.3 dB for sinc1 (the default), sinc2, and sinc3; a tone
at 1.5 x Nyquist aliases back at -10.5, -20.9, and -31.4 dBc.  R2 checks
each order against theory.

Record the results in this plan with dates, device serials, and firmware
versions.  Then finish Stage 7 and move the plan to `completed/`.

**Stage 7: release integration.**  Add a UI release farm test (open
widget via TCP, publish settings, read peak results), user docs/help,
screenshots, changelog, and update `docs/features_future.md`.  Move this
plan to `docs/plans/completed/`.

Done: `ci/uitest/test_spectrum.py` (device test through
`SpectrumWidget.spectrum_info`, 8/9 passing runs here, then 3/3 after
moving the gap check past the startup rate apply), CHANGELOG, and
`docs/features_future.md`.  Open: user documentation on
docs.joulescope.com, screenshots, translation extraction for the new
strings, the remaining Stage 6 items, then moving this plan to
`completed/`.

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
