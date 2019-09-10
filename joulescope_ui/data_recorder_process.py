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
from joulescope.stream_buffer import StreamBuffer


def run(cmd_queue, filehandle, sampling_frequency, calibration):
    r = DataRecorder(filehandle, sampling_frequency, calibration)
    b = StreamBuffer(int(sampling_frequency), [], sampling_frequency)
    b.calibration_set(calibration.current_offset, calibration.current_gain,
                      calibration.voltage_offset, calibration.voltage_gain)
    while True:
        cmd, args = cmd_queue.get()
        if cmd == 'stream_notify':
            raw_data, voltage_range = args
            b.voltage_range = voltage_range
            b.insert_raw(raw_data)
            b.process()
            r.stream_notify(b)
        elif cmd == 'close':
            r.close()
            break


class DataRecorderProcess:

    def __init__(self, filehandle, sampling_frequency, calibration=None):
        self.sample_id = None
        self._cmd_queue = Queue()
        args = (self._cmd_queue, filehandle, sampling_frequency, calibration)
        self._process = Process(target=run, name='Joulescope recorder', args=args)
        self._process.start()

    def stream_notify(self, stream_buffer):
        if self._cmd_queue is None:
            return
        if self.sample_id is None:
            self.sample_id = stream_buffer.sample_id_range[1]
            return
        sample_id = stream_buffer.sample_id_range[1]
        voltage = float(stream_buffer.voltage_range)
        raw_data = stream_buffer.raw_get(self.sample_id, sample_id)
        args = (raw_data, voltage)
        self._cmd_queue.put(('stream_notify', args))
        self.sample_id = sample_id

    def close(self):
        if self._cmd_queue is None:
            return
        self._cmd_queue.put(('close', None))
        self._cmd_queue = None
        self._process.join(timeout=5.0)
