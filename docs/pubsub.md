
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

* common  # shared across all profiles, saved as common.json
  * name: {app_name}
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
      * !add {name}
      * !remove {name}
      * !save
      * !load {name}
    * items
      * {name}
        * name: {name}
        * description: {description}
        * filename: {filename}
    * settings 
      * active: {name}
      * start_mode: {previous, ignore, named}
      * start_name: {name}
  * paths 
    * app
    * config
    * log
    * themes
    * update
* registry
  * classes
    * actions
      * !add
      * !remove
    * items
      * {package.module.class}
        * name: {name}
        * brief: {brief}
        * description: {description}
        * capabilities: []
        * settings  (optional defaults)
          * {path}: {value}
        * version: {version}
  * objects
    * actions
      * !add
      * !remove
    * items 
      * {unique_id}
        * item: {package.module.item}
        * metadata
          * id
          * name: {name}
          * brief: {brief}
          * description: {description}
          * capabilities: []
        * parent: {unique_id}
        * children: [{unique_id1}, ...]
        * actions
          * !{action1}
        * callbacks
          * !{callback1} 
        * settings
          * {path}: {value}
        * version: {version}
  * capabilities
    * {capability}
      * actions
        * !add
        * !remove
      * list: [{unique_id1}, ...]

Capabilities include:
* sample_range_tool
* device_factory
* device
* keyboard_shortcut
* signal_sink (JLS v2 recorder)
* signal_source (device, JLS v2 reader)
* statistics_source (device)
* view
* widget




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
  