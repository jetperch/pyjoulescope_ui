# Prompt to configure Windows high accuracy time

Status: proposed 2026-11-12, not started.


## Problem

**Tools** → **Configure high accuracy time** (`joulescope_ui/windows.py`)
is a manual step that most users never find.  Without it, Windows syncs its
clock rarely, so sample UTC timestamps drift by many milliseconds, which
hurts multi-instrument alignment.  The docs now tell users to run it
(docs.joulescope.com `/en/software/host_configuration/windows.html`,
label `host-config-windows-time`).


## Proposal

On Windows, at UI start, check whether high accuracy time is configured.
If not, show a non-modal prompt: **Configure now** / **Not now** /
**Don't ask again**.

* **Detect without admin.**  Read with `winreg` (HKLM read needs no
  elevation) and compare against the values the tool writes:
  * `Services\W32Time\Start` == 2 (auto)
  * `W32Time\Config`: `MinPollInterval` 6, `MaxPollInterval` 6,
    `UpdateInterval` 100, `FrequencyCorrectRate` 2
  * `W32Time\TimeProviders\NtpClient\SpecialPollInterval` 64
  * Keep the expected values in one table in `windows.py`, shared by the
    script and the check, so they cannot diverge.
* **Configure now** runs the existing `run_w32time_high_accuracy()`, then
  re-checks after the elevated process exits.  Today `Start-Process` returns
  before the elevated script finishes and the result is not reported; add
  `-Wait` and report success or failure to the user.
* **Don't ask again** stores a bool in UI preferences, for example
  `ui/w32time_prompt`.  Keep the Tools menu item.
* Skip the prompt on domain-joined computers, where group policy owns
  W32Time and the change may be reverted.


## Open questions

* `FrequencyCorrectRate`: the tool writes 2 (Microsoft's value), but the
  forum time sync study (topic 929, 2025) used 4 because the JS220 prefers
  slow host frequency corrections.  Decide which value to ship before the
  check enforces it.
* `SpecialPollInterval` only applies when `NtpServer` has the 0x1 flag.
  The default `time.windows.com,0x9` has it; a custom server may not.
  Decide whether to check or set `NtpServer`.
* Should the prompt wait until a JS220/JS320 is connected, since those use
  host UTC most?


## Tests

Unit-test the detection with a mocked `winreg` for configured, partly
configured and missing keys.  Manual test on Windows 11: fresh install
prompts once, configure succeeds, restart does not prompt.
