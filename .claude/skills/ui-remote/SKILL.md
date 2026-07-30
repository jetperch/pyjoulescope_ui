---
name: ui-remote
description: >
  Attach to and drive the running Joulescope UI via its --tcp-server
  remote-control interface. Use when asked to screenshot the UI, verify a UI
  change visually, switch views (multimeter/oscilloscope/file), read or change
  UI settings, inspect widget state, click/drag/type in the UI, watch live
  statistics, or launch the UI for verification. Not for editing UI source
  code — only for interacting with a live UI process.
---

# Driving the Joulescope UI remotely

The UI started with `--tcp-server` exposes remote PubSub + Qt inspection on
localhost (default port 21861). Authoritative protocol/API doc:
`docs/tcp_server.md`. One-shot helper for everything below:
`python ci/uitest/cli.py <cmd>` (run from the repo root, in the Python
environment where `joulescope_ui` is importable).

## Attach or launch — decision tree

1. Check for a live UI: `python ci/uitest/cli.py ping`
   - Exit 0 → connected; output includes the active view. Proceed.
   - Exit 2 → no UI with `--tcp-server`. Credentials live in
     `%LOCALAPPDATA%\joulescope\server.json` (`{'token','port'}`); the file is
     deleted on clean exit, so its presence normally means a live UI.
2. `server.json` exists but ping fails → stale file from a hard kill. Tell the
   user; do not silently delete it. Launching a new UI overwrites it.
3. No UI running and the task needs one → launch it yourself with Bash
   `run_in_background`:

       python -m joulescope_ui --tcp-server

   Wait in two stages: poll for `server.json` to appear (≤30 s), then poll
   `ping` until it succeeds. The token regenerates on every launch — never
   cache credentials across launches.
4. **Never use `ci/uitest/harness.py::UiSession` on the user's real UI.** Its
   `stop()` publishes `!close` with `config_clear`, which **wipes the
   developer's real UI configuration**. UiSession is for isolated pytest runs
   only.
5. Closing: only close a UI that you launched yourself, with a plain
   `cli.py publish "registry/ui/actions/!close" null` (no config clear).
   Never publish `!close` to a UI the user was already running.

## The verification loop

The core workflow for "verify this UI change":

1. Act (publish a setting, click, switch view).
2. Verify state: `query` the topic, or use `publish ... --wait`
   (read-after-write). `publish` is fire-and-forget with no ack —
   never sleep-and-hope.
3. Screenshot to the session scratchpad, numbered for before/after pairs:
   `python ci/uitest/cli.py screenshot <scratchpad>/ui_01.png`
4. Read the PNG (the Read tool renders images) and decide.

## CLI cheat sheet

All commands print one JSON object. Exit codes: 0 ok, 2 UI not running/stale
creds, 3 timeout, 4 server error. Globals: `--timeout` (default 15 s),
`--port`, `--token`, `--server-json`.

| Command | Example |
|---|---|
| `ping` | `cli.py ping` — attach check, reports active view |
| `screenshot` | `cli.py screenshot out.png --widget WaveformWidget:0` |
| `query` | `cli.py query registry/view/settings/active` |
| `publish` | `cli.py publish registry/view/settings/active view:multimeter --wait` |
| `view` | `cli.py view multimeter` \| `oscilloscope` \| `file` (waits, prints old→new) |
| `enum` | `cli.py enum registry` — discover the topic tree |
| `inspect` | `cli.py inspect --depth 3` or `cli.py inspect central_widget` |
| `find` | `cli.py find --class WaveformWidget` / `--name my_button` / `--text "1.5.1"` — prints usable widget paths |
| `action` | `cli.py action click --path my_button`; `cli.py action resize --kwargs '{"width":1280,"height":800}'` |
| `devices` | `cli.py devices` — connected Joulescopes (model, serial) |
| `stats` | `cli.py stats --duration 2` — sample live statistics safely |

PowerShell quoting for JSON args: wrap in single quotes (`--kwargs '{"x":1}'`).
Available `action` names: `click`, `drag`, `key`, `cursor`, `resize`,
`menu_invoke`, `menu_close`, `menu_items`, `set_property`, `get_property`,
`call` (see `docs/tcp_server.md`).

## Direct client use

For anything the CLI doesn't cover (persistent subscriptions, numpy signal
data), write a script:

```python
import sys
sys.path.insert(0, 'ci')
from uitest.discover import find_credentials
from joulescope_ui.tcp_client import Client

creds = find_credentials()          # {'token','port'} or None
with Client(**creds, timeout=15.0) as c:
    print(c.query('registry/view/settings/active'))
```

Pointers: full client API and wire protocol → `docs/tcp_server.md`.
Wait/interaction helpers (`wait_for`, `open_file`, `wait_for_statistics`,
`record_start/stop`, `export_range`, `is_waveform_rendered`) →
`ci/uitest/harness.py` (pytest only — see warning above). Widget-tree search →
`ci/uitest/qt.py`.

## Topics and widget paths

- `registry/view/settings/active` — `view:multimeter | view:oscilloscope | view:file`
- `registry/view/actions/!widget_open` / `!widget_close`
- `registry/+/events/statistics/!data` — live statistics (subscribe)
- Discover the rest: `cli.py enum registry`, then drill down.

Widget paths are slash-separated `objectName` values with `ClassName:index`
fallback (0-based among same-class siblings), e.g.
`central_widget/WaveformWidget:0`. **An empty path targets the ACTIVE window —
an open dialog steals targeting; dismiss dialogs first** (Escape key action or
`menu_close`).

## Pitfalls

- Never publish `registry/ui/actions/!close` or anything config-clearing to
  the user's own UI session.
- `publish` has no ack — verify via `query`, `--wait`, or a screenshot.
- The library's default client timeout is 5 s; the CLI already uses 15 s. Use
  more for device operations, file open, or export.
- The token changes every launch, and a stale `server.json` survives a hard
  kill — always `ping` before trusting it.
- Streaming signal topics deliver numpy arrays over binary frames — don't try
  to JSON-print them; use `stats` for quick numbers.
- Wildcard (`+`) subscriptions silently receive nothing through `tcp_client`:
  it dispatches incoming publishes by exact topic match. Subscribe to concrete
  topics (e.g. `registry/JS320-8W2A/events/statistics/!data`); `cli.py stats`
  already does this per device.
- Offscreen or unpainted OpenGL waveform: hit-test geometry stays empty and
  waveform mouse interactions **silently no-op**. Waveform interaction needs a
  real, visible display (`is_waveform_rendered` in the harness checks this).
- No CLI flags for port or window size — resize via `action resize`.
- Blank screenshot → the window may be minimized; ask the user to restore it.

## Reference map

- `docs/tcp_server.md` — protocol, full client API, all `qt_action` kwargs.
- `ci/uitest/harness.py` — launch-and-own `UiSession` harness (pytest only).
- `ci/uitest/README.md` + `ci/uitest/test_*.py` — worked interaction examples
  (menus, drag, export, markers).
