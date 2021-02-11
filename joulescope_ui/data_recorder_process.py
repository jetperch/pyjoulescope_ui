# Copyright 2019 Jetperch LLC
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

from multiprocessing import Queue, Process
from queue import Empty
from joulescope.data_recorder import DataRecorder
from joulescope_ui.logging_util import worker_configurer
import logging


def run(cmd_queue, filehandle, calibration, logging_queue):
    worker_configurer(logging_queue)
    log = logging.getLogger(__name__)
    log.info('run start')
    r = DataRecorder(filehandle, calibration)
    while True:
        try:
            cmd, args = cmd_queue.get(timeout=1.0)
            if cmd == 'stream_notify':
                data, = args
                r.insert(data)
            elif cmd == 'close':
                log.info('run closing')
                r.close()
                break
        except Empty:
            pass
        except Exception:
            log.exception("run exception during loop")
    log.info('run end')


class DataRecorderProcess:

    def __init__(self, filehandle, calibration=None, multiprocessing_logging_queue=None):
        self._log = logging.getLogger(__name__)
        self.sample_id = None
        self._cmd_queue = Queue()
        self._log.info('DataRecorderProcess recording: %s', filehandle)
        args = (self._cmd_queue, filehandle, calibration, multiprocessing_logging_queue)
        self._process = Process(target=run, name='Joulescope recorder', args=args)
        self._process.start()

    def stream_notify(self, stream_buffer):
        if self._cmd_queue is None:
            return
        if self.sample_id is None:
            self.sample_id = stream_buffer.sample_id_range[1]
            return
        sample_id = stream_buffer.sample_id_range[1]
        if self.sample_id == sample_id:
            return  # no new data, nothing to do
        data = stream_buffer.samples_get(self.sample_id, sample_id)
        cmd_queue = self._cmd_queue
        if cmd_queue is not None:
            cmd_queue.put(('stream_notify', (data, )))
            self.sample_id = sample_id

    def close(self):
        cmd_queue, self._cmd_queue = self._cmd_queue, None
        process, self._process = self._process, None
        if cmd_queue is not None:
            self._log.info('DataRecorderProcess cmd_queue close init')
            cmd_queue.put(('close', None))
            self._log.info('DataRecorderProcess cmd_queue close ack')
            cmd_queue.close()
            cmd_queue.join_thread()
            self._log.info('DataRecorderProcess cmd_queue close joined')
        if process is not None:
            self._log.info('DataRecorderProcess process join init')
            process.join(timeout=10.0)
            self._log.info('DataRecorderProcess process join done')
