# Dedup: installer index/SHA-256 resolver

## Context

Two places resolve a published installer from `index_v2.json` and verify its
SHA-256 sidecar:

- `joulescope_ui/software_update.py` — the **in-app** updater. Imports
  `PySide6` at module scope (it is a Qt widget/flow), so it cannot be reused by
  headless tooling.
- `ci/uitest/installer.py` — the **release-test** downloader (added in M0 of the
  UI test-automation plan). Re-implements the same URL base, index lookup, and
  `{file}.sha256` parsing in a Qt-free form so the HIL farm can install a build
  without a display.

This is intentional, minimal duplication today (the test harness must stay
import-light), but the index schema and `_URL_BASE` now live in two places and
can drift.

## Plan (do later; not blocking the test-automation milestones)

1. Extract the pure resolver from `software_update.py` into a new Qt-free module,
   e.g. `joulescope_ui/software_update_index.py`:
   - `URL_BASE`, `INDEX_URL`
   - `platform_key(system, machine)` (the consumer's `_platform_name()` logic)
   - `installer_for(index, channel, key) -> (url, sha256_url)`
   - `parse_sha256_sidecar(text)`
2. Have `software_update.py` import and use it (no behavior change to the app).
3. Replace the duplicated logic in `ci/uitest/installer.py` with imports from
   that module; keep only the install/uninstall/launch steps (which are
   genuinely test-side) in `installer.py`.
4. Move/extend the existing offline pipeline test (`ci/test_publish.py`,
   `test_consumer_round_trip`) to also cover the shared resolver directly.

## Risk

`software_update.py` parses the *deployed* index that already-shipped UIs poll,
so its public resolution behavior must not change. Cover the extraction with the
existing consumer round-trip test before and after.
