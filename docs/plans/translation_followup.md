<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# Translation follow-up

The November 2026 audit corrected all nine catalogs using the UI source
as context.  The code changes below are done.  The native-speaker
review remains.


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


## Native-speaker review

Each catalog would still benefit from a native-speaker review in the
running UI, especially for label length and truncation, which the audit
could not see.  Consistency fixes already made: de uses "ß" throughout,
ja uses the long-vowel forms (フィルター, インジケーター, コンピューター),
and ko uses 장치 for "device".  Open questions:

- es: For Spectrum "Span", should it be "Rango" or "Intervalo"?
- it: "Gamma" vs "Scala" for the Y-axis range menu.  Min/Max hold are
  kept as English loanwords.
- el: "Widgets" is kept as a loanword.  ασφάλεια means both Safety and
  Fuse.
- ko: Confirm 누적기 for Accumulator.
- zh: Is 关 or 关闭 better for "Off"?  Check 友好名称, 监控器 and 通道.
- ar: Confirm الأدوات المصغّرة for the dockable widgets, and settle on one
  word for "waterfall".
