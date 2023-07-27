# Copyright 2023 Jetperch LLC
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

"""
Inspect error report ZIP files.
"""

from joulescope_ui.zip_inspector import ZipInspectorDialog
from PySide6 import QtWidgets


def parser_config(p):
    """Start the Joulescope graphical user interface."""
    p.add_argument('path',
                   help='The path to display')
    return on_cmd


def on_cmd(args):
    app = QtWidgets.QApplication([])
    dialog = ZipInspectorDialog(None, args.path)
    rc = app.exec()
