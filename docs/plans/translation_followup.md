<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# Translation follow-up

The November 2026 audit corrected all nine catalogs using the UI source
as context.  The code changes and the terminology research below are
done.  Native-speaker feedback is the remaining step.


## Code changes (done 2026-11-23)

1. **Message context for shared msgids.**  Added `C_(context, text)`
   (`gettext.pgettext`), exported from `joulescope_ui`, with the babel
   keyword `C_:1c,2` in `ci/translations.py`.  The error-window button uses
   `C_('verb', 'View')`, and the serial-port Status column uses
   `C_('state', 'Open')`.  Use `C_` whenever a word needs a different
   translation in a different role.  Call it through an alias in tests,
   or babel extracts the test strings.
2. **Untranslated option values.**  The `default` source entry now shows
   `C_('source', 'default')` through `source_selector.source_name()`.  The
   source menu, Waveform, Value, Spectrum, and Efficiency all use it, and
   the help text quotes the translated label.  The JS110 IRF options
   (`off`, `mean`, `interp`, `NaN`) stay in English on purpose: the
   displayed text is also the stored setting value, and it matches the
   pyjoulescope API and the documentation.
3. **Combo box text matching.**  The Histogram dialog now stores the
   normalization id as item data instead of looking up the translated
   label.  The Value widget checks the selected source id, not the
   displayed name.  The remaining `currentText()` users store untranslated
   data (GPO names, device ports, baud rates, FFT sizes, time formats).


## More code changes (done 2026-11-23)

4. **Hardcoded English.**  An AST scan found user-visible strings that were
   never wrapped in `N_()`, so no catalog could translate them: the Waveform
   control bar (Markers, X-Axis, Min/Max, Signals), the Frequency and CDF
   dialogs, the annotation editor, the device information title, and the
   tooltips for several visible settings.  They are wrapped and translated.
   The developer widgets and demo widgets stay English on purpose.
5. **More contexts.**  `C_('state', 'Hold')` for the Spectrum and
   Efficiency status line (held, not the button verb), and
   `C_('clock', 'Time')` for the record-stop dialog and the serial console
   (clock time, not duration).
6. **Right-to-left layout.**  Qt only sets right-to-left from its own
   translator, so Arabic showed a mirrored left-to-right layout.  The UI
   now sets the layout direction from `locale.is_rtl()`.  Custom-painted
   plots are unaffected.


## Terminology research (done 2026-11-23)

Each language was checked against localized test-instrument manuals and
application notes (Rohde & Schwarz, Rigol, Siglent, Keysight, Promax,
PeakTech, Fluke, Hioki, Yokogawa, Anritsu), platform terminology
(Microsoft, Qt, GTK, Android), and standards bodies.  This changed 210
entries, each with a cited source, and verified about 190 key terms.
Examples: Spanish and Italian keep "Span" like their R&S manuals;
Japanese and Korean use the power-meter term 積算/적산 for the
accumulator; German uses Änderungsprotokoll and Mitwirkende; French uses
the official "modules d'extension" for plugins; Chinese uses 扫宽 for span
as Rigol and Siglent do.  Greek and Arabic have no localized instrument
UIs online, so they rest on university course material and platform
terminology, which is weaker evidence.


## Open questions

- **Settings row names.**  The Settings widget labels each row with the
  raw setting key (for example `target_power`), in every language; only
  the tooltip is translated.  Showing the translated brief instead would
  localize the widget, but it changes the existing design.
- **Label length.**  Screenshots of the Multimeter and Oscilloscope views
  in all nine languages show no truncation that English does not also
  have.  Other dialogs were not captured.
- **Preference calls** (all defensible either way):
  - es: "Plugins" vs Microsoft's "Complementos"; "Cascada" vs
    "Espectrograma".
  - it: "marcatore" vs the R&S Italian loanword "marker".
  - fr: "fréquence d'échantillonnage" vs R&S "taux d'échantillonnage".
  - de: "Statistikfrequenz" vs "Statistikrate".
  - el: Span and Range are both "Εύρος", in different widgets.
  - ko, ar: Hold and Pin share one word, in different widgets.
  - zh: 友好名称 vs 显示名称 for "Friendly name".
  - ar: راسم الذبذبات vs راسم إشارة for Oscilloscope.


## Native-speaker feedback (proposal)

1. **Distributors first.**  Welectron (DE/AT), YOTAVIS (CH: de, fr, it),
   NetScope Solutions (GR, CY), and Shenzhen LeaderX (CN) are native
   speakers who know the product.  Send each one a short request:
   install the UI, choose Help → Language, restart, and spend 20 minutes
   in the main views.  Point them to the open questions for
   their language.
2. **Make reports easy.**  Add a "Report a translation problem" link,
   or describe it in the existing Report Issue form, so that the report
   includes the language and the screen.  Treat corrections like code:
   one PR or issue per language.
3. **Ask the community.**  A forum post asking for one reviewer per
   language costs nothing; the 2024 German review came from a user.
4. **Paid review for the rest.**  es, ja, ko, and ar have no distributor
   coverage.  A professional technical review of about 6,500 words per
   language costs roughly USD 300 to 600 each.  Ask for an
   instrument-domain reviewer.
5. **Optional: a translation platform.**  Weblate (free hosting for
   open-source projects) reads these .po files directly and lets
   reviewers suggest changes in context.  This is only worthwhile if
   volunteers appear.
