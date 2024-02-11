# Copyright 2019-2023 Jetperch LLC
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

from .log_view_widget import LogViewWidget
from .profile_widget import ProfileWidget
from .publish_spy_widget import PublishSpyWidget
from .pubsub_explorer_widget import PubSubExplorerWidget

DEVELOPER_WIDGETS = [LogViewWidget, ProfileWidget, PublishSpyWidget, PubSubExplorerWidget]
