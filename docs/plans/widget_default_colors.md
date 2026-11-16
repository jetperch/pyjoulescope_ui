# Investigate: edit widget default colors in the Settings widget

Status: DONE 2026-11-16 on branch `fix/widget_default_colors` (live
inheritance approved).  Verified in the running UI.  Do not commit
to `main`.


## Problem

Forum topic 1153 (https://forum.joulescope.com/t/1153): a user changed the
Waveform signal colors on one widget and wants the same colors for every new
Waveform widget.  In UI 1.8.1 that is impossible from the UI:

* Side Bar **Settings** → **Widgets** → **Waveform** (the class, not an
  instance) shows the **Colors** tab empty.  **Fonts** and **Defines** are
  empty too.
* Selecting a Waveform instance below it shows all colors, and editing works.

Reproduce: start the UI, open the Side Bar Settings, select
**Widgets** → **Waveform**, select **Colors**.


## What we know

`joulescope_ui/widgets/settings/settings_widget.py`:

* `ColorEditorWidget.object` (about line 247), `FontEditorWidget` (about
  344) and `StyleDefineEditorWidget` (about 415) return early when
  `obj.style_obj` is missing or None.  Classes never get a rendered
  `style_obj`: `registry/WaveformWidget/settings/style_obj` is None at run
  time, while each instance has one.
* The editors then use `cls = obj.__class__`, which is `type` when `obj` is
  a class, so removing the early return alone is not enough.
* `_on_change` already publishes to `{topic}/settings/colors` keyed by color
  scheme, which works for a class topic as well.

`joulescope_ui/styles/manager.py`:

* `_render_cls` already merges `registry/<Class>/settings/colors`, fonts and
  style_defines over the class style files, and `_render_obj` applies the
  class vars to every instance before the instance overrides.  So the render
  side appears to support class defaults; verify it.
* `cls._style_cls` is only loaded on demand (`_load_style_for_class`), so it
  may be None for a class with no instance yet.
* `styled_widget` wires `on_cls_setting_colors` to publish a render of the
  class.  `StyleManager._render` for a class iterates
  `{class topic}/children` filtered by the active view.  Check that this
  actually re-renders the class's instances (instances may be listed under
  `/instances`, not `/children`).

Docs: joulescope_docs `source/software/joulescope_ui/settings.md`
(`ui-settings-colors`) has a note describing this limitation.  Update or
remove it with the fix.


## Questions to answer

1. What minimal change lets the Colors, Fonts and Defines tabs edit class
   defaults?  Prefer reusing `_load_style_for_class` / `_render_cls` over new
   code.
2. Semantics: widget *settings* defaults are copied when an instance is
   created, so they do not change existing widgets.  Class *colors* are
   merged at render time, so they would change existing widgets that have
   no instance override.  Confirm which behavior the code gives, and
   recommend one.  Matt decides.
3. Do class color changes persist across restart (saved in
   `joulescope_ui_config.json`) and survive **File** → **Config** →
   **Export** / **Import**?
4. Does the same fix apply to device classes and views (**View defaults**)?
5. Do the light and dark color schemes each keep their own class overrides?


## Deliverable

A short findings write-up with the proposed change, then, after Matt
approves, the fix with unit tests (see `joulescope_ui/styles/test/
test_manager.py`) and a CHANGELOG entry.  Verify in the running UI with the
`ui-remote` skill: set `waveform.plot_p` on the Waveform class, add a new
Waveform widget, and confirm the new color; restart and confirm it persists.
Never run `ci/uitest/harness.py::UiSession` against the real UI config: it
clears the config on exit.  For automated runs, set `HOME` to a temporary
directory first, as `joulescope_docs/scripts/ui_settings_screenshots.py` does.


## Findings (2026-11-16)

Verified by reading the code and with a pubsub-only experiment (a
`styled_widget` class, class colors published, then an instance registered).

**Why the class tabs are empty.**  All three editors return early when
`obj.style_obj` is None, which is always true for a class.  Past that, they
use `obj.__class__` (`type`) and `cls._style_cls`, which is None until the
first instance renders.

**Render side.**  `_render_cls` already merges `registry/<Class>/settings/
{colors,fonts,style_defines}` over the class style files, and `_render_obj`
applies the class vars before the instance overrides.  This works, with two
defects:

1. `StyleManager._render` for a class iterates `{class}/children`.  Classes
   have no `children` topic (only `instances`), so `query` raises KeyError
   and a class color change never re-renders anything.  Existing widgets pick
   it up only at the next full render (view switch or restart).
2. `colors`, `fonts` and `style_defines` lack the `noinit` flag, so
   `_register_settings_create` copies the class value into each *new*
   instance's own override setting.  The instance then shares the class
   dict object (aliasing) and is frozen: later class edits never reach it.
   `style_settings()` documents the opposite intent: these settings "contain
   the values that have been changed by the user ... They do not contain
   any values inherited from parents."

**Q2, semantics.**  With only the editor fixed, behavior would be mixed:
widgets created after a class edit snapshot the class colors and ignore
later edits, while older widgets follow class edits after the next render.
Recommendation: **live inheritance** (CSS-like), which is what the render
cascade was built for.  A class color applies to every widget of that class,
existing and new, unless the widget overrides that same color.  The
alternative, copy-on-create like widget settings, would need `_render_cls`
to stop merging class settings, which discards working code.  Matt decides.

**Q3, persistence.**  Yes.  Class settings are not `tmp`, so
`pubsub.save()` writes them under `registry/<Class>/settings/colors` and
`load()` restores them before classes register.  Export and Import copy the
same file.  Verify on the running UI.

**Q4, devices and views.**  Device classes are not styled (no
`style_settings`), so their Colors tab is correctly empty: nothing to do.
**View defaults** (the `View` class) has style settings, and `_render_obj`
for `ui` and each view already calls `_render_cls(View)`, so the same editor
fix applies.  The class render must re-render `ui` and the active view.

**Q5, schemes.**  Yes.  Overrides are stored as `{color_scheme: {name:
value}}` (fonts by font scheme), so light and dark keep separate class
overrides.  The editor shows and edits the active view's scheme.


## Proposed change

1. `styles/manager.py`
   * `style_settings()`: add `noinit` to `colors`, `fonts`, `style_defines`,
     so instances start with no overrides and inherit from the class.
   * Add `style_cls_ensure(cls)`: load `_style_cls` for the active view's
     theme when it is None (wraps `_load_style_for_class`).
   * `StyleManager._render(cls)`: iterate `{class}/instances` filtered by
     the active view.  For the `View` class, do a full render (`ui` plus the
     active view).
2. `widgets/settings/settings_widget.py`: in the three editors, use
   `cls = obj if isinstance(obj, type) else obj.__class__`, call
   `style_cls_ensure(cls)`, and replace the `style_obj is None` early return
   with "not a styled class" (`'colors' not in cls.SETTINGS`).  The rest of
   each editor already handles classes (`isinstance(obj, type)` checks), and
   `_on_change` already publishes to the class topic.
3. Tests in `styles/test/test_manager.py`: new instance has no override;
   class color reaches existing and new instances; instance override wins;
   class render re-renders instances; schemes are independent; save/load
   round trip.
4. CHANGELOG entry; update the `ui-settings-colors` note in joulescope_docs
   `source/software/joulescope_ui/settings.md`.
5. Verify with `ui-remote`: set `waveform.plot_p` on the Waveform class,
   confirm an existing and a new Waveform update, restart, confirm persist.

Not in scope: a per-color "reset to class default" for instances.


## Result (2026-11-16)

Implemented as proposed, plus: `View` gained `on_cls_setting_*` render
hooks (it is not a `styled_widget`) and instance font/define render hooks;
the Defines editor now publishes only the changed define instead of every
inherited value; the editors tolerate class overrides that lack the active
scheme.

UI check (isolated `HOME`, real Wayland display, live JS320 data): the
Waveform class Colors tab lists all colors; editing `waveform.plot_p`
there stores `{'dark': {'waveform.plot_p': ...}}` on the class only; the
existing Waveform and a newly added one both render the new color with no
instance override; the config file saves the class colors only, and both
widgets keep the color after restart.  View defaults → `base.foreground`
re-renders the active view live.  With several instruments the Waveform
colors by `waveform.trace1..4`, not `plot_*` (by design).
