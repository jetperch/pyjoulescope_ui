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
Test the axis ticks
"""

import unittest
from joulescope_ui.widgets.waveform import axis_ticks as t
from joulescope_ui import time64
import numpy as np


class TestAxisTicksXOffset(unittest.TestCase):

    def test_microsecond(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.MICROSECOND * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.MICROSECOND + 5, time64.YEAR + time64.MICROSECOND * 6))
        self.assertEqual(time64.YEAR + int(20 * time64.SECOND * 1e-6),
                         t.x_offset(time64.YEAR + time64.MICROSECOND * 22 + 5, time64.YEAR + time64.MICROSECOND * 24))

    def test_millisecond(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.MILLISECOND * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.MILLISECOND + 5, time64.YEAR + time64.MILLISECOND * 6))

    def test_second(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.SECOND * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.SECOND + 5, time64.YEAR + time64.SECOND * 6))

    def test_minute(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.MINUTE * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.MINUTE + 5, time64.YEAR + time64.MINUTE * 6))

    def test_hour(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.HOUR * 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + time64.HOUR + 5, time64.YEAR + time64.HOUR * 6))

    def test_day(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + time64.DAY * 6))
        self.assertEqual(time64.YEAR + time64.DAY, t.x_offset(time64.YEAR + time64.DAY + 5, time64.YEAR + time64.DAY * 6))

    def test_small(self):
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR, time64.YEAR + 6))
        self.assertEqual(time64.YEAR, t.x_offset(time64.YEAR + 6, time64.YEAR + 12))


class TestAxisXTicks(unittest.TestCase):

    def test_good(self):
        x0, x1 = 180025915120611983, 180025915208504625
        v = t.x_ticks(x0, x1, 13.857142857142858)
        z0 = v['offset'] + int(v['major'][0] * time64.SECOND)
        z1 = v['offset'] + int(v['major'][-1] * time64.SECOND)
        self.assertGreaterEqual(z0, x0)
        self.assertLessEqual(z1, x1)

    def test_bad(self):
        x0, x1 = 180027262723932739, 180027262785536828
        v = t.x_ticks(x0, x1, 13.857142857142858)
        #print((x0 - v['offset']) / time64.SECOND)
        z0 = v['offset'] + int(v['major'][0] * time64.SECOND)
        z1 = v['offset'] + int(v['major'][-1] * time64.SECOND)
        self.assertGreaterEqual(z0, x0)
        self.assertLessEqual(z1, x1)
        #print(v)

    def test_offset_str_utc(self):
        x0, x1 = 180025915120611983, 180025915208504625
        v = t.x_ticks(x0, x1, 13.857142857142858)
        self.assertTrue(v['offset_str'].endswith('+00:00'))

    def test_offset_str_local(self):
        from datetime import datetime, timezone
        x0, x1 = 180025915120611983, 180025915208504625
        v_utc = t.x_ticks(x0, x1, 13.857142857142858, time_zone='utc')
        v_local = t.x_ticks(x0, x1, 13.857142857142858, time_zone='local')
        self.assertEqual(v_utc['offset'], v_local['offset'])
        # The offset string only differs from UTC when the local zone is offset.
        if datetime.now(timezone.utc).astimezone().utcoffset().total_seconds() != 0:
            self.assertNotEqual(v_utc['offset_str'], v_local['offset_str'])


class TestXOffsetStrRelative(unittest.TestCase):

    def test_zero(self):
        self.assertEqual('0:00:00', t.x_offset_str_relative(0))

    def test_seconds(self):
        self.assertEqual('0:00:32', t.x_offset_str_relative(32 * time64.SECOND))

    def test_subsecond(self):
        self.assertEqual('0:00:00.00032', t.x_offset_str_relative(320 * time64.MICROSECOND))
        self.assertEqual('0:00:00.5', t.x_offset_str_relative(500 * time64.MILLISECOND))

    def test_minutes_hours(self):
        self.assertEqual('0:01:00', t.x_offset_str_relative(time64.MINUTE))
        self.assertEqual('2:03:04', t.x_offset_str_relative(2 * time64.HOUR + 3 * time64.MINUTE + 4 * time64.SECOND))

    def test_days(self):
        self.assertEqual('1:02:00:00', t.x_offset_str_relative(time64.DAY + 2 * time64.HOUR))

    def test_negative(self):
        self.assertEqual('-0:00:32', t.x_offset_str_relative(-32 * time64.SECOND))


class TestAxisXTicksRelative(unittest.TestCase):

    def test_epoch_at_x0_subsecond(self):
        # sub-second major interval with the view within 1 s of epoch:
        # no offset, labels relative to epoch directly
        x0, x1 = 180025915120611983, 180025915208504625
        v = t.x_ticks(x0, x1, 13.857142857142858, time_mode='relative', epoch=x0)
        self.assertEqual(x0, v['offset'])
        self.assertEqual('', v['offset_str'])

    def test_epoch_default(self):
        x0, x1 = 180025915120611983, 180025915208504625
        v = t.x_ticks(x0, x1, 13.857142857142858, time_mode='relative')
        self.assertEqual(x0, v['offset'])
        self.assertEqual('', v['offset_str'])

    def test_epoch_earlier_subsecond_interval(self):
        # sub-second major interval, magnitudes within label precision: direct labels
        epoch = time64.YEAR
        x0, x1 = epoch + 32 * time64.SECOND, epoch + 33 * time64.SECOND
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual(epoch, v['offset'])
        self.assertEqual('', v['offset_str'])
        self.assertIn('32.2', v['labels'])
        self.assertEqual('s', v['units'])

    def test_deep_zoom_positive(self):
        # magnitudes beyond label precision: quantized elapsed offset banner
        epoch = time64.YEAR
        x0 = epoch + 3600 * time64.SECOND
        x1 = x0 + 200 * time64.MICROSECOND
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual('1:00:00', v['offset_str'])
        self.assertGreaterEqual(v['offset'], epoch)

    def test_second_intervals_label_full_elapsed(self):
        # major interval >= 1 s: labels carry the full elapsed time, no offset
        epoch = time64.YEAR
        x0, x1 = epoch + 60 * time64.SECOND, epoch + 78 * time64.SECOND
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual(epoch, v['offset'])
        self.assertEqual('', v['offset_str'])
        self.assertIn('1:00', v['labels'])

    def test_ticks_within_range(self):
        epoch = time64.YEAR
        x0, x1 = epoch + 180 * time64.SECOND, epoch + 190 * time64.SECOND
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual(epoch, v['offset'])
        z0 = v['offset'] + int(v['major'][0] * time64.SECOND)
        z1 = v['offset'] + int(v['major'][-1] * time64.SECOND)
        self.assertGreaterEqual(z0, x0)
        self.assertLessEqual(z1, x1)


class TestAxisXTicksNegative(unittest.TestCase):
    """Relative mode with the epoch at the newest sample (relative negative)."""

    def test_seconds(self):
        epoch = time64.YEAR
        x0, x1 = epoch - 18 * time64.SECOND, epoch
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual(epoch, v['offset'])
        self.assertEqual('', v['offset_str'])
        self.assertEqual('0', v['labels'][-1])   # endpoint tick at the newest sample
        self.assertIn('-16', v['labels'])
        self.assertEqual('s', v['units'])

    def test_minutes(self):
        epoch = time64.YEAR
        x0, x1 = epoch - 90 * time64.SECOND, epoch
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual('-1:30', v['labels'][0])
        self.assertEqual('0:00', v['labels'][-1])
        self.assertEqual('m:ss', v['units'])

    def test_subsecond_near_epoch(self):
        # small magnitudes: direct labels, no offset banner
        epoch = time64.YEAR
        x0, x1 = epoch - 500 * time64.MICROSECOND, epoch
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual(epoch, v['offset'])
        self.assertEqual('', v['offset_str'])
        self.assertEqual('0', v['labels'][-1])

    def test_deep_zoom_negative(self):
        # far from the newest-sample epoch: offset quantized towards zero
        epoch = time64.YEAR
        x1 = epoch - 3600 * time64.SECOND
        x0 = x1 - 200 * time64.MICROSECOND
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        self.assertEqual('-1:00:00', v['offset_str'])
        self.assertEqual(epoch - 3600 * time64.SECOND, v['offset'])
        # residual tick values are small negatives, not huge positives
        self.assertLessEqual(v['major'][-1], 0.0)
        self.assertGreaterEqual(v['major'][0], -0.001)

    def test_dt_window_fill(self):
        # the Δt holdover fill case: 10 s window pinned right at the epoch,
        # 0.5 s major interval: direct negative labels, no confusing offset
        epoch = time64.YEAR
        x0, x1 = epoch - 10 * time64.SECOND, epoch
        v = t.x_ticks(x0, x1, 25, time_mode='relative', epoch=epoch)
        self.assertEqual('', v['offset_str'])
        self.assertEqual(epoch, v['offset'])
        self.assertIn('-10', v['labels'])
        self.assertIn('-0.5', v['labels'])
        self.assertEqual('0', v['labels'][-1])
        self.assertEqual('s', v['units'])

    def test_ticks_within_range(self):
        epoch = time64.YEAR
        x0, x1 = epoch - 18 * time64.SECOND, epoch
        v = t.x_ticks(x0, x1, 10, time_mode='relative', epoch=epoch)
        z0 = v['offset'] + int(v['major'][0] * time64.SECOND)
        z1 = v['offset'] + int(v['major'][-1] * time64.SECOND)
        self.assertGreaterEqual(z0, x0)
        self.assertLessEqual(z1, x1)


class TestXRelativeEpoch(unittest.TestCase):

    def setUp(self):
        self.state = {}
        self.e0 = time64.YEAR
        self.e1 = time64.YEAR + 10 * time64.SECOND

    def epoch(self, e0, e1, is_streaming=True):
        return t.x_relative_epoch(self.state, e0, e1, is_streaming)

    def test_buffer_growing(self):
        # e0 constant while e1 advances: epoch tracks e0 exactly
        self.assertEqual(self.e0, self.epoch(self.e0, self.e1))
        self.assertEqual(self.e0, self.epoch(self.e0, self.e1 + time64.SECOND))

    def test_jls_file(self):
        self.assertEqual(self.e0, self.epoch(self.e0, self.e1, is_streaming=False))
        self.assertEqual(self.e0, self.epoch(self.e0, self.e1, is_streaming=False))

    def test_buffer_wrap_streaming_is_stable(self):
        # e0 advances in 2 s chunks every other call, e1 advances 1 s per call
        s = time64.SECOND
        self.epoch(self.e0, self.e1)
        self.assertEqual(self.e0, self.epoch(self.e0, self.e1 + s))
        epoch = self.state['epoch']
        for k in range(2, 10):
            e0 = self.e0 + (k // 2) * 2 * s
            e1 = self.e1 + k * s
            # epoch advances in lockstep with e1: never jumps, never exceeds e0
            expect = epoch + (e1 - self.state['e1'])
            self.assertEqual(expect, self.epoch(e0, e1))
            self.assertLessEqual(expect, e0)
            epoch = expect

    def test_pause_resyncs_to_e0(self):
        s = time64.SECOND
        self.epoch(self.e0, self.e1)
        self.epoch(self.e0 + 2 * s, self.e1 + s)  # wrap active
        e0 = self.e0 + 3 * s
        self.assertEqual(e0, self.epoch(e0, self.e1 + 2 * s, is_streaming=False))
        # remains synchronized to e0 after resume until the next wrap
        self.assertEqual(e0, self.epoch(e0, self.e1 + 3 * s))

    def test_drift_resync_rides_sawtooth_bottom(self):
        s = time64.SECOND
        self.epoch(self.e0, self.e1)
        e0 = self.e0 + 2 * s
        self.epoch(e0, self.e1 + s)  # wrap active, chunk = 2 s
        # e1 races ahead without an e0 advance: epoch would exceed e0
        self.assertEqual(e0 - 2 * s, self.epoch(e0, self.e1 + 6 * s))

    def test_stream_restart_resets(self):
        s = time64.SECOND
        self.epoch(self.e0, self.e1)
        self.epoch(self.e0 + 2 * s, self.e1 + s)  # wrap active
        # stream restart: coherent forward shift larger than the held data
        e0, e1 = self.e0 + 100 * s, self.e1 + 95 * s
        self.assertEqual(e0, self.epoch(e0, e1))
        # buffer grows from the restart: epoch stays at the new start
        self.assertEqual(e0, self.epoch(e0, e1 + 5 * s))

    def test_source_change_resets(self):
        s = time64.SECOND
        self.epoch(self.e0, self.e1)
        self.epoch(self.e0 + 2 * s, self.e1 + s)  # wrap active
        # new source: e0 moves backwards
        e0, e1 = self.e0 - time64.YEAR, self.e1 - time64.YEAR
        self.assertEqual(e0, self.epoch(e0, e1))
        self.assertEqual(e0, self.epoch(e0, e1 + s))


class TestTimeFormat(unittest.TestCase):

    def test_seconds(self):
        self.assertEqual(('0', 's'), t.time_fmt(0, 1, 1))
        self.assertEqual(('1', 's'), t.time_fmt(1, 1, 1))
        self.assertEqual(('1', 's'), t.time_fmt(1.2, 1, 1))
        self.assertEqual(('0:30', 'm:ss'), t.time_fmt(30, 60, 1))

    def test_minutes(self):
        self.assertEqual(('1:00', 'm:ss'), t.time_fmt(60, 120, 1))
        self.assertEqual(('1', 'm'), t.time_fmt(60, 120, 60))

    def test_days(self):
        day = 60 * 60 * 24
        self.assertEqual(('1', 'd'), t.time_fmt(day, 3 * day, day))
        self.assertEqual(('2', 'd'), t.time_fmt(2 * day, 3 * day, day))
        self.assertEqual(('1:00:00:01', 'd:hh:mm:ss'), t.time_fmt(day + 1, 3 * day, 1))


class TestAxisTicks(unittest.TestCase):

    def test_normal(self):
        ticks = t.ticks(0, 1.01, 0.2, 10)
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 6), ticks['major'])
        self.assertEqual(0.2, ticks['major_interval'])
        self.assertEqual(0.02, ticks['minor_interval'])
        self.assertEqual('', ticks['unit_prefix'])

    def test_major_max(self):
        ticks = t.ticks(0, 1.01, major_max=3)
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 3), ticks['major'])

    def test_major_max_override(self):
        ticks = t.ticks(0, 1.01, 0.2, 3)
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 3), ticks['major'])

    def test_preferred_prefix(self):
        ticks = t.ticks(0, 1.01, 0.2, prefix_preferred='m')
        np.testing.assert_allclose(np.linspace(0.0, 1.0, 6), ticks['major'])
        self.assertEqual(['0', '200', '400', '600', '800', '1000'], ticks['labels'])
        self.assertEqual(0.2, ticks['major_interval'])
        self.assertEqual('m', ticks['unit_prefix'])
