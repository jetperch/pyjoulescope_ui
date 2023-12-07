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

    The pubsub class must implement the static method on_cls_action_run:
        * actions/!run: dict with the following keys:
          * x_range: (time64_min, time64_max)
          * origin: The unique_id for the originator.
          * signals: [signal_id, ...]
            where signal_id is in the form '{source}.{device}.{quantity}'.
            source is the unique_id of the source.
            '{device}.{quantity} is the subsignal_id for that source.
          * signal_default: signal_id.
            optional: The selected signal (if available) that should
            be used for the analysis if only one signal is required.
          * quantity: One of the quantity strings, like 'i'.
            optional: The active quantity for the range tool.    
          * kwargs: optional arguments for the command.
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
        * actions/!state_req 0:close, 1:open
        * settings
          * name
          * info: {vendor, model, version, serial_number} read-only
            version may be a dict with key/value pairs for each versioned subsystem.
          * state: 0:closed, 1:opening, 2:open, 3:closing (read-only for application)
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
        * actions/!accum_clear
    
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
        * settings/signals/{signal_id}/range: read-only dict with keys:
          * utc: [t_start, t_end]
          * samples: {'start': s_start, 'end': s_end, 'length': s_length}
          * sample_rate: For fixed-rate samples, the sample rate in Hz.
        * actions/!request obj with keys:
          * signal_id: The signal_id for the request.
          * time_type: 'utc' or 'samples'.
          * start: The starting time (utc time64 or samples).
          * end: The ending time (utc time64 or samples).
          * length: The number of requested entries evenly spread from start to end.          
          * rsp_topic: The arbitrary response topic.  When the computation is
            done, the response message will be sent here.
          * rsp_id: The optional and arbitrary response immutable object.
            Valid values include integers, strings, and callables.
            If providing method calls, be sure to save the binding to a
            member variable and reuse the same binding so that deduplication
            can work correctly.  Otherwise, each call will use a new binding
            that is different and will not allow deduplication matching.
        * actions/!annotations_request with keys:
          * rsp_topic: The arbitrary response topic called with list of 
            annotations.  See joulescope_ui/widgets/waveform/annotations.md for 
            definition, with two differences:
            1. Entries also contain an annotation_type field: x, y, text
            2. Entries contain plot_name rather than plot_index.
        * events/sources/!add {source_id}: (optional, only for dynamic sources)
        * events/sources/!remove {source_id}:  (optional, only for dynamic sources)
        * events/signals/!add {signal_id}: (optional, only for dynamic sources)
        * events/signals/!remove {signal_id}:  (optional, only for dynamic sources)
        
    The response is a dict with at least the following keys:
        * version: The response version = 1
        * rsp_id: The same rsp_id provided to the request
        * info: A dict with at least the following keys
          * field: The field name, one of i, v, p, r, 0, 1, 2, 3, T
          * units: The units for the values.
          * time_range_utc:
            * start
            * end
            * length
          * time_range_samples:
            * start
            * end
            * length
          * time_map
            * offset_time
            * offset_counter (samples)
            * counter_rate (sample rate)
        * response_type: Either 'samples' or 'summary'
        * data_type: one of f32, u4, u1
        * data: The data which whose shape is (N, 4) for summary or (N, ) for samples.
          u4 and u1 data is packed into bytes.
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
