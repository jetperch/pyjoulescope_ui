# Copyright 2022 Jetperch LLC
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


import joulescope_ui


class Profile:

    def __init__(self, pubsub=None):
        self.pubsub = joulescope_ui.pubsub if pubsub is None else pubsub
        self.pubsub.register(self, 'profile')

    def on_action_add(self, value):
        pass

    def on_action_remove(self, value):
        pass

    def on_action_save(self):
        pass

    def on_action_load(self, value):
        pass

