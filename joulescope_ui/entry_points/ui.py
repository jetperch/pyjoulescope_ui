# Copyright 2018-2022 Jetperch LLC
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


def parser_config(p):
    """Start the Joulescope graphical user interface."""
    p.add_argument('filename',
                   default=None,
                   nargs='?',
                   help='The optional filename to display immediately')
    p.add_argument('--console_log_level', '--log_level',
                   choices=list(LEVELS.keys()),
                   help='The console (stdout) log level.')
    p.add_argument('--file_log_level',
                   choices=list(LEVELS.keys()),
                   help='The file log level.')
    p.add_argument('--profile',
                   choices=['cProfile', 'yappi'],
                   help='Profile the capture')
    p.add_argument('--safe_mode', '-s',
                   action='store_true',
                   help='Start in safe mode for recovery')
    return on_cmd


def on_cmd(args):
    def local_run():
        run(log_level=args.console_log_level,
            file_log_level=args.file_log_level,
            filename=args.filename,
            safe_mode=args.safe_mode)
    if args.profile is None:
        return local_run()
    elif args.profile == 'cProfile':
        import cProfile
        import pstats
        cProfile.runctx('local_run()', globals(), locals(), "Profile.prof")
        s = pstats.Stats("Profile.prof")
        s.strip_dirs().sort_stats("time").print_stats()
    elif args.profile == 'yappi':
        import yappi
        yappi.start()
        rv = local_run()
        yappi.get_func_stats().print_all()
        yappi.get_thread_stats().print_all()
        return rv
    else:
        raise ValueError('bad profile argument')
