# Copyright 2018 Jetperch LLC
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

"""Save data."""

import numpy as np
# from joulescope.data_recorder import DataRecorder


def save_csv(path, extracted_data, sampling_frequency):
    x = np.arange(len(extracted_data), dtype=np.float) * (1.0 / sampling_frequency)
    i_mean = extracted_data[:, 0, 0]
    v_mean = extracted_data[:, 1, 0]
    valid = np.isfinite(i_mean)

    x = x[valid].reshape((-1, 1))
    i_mean = i_mean[valid].reshape((-1, 1))
    v_mean = v_mean[valid].reshape((-1, 1))
    values = np.hstack((x, i_mean, v_mean))

    with open(path, 'wt') as f:
        np.savetxt(f, values, ['%.8f', '%.4e', '%.4f'], delimiter=',')


def save_jls(path):
    pass
    #r = DataRecorder(
    #    rv['filename'],
    #    sampling_frequency=self._device.sampling_frequency,
    #    calibration=self._device.calibration.data)


