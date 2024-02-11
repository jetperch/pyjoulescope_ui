# Copyright 2019-2022 Jetperch LLC
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

from .double_slider import DoubleSlider
from .draggable_list_widget import DraggableListWidget

from .accumulator import AccumulatorWidget
from .clock import ClockWidget
from .device_control import DeviceControlWidget, DeviceUpdateDialog
from .developer import DEVELOPER_WIDGETS
# from .example import ExampleWidget
from .memory import MemoryWidget
from .hamburger import HamburgerWidget
from .help import HelpWidget
from .jls_info import JlsInfoWidget
from .js220_cal import JS220CalibrationWidget
from .notes import NotesWidget
from .progress_bar import ProgressBarWidget
from .record_status import RecordStatusWidget
from .sidebar import SideBar
from .settings import SettingsWidget
from .signal_record import SignalRecordConfigWidget, SignalRecord
from .statistics_record import StatisticsRecordConfigWidget, StatisticsRecord
from .value import ValueWidget
from .view_manager import ViewManagerWidget, ViewManagerDialog
from .waveform import WaveformWidget
