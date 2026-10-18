# uitest: interactive waveform tier skips on Wayland benches

## Context

Found 2026-10-18 while adding `test_fill_with_offscreen_spike` (#352).
On the agent machine (GNOME Wayland, three Joulescopes on the USB hub), every
test in `ci/uitest/test_waveform_interactive.py` skips with "waveform plot
not rendering (no GL/compositor)", even though the GL plot does render.
These skips are silent, so the tier gives no coverage on such benches.

Causes observed:

1. `rendered_waveform` uses a right-click y-axis menu as its render probe
   (`UiSession.is_waveform_rendered`).  On native Wayland, the synthetic
   click is delivered (`ok: True`), but no QMenu opens.  A Wayland popup
   needs a real input-event serial.
2. With devices attached, the auto-opened live waveform and Multimeter
   share the view.  Also, the 580x560 Multimeter view geometry is restored
   a few seconds after the fixture's `resize_window(1600, 900)`.  The file
   plot ends up about 759x172 px.
3. Grabbing `_PlotOpenGLWidget` directly returns a stale frame.  The GL
   plot may also skip repainting after `update()` while the window is
   occluded; a resize forces a fresh frame.
4. Under XWayland (`QT_QPA_PLATFORM=xcb`), one test passes and the others
   error with server `RuntimeError`s, intermittently.

Farm status, latest `ui_release` run (2026-10-17, coordinator 0.3.7):

| Station | Interactive tests |
| --- | --- |
| ci_win, ci_win_arm | all 5 pass |
| ci_mac | 3 pass; 2 skip after the render probe's 15 s timeout (flaky) |
| ci_linux | all 5 skip: "no display"; runner has no `DISPLAY`/`WAYLAND_DISPLAY` |

The runner (`joulescope_ci/runner/pytest_suite.py`, `WORKER_SPECS['ui']`)
never sets `JS_UITEST_DISPLAY`.  The rendered tests do not need it, since
`rendered_waveform` always launches on-screen.

## Plan

1. Replace the menu-based render probe with a non-input probe: query the
   painted y geometry over the TCP server, or compare a forced-repaint
   grab against the background color.
2. In `rendered_waveform`, close the live-device waveforms and resize
   again after the devices open, so the file plot gets the full window.
3. Make `test_waveform_interactive` fail, not skip, when
   `JS_UITEST_DISPLAY=1` is set and the probe reports no rendering.
   Silent skips hid this tier.
4. Run the menu tests under XWayland on Wayland benches, or move them to
   uinput real-input injection.  Root-cause the XWayland `RuntimeError`s.
5. Give the ci_linux runner a graphical session (or Xvfb with Mesa GL),
   so the Linux GL path is covered.  #352 was Linux-reported.

## Status (2026-10-18)

Steps 1-4 are done and verified on the agent machine (GNOME Wayland, three
devices attached).  `test_waveform_interactive` passes all 6 tests in 10 of
10 runs, in about 39 s.  Before, it skipped all of them in about 2 min.

1. Done.  `WaveformWidget.plot_render_info()` reports an on-screen paint
   count and the painted plot rows.  `UiSession.is_waveform_rendered()`
   reads it via the `call` action, with no input events.
   `UiSession.wait_for_paint()` waits for a fresh frame.
2. Done.  The fixture picks the waveform that `open_file` created, closes
   the earlier ones, and calls `UiSession.resize_window_settled()`.  That
   resizes until the size holds.
3. Done.  Both "no display" and "not rendering" fail under
   `JS_UITEST_DISPLAY=1`.
4. Done, using XWayland.  The fixture sets `QT_QPA_PLATFORM=xcb` on
   Wayland unless the caller sets it.  On native Wayland, the menu tests
   still fail as expected, and an occluded window can miss its first
   frame.

   The XWayland `RuntimeError`s were root-caused.  The bridge's 5 s wait
   for the Qt main thread timed out, and `str(TimeoutError())` is empty.
   The bench's screen was blanked (GNOME idle blank after 15 min without
   real input).  With nothing presented, each OpenGL buffer swap waited
   on vblank: the interactive file took 116 s, against 38 s with
   `vblank_mode=0`.  The Multimeter's `_InnerWidget._on_statistics` called
   `repaint()`, a synchronous paint, on every statistics update, so these
   slow swaps blocked the main thread for 5 s or more.  py-spy showed this
   as the dominant UI main-thread stack.  The full `-m "not device"` tier
   failed 4 of 4 runs with `repaint()` and passed 2 of 2 with `update()`,
   but stalls still occurred with `update()` alone.  `_new_session` now
   disables vsync for on-screen Linux sessions (`vblank_mode=0`,
   `__GL_SYNC_TO_VBLANK=0`).  With both changes and a blanked screen, the
   interactive file passes in 38 s and the full tier in 92 s, with no
   stalls.

   Also fixed: the bridge now names the timeout, and
   `_suppress_startup_dialogs` no longer returns before the dialog
   appears.  It still misses Getting Started on XWayland, where the
   dialog does not become `activeWindow()`.  Getting Started then stays
   open for about 5 s, which is harmless now.  `test_preferences` no
   longer leaves its config on disk for later tests.
5. Code done and verified locally, not deployed.  joulescope_ci 0.3.8
   starts an Xvfb display for the `ui` worker on a Linux runner without
   one (`PytestSuiteSpec.virtual_display`).  It also sets
   `QT_QPA_PLATFORM=xcb`, because with `XDG_SESSION_TYPE=wayland`, Qt
   otherwise picks the desktop's Wayland socket.  Verified 2026-10-18 on
   the agent machine with every session variable removed.  The runner's
   own `_virtual_display()` started Xvfb on `:2`, and the UI rendered
   with `llvmpipe`.  All 6 interactive tests passed in 39 s, and Xvfb was
   cleaned up afterwards.  With both #352 fixes disabled, the fill test
   fails on this path (5909 vs 77079 px).

   Xvfb found a UI bug: after the plot layout changed, the first paint
   drew the old row heights.  A static file view never repainted, so its
   rows stayed at the 20 px minimum.  `_plot_paint` now recomputes
   geometry after `_plots_height_adjust()`.

   joulescope_ci 0.3.8 was pushed 2026-10-18 (5ba7f20), with Xvfb
   installed on ci_linux.  Checks for the next `ui_release` run:
   * ci_linux runs the interactive tests instead of skipping them.
   * The new probe fixes the ci_mac render-probe timeouts.
