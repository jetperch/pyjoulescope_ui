# Copyright 2018 Jetperch LLC
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
This entry point is discoverable by the joulescope package and
executes the official Joulescope User Interface software.
"""

from joulescope_ui.main import run
from joulescope_ui.logging_util import LEVELS

# QT bug workaround for MacOS Big Sur, added 2020 Nov 20.
# https://bugreports.qt.io/browse/QTBUG-87014
import os
os.environ["QT_MAC_WANTS_LAYER"] = "1"


NAME = "ui"


def parser_config(p):
    """Start the Joulescope graphical user interface."""
    p.add_argument('filename',
                   default=None,
                   nargs='?',
                   help='The optional filename to display immediately')
    p.add_argument('--device_name',
                   help='The device name to search [joulescope]')
    p.add_argument('--console_log_level', '--log_level',
                   choices=list(LEVELS.keys()),
                   help='The console (stdout) log level.')
    p.add_argument('--file_log_level',
                   choices=list(LEVELS.keys()),
                   help='The file log level.')
    return on_cmd


def on_cmd(args):
    return run(device_name=args.device_name,
               log_level=args.console_log_level,
               file_log_level=args.file_log_level,
               filename=args.filename)
