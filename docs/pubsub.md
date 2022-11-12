
# Publish-Subscribe

The Joulescope UI is built around a publish-subscribe (PubSub) architecture
([Wikipedia](https://en.wikipedia.org/wiki/Publish%E2%80%93subscribe_pattern)).
This choice allows for loose coupling by topic name.  Compared to the Qt
Signal-Slot pattern, PubSub offers improved scalability.  For more details,
see the 
[Software Architecture and State](https://www.joulescope.com/blogs/blog/software-architecture-and-state)
blog post.

The Joulescope UI also uses the PubSub implementation to:

* Hold shared state and allow queries
* Many-to-many communication between endpoints
* Save and restore operation
* Support "profiles"
  * Reconfigure profile with auto-save
  * Save profile to different name 
  * Load arbitrary profile
  * Revert profile to past history, last manual save?
  * Restore to default for Multimeter & Oscilloscope profiles
* Support undo / redo
* Support automatic "preferences" widget population
  * Global, for all preferences in profile
  * Local, for a single entity [device, widget, plugin]
* Resynchronize all message processing the Qt thread.
  * Supports publishing from Qt, native, and Python threads.

This implementation has some features in common with "registry" systems,
such as the Microsoft Windows registry.


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
