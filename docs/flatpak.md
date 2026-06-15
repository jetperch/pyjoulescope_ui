<!--
# SPDX-FileCopyrightText: Copyright 2018-2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
-->

# Linux Flatpak

The Joulescope UI is packaged as a [Flatpak](https://flatpak.org/) for Linux
(`com.jetperch.JoulescopeUI`).  The bundle ships the full Python runtime
(PySide6/Qt, pyqtgraph, numpy) along with `pyjoulescope_driver`, `pyjls`,
`joulescope`, a bundled `libusb`, and a bundled `krb5` (the prebuilt Qt6Network
links `libgssapi_krb5`, which the freedesktop runtime omits), so it runs on any
Flatpak-capable distribution without installing Python dependencies
system-wide.

## Install

Download `joulescope-ui-<arch>.flatpak` from the GitHub release assets, then:

    flatpak install --user ./joulescope-ui-x86_64.flatpak
    flatpak run com.jetperch.JoulescopeUI

`aarch64` bundles are also published for ARM64 hosts.

The bundle **defaults to XWayland (xcb)** and falls back to native Wayland only
if X11 is unavailable (`QT_QPA_PLATFORM=xcb;wayland` is baked into the
manifest).  XWayland is preferred until the Qt-ADS Wayland docking fix lands
(Qt-Advanced-Docking-System PR #844 / issue #316).  To test native Wayland:

    flatpak run --env=QT_QPA_PLATFORM=wayland com.jetperch.JoulescopeUI

Note: the manifest intentionally does **not** use `--socket=fallback-x11`.
Combined with `--socket=wayland`, `fallback-x11` makes Flatpak drop X11 on
Wayland sessions (the sandbox gets no `DISPLAY` and xcb cannot start, even with
`--socket=x11` present).  Plain `--socket=x11` keeps XWayland available.

## USB device access (required)

The Flatpak is sandboxed and **cannot** install udev rules itself.  Raw USB
access (`--device=all`) only grants the sandbox the access the logged-in user
already has, so the host must have the Joulescope udev rules installed.
Without them the UI launches but enumerates zero devices.

Install the rules once on the host (from the `joulescope_driver` project):

    sudo cp 99-joulescope.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger

Then unplug and replug the Joulescope.

## Updates

Flatpak applications update through Flatpak, not the Joulescope UI in-app
updater.  Re-run `flatpak install --user ./joulescope-ui-<arch>.flatpak` with a
newer bundle, or update from the remote once a published Flatpak remote or
Flathub listing is available.

## Building locally

Requires `flatpak`, `flatpak-builder`, and `python3` (with `build` and
`babel`), plus the runtime and SDK:

    flatpak install flathub org.freedesktop.Platform//25.08 \
        org.freedesktop.Sdk//25.08

Build and install into the user installation (the helper compiles
translations, builds the prepared sdist, generates the pinned dependency
module, then runs `flatpak-builder`):

    flatpak/build.sh
    flatpak run com.jetperch.JoulescopeUI

Produce a distributable single-file bundle (what CI publishes):

    flatpak/build.sh --bundle
    # writes joulescope-ui.flatpak

## How the manifest is structured

`com.jetperch.JoulescopeUI.yml` builds these modules in order:

1. **libusb** — the native USB library that the `pyjoulescope_driver` / `pyjls`
   / `joulescope` wheels dynamically link.
2. **krb5** — provides `libgssapi_krb5.so.2`, a hard dependency of the bundled
   Qt6Network that the freedesktop runtime does not ship (without it PySide6
   and PySide6QtAds fail to import).  The UI never uses Kerberos.
3. **python3-modules.json** — the pinned, hashed Python dependency closure,
   generated from `flatpak/requirements-flatpak.txt` by
   `flatpak/gen_python_modules.sh`.  A single file pins wheels for both x86_64
   and aarch64 (each tagged with `only-arches`), so it is committed and used by
   CI for both arches.  Regenerate and commit it whenever the dependencies in
   `setup.py` change.
4. **joulescope-ui** — the app itself, installed from the prepared sdist with
   `pip install --no-deps --no-index`, which guarantees it can only use the
   dependencies installed by the modules above.

The prepared sdist (built by the CI `build_sdist` job, or by `flatpak/build.sh`
locally) carries the compiled Qt resources and translations, so the app module
never rebuilds them inside the sandbox.

## Regenerating the dependency lock

After editing `flatpak/requirements-flatpak.txt` or bumping versions in
`setup.py`:

    flatpak/gen_python_modules.sh   # writes flatpak/python3-modules.json

Commit the regenerated `flatpak/python3-modules.json`.  One run pins wheels for
both x86_64 and aarch64, so a single committed file serves every CI arch; you
do not need to run it on each architecture.

## Troubleshooting

Inspect the sandbox interactively:

    flatpak run --command=bash --devel com.jetperch.JoulescopeUI
    python3 -c "import PySide6, numpy, pyjoulescope_driver, joulescope, pyjls"
    drv=$(python3 -c 'import pyjoulescope_driver as d, os; print(os.path.dirname(d.__file__))')
    ldd "$drv"/*.so | grep usb

The imports must all succeed and `libusb-1.0.so` must resolve to the bundled
copy.  If devices do not appear, recheck the host udev rules above.
