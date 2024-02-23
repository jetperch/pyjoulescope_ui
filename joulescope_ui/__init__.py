# Copyright 2018-2022 Jetperch LLC
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
from .pubsub import PubSub, get_instance, get_topic_name, get_unique_id, PUBSUB_TOPICS, REGISTRY_MANAGER_TOPICS, \
                    is_pubsub_registered
from .metadata import Metadata
from .tooltip import tooltip_format
from .capabilities import CAPABILITIES
from .locale import N_
from pyjoulescope_driver import time64


__all__ = ['__version__', 'pubsub_singleton', 'register', 'register_decorator', 'is_pubsub_registered',
           'is_release',
           'time64',
           'PUBSUB_TOPICS', 'REGISTRY_MANAGER_TOPICS',
           'tooltip_format',
           'CAPABILITIES', 'Metadata', 'N_',
           'get_instance', 'get_topic_name', 'get_unique_id']


def _pubsub_factory() -> PubSub:
    """Generate and configure the singleton pubsub instance."""
    p = PubSub(skip_core_undo=True)
    p.registry_initialize()
    for capability in CAPABILITIES:
        p.register_capability(capability.value)
    return p


pubsub_singleton = _pubsub_factory()  # type: PubSub
"""Singleton PubSub instance."""


def register(obj, unique_id: str = None):
    """Registration function for classes and instances.

    :param obj: The class type or instance to register.
    :param unique_id: The unique_id to use for this class.
        None (default) determines a suitable unique_id.
        For classes, the class name.
        For instances, a randomly generated value.
    :type unique_id: str, optional.  When provided,
        this function CANNOT be used as a class decorator.
    :return: obj.  Note the difference from func:`PubSub.register`!

    This function can be used as a class decorator as long
    as no arguments are provided.  Use :meth:`register_decorator`
    when arguments are required.
    """
    pubsub_singleton.register(obj, unique_id)
    return obj


def register_decorator(unique_id: str = None):
    """Registration function for classes and instances.

    :param unique_id: The unique_id to use for this class.
        None (default) determines a suitable unique_id.
        For classes, the class name.
        For instances, a randomly generated value.
    :type unique_id: str, optional.
    :return: The decorator function that calls :meth:`register`.
    """
    def fn(obj):
        return register(obj, unique_id=unique_id)
    return fn


is_pyinstaller = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
is_nuitka = '__compiled__' in globals()
is_release = is_pyinstaller or is_nuitka
