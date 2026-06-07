# Copyright 2026 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Automated UI release-test harness.

This package drives the Joulescope UI through its TCP control socket
(``joulescope --tcp-server``) to execute the release test plan
(``doc/ui_test_1_3_4.xlsx``) across platforms on a hardware-in-the-loop (HIL)
farm.

Module layout::

    discover    -- locate server.json per-OS; enumerate connected devices
    verify      -- verify JLS recordings/exports with pyjls.Reader
    assets      -- fetch & cache large test-data fixtures on demand
    installer   -- resolve/download/silent-install a published installer
    stations    -- load the HIL bench registry (advertised capabilities)
    harness     -- UiSession: launch the UI and drive it via tcp_client.Client
    conftest    -- pytest fixtures (ui_session, device, screenshot-on-failure)

The Qt-free modules (discover, verify, assets, installer, stations) import
neither PySide6 nor ``joulescope_ui`` at module scope so their unit tests run
without a display or the UI installed.  ``harness`` imports the UI client
lazily, inside :class:`harness.UiSession`.
"""
