
# Publish-Subscribe

The Joulescope UI is built around a publish-subscribe (PubSub) architecture
([Wikipedia](https://en.wikipedia.org/wiki/Publish%E2%80%93subscribe_pattern)).
combined with the 
Command pattern ([Wikipedia](https://en.wikipedia.org/wiki/Command_pattern)).
This choice allows for loose coupling by topic name.  Compared to the Qt
Signal-Slot pattern, PubSub offers improved scalability.  For more details,
see the 
[Software Architecture and State](https://www.joulescope.com/blogs/blog/software-architecture-and-state)
blog post.

The Joulescope UI also uses the PubSub implementation to:

* Hold shared state (retained values)
  * Arbitrary value types: integers, floats, str, binary, lists, maps 
  * Support metadata
  * Support retained value query
  * Support subscriber callbacks of retained values on subscribe
* Hierarchical pubsub support
* Support commands (no retained value, with undo/redo)
* Support events (no retained value, no undo)
* Support request / response 
* Many-to-many communication between endpoints
* Save and restore operation
* Support "profiles"
  * Reconfigure profile with auto-save
  * Save profile to different name 
  * Load arbitrary profile
  * Revert profile to past history, last manual save?
  * Restore to default for Multimeter & Oscilloscope profiles
* Support undo / redo for values & commands
* Support completion code
* Support event
* Support automatic "preferences" widget population
  * Global, for all preferences in profile
  * Local, for a single entity [device, widget, plugin]
* Resynchronize all message processing the Qt thread.
  * Supports publishing from Qt, native, and Python threads.
  * Guaranteed in-order processing

This implementation has some features in common with "registry" systems,
such as the Microsoft Windows registry.

Topic names are any valid UTF-8. However, we highly recommend restricting topic
names to ASCII standard letters and numbers 0-9, A-Z, a-z, ".", _ and - 
(ASCII codes 45, 46, 48-57, 65-90, 95, 97-122).
The following symbols are reserved:

    /?#$'"`&@%

Topic metadata can be queried.  Updates are published to metadata
subscribers with the topic name appended with "$".  The metadata
is a map with the following fields:
* dtype: one of [obj, str, json, bin, f32, f64, u8, u16, u32, u64, i8, i16, i32, i64]
* brief: A brief string description (recommended).
* detail: A more detailed string description (optional).
* default: The recommended default value (optional).
* options: A list of options, where each option is each a flat list of: 
  [value [, alt1 [, ...]]] The alternates must be given in preference order. 
  The first value must be the value as dtype. The second value alt1 
  (when provided) is used to automatically populate user interfaces, 
  and it can be the same as value. Additional values will be 
  interpreted as equivalents.
* range: The list of [v_min, v_max] or [v_min, v_max, v_step]. 
  Both v_min and v_max are inclusive. v_step defaults to 1 if omitted.
* format: Formatting hints string:
* version: The u32 dtype should be interpreted as major8.minor8.patch16.
* flags: A list of flags for this topic. Options include:
  * ro: This topic cannot be updated.
  * hide: This topic should not appear in the user interface.
  * dev: Developer option that should not be used in production.


## Topics

The Joulescope UI uses a topic hierarchy.  The topic name
is constructed by concatenating each level with '/'.  Leading
and trailing '/' are not used.  The hierarchy is

* app_common  # shared across all profiles
  * profile
    * active: {profile_name}
    * available: [...]
    * start: {previous, ignore, named}
    * start_name: {profile_name}
  * paths
    * app
    * config_path
    * config_file
    * log
    * themes
    * update
  * app_update
    * check: [start, daily, weekly]
    * channel
  * log_level
  * developer
  * process_priority
* app
  * auto_open: [off, first, all, profile]
  * path
    * data_path 
    * data_path_type: ['Use fixed data_path', 'Most recently saved', 'Most recently used']
    * _mru_saved
    * _mru_used
    * _mru_list
    * mru_count
  * units
    * accumulator   
    * charge
    * energy
    * time
* devices (device registry)
  * {device}
    * name: {name}
    * driver: {package.module.driver}
    * path: {subtopic}
    * capabilities
      * stream: 0, 1
      * statistics: 0, 1
    * settings
      * {subtopic}: {value}
    * sources
      * {source}  ( for JS110 and JS220)
        * name
        * vendor
        * model
        * version
        * serial_number
        * !statistics
        * statistics_status
        * stream_status
        * !status
        * signals
          * {signal}
            * units
            * sample_rate
            * !stream
            * !data_req
* drivers (driver registry)
  * {package.module.driver}
    * name 
    * version
    * device_paths: [{p1}, ...]
    * defaults
      * {device} 
        * {subtopic}: {value} 
  * jsdrv
  * jls_v1
  * jls_v2
* plugins (plugin registry)
  * {package.module.plugin}
    * name
    * settings
      * {subtopic}: {value}
* ui
  * font
  * theme
  * widgets (currently instantiated)
    * {package.module.widget}
      * {id}
        * name: {name}
        * settings
          * {subtopic}: {value}
  * windows (currently active)
    * {window}
      * name: {name} 
      * keep_on_top 
      * state
      * widgets: [{widget1/id1}, {widget2/id2}]
* widgets (widget registry)
  * {package.module.widget}
    * {subtopic}: {value}


## Changes from 0.10.x to 1.x.x

The 0.10.x (and earlier) Joulescope UI implementation evolved over time
and features a 
command processor ([Wikipedia](https://en.wikipedia.org/wiki/Command_pattern))
coupled with a preferences implementation.  Together, these form a
PubSub implementation.  While this supports shared state and PubSub,
the multiple profile implementation with defaults was confusing.  Some items
should never be overwritten, and too many things that could be overwritten
were unclear when moving between profiles.  The existing implementation was
also not well-structured to support to split registries and active entities.
The 1.x.x implementation upgrades the existing implementation to provide 
even more robustness and scalability.


## References

* Publish-subscribe
  * [Software Architecture and State](https://www.joulescope.com/blogs/blog/software-architecture-and-state)
  * [Wikipedia](https://en.wikipedia.org/wiki/Publish%E2%80%93subscribe_pattern)
  * [The Many Faces of Publish/Subscribe](http://members.unine.ch/pascal.felber/publications/CS-03.pdf)
* Command pattern
  * [Wikipedia](https://en.wikipedia.org/wiki/Command_pattern
* Implementations
  * Fitterbap pubsub 
    [doc](https://github.com/jetperch/fitterbap/blob/main/include/fitterbap/pubsub.md)
    [header](https://github.com/jetperch/fitterbap/blob/main/include/fitterbap/pubsub.h)
