# Copyright 2024 Jetperch LLC
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


from joulescope_ui.plugins import *


@register
class P1:
    SETTINGS = {
        'counter': {
            'dtype': 'int',
            'brief': 'A counter to keep track of class register',
            'default': 0,
        },
    }

    def __init__(self):
        pass

    @classmethod
    def on_cls_pubsub_register(cls, pubsub):
        topic = 'registry/P1/settings/counter'
        pubsub.publish(topic, pubsub.query(topic) + 1)
