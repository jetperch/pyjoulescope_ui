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

    RANGE_TOOL = 'range_tool'
    """An instantiable analysis tool class
    
    See RANGE_TOOL_CLASS and RANGE_TOOL_OBJECT.
    """

    RANGE_TOOL_CLASS = 'range_tool.class'
    """An analysis tool class that operates over a time range.

    The pubsub object must implement the following:
        * actions/!create
    """

    RANGE_TOOL_OBJECT = 'range_tool.object'
    """An active range tool instance."""

    DEVICE_FACTORY = 'device_factory'
    """A factory for physically attached devices."""

    DEVICE = 'device'                           # A physically attached device (JS110, JS220)
    """A physically attached device.
    
    The pubsub object must implement the following:
        * actions/!open
        * actions/!close
        * settings/name
        * info: {vendor, model, version, serial_number} read-only 
    """

    SIGNAL_SOURCE = 'signal.source'             # device (JS110, JS220), JLS reader
    """A source that provides signal samples.
    
    The pubsub object must implement the following:
        * settings/name
        * sources/{source}/name
        * sources/{source}/id
        * sources/{source}/info : {vendor, model, version, serial_number} read-only
        * sources/{source}/signals: [{source_id}.{signal}, ...] 
        * signals/{source_id}.{signal}/range [t_start, t_end]
        * signals/{source_id}.{signal}/!sample_req [t_start, t_end, cbk_topic, cbk_identifier]
        * signals/{source_id}.{signal}/!summary_req [t_start, t_end, t_incr, cbk_topic, cbk_identifier] 
    """

    SIGNAL_STREAMING = 'signal.streaming'
    """A signal source that can provide live data.
        * signals/{source_id}.{signal}/!signal_sink_add {sink_topic}: Add a sink.
          range publishes on new data.
        * signals/{source_id}.{signal}/!signal_sink_remove {sink_topic}: Remove a sink.
        * setting/signal_streaming_enable: Enable/disable signal streaming.  When true,
          the device may completely disable signal streaming to save bandwidth & processing
          until at least one sink is added to a signal. 
    """

    SIGNAL_SINK = 'signal.sink'                 # JLS recorder
    """A sink that consumes SIGNAL_SOURCE data."""

    STATISTICS_SOURCE = 'statistics.source'     # device (JS110, JS220)
    """A source that provides statistics for multimeter-like displays.
    
    A statistics source always provides data when the device is open.

    The pubsub object must implement the following:
        * events/!statistics_data {}  (sink subscribes)
        * settings/name
        * settings/statistics_source/enable
        * settings/statistics_source/frequency
        * settings/statistics_source/period
    """

    STATISTICS_SINK = 'statistics.sink'
    """A sink that consume STATISTICS_SOURCE information."""

    VIEW = 'view'
    WIDGET = 'widget'  # denotes both class and object
    WIDGET_CLASS = 'widget.class'
    """A widget class.
    
    The pubsub object must implement the following:
        * action/!create
    """

    WIDGET_OBJECT = 'widget.object'
