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


from typing import TypeAlias, Union
from .metadata import Metadata


MetadataFreeformType = dict[str, object]
MetadataExactType = dict[str, Metadata]
MetadataType = Union[MetadataFreeformType, MetadataExactType]


class RegisterClassAPI:

    CAPABILITIES = []
    """The list of capabilities supported by this class and it's instances.
    
    See joulescope_ui.capabilities.CAPABILITIES for the available options.
    Capabilities that register differently for class and instance/object
    should be specified as strings with a "@" suffix, like 'widget@'. 
    """

    EVENTS: MetadataType = {}
    """Define the events emitted by this class and/or its instances.
    
    This structure contains a map of event name strings to metadata.
    The metadata can either be a joulescope_ui.metadata.Metadata instance
    or a map suitable for providing to Metadata.
    """

    SETTINGS: MetadataType = {}
    """The map of setting name to metadata.

    If a setting provides on_cls_setting_{setting} or on_setting_{setting},
    then this will be registered with the PubSub instance.  Otherwise,
    a connection will be dynamically created to set the attribute value.
    If instance getters/setters are available, then the setter will be 
    monkey-patched to work.
    
    The metadata can either be a joulescope_ui.metadata.Metadata instance
    or a map suitable for providing to Metadata.
    """

    @staticmethod
    def on_cls_action_myname(value):
        """Register a class action under action/!myname.

        This function can have multiple signature types.
        See joulescope_ui.pubsub.PubSub.register_command for details.
        """
        raise NotImplementedError()

    @staticmethod
    def on_cls_callback_myname(topic: str, value):
        """Register a class callback under cbk/!myname.

        This function can have multiple signature types.
        See joulescope_ui.pubsub.PubSub.register_command for details.
        """
        raise NotImplementedError()

    @staticmethod
    def on_cls_setting_myname(value):
        """Register a class setting callback under settings/myname.

        The setting MUST be listed in SETTINGS.
        This function can have multiple signature types.
        See joulescope_ui.pubsub.PubSub.register_command for details.
        """
        raise NotImplementedError()

    def on_action_myname(self, value):
        """Register an instance action under action/!myname.

        This function can have multiple signature types.
        See joulescope_ui.pubsub.PubSub.register_command for details.
        """
        raise NotImplementedError()

    def on_callback_myname(self, pubsub, topic, value):
        """Register an instance callback under cbk/!myname.

        This function can have multiple signature types.
        See joulescope_ui.pubsub.PubSub.register_command for details.
        """
        raise NotImplementedError()

    def on_setting_myname(self, value):
        """Register a setting callback under settings/myname.

        The setting MUST be listed in SETTINGS.
        This function can have multiple signature types.
        See joulescope_ui.pubsub.PubSub.register_command for details.
        """
        raise NotImplementedError()
