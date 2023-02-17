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
        * actions/!create:  what is provided?  time64 range, SIGNAL_BUFFER_SOURCE topics? 
    """

    RANGE_TOOL_OBJECT = 'range_tool.object'
    """An active range tool instance."""

    DEVICE_FACTORY = 'device_factory'
    """A factory for physically attached devices.
    
    The factory must implement the following:
        * actions/!finalize
    """

    DEVICE_CLASS = 'device.class'    # A physically attached device (JS110, JS220)
    """Default settings for physically attached devices"""

    DEVICE_OBJECT = 'device.object'  # A physically attached device (JS110, JS220)
    """A physically attached device.
    
    The pubsub object must implement the following:
        * actions/!finalize (on device removal or application close)
        * settings
          * name
          * info: {vendor, model, version, serial_number} read-only
          * state: 0:closed, 1:opening, 2:open, 3:closing (read-only for application)
          * state_req: 0:close, 1:open
    """

    SOURCE = 'source'             # device (JS110, JS220), JLS reader
    """A source that provides data.
    
    The pubsub source object must implement the following:
        * settings/name
        * settings/sources/{source_id}/name
        * settings/sources/{source_id}/info:  (read-only), recommend
          * vendor
          * model
          * version
          * serial_number
            
    Each STATISTIC_STREAM_SOURCE must implement:
        * events/statistics/!data
    
    Each SIGNAL_STREAM_SOURCE must implement:
        * settings/signals/{signal_id}/name
        * settings/signals/{signal_id}/enable
        * events/signals/{signal_id}/!data, obj with
          * source: source info
          * sample_id: starting sample id
          * sample_freq: in Hz
          * time: starting sample time, in int64 Q30 time
          * field: (current, voltage, power, current_range, voltage_range, gpi[N])
          * data
          * dtype: f32, u8, u1
          * units
          * origin_sample_id: starting sample id
          * origin_sample_freq
          * origin_decimate_factor
    
    Each SIGNAL_BUFFER_SOURCE must implement:
        * settings/signals/{signal_id}/name
        * settings/signals/{signal_id}/meta: obj with keys:
          * vendor
          * model
          * version
          * serial_number
          * field: (current, voltage, power, ...)
          * units
          * source: (unique_id, if not same as this instance)
          * source_topic: (fully qualified topic, if not from this instance)
          * sample_freq: (output)
        * settings/signals/{signal_id}/range: [t_start, t_end] in time64 (read-only)
        * actions/signals/{signal_id}/!req obj with keys:
          * time_start: The start time as time64.
          * time_end: The end time as time64.
          * length: The desired number of response entries.
          * rsp_topic: When computed, the results will be sent to this topic.
            The results can be either sample data or summary data.
            To guarantee sample data, specify either time64_end or length.
            Other requests may return sample data or summary data.
          * rsp_id: The arbitrary, immutable argument for rsp_topic.  Examples
            included int, string, and callables.
        * events/sources/!add {source_id}: (optional, only for dynamic sources)
        * events/sources/!remove {source_id}:  (optional, only for dynamic sources)
        * events/signals/!add {signal_id}: (optional, only for dynamic sources)
        * events/signals/!remove {signal_id}:  (optional, only for dynamic sources)
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
