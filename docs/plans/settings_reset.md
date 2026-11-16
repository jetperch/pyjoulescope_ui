# Proposal: reset settings in the Settings widget

Status: PROPOSAL for discussion, 2026-11-16.  No code yet.  Follows
[widget_default_colors.md](widget_default_colors.md).


## Goal

Give the user one easy, consistent way to undo their customization:

* A widget, device or view **instance** goes back to its type's defaults
  (the class: **Widgets** → **Waveform**, **Devices** → **JS220**,
  **View defaults**).
* A **defaults** entry (the class) goes back to the values that ship with
  the Joulescope UI.

Each covers all tabs (Settings, Colors, Fonts, Defines) or one tab.


## Terminology

What other software uses, in two groups:

| Software | Back to shipped values | Back to a parent or template |
|---|---|---|
| Qt (`QDialogButtonBox`) | **Restore Defaults** | |
| VS Code Settings | **Reset Setting** (gear menu per row) | |
| JetBrains IDEs | **Restore Default Settings**; schemes: **Restore Defaults** | |
| Chrome | **Reset settings** → "Restore settings to their original defaults" | |
| Unity | | **Revert**, **Revert All** (prefab overrides) |
| Figma ¹ | | **Reset all changes** (component instance) |
| MS Office ¹ | **Reset** (ribbon: "Reset all customizations") | |
| KiCad, GIMP ¹ | **Reset to Defaults**, **Reset to default values** | |
| Joulescope UI today | **Reset to defaults** (device control), **Restore factory calibration** | |

¹ From memory, not re-checked for this proposal.

"Reset" and "Restore" are both common for shipped values.  "Restore
Defaults" is the Qt and older macOS idiom; "Reset" dominates current menus
and is already in the Joulescope UI.  "Revert" appears mostly in developer
tools for overrides and reads as "undo my edits" to most users.  "Clear"
means removing data, not settings.

**Recommendation:** use one verb, **Reset**, and name the target:

| Item | All tabs | One tab |
|---|---|---|
| Instance (a Waveform) | **Reset to defaults** | **Reset Colors to defaults** |
| Defaults (Waveform, View) | **Reset to factory defaults** | **Reset Colors to factory defaults** |
| Common (app, ui, paths): no parent type | **Reset to factory defaults** | same |

"Defaults" then always means the type's defaults that the user can edit,
matching the existing tree label **View defaults** and the docs ("widget
defaults").  "Factory defaults" means what ships with the UI, matching
"Restore factory calibration".  Keep **Clear** for data (accumulators,
markers, history, **Clear configuration**).


## UI

Three entry points, one implementation:

1. **Tree right-click** on an instance or a defaults entry: **Reset to
   defaults…** or **Reset to factory defaults…**.  Group rows (Devices,
   Widgets) get no menu.
2. **Reset button** at the right end of the tab bar
   (`QTabWidget.setCornerWidget`), a `QToolButton` with a menu:
   **Reset Colors to defaults** (the current tab) and **Reset all to
   defaults…**.  This matters because a widget's own right-click
   **Settings** opens the Settings widget with the tree hidden
   (`on_setting_target`), so the tree menu alone would miss the most
   common path.
3. **Tab right-click**: the same per-tab action as the button, for users
   who look there.

Optional, later stage: **per-setting reset** and a **modified indicator**.
Show changed rows with a bold name (VS Code uses a colored bar), and add
**Reset to default** to a row's right-click menu.  This also shows the user
what a reset would change.

**Undo instead of confirmation.**  pubsub undo already supports a command
whose handler returns `{'undo': [...], 'redo': [...]}` as one undo step.
Implement the reset as one command, so Ctrl+Z restores everything at once.
Recommendation: confirm only **Reset all…** (the "…"), not the one-tab or
one-row resets.


## Semantics

**What resets:**

* **Settings tab:** the settings it shows, which have no `hide`, `ro` or
  `tmp` flag.  Hidden settings are widget state, not configuration
  (Waveform markers and x range, view layout, window geometry), so they
  stay.
* **Colors, Fonts, Defines:** publish None to clear the overrides.  An
  instance then inherits its class; a class falls back to its style files.
  The tab shows only the active color or font scheme.  Recommendation: the
  one-tab reset clears the active scheme only, and **Reset all** clears
  every scheme.
* **`name`:** keep it.  Resetting would rename "Waveform 2" to "Waveform"
  and a device to its class name.

**Where the values come from:**

* Instance → its class's current value, `registry/<Class>/settings/<name>`.
  Do not use the instance metadata default: it is the class value copied
  when the instance was created, or the code default after a restart
  (`PubSub.load` → `_update_meta`), so it is stale either way.
* Class or Common → the metadata default from `SETTINGS`.

**Devices:** an instance reset applies to an open instrument immediately.
`js220_ctrl_widget.py` `_reset_to_defaults` first disables streaming and
returns to the idle state.  Keep that order for devices.  Also, today that
button resets to the factory defaults, not to **Devices → JS220**.  Under
the terminology above, **Reset to defaults** should use the device
defaults.  Recommendation: route the button through the new code (removing
its own reset loop) and use the device defaults.


## Implementation sketch

* One reusable function, `settings_reset(pubsub, unique_id, tabs)`, plus a
  command (for example `registry/settings/actions/!reset`, value
  `{'target': unique_id, 'tabs': [...]}`) that returns one undo step.
  Unit tests: instance → class values; class → `SETTINGS` defaults;
  hidden, `ro`, `tmp` and `name` untouched; styles cleared per scheme;
  one undo restores all.
* Settings widget: tree context menu, tab corner button and tab
  right-click.  The editors refresh from the published values.
* Device control: reuse the function (dedup).
* Docs: a "Reset settings" section in `settings.md`; CHANGELOG.

Stages, each buildable and reviewable on its own:

1. Reset function and command with tests.
2. Settings widget menus and button; UI check with `ui-remote`.
3. Device control button on the shared code; HIL check with a JS220 and a
   JS320 while streaming.
4. Optional: per-setting reset and the modified indicator.
5. Docs and CHANGELOG.


## Questions for Matt

1. Terminology: **Reset to defaults** / **Reset to factory defaults**, or
   a different pair?
2. Keep hidden widget state (markers, layout) and `name` out of the reset?
3. One-tab reset on the active scheme only, and **Reset all** on every
   scheme?
4. Confirmation only for **Reset all…**, relying on undo otherwise?
5. Change the device control **Reset to defaults** to use the device
   defaults instead of the factory defaults?
6. Include per-setting reset and the modified indicator (stage 4)?
7. Ship in 1.8.1 with the colors fix, or in a later release?
