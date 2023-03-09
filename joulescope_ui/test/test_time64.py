# Copyright 2023 Jetperch LLC
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
Test the time module.
"""

import unittest
from joulescope_ui import time64
import datetime


class TestTime(unittest.TestCase):

    def test_conversion(self):
        dt_now = datetime.datetime.now()
        t_now = dt_now.timestamp()
        t64_now = time64.as_time64(t_now)
        t2_now = time64.as_timestamp(t64_now)
        self.assertEqual(t_now, t2_now)

        dt2_now = time64.as_datetime(t64_now)
        self.assertEqual(dt_now, dt2_now)
