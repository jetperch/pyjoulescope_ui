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


from enum import Enum


class CAPABILITIES(Enum):
    """Define the capabilities of a registered class or object."""

    RANGE_TOOL_CLASS = 'range_tool.class'
    """An analysis tool class that operates over a time range.

    The pubsub object must implement the following:
        * actions/!create
    """

    RANGE_TOOL_OBJECT = 'range_tool.object'
    """An active range tool instance."""

    DEVICE_FACTORY = 'device_factory'
    """A factory for physically attached devices.
    
    The factory must implement the following:
        * actions/!finalize
    """

    DEVICE_CLASS = 'device.class'  # A physically attached device (JS110, JS220)
    """Default settings for physically attached devices"""

    DEVICE_OBJECT = 'device.object'            # A physically attached device (JS110, JS220)
    """A physically attached device.
    
    The pubsub object must implement the following:
        * actions/!open
        * actions/!close
        * settings
          * name
          * info: {vendor, model, version, serial_number} read-only 
    """

    SOURCE = 'source'             # device (JS110, JS220), JLS reader
    """A source that provides data.
    
    The pubsub source object must implement the following:
        * settings
          * name
          * statistics 
          * sources/{source_id}
            * name
            * info : {vendor, model, version, serial_number}  (read-only)
            * signals: [{signal_id}, ...]  (read-only) 
          * signals/{signal_id}
            * name 
            
    Each STATISTIC_STREAM_SOURCE must also implement:
        * settings/statistics
          * frequency_base  (read-only)
          * rate_divisor
        * events
          * statistics/!data
    
    Each SIGNAL_STREAM_SOURCE must also implement:
        * settings/signals/{signal_id}
          * frequency: (may be read-only)
          * range: [t_start, t_end] (read-only)
        * events
          * signals/{signal_id}/!data
    
    Each SIGNAL_BUFFER_SOURCE must also implement:
        * settings/signals/{signal_id}
          * frequency: (may be read-only)
          * range: [t_start, t_end] (read-only)
        * actions/signals/{signal_id}
            * !sample_req [t_start, t_end, cbk_topic, cbk_identifier]
            * !summary_req [t_start, t_end, t_incr, cbk_topic, cbk_identifier] 
    """

    SIGNAL_STREAM_SOURCE = 'signal_stream.source'
    """A signal source that can provide live streaming signal sample data."""

    SIGNAL_STREAM_SINK = 'signal_stream.sink'                 # JLS recorder
    """A sink that consumes SIGNAL_STREAM_SOURCE data."""

    SIGNAL_BUFFER_SOURCE = 'signal_buffer.source'

    SIGNAL_BUFFER_SINK = 'signal_buffer.sink'

    STATISTIC_STREAM_SOURCE = 'statistics_stream.source'     # device (JS110, JS220)
    """A source that provides live streaming statistics for multimeter-like displays."""

    STATISTIC_STREAM_SINK = 'statistics_stream.sink'
    """A sink that consume STATISTIC_STREAM_SOURCE information."""

    VIEW_CLASS = 'view.class'
    """The central view manager."""

    VIEW_OBJECT = 'view.object'
    """A view instance."""

    WIDGET_CLASS = 'widget.class'
    """A widget class.
    
    The pubsub object must implement the following:
        * action/!create
    """

    WIDGET_OBJECT = 'widget.object'

    def __repr__(self):
        return "<%s.%s>" % (self.__class__.__name__, self._name_)

    def __str__(self):
        return self._value_
