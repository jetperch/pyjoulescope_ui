# Copyright 2018-2023 Jetperch LLC
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
The Python time standard uses POSIX (UNIX) time which is defined relative
to Jan 1, 1970.  Python uses floating point seconds to express time.
This module defines a much simpler 64-bit fixed point integer for
representing time which is much friendlier for microcontrollers.
The value is 34Q30 with the upper 34 bits
to represent whole seconds and the lower 30 bits to represent fractional
seconds.  A value of 2**30 (1 << 30) represents 1 second.  This
representation gives a resolution of 2 ** -30 (approximately 1 nanosecond)
and a range of +/- 2 ** 33 (approximately 272 years).  The value is
signed to allow for simple arithmetic on the time either as a fixed value
or as deltas.

For more details on a compatible C implementation, see
https://github.com/jetperch/fitterbap/blob/main/include/fitterbap/time.h
"""


import datetime
import time as pytime

EPOCH = datetime.datetime(2018, 1, 1, tzinfo=datetime.timezone.utc).timestamp()  # seconds
SCALE = (1 << 30)
SECOND = SCALE
MINUTE = SECOND * 60
HOUR = MINUTE * 60
DAY = HOUR * 24


def now():
    """Get the current timestamp.

    :return: The time64 representation of the current time.
    """
    return as_time64(pytime.time())


def as_time64(t):
    """Convert a time to a Joulescope timestamp.

    :param t: The time which can be:
        * datetime.datetime
        * python timestamp
        * integer Joulescope timestamp
    """
    if isinstance(t, int):
        return t
    if isinstance(t, datetime.datetime):
        t = t.timestamp()
    else:
        t = float(t)
    return int((t - EPOCH) * SCALE)


def as_timestamp(t):
    """Convert a time to a python UTC timestamp.

    :param t: The time which can be:
        * datetime.datetime
        * python timestamp
        * integer Joulescope timestamp
    """
    t64 = as_time64(t)
    return (t64 / SCALE) + EPOCH


def as_datetime(t):
    """Convert a time to a python UTC timestamp.

    :param t: The time which can be:
        * datetime.datetime
        * python timestamp
        * integer Joulescope timestamp
    """
    t = as_timestamp(t)
    return datetime.datetime.fromtimestamp(t)


def filename(extension=None):
    """Construct a filename using the current time.

    :param extension: The filename extension, such as '.png'.
        None (default) uses '.jls'.
    :return: The filename.
    """

    extension = '.jls' if extension is None else str(extension)
    time_start = datetime.datetime.utcnow()
    timestamp_str = time_start.strftime('%Y%m%d_%H%M%S')
    return f'{timestamp_str}{extension}'


def _local_offset():
    now = datetime.datetime.now()
    local_now = now.astimezone()
    local_tz = local_now.tzinfo
    print('hi')
    print(local_tz)


if __name__ == '__main__':
    _local_offset()
