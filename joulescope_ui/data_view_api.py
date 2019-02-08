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

"""
Device implementations must implement a view member that conforms to this API.
USB backend which must be implemented for each platform type.
"""


class DataViewApi:
    """The data view API.

    :member x_range: (min: float, max: float)
    """
    def on_x_change(self, command: str, kwargs: dict):
        """Signal a requested change in the x-axis.

        :param command: The list of commands.
            * 'refresh' - {}  # resend the most recent data
            * 'resize' - {pixels: int}
            * 'span_absolute' - {range: (start: float, stop: float)}]
            * 'span_relative' - {center: float, gain: float}]
            * 'span_pan' - {delta: }]
        :param kwargs: The keyword arguments for the command.
        """
        raise NotImplementedError()

    def update(self):
        """Provide a data update.

        :return: (is_changed, (x, data)).  The is_change is True when
            (x, data) has changed, but False when no change.
            x is a length N np.ndarray(np.float) and data is
            np.ndarray((N, 3, 4), np.float32) of
            [length][current, voltage, power][mean, variance, min, max].
            The values x and data may be None when no data is available.
        """
        raise NotImplementedError()


class NullView:
    def __init__(self):
        self.x_range = [0.0, 1.0]  # why not

    def on_x_change(self, command: str, kwargs: dict):
        pass

    def update(self):
        return True, (None, None)
