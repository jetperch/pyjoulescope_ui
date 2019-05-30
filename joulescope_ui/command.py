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
This executable captures the raw USB stream from Joulescope devices
and saves the raw stream data to a file.  This executable is a
development tool and is not intended for customer use.
"""

from joulescope_ui.main import run
from joulescope_ui.logging_util import LEVELS


NAME = "ui"


def parser_config(p):
    """Start the Joulescope graphical user interface"""
    p.add_argument('--device_name',
                   help='The device name to search [joulescope]')
    p.add_argument('--log_level',
                   choices=list(LEVELS.keys()),
                   help='The console (stdout) log level.')
    return on_cmd


def on_cmd(args):
    return run(device_name=args.device_name, log_level=args.log_level)
