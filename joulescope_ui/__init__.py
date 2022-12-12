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

from .version import __version__
import sys
from .pubsub import PubSub
from .metadata import Metadata
from .capabilities import CAPABILITIES

__all__ = ['__version__', 'pubsub', 'register', 'CAPABILITIES', 'Metadata']


def _pubsub_factory() -> PubSub:
    """Generate and configure the singleton pubsub instance."""
    p = PubSub()
    p.registry_initialize()
    for capability in CAPABILITIES:
        p.register_capability(capability.value)
    return p


pubsub = _pubsub_factory()  # type: PubSub
"""Singleton PubSub instance."""


def register(obj, unique_id: str = None):
    """Registration function for classes and instances.

    :param obj: The class type or instance to register.
    :param unique_id: The unique_id to use for this class.
        None (default) determines a suitable unique_id.
        For classes, the class name.
        For instances, a randomly generated value.
    :type unique_id: str, optional
    :return: obj.  Note the difference from func:`PubSub.register`!

    Can be used as a class decorator!
    """
    pubsub.register(obj, unique_id)
    return obj


frozen = getattr(sys, 'frozen', False)
if frozen:
    frozen = getattr(sys, '_MEIPASS', frozen)
