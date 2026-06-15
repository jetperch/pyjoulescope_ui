#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright 2018-2026 Jetperch LLC
# SPDX-License-Identifier: Apache-2.0
#
# Generate the pinned, hashed Python dependency module for the Joulescope UI
# Flatpak (flatpak/python3-modules.json) from flatpak/requirements-flatpak.txt.
#
# This MUST be run on a host that has flatpak + the Flatpak SDK installed so
# that dependencies resolve against the runtime's Python (not the host's).
# One invocation pins wheels for BOTH x86_64 and aarch64 (each tagged with
# only-arches), so the resulting python3-modules.json is committed and used by
# CI for both arches -- regenerate it only when dependencies change.
#
# Usage:
#   flatpak/gen_python_modules.sh
#
# Requirements:
#   - flatpak, with org.freedesktop.Sdk//${RUNTIME_VERSION} installed
#   - python3 (host) to run flatpak-pip-generator
#   - network access (downloads wheel metadata + hashes from PyPI)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_VERSION="${RUNTIME_VERSION:-25.08}"
PIP_GENERATOR_REF="${PIP_GENERATOR_REF:-master}"
# Note: pip/flatpak-pip-generator is a symlink in the upstream repo, so fetch
# the real script (flatpak-pip-generator.py) directly.
PIP_GENERATOR_URL="https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/${PIP_GENERATOR_REF}/pip/flatpak-pip-generator.py"

cd "${HERE}"

# Fetch flatpak-pip-generator if it is not already present next to this script.
if [ ! -f flatpak-pip-generator ]; then
    echo "Downloading flatpak-pip-generator (${PIP_GENERATOR_REF})..."
    curl -fsSL "${PIP_GENERATOR_URL}" -o flatpak-pip-generator
fi

# flatpak-pip-generator needs these host modules to parse the requirements.
python3 -c "import requirements, packaging" 2>/dev/null || \
    python3 -m pip install "requirements-parser>=0.11.0,<1" "packaging>=23.0"

# Resolve every dependency to a binary wheel with a pinned URL + sha256.
# We deliberately bundle the PySide6 wheel (matches setup.py's >=6.11.1 pin and
# the Windows/macOS builds) instead of the io.qt.PySide.BaseApp, so allow the
# otherwise-restricted PySide6/shiboken6 wheels.  This flag also stops the
# generator from omitting packages it assumes the SDK provides (markdown,
# setuptools, ...): the org.freedesktop.Platform *runtime* does not ship them,
# so the app needs them bundled.
export FLATPAK_PIP_GENERATOR_ALLOW_RESTRICTED_MODULES=1

# Packages that ship as architecture-specific (manylinux) wheels rather than
# pure-Python wheels.  --prefer-wheels makes the generator pin their platform
# wheels (one entry per arch, tagged with only-arches) instead of falling back
# to sdists that would have to compile inside the sandbox (numpy/Qt/native USB).
PREFER_WHEELS="numpy,psutil,pyjoulescope_driver,joulescope,pyjls,pymonocypher,\
PySide6,PySide6-Essentials,PySide6-Addons,shiboken6,PySide6-QtAds,watchdog"

python3 flatpak-pip-generator \
    --runtime="org.freedesktop.Sdk//${RUNTIME_VERSION}" \
    --requirements-file=requirements-flatpak.txt \
    --prefer-wheels="${PREFER_WHEELS}" \
    --output=python3-modules

echo "Wrote ${HERE}/python3-modules.json"
echo "Reference it from com.jetperch.JoulescopeUI.yml and commit it."
