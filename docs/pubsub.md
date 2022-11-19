
# Publish-Subscribe

The Joulescope UI is built around a publish-subscribe (PubSub) architecture
([Wikipedia](https://en.wikipedia.org/wiki/Publish%E2%80%93subscribe_pattern)).
combined with the 
Command pattern ([Wikipedia](https://en.wikipedia.org/wiki/Command_pattern)).
This choice allows for loose coupling between UI modules by topic name.
Modules can create, publish, and subscribe without importing other modules.
Compared to the Qt Signal-Slot pattern, PubSub offers improved scalability.
The downside is that topic names must be stable and well-known.
For more details, see the 
[Software Architecture and State](https://www.joulescope.com/blogs/blog/software-architecture-and-state)
blog post.

The Command pattern (also called "action" or "transaction" pattern)
allows for all UI actions to funnel through a central location.  This enables
consistent state management and support for undo/redo.  The Joulescope UI
intentionally does not use the Qt Undo framework, because we can provide
much greater flexibility in Python.

The Joulescope UI also uses the PubSub implementation to:

* Hold shared state (retained values)
  * Arbitrary value types: integers, floats, str, binary, lists, maps
  * Value validation on publish
  * Support metadata
  * Support retained value query
  * Support subscriber callbacks of retained values on subscribe
* Hierarchical pubsub support
* Support commands (no retained value, with undo/redo)
* Support events (no retained value, no undo)
* Support completion code
  * Supports request topic that replies to response topic when done
* Many-to-many communication between endpoints
* Save and restore operation
* Support "profiles"
  * Reconfigure profile with auto-save
  * Save profile to different name 
  * Load arbitrary profile
  * Revert profile to past history, last manual save?
  * Restore to default for Multimeter & Oscilloscope profiles
* Support undo / redo for values & commands
* Support automatic "preferences" widget population
  * Global, for all preferences in profile
  * Local, for a single entity [device, widget, plugin]
* Resynchronize all message processing the Qt thread.
  * Supports publishing from Qt, native, and Python threads.
  * Guaranteed in-order processing
  * Support blocking publish (except on Qt event thread). 

This implementation has some features in common with "registry" systems,
such as the Microsoft Windows registry.

Topic names are any valid UTF-8. However, we highly recommend restricting topic
names to ASCII standard letters and numbers 0-9, A-Z, a-z, ".", _ and - 
(ASCII codes 45, 46, 48-57, 65-90, 95, 97-122).
The following symbols are reserved:

    /?#$'"`&@%~

Topic values are retained and deduplicated by default.
Subtopic starting with '!' are not retained and are not deduplicated.
As a result, subtopics for commands, events, and completion callbacks
should all start with '!'.

Topic metadata can be queried.  Updates are published to metadata
subscribers with the topic name appended with "$".  For details
on the metadata fields, see 
:meth:`joulescope_ui.pubsub.Metadata`.


## Topics

The Joulescope UI uses a topic hierarchy.  The topic name
is constructed by concatenating each level with '/'.  Leading
and trailing '/' are not used.  The hierarchy is

* app_common  # shared across all profiles
  * name: {name}
  * actions
    * !undo {count}
    * !redo {count}
    * !subscribe {topic, update_fn, flags}
    * !unsubscribe {topic, update_fn, flags}
    * !unsubscribe_all {update_fn}
    * !topic_add {topic, metadata}
    * !topic_remove {topic}
  * profile
    * actions 
      * !add
      * !remove
      * !select
      * !save
      * !load
      * !restore
    * active
      * name: {name}
      * description: {description}
      * filename: {filename}
    * available:
      * {name}
        * name: {name}
        * description: {description}
        * filename: {filename}
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
    * channel: [alpha, beta, stable]
  * logging
    * console_level
    * file_level
    * module_levels
      * {module_name}: {level} 
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
    * accumulator_default: ['charge', 'energy']   
    * charge
    * energy
    * elapsed_time: ['seconds', 'D:hh:mm:ss']
* registry
  * actions
    * !add
    * !remove
  * devices (device registry)
    * {device}
      * name: {name}
      * description: {description}
      * driver: {package.module.driver}
      * path: {subtopic}
      * capabilities
        * stream: 0, 1
        * statistics: 0, 1
      * settings
        * {subtopic}: {value}
      * sources
        * {source}  (for JS110 and JS220)
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
              * dtype 
              * units
              * sample_rate
              * !sample_req [t_start, t_end, cbk_topic, cbk_identifier] 
              * !summary_req [t_start, t_end, t_incr, cbk_topic, cbk_identifier]
  * drivers (driver registry)
    * {package.module.driver}
      * name: {name}
      * description: {description}
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
      * name: {name}
      * description: {description}
      * settings
        * {subtopic}: {value}
  * widgets (widget registry)
    * {package.module.widget}
      * {subtopic}: {value}
* ui
  * font
  * theme
  * actions
    * !widget_add {widget, }
    * !widget_remove
    * !window_add
    * !window_remove
  * widgets (currently instantiated)
    * {package.module.widget}:{id}
      * name: {name}
      * settings
        * {subtopic}: {value}
  * windows (currently active)
    * {window}
      * name: {name}
      * keep_on_top 
      * state
      * widgets: [{widget1/id1}, {widget2/id2}]


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
  * [QSettings](https://doc.qt.io/qt-6/qsettings.html) -
    [PySide](https://doc.qt.io/qtforpython/PySide6/QtCore/QSettings.html)
  * [Implementing a preferences dialog window in PyQt](https://stackoverflow.com/questions/39023584/implementing-a-preferences-dialog-window-in-pyqt)
  * [PyQtConfig](https://www.mfitzp.com/article/pyqtconfig/)
  