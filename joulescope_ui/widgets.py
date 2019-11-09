# Copyright 2019 Jetperch LLC
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

# from joulescope_ui.uart import UartWidget
from joulescope_ui import control_widget
from joulescope_ui import developer_widget
from joulescope_ui import gpio_widget
from joulescope_ui import meter_widget
from joulescope_ui import single_value_widget


WIDGETS = [
    control_widget,
    developer_widget,
    gpio_widget,
    meter_widget,
    single_value_widget,
]


def widget_register(cmdp):
    widgets = {}
    for widget in WIDGETS:
        r = widget.widget_register(cmdp)
        widgets[r['name']] = r
    return widgets
