# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generate example serial data for testing."""

import argparse
import serial
import time


def get_parser():
    p = argparse.ArgumentParser(
        description='Generate example serial data for testing.')
    p.add_argument('--baudrate', type=int, default=115200)
    p.add_argument('--period', type=float, default=1.0)
    p.add_argument('port')
    return p


def run():
    args = get_parser().parse_args()
    s = serial.Serial(args.port, baudrate=args.baudrate)
    try:
        message_count = 0
        while True:
            start_time = time.time()
            msg = f'serial message {message_count:d}'.encode('utf-8')
            message_count += 1
            s.write(msg)
            delay = args.period - (time.time() - start_time)
            if delay > 0.0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        s.close()


if __name__ == '__main__':
    run()
