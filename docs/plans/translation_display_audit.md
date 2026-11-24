<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# Translation display audit

Status: stages 1 to 8 done on 2026-11-24.  Native-speaker review (stage 7
packs) is waiting on reviewers.  See [Results](#results).

The catalogs are now correct as text (see
[translation_followup.md](translation_followup.md)), but nobody has looked
at most screens in most languages.  This plan finds the display problems
that catalog review cannot see:

- **Truncation.**  Text clipped or elided because a label, button, tab, or
  column header is too narrow.
- **Hardcoded English.**  Text that never went through `N_()`.
- **Missing glyphs.**  Boxes ("tofu") where the platform font lacks
  CJK, Greek, or Arabic glyphs.
- **Right-to-left layout.**  Arabic mirroring problems, especially in
  custom-painted widgets and direction-sensitive icons.
- **Context errors.**  Text that is correct in isolation but wrong on
  screen: a verb used as a status, a label whose help text quotes a
  different word.

Settings rows keep showing the setting key in English by design.  The
audit ignores them.


## Building blocks that already exist

- `ci/uitest` launches the UI with `--tcp-server` and drives it.
  `UiSession.qt_screenshot()` returns a PNG of any widget, and
  `qt_inspect()` returns the widget tree with geometry and properties.
- A language is selected with `~/.joulescope/language.txt` (Help →
  Language writes the same file), so `HOME=<scratch dir>` gives an
  isolated profile per language.
- On Linux, `bwrap --dev-bind / / --tmpfs /dev/bus/usb --tmpfs
  /sys/bus/usb/devices` hides attached instruments.  The audit can then
  run on a bench machine without touching its Joulescopes.
- The uitest asset `js110_evk1_10s_0_7_0.jls` provides data for the
  Waveform, range tools, and file views without a device.
- `joulescope_ui/test/test_translations.py` already checks placeholders,
  markup, line breaks, signal-name collisions, and context entries.


## Stages

Each stage builds, passes the existing tests, and is useful on its own.

### Stage 1: inspector support for truncation

Extend `_widget_info()` in `joulescope_ui/tcp_server/qt_inspector.py` to
report, for text widgets (`QLabel`, `QAbstractButton`, `QComboBox`,
`QTabBar` tabs, `QHeaderView` sections, `QGroupBox`, dock titles):

- the displayed text,
- `sizeHint()` and `minimumSizeHint()`,
- the word-wrap flag, and
- for tab bars and header views, the per-item text and rectangle.

Add a pure function `find_truncation(tree)` in `ci/uitest`.  It flags
visible text widgets where the needed width exceeds the actual width.
Unit-test it with a synthetic tree.  Also check why
`resize_window_settled()` does not resize the offscreen window.  The
November screenshots came out 798 px wide instead of 1280.

### Stage 2: pseudo-localization

Add a test-only pseudo-locale (`qps`).  It is generated at run time from
the POT, never committed.  Each string:

- is wrapped in `⟦…⟧`,
- has accented letters, and
- is padded about 40 % longer, the typical German and French growth.

Placeholders, markup, and `\n` stay intact.  Load it with an environment
variable that adds a locale directory (`JOULESCOPE_UI_LOCALE_PATH`),
handled in `joulescope_ui/locale/__init__.py`.

Pseudo-localization finds most problems without knowing any language:

- visible text without `⟦` is hardcoded English,
- truncated `⟦…⟧` text shows a label that will not fit long translations,
- a missing `⟧` shows text cut by code (string slicing, eliding).

### Stage 3: screen catalog and capture

Write `ci/uitest/display_audit.py`, a CLI that walks a fixed list of
screens for one language at two window sizes, 1280×720 and 1920×1080.
At each screen it saves a screenshot, the inspector tree, and a report of
truncated text and text identical to its English msgid.  The screen list
is data, so it can grow:

- Views: Multimeter, Oscilloscope, File (with the JLS asset open).
- Every widget from the Widgets menu, docked once.
- Menus: File, View, Widgets, Tools, Help, and their submenus.
- Waveform context menus: plot, x-axis, y-axis, markers, summary.
- Dialogs: Settings for each widget, View Manager, Language, About,
  Getting Started, Changelog, Credits, Report Issue, serial port,
  signal record config, statistics record config, record stop.
- Range tools on the JLS with dual markers: Histogram, CDF (both
  modes), Frequency, Max window, and USB Inrush when USBET is installed.
- The sidebar flyouts.

The runner loops over all locales plus `qps` and `en`.  It builds one
HTML contact sheet per screen with the languages side by side, so a
reviewer can compare a screen across languages at a glance.

### Stage 4: device screens on a bench

Some screens need an instrument: Device Control (JS110, JS220, JS320),
the live Multimeter and Value readouts, fuse configuration, current
limits, GPIO, firmware update, and calibration.  Run the Stage 3 runner
on a joulescope_ci bench, with the device screens enabled.  Stay
read-only: no firmware update, no calibration writes, and leave the fuse
and power settings unchanged.  Bench time is short, so capture all
languages in one UI session per language and model.

### Stage 5: fonts on each platform

Glyph coverage depends on the operating system, not the catalog.  Add a
small check that runs on Windows, macOS, and Linux.  For each locale it
loads the UI default font and checks, with `QFontMetrics.inFont()`, that
every character in every msgstr is covered or has a fallback font.
Run it on the CI farm stations, one per platform, and in the Flatpak,
whose font set is minimal.  Report missing characters by locale.

### Stage 6: right-to-left review

Capture every Stage 3 screen in Arabic and review it by eye:

- layout mirroring,
- direction-sensitive icons (arrows, play, the sidebar flyout side),
- custom-painted widgets (Waveform, Value, Spectrum, Efficiency, Fuse),
  which must keep time and frequency increasing left to right,
- text alignment in tables, and
- mixed Arabic and Latin text: units, numbers, and the colon in labels.

Fix the problems found with `setLayoutDirection(LeftToRight)` on the
specific widget, not by disabling RTL globally.

### Stage 7: review packs for native speakers

Generate one HTML review pack per language from the Stage 3 and 4
output: every screen, with the open questions for that language from
`translation_followup.md`, and a way to comment on each screenshot.
Send packs to the distributors that cover the language (Welectron,
YOTAVIS, NetScope Solutions, Shenzhen LeaderX), and to paid reviewers
for es, ja, ko, and ar.  Record each answer as a catalog change or a
closed question.

### Stage 8: continuous checks

Add the pseudo-locale run (Stages 2 and 3, hardware-free screens only) to
the `ci/uitest -m "not device"` job.  It fails on new hardcoded English
or new truncation in the pseudo-locale.  The real-language captures stay
a release-time task: run Stage 3 for all languages before each release
and attach the contact sheets to the release checklist in
`docs/release.md`.


## Out of scope

- Translating the developer widgets (PubSub Explorer, Publish Spy,
  Profile, Timesync) and the demo widgets.  They stay English.
- Settings row names, which stay as English setting keys.
- Firmware and device strings that come from pyjoulescope_driver.


## Results

The final audit on 2026-11-24 captured 98 screens per locale (49 screens at
1280×720 and at 1920×1080) for en, qps, and all nine languages: 1,078
captures with no errors, no truncated text, no untranslated text, and no
blank buttons.  The device screens (live Multimeter, Device Control,
Device Information, and the JS220 and JS320 settings pages) were captured
on a JS220 and a JS320 in every language at 1280×720.

Problems the audit found and fixed:

- **Hardcoded English:** the Waveform control bar, the Frequency and CDF
  dialogs, the annotation editor, several settings tooltips, the plugin
  warning, the About labels, and the help window titles.
- **Qt's own text:** dialog buttons and the docking panel menus and
  buttons were English in every language.  `locale/qt_translator.py` now
  loads Qt's `qtbase` translation and answers Qt `tr()` lookups from the
  gettext catalog.  A first version blanked English dialog buttons by
  returning an empty string; the blank-button check now guards this.
- **Fonts:** Qt drew Chinese with Japanese glyph shapes on Linux.  The UI
  now sets per-language fallback fonts.
- **Right-to-left:** Arabic used a left-to-right layout, and its plots
  showed "-600" as "600-".  A QPainter takes its direction from the
  application, not the widget, so the plot painters now set it.

Found but not fixed:

- The range tools fail on JLS v1 files, before this work too.  See
  [jls_v1_range_tools.md](jls_v1_range_tools.md).
- Glyph coverage was checked on Linux only.  Run
  `ci/uitest/font_coverage.py` on Windows, macOS, and in the Flatpak.
- The Nuitka build may not bundle Qt's `qtbase_*.qm` files.  Without them,
  Qt dialog buttons fall back to English.  Check the Windows build.
- pyqtgraph plots (fuse, range tool results) mirror their axis side in
  Arabic.  The numbers are correct, and this is a valid right-to-left
  layout.
