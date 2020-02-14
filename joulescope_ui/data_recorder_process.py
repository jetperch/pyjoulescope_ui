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
from joulescope.data_recorder import DataRecorder
from joulescope.stream_buffer import StreamBuffer, DownsamplingStreamBuffer
import logging


def run(cmd_queue, filehandle, calibration):
    r = DataRecorder(filehandle, calibration)
    b = None
    has_raw = None
    while True:
        cmd, args = cmd_queue.get()
        if cmd == 'stream_notify':
            data, voltage_range = args
            if has_raw:
                b.voltage_range = voltage_range
                b.insert_raw(data)
                b.process()
            else:
                b.insert_downsampled_and_process(data)
            r.stream_notify(b)
        elif cmd == 'open':
            in_freq, out_freq, has_raw = args
            if has_raw:
                b = StreamBuffer(1.0, [], in_freq)
                b.calibration_set(calibration.current_offset, calibration.current_gain,
                                  calibration.voltage_offset, calibration.voltage_gain)
            else:
                duration = 2000000 / out_freq
                b = DownsamplingStreamBuffer(duration, [], in_freq, out_freq)

        elif cmd == 'close':
            r.close()
            break


class DataRecorderProcess:

    def __init__(self, filehandle, calibration=None):
        self._log = logging.getLogger(__name__)
        self.sample_id = None
        self._cmd_queue = Queue()
        args = (self._cmd_queue, filehandle, calibration)
        self._process = Process(target=run, name='Joulescope recorder', args=args)
        self._process.start()

    def stream_notify(self, stream_buffer):
        if self._cmd_queue is None:
            return
        if self.sample_id is None:
            in_freq = stream_buffer.input_sampling_frequency
            out_freq = stream_buffer.output_sampling_frequency
            self.sample_id = stream_buffer.sample_id_range[1]
            args = (in_freq, out_freq, stream_buffer.has_raw)
            self._log.info('Start recording: %s', args)
            self._cmd_queue.put(('open', args))
            return
        sample_id = stream_buffer.sample_id_range[1]
        voltage = float(stream_buffer.voltage_range)
        if stream_buffer.has_raw:
            data = stream_buffer.samples_get(self.sample_id, sample_id, fields='raw')
        else:
            data = stream_buffer.samples_get(self.sample_id, sample_id)
        args = (data, voltage)
        self._cmd_queue.put(('stream_notify', args))
        self.sample_id = sample_id

    def close(self):
        if self._cmd_queue is None:
            return
        self._cmd_queue.put(('close', None))
        self._cmd_queue = None
        self._process.join(timeout=5.0)
