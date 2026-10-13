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

"""
Test Exporter JLS write error handling.
"""

"""Test the JLS v2 file source request handling."""

import os
import tempfile
import unittest
from unittest.mock import Mock
import numpy as np
from pyjls import Writer, DataType, time64
from joulescope_ui.jls_v2 import JlsV2


_FS = 1_000_000
_LENGTH = 100_000
_T0 = 1_800_000_000 * time64.SECOND


class TestJlsV2Process(unittest.TestCase):
    """JLS rejects reads past a signal, so requests must clamp to it (#source extents)."""

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self._path = os.path.join(self._tempdir.name, 'test.jls')
        with Writer(self._path) as w:
            w.source_def(source_id=1, name='JS220-000043', vendor='Jetperch LLC', model='JS220',
                         version='1', serial_number='000043')
            w.signal_def(signal_id=1, source_id=1, data_type=DataType.F32, sample_rate=_FS,
                         name='current', units='A')
            w.utc(1, 0, _T0)
            w.fsr_f32(1, 0, np.zeros(_LENGTH, dtype=np.float32))
            w.utc(1, _LENGTH - 1, _T0 + ((_LENGTH - 1) * time64.SECOND) // _FS)
        self._jls = JlsV2(self._path, Mock(), 'registry/jls')
        self._signal_id = 'registry/jls.JS220-000043.i'

    def tearDown(self):
        self._jls.close()
        self._tempdir.cleanup()

    def _req(self, time_type, start, end=0, length=0):
        return self._jls.process({'signal_id': self._signal_id, 'time_type': time_type,
                                  'start': start, 'end': end, 'length': length, 'rsp_id': 1})

    def test_utc_view_past_both_ends_summary(self):
        # the view of another source slid past this signal: 1503 pixels, full extent
        t_start, t_end = self._jls._jls.sample_id_to_timestamp(1, [0, _LENGTH - 1])
        rsp = self._req('utc', t_start - time64.SECOND // 100, t_end + time64.SECOND // 100, 1503)
        self.assertEqual('summary', rsp['response_type'])
        s = rsp['info']['time_range_samples']
        self.assertEqual(0, s['start'])
        self.assertLessEqual(s['end'], _LENGTH - 1)
        self.assertGreaterEqual(len(rsp['data']), 1503)  # interval // increment rounds up the count

    def test_samples_past_end(self):
        rsp = self._req('samples', _LENGTH - 10, _LENGTH + 50)
        self.assertEqual('samples', rsp['response_type'])
        self.assertEqual(10, len(rsp['data']))
        self.assertEqual(_LENGTH - 1, rsp['info']['time_range_samples']['end'])

    def test_samples_before_start(self):
        rsp = self._req('samples', -20, 9)
        self.assertEqual(10, len(rsp['data']))
        self.assertEqual(0, rsp['info']['time_range_samples']['start'])

    def test_length_past_end(self):
        rsp = self._req('samples', _LENGTH - 10, 0, 100)
        self.assertEqual(10, len(rsp['data']))

    def test_in_range_unchanged(self):
        rsp = self._req('samples', 100, 199)
        self.assertEqual(100, len(rsp['data']))
        self.assertEqual(100, rsp['info']['time_range_samples']['start'])
        self.assertEqual(199, rsp['info']['time_range_samples']['end'])


if __name__ == '__main__':
    unittest.main()
