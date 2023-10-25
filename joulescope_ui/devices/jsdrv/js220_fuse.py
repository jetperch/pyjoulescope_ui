# Copyright 2022-2023 Jetperch LLC
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


import numpy as np
from collections.abc import Iterable


_I_SUM_LEN = 61
_JS220_Fq = 14  # 4q14
_JS220_Kq = 10  # 8q10
_DT = 2**-14


def to_q(value, q):
    return int(value * 2**int(q) + 0.5)


def fuse_to_config(threshold1, threshold2, duration):
    """Configure thresholds and duration to K, T.

    :param threshold1: The first threshold.
    :param threshold2: The second threshold.
    :param duration: The duration to trip at constant threshold2 input.
    :return: dict containing keys K, T, F, tau
    """
    t1 = threshold1
    t2 = threshold2
    d = duration
    L2 = t1 ** 2
    M2 = t2 ** 2
    K = (-1 / d) * np.log((M2 - L2) / M2)
    T = L2 / K
    F = 1 / (_I_SUM_LEN * np.sqrt(T))
    tau = - _DT / np.log(1 - K * _DT)
    return {
        'threshold1': t1,
        'threshold2': t2,
        'duration': d,
        'K': K,
        'T': T,
        'F': F,
        'tau': tau,
        'js220_fq': to_q(F, _JS220_Fq),
        'js220_kq': to_q(K, _JS220_Kq),
    }


# closed-form first order ODE solution
def fuse_curve(t, k, i):
    """Compute the fuse's response time.

    :param t: the current squared time coefficient
    :param k: the decay coefficient
    :param i: The constant current or np.ndarray of constant currents
    :return: The engage duration or durations.
        Return NaN if does not trip.
    """
    is_array = True
    if isinstance(i, np.ndarray):
        pass
    elif isinstance(i, Iterable):
        i = np.array([i], dtype=float)
    else:
        i = np.array([i], dtype=float)
        is_array = False
    y = np.empty(i.shape)
    y[:] = np.nan
    i2 = i ** 2
    log_top = i2 - k * t
    idx = log_top > 0
    y[idx] = -1 / k * np.log((i2[idx] - k * t) / i2[idx])
    if is_array:
        return y
    else:
        return y[0]
