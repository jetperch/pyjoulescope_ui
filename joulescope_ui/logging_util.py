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

"""Configure logging for the Joulescope user interface application"""


import logging
from logging import FileHandler
import time
import datetime
import json
import os
import sys
import platform
from . import __version__ as UI_VERSION
from . import is_release


EXPIRATION_SECONDS = 7 * 24 * 60 * 60  # 7 days
STREAM_SIMPLE_FMT = "%(levelname)s:%(name)s:%(message)s"
STREAM_VERBOSE_FMT = "%(levelname)s:%(asctime)s:%(filename)s:%(lineno)d:%(name)s:%(message)s"
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


_BANNER = """\
Joulescope User Interface
UI Version = {ui_version}"""


def log_banner():
    banner = _BANNER.format(ui_version=UI_VERSION)
    lines = banner.split('\n')
    line_length = max([len(x) for x in lines]) + 4
    lines = ['* ' + line + (' ' * (line_length - len(line) - 3)) + '*' for line in lines]
    k = '*' * line_length
    lines = [k] + lines + [k, '']
    return '\n'.join(lines)


def log_info():
    info = {
        'joulescope': {
            'ui_version': UI_VERSION,
        },
        'platform': {
            'name': sys.platform,
            'python_version': sys.version,
            'platform': platform.platform(),
            'processor': platform.processor(),
            'executable': sys.executable,
            'is_release': is_release,
        }
    }
    return json.dumps(info, indent=2)


def log_header():
    banner = log_banner()
    return banner + '\ninfo = ' + log_info() + '\n\n=====\n'


def _cleanup_logfiles(path):
    """Delete old log files.

    :param path: The path for the log files.
    """
    now = time.time()
    for f in os.listdir(path):
        fname = os.path.join(path, f)
        try:
            if os.path.isfile(fname):
                expire_time = os.stat(fname).st_mtime + EXPIRATION_SECONDS
                if expire_time < now:
                    os.unlink(fname)
        except Exception:
            logging.getLogger(__name__).warning('While cleaning up %s', fname)


class DeferredLogHandler(logging.Handler):

    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def preconfig():
    """Capture log in memory until :func:`logging_config`."""
    root_log = logging.getLogger()
    root_log.handlers = []
    root_log.addHandler(DeferredLogHandler())
    root_log.setLevel(logging.WARNING)


def config(path, stream_log_level=None, file_log_level=None):
    """Configure logging.

    :param path: The path for the log files.
    :param stream_log_level: The logging level for stderr which
        can be the integer value or name.  None (default) is 'WARNING'.
    :param file_log_level: The logging level for the log file which
        can be the integer value or name.  None (default) is 'INFO'.
    """
    header = log_header()
    os.makedirs(path, exist_ok=True)
    d = datetime.datetime.utcnow()
    time_str = d.strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(path, 'joulescope_%s_%s.log' % (time_str, os.getpid(), ))

    root_log = logging.getLogger()
    deferred_log_handler = None
    if len(root_log.handlers) == 1:
        if isinstance(root_log.handlers[0], DeferredLogHandler):
            deferred_log_handler = root_log.handlers[0]
    root_log.handlers = []

    stream = sys.stderr
    if stream is not None:
        stream_lvl = logging.WARNING if stream_log_level is None else LEVELS[stream_log_level]
        stream_fmt = logging.Formatter(STREAM_VERBOSE_FMT)
        stream.write(header)
        stream_hnd = logging.StreamHandler(stream)
        stream_hnd.setFormatter(stream_fmt)
        stream_hnd.setLevel(stream_lvl)
        root_log.addHandler(stream_hnd)
    else:
        stream_lvl = logging.CRITICAL

    file_lvl = logging.INFO if file_log_level is None else LEVELS[file_log_level]
    if file_lvl < LEVELS['OFF']:
        file_fmt = logging.Formatter(FILE_FMT)
        file_hnd = FileHandler(filename=filename)
        file_hnd.stream.write(header)
        file_hnd.setFormatter(file_fmt)
        file_hnd.setLevel(file_lvl)
        # Removed faulthandler due to complications
        # See https://bugreports.qt.io/browse/PYSIDE-2501
        # faulthandler.enable(file=file_hnd.stream)
        root_log.addHandler(file_hnd)

    root_log.setLevel(min([stream_lvl, file_lvl]))
    _cleanup_logfiles(path)
    root_log.info('logging configuration: stream_level=%s, file_level=%s', stream_lvl, file_lvl)
    if deferred_log_handler:
        for record in deferred_log_handler.records:
            root_log.handle(record)
        deferred_log_handler.records.clear()


def flush_all():
    root_log = logging.getLogger()
    for h in root_log.handlers:
        if hasattr(h, 'stream'):
            h.flush()
