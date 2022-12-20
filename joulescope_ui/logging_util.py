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
from logging.handlers import QueueHandler
from logging import FileHandler
import time
import datetime
import faulthandler
import json
import multiprocessing
import threading
import traceback
import queue
import os
import sys
import platform
from joulescope_ui.paths import paths_current
from . import __version__ as UI_VERSION
from . import frozen
from joulescope import VERSION as DRIVER_VERSION


paths = paths_current()
LOG_PATH = paths['dirs']['log']
EXPIRATION_SECONDS = 7 * 24 * 60 * 60
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
UI Version = {ui_version}
Driver Version = {driver_version}"""


def _make_banner():
    banner = _BANNER.format(ui_version=UI_VERSION, driver_version=DRIVER_VERSION)
    lines = banner.split('\n')
    line_length = max([len(x) for x in lines]) + 4
    lines = ['* ' + line + (' ' * (line_length - len(line) - 3)) + '*' for line in lines]
    k = '*' * line_length
    lines = [k] + lines + [k, '']
    return '\n'.join(lines)


def _make_info():
    info = {
        'joulescope': {
            'ui_version': UI_VERSION,
            'driver_version': DRIVER_VERSION,
        },
        'platform': {
            'name': sys.platform,
            'python_version': sys.version,
            'platform': platform.platform(),
            'processor': platform.processor(),
            'executable': sys.executable,
            'frozen': frozen,
            'paths': paths,
        }
    }
    return json.dumps(info, indent=2)


def _cleanup_logfiles():
    """Delete old log files"""
    now = time.time()
    for f in os.listdir(LOG_PATH):
        fname = os.path.join(LOG_PATH, f)
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


def logging_preconfig():
    """Capture log in memory until :func:`logging_config`."""
    root_log = logging.getLogger()
    root_log.handlers = []
    root_log.addHandler(DeferredLogHandler())
    root_log.setLevel(logging.WARNING)


def logging_config(stream_log_level=None, file_log_level=None):
    """Configure logging.

    :param stream_log_level: The logging level for stderr which
        can be the integer value or name.  None (default) is 'WARNING'.
    :param file_log_level: The logging level for the log file which
        can be the integer value or name.  None (default) is 'INFO'.
    """
    banner = _make_banner()
    banner = banner + '\ninfo = ' + _make_info() + '\n\n=====\n'
    os.makedirs(LOG_PATH, exist_ok=True)
    d = datetime.datetime.utcnow()
    time_str = d.strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(LOG_PATH, 'joulescope_%s_%s.log' % (time_str, os.getpid(), ))

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
        stream.write(banner)
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
        file_hnd.stream.write(banner)
        file_hnd.setFormatter(file_fmt)
        file_hnd.setLevel(file_lvl)
        faulthandler.enable(file=file_hnd.stream)
        root_log.addHandler(file_hnd)

    root_log.setLevel(min([stream_lvl, file_lvl]))
    _cleanup_logfiles()
    root_log.info('logging configuration: stream_level=%s, file_level=%s', stream_lvl, file_lvl)
    if deferred_log_handler:
        for record in deferred_log_handler.records:
            root_log.handle(record)
        deferred_log_handler.records.clear()


# See https://docs.python.org/3/howto/logging-cookbook.html#logging-to-a-single-file-from-multiple-processes

def _listener_run(log_queue):
    while True:
        try:
            record = log_queue.get(True, 0.25)
            if record is None:  # We send this as a sentinel to tell the listener to quit.
                break
            logger = logging.getLogger(record.name)
            logger.handle(record)  # No level or filter logic applied - just do it!
        except queue.Empty:
            pass
        except KeyboardInterrupt:
            break
        except Exception:
            print('Logging problem:', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


# The worker configuration is done at the start of the worker process run.
# Note that on Windows you can't rely on fork semantics, so each process
# will run the logging configuration code when it starts.
def worker_configurer(queue):
    if queue is None:
        return
    h = QueueHandler(queue)  # Just the one handler needed
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(h)
    root.setLevel(logging.INFO)


def logging_start():
    queue = multiprocessing.Queue(-1)
    listener = threading.Thread(name='logging', target=_listener_run, args=(queue, ))
    listener.start()

    def stop():
        try:
            queue.put_nowait(None)
            listener.join(timeout=2.0)
        except Exception:
            print('Error stopping logging thread')

    return queue, stop, listener
