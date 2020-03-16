#!/usr/bin/env python3

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

import sys
from joulescope.entry_points.runner import run
import argparse
import multiprocessing


def _argv_patch():
    """Add the "ui" command as needed."""
    for argv in sys.argv[1:]:
        if argv.startswith('-'):
            # not fully supported, presume "ui" command.
            break
        if argv.endswith('.jls'):
            # first positional argument is filename, "ui" command.
            break
        else:
            return  # command present
    sys.argv.insert(1, 'ui')


if __name__ == '__main__':
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description='Joulescope™ user interface.')
    _argv_patch()
    sys.exit(run())
