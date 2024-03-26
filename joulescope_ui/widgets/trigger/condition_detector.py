# Copyright 2024 Jetperch LLC
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

import numpy as np


def is_digital_signal(s):
    return s in ['0', '1', '2', '3', 'T']


class _DetectAlways:

    def __init__(self, duration):
        self._duration = float(duration)
        self._d = 0.0

    def __call__(self, fs, samples):
        d = len(samples) / fs
        if (self._d + d) >= self._duration:
            idx = int(np.ceil((self._duration - self._d) * fs))
            self._d = 0.0
            return idx
        self._d += d


def _detect_never(fs, samples):
    return None


class _DetectEdge:

    def __init__(self, edge_type: str, threshold=None):
        self._carryover = None
        self._edge_type = edge_type.lower()
        if self._edge_type not in ['rising', 'falling', 'both']:
            raise ValueError(f'Invalid edge type {edge_type}')
        self._threshold = 0.5 if threshold is None else float(threshold)

    def clear(self):
        self._carryover = None

    def _detect(self, samples):
        if self._edge_type == 'rising':
            x = samples > self._threshold
            z = np.logical_and(np.logical_not(x[0:-1]), x[1:])
        elif self._edge_type == 'falling':
            x = samples < self._threshold
            z = np.logical_and(np.logical_not(x[0:-1]), x[1:])
        else:
            x = samples > self._threshold
            z = np.logical_xor(x[0:-1], x[1:])
        k = np.where(z)[0]
        if len(k) == 0:
            self._carryover = samples[-1]
            return None
        idx = k[0] + 1
        self._carryover = samples[idx]
        return idx

    def __call__(self, fs, samples):
        if not len(samples):
            return None
        if self._carryover is not None:
            if self._detect(np.array([self._carryover, samples[0]], dtype=samples.dtype)) is not None:
                return 0
        return self._detect(samples)


class _DetectDuration:

    def __init__(self, duration, fn):
        self._duration = float(duration)
        self._d = 0.0
        self._fn = fn

    def clear(self):
        self._d = 0.0

    def __call__(self, fs, samples):
        s = self._fn(samples)
        edges = np.where(np.diff(s))[0]
        edges = np.concatenate((edges, np.array([len(s) - 1], dtype=edges.dtype)))
        v = s[0]
        edge_last = 0
        for edge in edges:
            if not v:
                self._d = 0.0
            else:
                d = (edge - edge_last + 1) / fs
                if (self._d + d) >= self._duration:
                    idx = int(np.ceil((self._duration - self._d) * fs))
                    self._d = 0.0
                    return edge_last + idx
                self._d += d
            v = not v
            edge_last = edge + 1


def condition_detector_factory(config):
    """Construct a condition detector.

    :param config: The detector configuration.
    :return: Callable(fs, samples) the returns the sample offset
        of the first detected event or None.
    """
    config_type = config['type']
    signal = config['signal']
    if config_type == 'edge':
        threshold = 0.5 if is_digital_signal(signal) else float(config['value1'])
        return _DetectEdge(config['condition'], threshold)
    elif config_type == 'duration':
        if signal == 'always':
            return _DetectAlways(config['duration'])
        elif signal == 'never':
            return _detect_never
        elif is_digital_signal(signal):
            v = int(config['condition'])
            return _DetectDuration(config['duration'], lambda x: v == x)
        condition = config['condition']
        v1 = float(config['value1'])
        if condition in ['>', '<']:
            if condition == '>':
                fn = lambda x: x > v1
            else:
                fn = lambda x: x < v1
        elif condition in ['between', 'outside']:
            v2 = float(config['value2'])
            if condition == 'between':
                fn = lambda x: np.logical_and(x >= v1, x <= v2)
            else:
                fn = lambda x: np.logical_or(x < v1, x > v2)
        else:
            raise ValueError(f'Invalid condition {condition}')
        return _DetectDuration(config['duration'], fn)
    raise ValueError(f'Unsupported config type {config_type}')
