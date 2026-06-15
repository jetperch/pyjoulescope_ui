#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright 2018-2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
#
# Build (and optionally install / bundle) the Joulescope UI Flatpak locally.
#
# Steps:
#   1. Compile translations and build the prepared sdist into dist/ (the app
#      module installs this tarball, which carries the generated Qt resources).
#   2. Generate the pinned Python dependency module (python3-modules.json) if
#      it is missing.
#   3. Run flatpak-builder to build, and --install into the user installation.
#   4. Optionally emit a distributable single-file bundle (--bundle).
#
# Usage:
#   flatpak/build.sh             # build + install into the user installation
#   flatpak/build.sh --bundle    # also write joulescope-ui.flatpak
#
# Requirements: flatpak, flatpak-builder, python3 (with build, babel, polib),
# and the org.freedesktop.{Platform,Sdk}//25.08 runtime + SDK installed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${ROOT}/com.jetperch.JoulescopeUI.yml"
APP_ID="com.jetperch.JoulescopeUI"
BUILD_DIR="${ROOT}/flatpak-build"
REPO_DIR="${ROOT}/repo"
MAKE_BUNDLE=0

for arg in "$@"; do
    case "${arg}" in
        --bundle) MAKE_BUNDLE=1 ;;
        *) echo "Unknown argument: ${arg}" >&2; exit 2 ;;
    esac
done

cd "${ROOT}"

# 1. Prepare the sdist (compile translations first so they are bundled).
echo "==> Compiling translations and building sdist"
python3 ci/translations.py --compile-only || \
    echo "warning: translation compile failed; continuing with English only"
rm -f dist/joulescope_ui-*.tar.gz
python3 -m build --sdist

# 2. Generate the pinned dependency module if absent.
if [ ! -f "${ROOT}/flatpak/python3-modules.json" ]; then
    echo "==> Generating flatpak/python3-modules.json"
    "${ROOT}/flatpak/gen_python_modules.sh"
fi

# 3. Build and install.
echo "==> Running flatpak-builder"
flatpak-builder --user --install --force-clean "${BUILD_DIR}" "${MANIFEST}"

# 4. Optional single-file bundle (what CI ships to download.joulescope.com).
if [ "${MAKE_BUNDLE}" -eq 1 ]; then
    echo "==> Building bundle joulescope-ui.flatpak"
    flatpak-builder --repo="${REPO_DIR}" --force-clean "${BUILD_DIR}" "${MANIFEST}"
    flatpak build-bundle "${REPO_DIR}" "${ROOT}/joulescope-ui.flatpak" "${APP_ID}"
    echo "Wrote ${ROOT}/joulescope-ui.flatpak"
fi

echo "==> Done.  Run with: flatpak run ${APP_ID}"
