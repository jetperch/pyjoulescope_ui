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

"""File-system helpers for the captures the tests write."""

import os
import shutil
import time

#: Seconds to retry a removal: Windows refuses to delete a file that another
#: process, such as the UI, still has open.
REMOVE_TIMEOUT_S = 60.0


def remove(path, timeout=REMOVE_TIMEOUT_S):
    """Remove a file or directory tree, retrying while it is still in use.

    A missing path is not an error.

    :raises OSError: If ``path`` is still in use after ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1.0)
