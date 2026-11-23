<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# Translation follow-up

The November 2026 audit corrected all nine catalogs using the UI source
as context.  These items remain.


## Code changes

1. **Message context for shared msgids.**  Some English words have two
   roles that need different translations.  The UI has no `pgettext`
   support, so add a context-aware `N_` variant, and teach
   `ci/translations.py` to extract it.
   - "View": the View menu and the error-window button (de Ansicht vs
     Anzeigen, fr Vue vs Afficher).
   - "Open": the File menu action and the serial-port Status column
     ("Open"/"Closed"), where ja, el, and others need a state, not an
     action.
2. **Untranslated option values.**  The IRF dropdowns show `interp`,
   `mean`, and `off` untranslated, and the Waveform source menu shows
   `default`.  The help text now quotes these in English.  Either
   translate the displayed labels, or keep them English on purpose.
3. **Combo box text matching.**  `comboBoxConfig` now keeps the
   selection by index.  Other widgets that store `currentText()` (for
   example the trigger widget `output_signal`) still rely on text and
   should store values instead.


## Native-speaker review

Each catalog would still benefit from a native-speaker review in the
running UI, especially for label length and truncation, which the audit
could not see.  Open questions:

- de: The human-reviewed entries use the Swiss "ss" spelling
  (Anschliessen), while the rest of the catalog uses "ß".
- es: For Spectrum "Span", should it be "Rango" or "Intervalo"?
- it: "Gamma" vs "Scala" for the Y-axis range menu.  Min/Max hold are
  kept as English loanwords.
- el: "Widgets" is kept as a loanword.  ασφάλεια means both Safety and
  Fuse.
- ja: フィルタ/フィルター and インジケータ/インジケーター are mixed.
- ko: 디바이스 and 장치 are mixed for "device".  Confirm 누적기 for
  Accumulator.
- zh: Is 关 or 关闭 better for "Off"?  Check 友好名称, 监控器 and 通道.
- ar: Confirm الأدوات المصغّرة for the dockable widgets, and settle on one
  word for "waterfall".
