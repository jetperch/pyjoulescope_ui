# Efficiency widget follow-up

## Status (2026-11-19)

Nothing here is done yet.  Item 6 (unit tests) is pure software and can
run now: `test_efficiency_engine.py` and `test_efficiency_widget.py` exist,
but none of the item 6 cases is covered.  Items
1-4 need the agent bench, and item 5 needs a farm station with two
instruments.

## Context

The Efficiency widget shipped from
[completed/efficiency.md](completed/efficiency.md) (stages 0-6 plus the
Stage 7 replug test, 2026-11-16).  It is verified on hardware: null test,
load sweep, square-wave load, a real LDO, and unplug/replug of each
instrument.  This plan holds the remaining verification, investigation and
test work, none of which blocks release.

Bench: agent machine, JS220-000049 (hub port 2), JS320-8W2A (hub port 3),
USB Insight Hub with Jetperch firmware (`uih set <port> --power off|on`),
ADP3450 for stimulus.  Run the UI offscreen
(`QT_QPA_PLATFORM=offscreen python -m joulescope_ui --tcp-server`), drive
it with `ci/uitest/cli.py`, and read `efficiency_info()`.  Close any widget
you open before closing the UI, since the UI saves views to the user's
config.


## 1. Soak

Run both instruments streaming into the widget for at least 1 hour, logging
`efficiency_info()` every few seconds.

Pass criteria:

* Windows increase at the statistics rate for the whole run, with no
  invalid windows and no overruns.
* UI process memory (RSS) is flat after the history buffer fills.
* Efficiency stays within the instruments' accuracy of its starting value
  for a steady load.

Repeat at 100 Hz statistics (the highest window rate) with the 1 hour time
plot, which fills the largest `WindowHistory`.


## 2. Switching converter sweep

Measure a real buck or boost converter module across its load range with a
programmable load (or the ADP3450 driving a load transistor), and compare
the curve shape to the module datasheet.  Then replace the docs screenshot
`joulescope_docs/source/software/joulescope_ui/media/ui_efficiency_widget.png`,
which is rendered from a simulated converter, with this real measurement.


## 3. Resistor test

Replace the converter with a series resistor R and a load R_L, and check
that efficiency follows `R_L / (R + R_L)` across several R_L values (see
`joulescope_docs/source/theory/efficiency.md`).


## 4. Load-step windows read up to +0.18%

On the ADP3450 load-step sweep, windows spanning a load step read up to
0.18% high, above the ~0.06% that the measured time alignment predicts.
Hypothesis: the two instruments switch current ranges at different moments.
Test with slower steps and with both instruments on a fixed current range.
These windows are already excluded from the curve.


## 5. Farm test

Add a uitest for the null test once a farm station has two instruments,
or run it on the agent bench under `ci/uitest` as a manual test.


## 6. More unit tests

* `EfficiencyWorker` directly: `update` (rate change keeps totals),
  `configure` (reset), backpressure with three streams.
* `CurvePlot` paint edge cases: a single bin, all bins faded, linear axis
  through zero, power x-axis.
* `export_history` with V/I shown, and an empty history.
* Engine: a statistics rate change while one instrument is missing.


## Resolved during Stage 7

* The "curve whisker past the y range" observation was not a bug: the y
  autoscale includes the whiskers with half a step of margin, so a bin's
  whisker can span almost the full plot height.
