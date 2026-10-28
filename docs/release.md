<!--
# SPDX-FileCopyrightText: Copyright 2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# Releasing the Joulescope UI

A release moves through these stages:

1. **main**: every push builds the sdist and installers, and the
   joulescope_ci farm runs the `ui_release` suite on the sdist.
2. **alpha**: a `vX.Y.Z` tag builds and signs the installers, publishes
   them to `download.joulescope.com` on the alpha channel, publishes the
   sdist to PyPI, and attaches the installers to the GitHub Release.  The
   farm then installs and tests the published installers.
3. **beta** and **stable**: `ci/release_update.py` re-points a channel at
   the published release.  The UI's in-app update follows its channel,
   which defaults to stable.

The automated tests cover most of the manual release test plan
(`ui_test_1_7_3.xlsx`); the rest is listed in
[Manual tests](#3-manual-tests).  The design and history are in
[`plans/completed/ui_release_test_automation.md`](plans/completed/ui_release_test_automation.md).


## 1. Prepare the release on main

1. Add the release to the top of `CHANGELOG.md`: a `## X.Y.Z` heading, the
   date line, and an entry for each user-visible change.
2. Update the version everywhere from the CHANGELOG heading:

   ```bash
   python version_update.py
   ```

   It updates `joulescope_ui/version.py`, `joulescope.iss`,
   `joulescope_ui/locale/joulescope_ui.pot` and the issue forms.
3. Update the translations (needs `DEEPL_AUTH`; see [locale.md](locale.md)):

   ```bash
   python ci/translations.py
   ```

   The Packaging workflow fails when the translations are out of date,
   which any change to a translated source file can cause.
4. Commit and push to main.


## 2. Check the main build

1. The **Packaging** workflow on GitHub passes.
2. The `ui_release` jobs for the commit pass on every station of the
   joulescope_ci dashboard (`http://192.168.42.211:8080`, LAN only).  A
   failure uploads its pytest log and a screenshot to the job page.


## 3. Manual tests

These rows of the test plan are not automated.  Run them on the platforms
that a change affects.

* **CHANGELOG.**  Review each entry and test each change that no
  automated test covers.
* **USB Inrush** analysis.  It needs the external USBET library.
* **Measured values.**  The stations have no known load or signal source,
  so the tests check function and round trips, not that a measured value
  is correct.  Check against a known load.
* **Hotplug, USB disconnect, power loss and host sleep.**  The tests may
  not control the stations' USB hubs.
* **Long-term tests.**  On the dashboard Jobs page, run the `ui_longterm`
  suite.  Each station records every Joulescope for an hour at full rate
  and at 10 kHz, then runs the waveform for 10 hours, so a run takes about
  12 hours.  Run it for a release that changes streaming, buffering or
  memory use.
* **Flatpak.**  The farm does not test the Flatpak bundles.  Install one on
  Linux (see [flatpak.md](flatpak.md)) and check that the UI starts and
  streams.
* **Linux ARM64.**  ci_linux_arm tests the sdist, since there is no Linux
  ARM64 installer.


## 4. Publish to alpha

1. Create the GitHub Release with tag `vX.Y.Z`, which must match
   `joulescope_ui/version.py`.  Use the CHANGELOG section as the notes:

   ```bash
   gh release create vX.Y.Z --title X.Y.Z --notes-file notes.md
   ```

   Creating the release pushes the tag, which runs the Packaging workflow.
2. Wait for the Packaging workflow to pass.  Its `publish` job:
   * uploads the installers to `download.joulescope.com` and points the
     **alpha** channel at them (`ci/publish.py`);
   * publishes the sdist to PyPI;
   * attaches the installers, the Flatpak bundles and
     `joulescope_ui_config.json` to the GitHub Release.  The next release's
     upgrade test downloads this config, so check that it is attached.


## 5. Check the release run

The tag pushes the `ui_release` suite to the farm with build kind
`release`.  Each station installs the published installer and tests it:
Windows for the current user, macOS copied as a Finder drag does and
checked by `codesign` and `spctl`, and Linux x64 from the `.tar.gz`.

1. Every station's `ui_release` job passes on the dashboard.
2. Each pytest log ends with `UI under test:` naming the installed
   executable, except ci_linux_arm, which names the sdist.
3. Upload each installer to [VirusTotal](https://www.virustotal.com/) and
   check that it reports no detections.  This stays manual: its API is not
   licensed for business workflows.


## 6. Promote to beta

`ci/release_update.py` re-points a channel at a published release.  It
rewrites only `index_v2.json` and `index.html`; it uploads no installers.
It needs the publish credentials (see
[`ci/aws_publish_README.md`](../ci/aws_publish_README.md)):

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=...
export JOULESCOPE_DOWNLOAD_BUCKET=download-joulescope-com
```

1. Preview, then promote to beta:

   ```bash
   python ci/release_update.py X.Y.Z beta --dry-run
   python ci/release_update.py X.Y.Z beta
   ```

2. Check the in-app update: in a previous release with the update channel
   set to beta, the UI offers X.Y.Z, then installs it and relaunches.

Let beta users run it, and keep testing, before promoting to stable.


## 7. Promote to stable

When beta has had enough use, promote to stable the same way:

```bash
python ci/release_update.py X.Y.Z stable
```

To roll back, re-point the channel at the previous version, such as
`python ci/release_update.py X.Y.W stable`.

When a new OS version ships, existing releases lack its platform key and the
update check fails on it.  `ci/release_alias.py` adds the key to the
published releases; see its usage.


## 8. Advertise stable

1. Update Shopify:
   1. Select Online Store → Edit theme.
   2. Click Home page → Pages → concept-downloads_user-guides.
   3. Click the "Download by OS" custom liquid section.  In the liquid
      code, scroll to `var VERSION = ` and replace it with the new version.
2. Post to LinkedIn
3. Release to forum
4. Respond to pending emails regarding issues fixed
5. Close addressed GitHub issues, if not already closed
6. Respond to forum.joulescope.com to close threads
