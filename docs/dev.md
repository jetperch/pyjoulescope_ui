

## Guiding Principles

* Easy things must be easy.
  New UI installations must start in Multimeter view and just work.
  Switching to Oscilloscope (Waveform) view should also just work.
* Hard things should be possible, but not necessarily in the UI.
  Forcing some features to Python scripting is acceptable.
  We prioritize UI ease of use over breadth.  Any potential feature
  implementation that compromises the ease of "easy things" MUST
  be redesigned.
* Single instrument support must be automatic and seamless, 
  even if the user swaps instruments.
* Multiple instrument support and controls should be hidden if possible when
  only have a single instrument.  If not hidden, they must not be 
  intrusive or needed.
* When multiple instruments are connected, automatically show multiple 
  instrument controls.

## State
The Joulescope UI stores state for each widget in each view on exit.
The file is 
`{userappdir}/joulescope/config/joulescope_ui_config.json`.
It also keeps historical settings in 
`{userappdir}/joulescope/config/joulescope_ui_config.ZZZ.json`.

Note that `{userappdir}` depends on the OS.
The easiest way to find it is to select **Help** → **View logs...** 
in the Joulescope UI.  Go up one directory and select the `config` directory.,

The Joulescope UI maintains state for JLS viewer mode separately.
These are `joulescope_ui_file_config.json` and `joulescope_ui_file_config.ZZZ.json`.

You could edit these configuration files outside of the Joulescope UI
to control your Joulescope UI experience. 
We definitely do not support this though.

The JLS file also has some settings that get applied when you
load it in the UI, as we discussed on the
[forum](https://forum.joulescope.com/t/default-view-when-loading-a-pre-generated-jls-file/1034)

You can explore and edit nearly all state with the **Settings** widget.
Note the tabs for `Settings`, `Colors`, `Fonts`, and `Defines`.
Under the `Widgets` hierarchy, you can find the defaults for 
the Widget type and the specific settings for each of those 
Widgets in the current view.
Widgets can provide other ways to manipulate this state, 
such as dedicated UI buttons.

Note that when you close a widget, 
you lose any settings changes for that widget.
Adding a new widget of the same type starts with the defaults fo
that widget type.
If you want to maintain different widget settings, you can add more views.

The UI uses Publish-Subscribe internally, and the application state
lives as retained values in the PubSub instance.
The PubSub instance is responsible for saving and restoring this state.

You can also explore the full PubSub mechanism.
In the **Settings** widget, select **UI** and activate **developer**.
You can add the **Publish Spy** and **PubSub Explorer** widgets to your view.

Since the Joulescope UI 1.0 and newer is all-in on PubSub and the command pattern,
you can do everything programmatically that you can do with human UI interaction.

## Qt / PySide6 memory model and object lifetime

To correctly manage memory in PySide6:

* Ensure all QObjects get a parent, except for the few top-level QObjects. 
  You only need to maintain a Python reference to the QObjects without 
  a parent. You may opt to keep a reference to QObjects you need to 
  manipulate through code and not just Signal / Slot connections.
  The following methods assign ownership:
  * QWidget (and child class) constructors with parent argument.
  * QLayout: addWidget(), addItem(), setParent()
  * QWidgetAction: setDefaultWidget()
  * QStatusBar: addPermanentWidget()
* When using Signals and Slots, any callable works as a slot in Python. 
  Avoid the temptation and stick to QObjects with Slot methods. 
  Qt is designed for this.
* If you do want to use a lambda for a Slot, use a wrapper QObject 
  with a Slot method that invokes the lambda.
* Note that Qt automatically deletes all children when the 
  parent is deleted.
* Note that Qt automatically disconnects all Signals and Slots for 
  a QObject when that QObject is deleted.
* Use QObject.deleteLater() to delete QObjects.
* Keep QObject Python references local. Use Signals and Slots to communicate,
  especially between parent-child Widgets. For larger applications, 
  Signals & Slots communication has scaling challenges. Consider using PubSub.

General Guidance:

* Avoid QLayout.setLayout().
  Pass the parent widget in the constructor for all layouts.
* Use QObject.parent() rather than store separate member references.
* Maintaining local QWidget member references is not required 
  unless you need to programmatically manipulate
  to QWidget (not just signals & slots) or you want to remove the widget
  from the layout but keep it (usually hidden).
  Default to not storing local member references.
* All QDialog's must have the main window (or a child widget) as
  the parent, which is necessary for both memory management and styles.
* Mark all slots using the `QtCore.Slot` decorator.
  See [docs](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/signals_and_slots.html#the-slot-class).


See [forum post](https://forum.qt.io/topic/154590/pyside6-memory-model-and-qobject-lifetime-management/11)


## Notes

* [PubSub](pubsub.md)
* [Qt Advanced Docking System](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System)
  * PySide6-QtAds python bindings:
    [GitHub](https://github.com/mborgerson/Qt-Advanced-Docking-System)
    | [pypi](https://pypi.org/project/PySide6-QtAds/) 
  * [Examples](https://github.com/mborgerson/Qt-Advanced-Docking-System/tree/pyside6/examples)
* [Display PDF in Qt](https://python-forum.io/thread-36741.html)
* Sidebar
  * [QStackedLayout](https://doc.qt.io/qt-6/qstackedlayout.html)
  * Widget Overlay
    * [StackOverflow] (https://stackoverflow.com/questions/19199863/draw-rectangular-overlay-on-qwidget-at-click)
    * TLDR; Don't add to layout, use setGeometry() and raise_().
* [pyinstaller](https://pyinstaller.org/en/stable/):
  [pypi](https://pypi.org/project/pyinstaller/)
  | [GitHub](https://github.com/pyinstaller/pyinstaller)
* [Nuitka](https://nuitka.net/)