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
Test joulescope_ui.widgets.waveform.line_segments
"""

import unittest
import numpy as np
from joulescope_ui.widgets.waveform.line_segments import clip_y, PointsF


class TestClipY(unittest.TestCase):

    def assert_xy(self, x_expect, y_expect, xy):
        np.testing.assert_allclose(x_expect, xy[0])
        np.testing.assert_allclose(y_expect, xy[1])

    def test_in_range(self):
        self.assert_xy([0, 1, 2], [0, 5, -5], clip_y([0, 1, 2], [0, 5, -5], -10, 10))

    def test_empty(self):
        self.assert_xy([], [], clip_y([], [], -10, 10))

    def test_single_point_run(self):
        xy = clip_y([0, 10, 20], [0, -100, 0], -10, 10)
        self.assert_xy([0, 1, 19, 20], [0, -10, -10, 0], xy)

    def test_multiple_point_run(self):
        xy = clip_y([0, 10, 20, 30, 40], [0, 100, 200, 100, 0], -10, 10)
        self.assert_xy([0, 1, 39, 40], [0, 10, 10, 0], xy)

    def test_first_and_last_out(self):
        xy = clip_y([0, 10, 20], [100, 0, -100], -10, 10)
        self.assert_xy([0, 9, 10, 11, 20], [10, 10, 0, -10, -10], xy)

    def test_opposite_runs(self):
        xy = clip_y([0, 10], [-100, 100], -10, 10)
        self.assert_xy([0, 4.5, 5.5, 10], [-10, -10, 10, 10], xy)

    def test_matches_clipped_original(self):
        """The in-range part does not move at any x."""
        rng = np.random.default_rng(352)
        for _ in range(20):
            x = np.cumsum(rng.uniform(0.5, 100, 200))
            y = rng.uniform(-50, 50, 200)
            spikes = rng.random(200) < 0.2
            y[spikes] = rng.choice([-1e6, 1e6], np.count_nonzero(spikes))
            x_c, y_c = clip_y(x, y, -20, 20)
            x_eval = np.linspace(x[0], x[-1], 20001)
            np.testing.assert_allclose(np.clip(np.interp(x_eval, x, y), -20, 20),
                                       np.interp(x_eval, x_c, y_c), atol=1e-6)


class TestPointsF(unittest.TestCase):

    def test_set_fill_y_limits(self):
        points = PointsF()
        segs = points.set_fill(np.array([0., 10, 20]), np.array([5., 5, 5]),
                               np.array([0., -100, 0]), (-10, 10))
        xy = [(p.x(), p.y()) for p in segs]
        self.assertEqual([(0, 5), (10, 5), (20, 5), (20, 0), (19, -10), (1, -10), (0, 0)], xy)

    def test_set_line_y_limits(self):
        points = PointsF()
        segs = points.set_line(np.array([0., 10, 20]), np.array([0., -100, 0]), (-10, 10))
        self.assertEqual([(0, 0), (1, -10), (19, -10), (20, 0)], [(p.x(), p.y()) for p in segs])
