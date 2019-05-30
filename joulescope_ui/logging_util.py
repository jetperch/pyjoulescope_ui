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

"""Configure logging for the Joulescope user interfaace application"""


import logging
from logging import FileHandler
import time
import datetime
import os
from joulescope_ui.config import APP_PATH


LOG_PATH = os.path.join(APP_PATH, 'log')
EXPIRATION_SECONDS = 7 * 24 * 60 * 60
STREAM_FMT = "%(levelname)s:%(name)s:%(message)s"
FILE_FMT = "%(levelname)s:%(asctime)s:%(filename)s:%(lineno)d:%(name)s:%(message)s"

LEVELS = {
    'OFF': 100,
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
    'ALL': 0,
}
for name, value in list(LEVELS.items()):
    LEVELS[value] = value
assert(logging.CRITICAL == 50)
assert(logging.DEBUG == 10)


def _cleanup_logfiles():
    """Delete old log files"""
    now = time.time()
    for f in os.listdir(LOG_PATH):
        fname = os.path.join(LOG_PATH, f)
        if not os.path.isfile(fname):
            continue
        if os.stat(fname).st_mtime + EXPIRATION_SECONDS < now:
            try:
                os.unlink(fname)
            except Exception:
                logging.getLogger(__name__).warning('Could not unlink %s', fname)


def logging_config(stream_log_level=None, file_log_level=None):
    """Configure logging.

    :param stream_log_level: The logging level for stderr which
        can be the integer value or name.  None (default) is 'WARNING'.
    :param file_log_level: The logging level for the log file which
        can be the integer value or name.  None (default) is 'INFO'.
    """
    os.makedirs(LOG_PATH, exist_ok=True)
    d = datetime.datetime.utcnow()
    time_str = d.strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(LOG_PATH, 'joulescope_%s_%s.log' % (time_str, os.getpid(), ))

    stream_lvl = logging.WARNING if stream_log_level is None else LEVELS[stream_log_level]
    stream_fmt = logging.Formatter(STREAM_FMT)
    stream_hnd = logging.StreamHandler()
    stream_hnd.setFormatter(stream_fmt)
    stream_hnd.setLevel(stream_lvl)

    file_lvl = logging.INFO if file_log_level is None else LEVELS[file_log_level]
    if file_lvl < LEVELS['OFF']:
        file_fmt = logging.Formatter(FILE_FMT)
        file_hnd = FileHandler(filename=filename)
        file_hnd.setFormatter(file_fmt)
        file_hnd.setLevel(file_lvl)

    root_log = logging.getLogger()
    root_log.addHandler(stream_hnd)
    root_log.addHandler(file_hnd)

    root_log.setLevel(min([stream_lvl, file_lvl]))
    _cleanup_logfiles()

