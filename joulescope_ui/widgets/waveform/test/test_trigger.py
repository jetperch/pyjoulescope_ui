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

"""Test joulescope_ui.widgets.waveform.trigger."""

import unittest
import numpy as np
from joulescope_ui.widgets.waveform import trigger
from joulescope_ui.widgets.waveform.trigger import EdgeTrigger, TriggerHistory, TriggerScanner


def _sine(n, period, offset=0.0, phase=0.0):
    k = np.arange(n, dtype=np.float64)
    return (np.sin(2 * np.pi * (k / period) + phase) + offset).astype(np.float32)


class TestSiParse(unittest.TestCase):

    def test_plain(self):
        self.assertEqual(1.5, trigger.si_parse('1.5'))
        self.assertEqual(-2.0, trigger.si_parse(' -2 '))
        self.assertEqual(1e-3, trigger.si_parse('1e-3'))
        self.assertEqual(0.5, trigger.si_parse('.5'))

    def test_prefix(self):
        self.assertAlmostEqual(-20e-6, trigger.si_parse('-20u'))
        self.assertAlmostEqual(20e-6, trigger.si_parse('20 µ'))
        self.assertAlmostEqual(0.150, trigger.si_parse('150 mA', 'A'))
        self.assertAlmostEqual(3.3, trigger.si_parse('3.3V', 'V'))
        self.assertAlmostEqual(2e3, trigger.si_parse('2k'))

    def test_invalid(self):
        for txt in ['', 'abc', '1.2.3', '5 V', '5 mV', '1 x']:
            with self.assertRaises(ValueError, msg=txt):
                trigger.si_parse(txt, 'A')


class TestEdgeTrigger(unittest.TestCase):

    def test_rising_interpolated(self):
        d = EdgeTrigger('rising', 0.5)
        p = d.process(100, np.array([0, 0, 1, 1, 0, 0, 1], dtype=np.float32))
        np.testing.assert_allclose([101.5, 105.5], p)

    def test_rising_interpolation_fraction(self):
        d = EdgeTrigger('rising', 0.25)
        p = d.process(0, np.array([0.0, 0.0, 1.0], dtype=np.float32))
        np.testing.assert_allclose([1.25], p)

    def test_falling(self):
        d = EdgeTrigger('falling', 0.5)
        p = d.process(0, np.array([1, 1, 0, 0, 1, 0], dtype=np.float32))
        np.testing.assert_allclose([1.5, 4.5], p)

    def test_either(self):
        d = EdgeTrigger('either', 0.5)
        p = d.process(0, np.array([0, 1, 1, 0, 1], dtype=np.float32))
        np.testing.assert_allclose([0.5, 2.5, 3.5], p)

    def test_initial_level_does_not_trigger(self):
        # starting above the level is not a rising edge: the trigger must arm first
        d = EdgeTrigger('rising', 0.5)
        self.assertEqual(0, len(d.process(0, np.ones(10, dtype=np.float32))))

    def test_sine_period(self):
        period = 100.0
        d = EdgeTrigger('rising', 0.0)
        p = d.process(0, _sine(1000, period, phase=-np.pi / 2))
        np.testing.assert_allclose(np.diff(p), period, atol=0.05)

    def test_across_blocks(self):
        x = _sine(10000, 37.3)
        d1 = EdgeTrigger('either', 0.1)
        p1 = d1.process(5000, x)
        d2 = EdgeTrigger('either', 0.1)
        p2 = np.concatenate([d2.process(5000 + k, x[k:k + 777]) for k in range(0, len(x), 777)])
        np.testing.assert_allclose(p1, p2)

    def test_edge_on_block_boundary(self):
        d = EdgeTrigger('rising', 0.5)
        self.assertEqual(0, len(d.process(0, np.array([0, 0, 0], dtype=np.float32))))
        np.testing.assert_allclose([2.5], d.process(3, np.array([1, 1], dtype=np.float32)))

    def test_hysteresis_rejects_noise(self):
        rng = np.random.default_rng(1)
        x = np.repeat(np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float32), 1000)
        x += rng.normal(0, 0.02, len(x)).astype(np.float32)
        x[1000 - 50: 1000 + 50] = 0.5 + rng.normal(0, 0.05, 100)  # noise at the edge
        d0 = EdgeTrigger('rising', 0.5)
        self.assertGreater(len(d0.process(0, x)), 2)  # chatter
        d1 = EdgeTrigger('rising', 0.5, hysteresis=0.3)
        p = d1.process(0, x)
        self.assertEqual(2, len(p))
        self.assertTrue(949 <= p[0] <= 1050)  # first crossing in the noisy edge
        self.assertTrue(2990 <= p[1] <= 3010)

    def test_hysteresis_falling(self):
        x = np.array([1, 0.45, 0.55, 0.45, 0.55, 1.0, 0.0], dtype=np.float32)
        d = EdgeTrigger('falling', 0.5, hysteresis=0.2)
        np.testing.assert_allclose([0.0 + (1 - 0.5) / (1 - 0.45), 5.5], d.process(0, x), atol=1e-6)

    def test_holdoff(self):
        x = np.tile(np.array([0, 1], dtype=np.float32), 50)  # rising at 0.5, 2.5, 4.5, ...
        d = EdgeTrigger('rising', 0.5, holdoff=5.0)
        p = d.process(0, x)
        np.testing.assert_allclose(np.arange(0.5, 100, 6.0), p)

    def test_holdoff_across_blocks(self):
        x = np.tile(np.array([0, 1], dtype=np.float32), 50)
        d1 = EdgeTrigger('rising', 0.5, holdoff=7.0)
        p1 = d1.process(0, x)
        d2 = EdgeTrigger('rising', 0.5, holdoff=7.0)
        p2 = np.concatenate([d2.process(k, x[k:k + 3]) for k in range(0, len(x), 3)])
        np.testing.assert_allclose(p1, p2)

    def test_holdoff_locks_burst_start(self):
        # bursts of 5 pulses every 100 samples: holdoff 50 locks to each first pulse
        burst = np.zeros(100, dtype=np.float32)
        for k in range(5):
            burst[10 + 4 * k: 12 + 4 * k] = 1
        x = np.tile(burst, 10)
        d = EdgeTrigger('rising', 0.5, holdoff=50)
        np.testing.assert_allclose(9.5 + 100 * np.arange(10), d.process(0, x))

    def test_gap_resets_state(self):
        d = EdgeTrigger('rising', 0.5)
        d.process(0, np.array([0, 0], dtype=np.float32))
        # gap: the edge state before sample 10 is unknown, so no trigger at 10
        self.assertEqual(0, len(d.process(10, np.array([1, 1], dtype=np.float32))))

    def test_overlap_skipped(self):
        d = EdgeTrigger('rising', 0.5)
        np.testing.assert_allclose([1.5], d.process(0, np.array([0, 0, 1, 1], dtype=np.float32)))
        p = d.process(2, np.array([1, 1, 0, 1], dtype=np.float32))  # samples 2, 3 repeat
        np.testing.assert_allclose([4.5], p)

    def test_nan_holds_state(self):
        d = EdgeTrigger('rising', 0.5)
        p = d.process(0, np.array([0, np.nan, np.nan, 1], dtype=np.float32))
        np.testing.assert_allclose([3.0], p)  # cannot interpolate across NaN

    def test_digital(self):
        d = EdgeTrigger('rising', trigger.DIGITAL_LEVEL)
        p = d.process(0, np.array([0, 0, 1, 1, 0, 1], dtype=np.uint8))
        np.testing.assert_allclose([1.5, 4.5], p)

    def test_invalid_edge(self):
        with self.assertRaises(ValueError):
            EdgeTrigger('sideways')


class TestTriggerHistory(unittest.TestCase):

    def test_latest(self):
        h = TriggerHistory()
        self.assertIsNone(h.latest())
        h.extend([10, 20, 30])
        self.assertEqual(30, h.latest())
        self.assertEqual(20, h.latest(29))
        self.assertEqual(30, h.latest(30))
        self.assertIsNone(h.latest(9))

    def test_increasing_only(self):
        h = TriggerHistory()
        h.extend([10, 20, 15, 20, 25])
        self.assertEqual(3, len(h))

    def test_prune_and_maxlen(self):
        h = TriggerHistory(maxlen=3)
        h.extend([1, 2, 3, 4, 5])
        self.assertEqual(3, len(h))
        h.prune(5)
        self.assertEqual(1, len(h))
        self.assertEqual(5, h.latest())


class TestTriggerSelect(unittest.TestCase):

    def test_window(self):
        self.assertEqual([900, 1100], trigger.trigger_window(1000, 200, 0.5))
        self.assertEqual([1000, 1200], trigger.trigger_window(1000, 200, 0.0))
        self.assertEqual([800, 1000], trigger.trigger_window(1000, 200, 1.0))

    def test_select_requires_post_trigger_data(self):
        h = TriggerHistory()
        h.extend([100, 500, 900])
        # view 200, centered: post-trigger needs 100 after the trigger
        self.assertEqual(900, trigger.trigger_select(h, 1000, 200, 0.5))
        self.assertEqual(500, trigger.trigger_select(h, 999, 200, 0.5))
        self.assertEqual(500, trigger.trigger_select(h, 1000, 200, 0.0))
        self.assertEqual(900, trigger.trigger_select(h, 900, 200, 1.0))


class TestTriggerScanner(unittest.TestCase):

    def test_first_request_uses_lookback(self):
        s = TriggerScanner()
        self.assertEqual((900, 1000), s.request(0, 1000, 100, now=0.0))
        self.assertIsNone(s.request(0, 1000, 100, now=0.1))  # pending

    def test_lookback_bounded_by_buffer(self):
        s = TriggerScanner()
        self.assertEqual((500, 1000), s.request(500, 1000, 10000, now=0.0))

    def test_continue_after_response(self):
        s = TriggerScanner()
        s.request(0, 1000, 100, now=0.0)
        s.on_response(900, np.zeros(101, dtype=np.float32))
        self.assertEqual(1001, s.sample_next)
        self.assertIsNone(s.request(0, 1000, 100, now=0.1))  # nothing new
        self.assertEqual((1001, 1500), s.request(0, 1500, 100, now=0.2))

    def test_chunked(self):
        s = TriggerScanner()
        n = trigger.SCAN_CHUNK_SAMPLES
        start, end = s.request(0, 3 * n, 3 * n, now=0.0)
        self.assertEqual((0, n - 1), (start, end))

    def test_timeout(self):
        s = TriggerScanner()
        s.request(0, 1000, 100, now=0.0)
        self.assertIsNone(s.request(0, 1000, 100, now=trigger.SCAN_TIMEOUT_S / 2))
        self.assertEqual((900, 1000), s.request(0, 1000, 100, now=trigger.SCAN_TIMEOUT_S * 2))

    def test_evicted_restarts(self):
        s = TriggerScanner()
        s.request(0, 1000, 100, now=0.0)
        s.on_response(900, np.zeros(101, dtype=np.float32))
        self.assertEqual((1900, 2000), s.request(1500, 2000, 100, now=1.0))

    def test_backlog_skips_ahead(self):
        s = TriggerScanner()
        s.request(0, 1000, 100, now=0.0)
        s.on_response(900, np.zeros(101, dtype=np.float32))
        end = 1001 + trigger.SCAN_BACKLOG_SAMPLES + 10
        self.assertEqual((end - 100, end), s.request(0, end, 100, now=1.0))

    def test_stale_response_ignored(self):
        s = TriggerScanner()
        s.detector.configure('rising', 0.5)
        x = np.array([0, 1] * 10, dtype=np.float32)
        self.assertIsNone(s.on_response(0, x))  # no request pending
        s.request(0, 1000, 100, now=0.0)        # requests 900..1000
        s.reset(start=990)                      # such as single mode arm
        s.request(0, 1000, 100, now=0.1)        # requests 990..1000
        self.assertIsNone(s.on_response(900, x))  # response to the old request
        self.assertTrue(s.is_pending)
        np.testing.assert_allclose([990.5], s.on_response(990, x[:2]))

    def test_evicted_response_accepted(self):
        s = TriggerScanner()
        s.request(0, 1000, 100, now=0.0)
        self.assertIsNotNone(s.on_response(950, np.zeros(10, dtype=np.float32)))
        self.assertEqual(960, s.sample_next)

    def test_reset_with_start(self):
        s = TriggerScanner()
        s.history.extend([5])
        s.reset(start=1000)
        self.assertEqual(0, len(s.history))
        self.assertEqual((1000, 1200), s.request(0, 1200, 500, now=0.0))

    def test_detects_through_scans(self):
        s = TriggerScanner()
        s.detector.configure('rising', 0.0)
        x = _sine(20000, 250.0, phase=-np.pi / 2)
        positions = []
        buf_end = 4999
        while True:
            r = s.request(0, buf_end, 5000, now=0.0)
            if r is None:
                if buf_end >= len(x) - 1:
                    break
                buf_end = min(len(x) - 1, buf_end + 3000)
                continue
            start, end = r
            positions.append(s.on_response(start, x[start:end + 1]))
        p = np.concatenate(positions)
        np.testing.assert_allclose(np.diff(p), 250.0, atol=0.05)
        self.assertEqual(len(x) // 250, len(p))  # crossings at 62.5 + 250 * k


if __name__ == '__main__':
    unittest.main()
