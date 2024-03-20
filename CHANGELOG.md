
# CHANGELOG

This file contains the list of changes made to pyjoulescope_ui.

---

## 1.0.61

2024 Mar 20

* Fixed JS110 performance degradation (blocking status in device thread) 
  using pyjoulescope_driver 1.4.8 → 1.4.10.


## 1.0.59

2024 Mar 12

* Modified sidebar buttons to disable when no Joulescopes connected.
* Renamed "plugins" directory to "range_tools".
* Modified widgets to display device name, not model-serial_number  #256
* Added optional Waveform widget feature to set the plot label  #255
* Added JLS v1 support to JLS Info Widget  #259
* Fixed JLS reopen support by adding optional on_pubsub_delete callback  #260
* Added "dots" to each Waveform widget sample when sufficiently zoomed in  #261
* Added snap to sample for Waveform widget hover display. 


## 1.0.58

2024 Feb 27

* Dropped Python 3.9 support as static methods are not callable until 3.10.
  See https://docs.python.org/3/whatsnew/3.10.html
* Updated Intel OpenGL dialog text.
* Updated 2024 out-of-office days.
* Added widget class not found handling on config load.
* Deferred rendering on class registration.
* Improved "developer" mode.
  * Renamed "debug" mode to "developer" mode.
  * Automatically close developer widgets on setting disable.
  * Renamed Debug widget to Profile widget.
  * Added Publish Spy widget.
  * Added Log View widget.
  * Added PubSub Explorer widget.
* Added WindowStaysOnTopHint to HelpHtmlMessageBox  #245
* Modified Export all data to work when streaming  #246
* Added zoom to dual markers in Waveform widget  #243
* Added Waveform widget move both dual markers when click on top Δt bar  #247
* Added preferred units to Waveform widget i, v, p plots  #248
* Added time format options to CSV statistics recording  #231
* Added option to set exact plot y-axis range in Waveform widget  #126
* Added support for Waveform widget precision and quantity selection  #130
* Added clock widget with support for local and UTC time.
* Added path info the issue report index.
* Added safe mode (Hold shift key at launch until window shows)  #250
* Modified view activate to restore geometry before dock state.
* Improved JsdrvStreamBuffer shutdown to prevent log warnings.
* Added startup dialog sequencing.
* Improved device update.
  * Defer update for several seconds to help insure system stability. 
  * Prompt user.
  * Update sequentially to minimize any update failure risks.
* Added color legend to Memory widget.
* Updated pyjls from 0.9.1 to 0.9.2 to improve corrupted JLS file handling.
* Updated pyjoulescope_driver from 1.4.6 to 1.4.8.
* Updated joulescope from 1.1.8 to 1.1.12.
* Updated PySide6-QtAds from 4.1.0.2 to
  [4.2.1](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System/releases)
  and PySide6 from 6.2.0 to 
  [6.2.2](https://code.qt.io/cgit/qt/qtreleasenotes.git/about/qt/6.6.2/release-note.md).
  The new versions address a number of stability issues.
* Removed unused pyperclip dependency.
* Converted deprecated QMouseEvent method calls to supported methods.
* Added missing menu items to menu widget storage.
* Added QtCore.Slot decorator to PySide6/Qt6 slots.
* Improved QMenu and Qt Slot memory management and object lifecycle management.
* Updated credits to include missing entries.
* Improved pubsub registration and callback management  #254
  * Added auto unsubscribe on object unregister to fix dangling subscribes.
  * Improved bound method handling to reduce memory leaks.
  * Reduced the number of pubsub_singleton usages.
  * Added subscribe() return object for use with unsubscribe().
  * Fixed settings widget to update on view changes  #253
* Fixed QDialog memory management.
* Improved widget open / close handling.
* Upgraded to Nuitka 2.0.5. 
* Fixed sidebar widget  #257  #258


## 1.0.48

2023 Dec 11

* Fixed device open when UI started with device open in another app.
  When other app closes device, can now open in the UI.
* Improved Waveform widget error handling.
* Updated pyjoulescope_driver 1.4.1 -> 1.4.6 with FW 1.2.1 and FPGA 1.2.1.
  * Improved JS220 communication robustness
  * Improved JS110 time sync long-term stability.
  * Fixed stream buffer use-after-free and remove timeout.
  * Fixed year on POSIX (macOS & Linux) systems.  #241
* Forced Nuitka 1.8.6 (1.9.3 causes crashes in Waveform widget).
* Bumped PySide6 to 6.6.0 with PySide6-QtAds to 4.1.0.2.
* Specified OpenGL 2.1 for "software" renderer (was 3.3 for all).
* Included opengl32sw.dll in Windows distribution.  #216
* Added dialog prompt to switch from Intel to software OpenGL renderer.  #216
* Added *.png to MANIFSET.in to fix "pip install".  #242
* Added CONTRIBUTING.md and CODE_OF_CONDUCT.md.  Updated docs. #151
* Fixed streaming Waveform widget not showing waveforms after opening JLS file.
* Improved Device Control widget device open/close.
* Updated QAction.triggered callback signatures from fn() to fn(checked=False)
  to eliminate warnings with Nuitka compiled code.


## 1.0.43

2023 Nov 30

* Deferred Waveform render_to_image operations to synchronize.  Fixes #239.
* Added app "opengl" setting and use "desktop" by default.
  Select "software" to workaround Intel UHD graphics issue #216. 
* Fixed JS220 device settings log warnings. 
* Increased the max number of logs from 4 to 10 included in issue reports.
* Changed VersionedFile to use temp file with process ID to avoid collisions.
* Display tooltips for Settings widget labels, not just values.
* Fixed device selection in Multimeter, Value, and Accumulator widgets.  #233
* Fixed software_update to log warning (not exception) on unsupported platform.
* Updated pyjoulescope_driver 1.4.0 -> 1.4.1 with fw 1.2.0 and FPGA 1.2.0.
  * Improved JS220 UTC time sync with FW 1.2.0 & FPGA 1.2.0 support.
  * Improved JS220 skip / drop sample handling.
* Modified internal signal_id format.


## 1.0.42

2023 Nov 14

* Attempted to further reduce potential anti-virus false positive detection.
  * Added '--python-flag=isolated' to Nuitka build. 
  * Added Nuitka report.
* Fixed macOS build process for latest delocate.


## 1.0.40

2023 Nov 13

* Added Nuitka commercial build for MS Windows in addition to pyinstaller.
* Bumped pyjoulescope_driver to 1.4.0 with JS220 FW 1.1.1.
* Added JS220 current offset calibration and voltage offset calibration.


## 1.0.37

2023 Oct 30

* Fixed devices not correctly added to CAPABILITIES  #234.
* Signed the joulescope.exe application for Windows distribution. 


## 1.0.36

2023 Oct 29

* Removed device control widget's color dependency on sidebar.


## 1.0.35

2023 Oct 26

* Added software controlled fuse support.
* Updated to pyjoulescope_driver 1.3.20 which includes
  JS220 FPGA & FW to 1.1.0 with fuse support.
* Updated to pyjls 0.8.2 with improved truncation recovery.
* Added exception catch to GL string get.
* Added Waveform widget "auto" marker statistics text position as default  #224
* Improved Waveform widget autoranging  #228
* Reduced required OpenGL API version from 4.4 to 3.3.
* Improved sidebar flyout widget #225
  * Automatically close when mouse leaves to the right.
  * Added vertical scroll bar to flyout.
  * Converted settings widget to flyout, not pop-over.
* Added automatic recording close on app exit  #232 


## 1.0.31

2023 Sep 19

* Fixed recording to a bad / missing path silently fails  #223
* Added automatic default user data path creation, helps with #223.
* Added option to specify full JLS record filename path.


## 1.0.30

2023 Sep 18

* Fixed multiple objects to delete themselves on unregister.
* Added zip_inspector entry point.
* Added disk free monitor to automatically close JLS recordings  #185
* Improved target power on/off icon  #218
* Fixed Waveform widget "mWh" right-hand statistics truncation.
* Fixed Waveform widget y-axis auto ranging when Min/Max is off.
* Added CI Windows installer signing using Azure HSM signing key.
* Improved JLS recordings
  * Migrated to pyjls 0.8.1
    * Automatically repair truncated files.
    * Added real-time mode that drops files rather than blocking PubSub.
  * Added error display when cannot open JLS  #217
  * Removed JLS blocking writes when streaming data (keep for export).
  * Display status message when JLS recording cannot keep up.
  * Added support for omitting data & reconstructing omitted data.
    BUT no UI configuration support yet.


## 1.0.29

2023 Jul 27

* Improved pubsub publish resynchronization.
* Improved waveform repaint synchronization.
* Reduced OpenGL from 4.6 (default) to 4.4 (helps Intel UHD graphics?)
* Fixed "abort" button on report issue widget.


## 1.0.28

2023 Jul 25

* Fixed waveform file display not zooming.


## 1.0.27

2023 Jul 25

* Fixed waveform relative dual markers on zoom.
* Added status and response time to report issue widget #212
* Fixed waveform relative x-axis dual marker "jitter" with streaming data #215


## 1.0.26

2023 Jul 24

* Fixed Value / Multimeter widget source combobox width.
  Also fixed a few other combobox widths.
* Added more detail to Help -> About.
* Fixed waveform add relative signal x-axis marker.
* Added manual size entry to Memory widget.
* Bumped pyjoulescope_driver from 1.3.17 to 1.3.18, which
  fixes dual markers showing incorrect values #213
* Bumped pyjls from 0.7.2 to 0.7.3.
* Fixed dual marker failure on edge #214


## 1.0.25

2023 Jul 19

* Fix menubar on macOS when dialog shown at start.


## 1.0.24

2023 Jul 19

* Added CHANGELOG.md and CREDITS.html to package data #207
* Fixed Multimeter widget hold not holding on resize #203
* Improved launch error handling.
  * Bundle error information and submit to support #210
  * Prompt the user with recovery options #204
* Added source selection to Accumulator Widget #201
* Added dual marker Δt interval entry on context menu #202
* Added relative time x-axis marker mode #200
* Added JLS info widget #209 #93
* Added export notes and dir icon.
* Added JLS viewer mode with separate configuration #205
  When open files using file association, just view the file.
  Does not affect "normal" configuration or open widgets.
* Fixed elided tab text in dock manager.
* Added manual "Report Issue" option.
* Added waveform right-click on Δt to manually set. 
* Added notes widget #93
* Renamed joulescope_ui.json to joulescope_ui.json_plus to avoid name collision.
* Bumped dependency versions:
  * joulescope 1.1.7 -> 1.1.8
  * pyjoulescope_driver 1.3.16 -> 1.3.17
  * PySide6 6.5.0 -> 6.5.1.1
  * PySide6-QtAds 4.0.3 -> 4.1.0


## 1.0.23

2023 Jun 29

* Fixed silent failure on waveform widget save image when extension omitted.  #196
* Fixed JLS v1 files voltage display incorrect.  #198
  * Affects recordings made with UI 0.10 and earlier. 
  * Fixes voltage waveform when zoomed in. 
  * Fixes voltage dual marker statistics.


## 1.0.22

2023 Jun 14

* Switched to "stable" update channel by default.
* Added GitHub Actions build.
* Improved macOS build: universal2 for macOS 11, 12, 13.


## 1.0.20

2023 Jun 1

* Fixed stream buffer warning.
* Fixed software update action incorrect when running python package. #192
* Display "Getting Started" on first UI run.
* Added help link to the new Joulescope UI User's Guide.
* Fixed missing folder icon. #191


## 1.0.19

2023 May 31

* Fixed text annotation remove.
* Fixed MemoryWidget still referenced after close (timer & pubsub).
* Fixed MemoryWidget "duration" oscillation.


## 1.0.18

2023 May 31

* Fixed JLS v2 open not working by correcting pubsub use.
* Deferred initial widget rendering.
  * Added pubsub_is_registered attribute.
  * Manager ignores render until pubsub_is_registered is true.
* Improved topic descriptions. 
* Modified macOS software update to query exact OS version. 
* Improved JLS v2 writer logging and error handling.
* Fixed JLS v2 recording with pyjls 0.7.0. 


## 1.0.17

2023 May 24

* Improved Waveform widget performance by using only one PointsF array.
* Added debug widget.
* Added "skip_undo" to settings metadata flags as needed.
* Reworked pubsub for better undo / redo support.
  * Fixed memory leak (excessive undo / redo information). 
  * Immediately process publish on pubsub thread.
  * Removed hierarchical undo/redo capture.
  * Add option to skip undo/redo for core pubsub actions. 
  * Added undo clear and redo clear.


### Known issues

1. Sidebar icons do not update on color scheme change #183
2. UI crashes when recording to JLS fills drive #185
3. Waveform widget does not implement undo / redo for all features #188
4. Widget close then undo does not restore state #189


## 1.0.16

2023 May 19

* Improved Waveform widget performance.
* Reduced process monitor CPU loading.
* Improved joulescope_driver performance on Windows.
* Fixed memory leak.


## 1.0.15

<span style="color:#6090ff">🛈 BETA RELEASE 🛈</span> 

2023 May 17

* Fixed "Device Control" widget not opening & closing cleanly.
* Fixed installation on Ubuntu from packages (joulescope_driver 1.3.9).
* Improved JLS annotations.
  * Added support for multiple JLS annotations files "base.anno*.jls".
  * Redirected JLS annotation file open to base JLS file open.
  * On dual x-marker export, exclude outer exported x-markers.
  * Added annotation save menu option.
* Fixed Waveform widget not fully unsubscribing.
* Fixed units preferences to take effect immediately #119.
* Added Waveform widget trace_width support.


## 1.0.14

<span style="color:#6090ff">🛈 BETA RELEASE 🛈</span> 

2023 May 16

### Changes

* Fixed UI widgets in undocked windows not restored on subsequent UI launches.
* Updated README and docs.
* Fixed threads not closing on exit (pubsub not processed).
* Added view manager (reorder, rename, add, reset/delete).
* Improved main window menu style.
* Added current range limit slider to JS220 control widget.
* Added option to use QWidget (not OpenGL widget) for waveform widget plot.
* Added text annotations.
* Added annotations save on export.  Automatically load on open. 


### Known issues

1. Partial Qt Hang (Waveform no longer updates, some Qt actions still work)
   on one Windows PC with Intel graphics.  Problem does not occur with
   other widgets.  We suspected an OpenGL issue.  Unchecking the "opengl"
   setting and changing min/max to lines works around the issue. 
2. Undo / redo support is not working


---

## 1.0.12

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Continued improvements but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Apr 28

* Fixed Accumulate widget to respect global statistics play/pause.
* Added drag & drop support for JLS files from File Explorer into UI.
* Fixed broken JLS record, export and read.

---

## 1.0.11

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Continued improvements but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Apr 27

* Added pyjoulescope_driver 1.3.5 with updated JS220 firmware.

---

## 1.0.10

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Continued improvements but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Apr 26

* Fixed current range constrained to 0 or 1 at high zoom levels.
* Updated to pyjoulescope_driver 1.3.4..
* Fixed Memory Widget "Clear" not clearing when streaming is paused.
* Hide status bar troubleshooting details by default.
* Improved waveform time axis to display conventional time format.
* Removed default quantization from time_map trel_offset.
* Fixed x_range inaccuracy due to unit corruption (int->float) when pinned.
* Updated to pyjls 0.6.0.

---

## 1.0.9

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Improves upon 1.0.7 but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Apr 19

* Improved pyjoulescope_driver stability (version 1.3.3).
* Improved firmware update.
  * Does not block Qt event thread.
  * Added recovery (handles JS220's in updater).
* Improved JS220 close error handling. 
* Removed unnecessary timeouts for driver publish that lock Qt event thread.
* Added record status to status bar.
* Switched to monochromatic waveform traces. (prep for multiple traces)
* Added light color scheme.
* Fixed defect with settings widget not populating current value.
* Fixed waveform widget to work with device open/close & insert/remove.
* Fixed pubsub reregister for class properties.
* Fixed multimeter not respected default source.

---

## 1.0.8

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Improves upon 1.0.7 but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Apr 13

* Fixed unplug/replug creating duplicate sample stream buffers.
* Added JS220 firmware update.
* Fixed metadata flag 'hidden' -> 'hide'.
* Added duration to memory widget.
* Increased default sidebar flyout width from 250 to 300. 
* Added accumulator widget.
* Added support for customary Ah & Wh units.
* Added global settings support.
  * Added sidebar direct link. 
  * Added Settings Widget to Widget menu bar.
* Added keyboard shortcuts to main and waveform widget.

---

## 1.0.7

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Improves upon 1.0.6 but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Apr 4

* Added logarithmic y-axis scale to waveform widget.
* Bounded waveform widget x-axis zoom.
* Added save/load next unique id to prevent instances incorrectly sharing state.
* Fixed font parsing & settings to work directly with QSS.
* Fixed fail on subsequent launch with JS110 connected on macOS.
* Fixed intermittent export fail.
* Increased process and backend thread priority for Windows.

---

## 1.0.6 

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Improves upon 1.0.5 but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Mar 30

* Added settings widget support for None metadata. 
* Added waveform std bound to min/max range.
* Moved time64 to pyjoulescope_driver.
* Added exception handling on close/delete widget.
* Fixed waveform widget save/copy image.
* Adjusted default waveform fps to 20 Hz (not vsync).
* Fixed JLS v2 recording to include current range when requested. 
* Fixed JLS v2 to display correctly when only has single UTC entry.
* Fixed crash due to invalid time ranges at start (pyjoulescope_driver 1.3.0).
* Updated to PySide6-QtAds 4.0.1.2, which fixes dock/undock crash.

---

## 1.0.5

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Improves upon 1.0.2 but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Mar 20

* Added File->Open recent.
* Added default load/save path, defaults to most recently used.
* Improved waveform widget.
  * Improved zoom/pan mouse interaction. 
  * Added x-axis pan to summary waveform.
  * Added "Y-axis auto range" to plot context menu.
  * Added Y zoom all control.
* Improved styles to separate incorrect sharing between objects. 
* Fixed intermittent timeout broken for API calls (pyjoulescope_driver 1.2.2).
* Fixed max window range tool.
* Added automatic JLS waveform widget naming using JLS filename.
* Fixed JLS open and waveform widget to support simultaneous files.
* Added context menu to waveform summary signal selection.
* Added Tools → Clear Accumulators.
* Reintegrated CDF and CCDF range tools.
* Added left-click on Value widget to copy value to clipboard.
* Fixed software update on macOS to open dmg file.
* Fixed macOS dynlib not found (1.0.3 & 1.0.4).

---

## 1.0.2

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Improves upon 1.0.1 but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Mar 17

* Reintegrate max_window range tool.
* Fixed command line filename open for JLS file association.
* Added back ctrl-left-click on dual markers to move both.
* Added software update install support for macOS and Ubuntu.
* Added standard deviation accrue to value widget.
* Fixed stream buffer resume that failed due to duplicate topic_add.
* Added dock widget removal exception handler on underlying C++ object already free.
* Added waveform control_location setting.
* Fixed waveform y-axis autoscaling when range difference was zero.

---

## 1.0.1

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

Improves upon 1.0.0 but still alpha quality.  See the 1.0.0 release
notes below for additional usage guidelines.

2023 Mar 16

* Added JLS v1 read/display support.
* Deduplicated JLS v2 requests for improved performance.
* Fixed dual marker integral value for JLS v2 files #177
* Waveform Widget
  * Fixed waveform export.
  * Modified waveform widget to only request dual marker data when needed.
  * Fixed waveform widget summary display x-axis.
  * Reduced waveform widget signal requests for more consistent frame rate.
  * Added waveform y-axis pan & zoom.
* Added minimum 1 pixel wide rectangle fills in waveform widget.
* Added individual statistics display to each marker of dual markers. 
* Added range RangeTool and RangeToolBase.  Refactored "export".
* Added back range tools: USB Inrush, histogram, frequency.
* Fixed low samples rates, like 10 Hz (pyjoulescope_driver 1.2.1).
* Added memory stream buffer Clear and "Clear on play" buttons.
* Preserve memory stream buffer settings between invocations. 
* Open device widget expanded.
* Added active sidebar flyout indication.
* Added clear memory buffer on sample rate change.
* Added signal_record check to ignore zero length sample messages. 
* Added PubSub process count monitor to status bar.
* Modified "Clear config and exit" to also clear rendered views.
* Open floating dock widgets to (800, 600) size.
* Fixed view menu to have radio buttons.

---

## 1.0.0

<span style="color:yellow">⚠ ALPHA RELEASE - USE WITH CAUTION ⚠</span> 

The first alpha release for the new Joulescope UI 1.x.
Limited testing performed.  This release may crash and lose data.
Not recommended for production use without thorough understanding
of the issues listed below.

This release features a major overhaul to the Joulescope UI.
The prior Joulescope UI 0.10.x and earlier has been an excellent tool for the
past 4 years, but several major architectural choices hampered 
new feature development and full JS220 support.

Key improvements coming in the 1.x release series include:

* Full JS220 feature support.
* Greatly improved waveform widget.
* Support for multiple, simultaneously connected Joulescopes.
* Langauge localization.

While all of these features are underway, they are not all ready.
This first alpha release nearly reaches feature parity with 
the previous 0.10.x release.


2023 Mar 9

* Migrated to new PubSub implementation from CommandProcessor + Preferences.
* New dock window system
  [ADS](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System).
* Added sidebar and removed old singleton control widgets.
* Added statistics "hold" feature to pause Multimeter widget display.
* Improved buffer memory management - select by RAM not duration #172
* Migrated to pyjoulescope_driver from pyjoulescope.
* Removed command line options "device_name" and "window_state".
* Restructured to clearly define profiles and views.
* Implemented clean style management with widget customization.
* Added localization support (but no localization yet).
* Separated support for JS110 and JS220 controls #175
* Added high-performance read/write support for JLS v2.  #48
* Added new Value widget (serves as both Multimeter and Value widgets).
* Added new Waveform widget.
  * Improved buffering performance using pyjoulescope_driver backend.
  * Summary plot displays waveform.
  * Operates entirely on UTC time #55.
  * Clearly indicates dropped samples #76.
  * OpenGL backend for improved rendering performance.
  * Vertically resize waveforms.
  * Added current range labels  #162.
  * Display statistics on hover #61.
  * Better state management #68.
* Fixed macOS support #171.


### Tips for use

* Settings are still a work in progress.  If you get stuck,
  select File → "Exit and clear config".  You can also manually
  delete the settings file:
  * Windows: %LOCALAPPDATA%\joulescope\config\joulescope_ui_config.json
  * macOS: ~/Library/Application Support/joulescope/config/joulescope_ui_config.json
  * linux: ~/.joulescope/config/joulescope_ui_config.json
* Hover the mouse over items to display tooltips
* Right-click (control click on macOS) for context-sensitive menus.
* Visit the [forum](https://forum.joulescope.com/) to post 
  questions, feedback, and issues.  Feel free to also create
  [GitHub issues](https://github.com/jetperch/pyjoulescope_ui/issues).
* Before opening a file, select View → File.  While you can open
  a file in any view, it often helps keep things less confusing
  if you use a separate view.
* When you open the UI, it returns exactly to where you left off.
  This can be confusing if you were viewing a JLS file and you
  are expecting live data.  Select View → Oscilloscope.


### Features temporarily removed

The Joulescope UI 1.x is reconstructed.  We started from a stripped-down
application and migrated / ported code back in.  We have not yet
completed this process.  Here are the features that are knowingly
not included in this release:

* JLS v1 read support.
* Waveform
  * analysis tools (range tools) including USB inrush.
  * text annotations.
  * Panning using summary waveform.
  * Save/load annotations to/from file.
  * y-axis zoom and pan.
  * y-axis logarithmic scale.
* Manage (add / delete / reorder) Views.
* Global settings / style / preferences management.
* Only dark mode for now: no light or system.
* Click to copy from Value (Multimeter & Value) widget.
* Units selection for mAh and mWh.
* Plugin architecture, which was never fully completed, 
  will be reintegrated but with new API #14.
* Most-recently used support
  * File → Open Recent
  * Path management
* ALL key bindings (no key presses work for now)
* Clear accumulator (workaround: close & reopen UI)

If you find other missing features, please post on the 
[Joulescope forum](https://forum.joulescope.com/).


### Known issues

* Style settings linked between widgets of same class.
* Waveform
  * The waveform defaults to fastest possible frame rate (vsync),
    which may not be desirable.  Right click on waveform,
    select settings, fps to change.
  * JS220 current range, GPI and trigger channels are time shifted
    from current, voltage, and power.
  * Missing clear streaming buffer button / feature.
  * Top summary waveform is not correct on file open until zoom/pan.
  * Crops view to extents of minimal signal. This avoids a JLS v2
    rd_fsr_statistics PARAMETER_INVALID[5] when reading beyond bounds.
* JS220 cannot stream all channels simultaneously.
* "Settings" menu does not open to nice sizes.
* JLS v2 file format does not yet implement corrupted file recovery.
* Menu View does not indicate active view.
* Device control expanded/hidden status not restored on view switch.
* UI sometimes hangs on close on Windows.
* Starting the UI with a different Joulescope causes unusual behavior.
* Using the UI with multiple Joulescopes is only partially supported.
  Value / Multimeter is great.  Waveform displays the signals in
  the same color  without any configuration / selection options.
* Flyout sidebar menu does not indicate which flyout is active.
* Value widget does not accrue standard deviation.


### JS220 features still not implemented

* Soft-fuse
* UI support for triggers
* Precision UTC time sync (existing UTC time only accurate to ~100 ms)
* UTC time sync between JS220's
* UART in / out
* On-instrument downsampling (host-side downsampling works great)


---


## 0.10.14

2023 Mar 9

* Fixed USB inrush analysis: changed deprecated np.float to np.float64.
* Fixed deprecated Control key modifiers for dual markers.


## 0.10.13

2022 Dec 20

* Fixed JS110 charge & energy statistics computation.
  All prior 0.10.x releases sometimes computed bad values.
  This issue does not affect the JS220.


## 0.10.12

2022 Nov 11

* Handle exception on firmware update check.
* Fixed UI distribution to include firmware images.
* Fixed waveform annotation export exception.


## 0.10.11

2022 Nov 10

* Fixed swapped FPGA version from=>to in firmware upgrade dialog box.
  Fixes https://forum.joulescope.com/t/joulescope-ui-prompts-to-downgrade-firmware-on-new-js220/492/2 
* Updated Windows installation
  * Uninstall old version, fixes #173.
  * Install into x64 "C:\Program Files" rather than "C:\Program Files (x86)".
  * Future updates will install automatically without prompts.


## 0.10.10

2022 Nov 8

* Updated documentation to link to JS220 User's Guide.
* Updated credits.
* Fixed JS220 parameters.
  * Added support for JS220 v_range "2 V".
  * Removed JS220 i_range "2 A" option.


## 0.10.9

2022 Nov 1

* Updated to pyjoulescope 1.0.9
  * Updated to pyjoulescope_driver 1.0.5
    * Fixed JS110 current range processing for window N and M.
    * Fixed JS110 sample alignment.
    * Fixed JS110 statistics generation time and rate.
  * Fixed v1 JS110 config=auto.
  * Fixed v1 JS220 voltage to use 15V manual range by default.
  * Modified v1 stats to skip NaN values.


## 0.10.8

2022 Oct 30

* Added support for macOS 13 Ventura and built on macOS 13.
* Added back JS110 support for macOS and Linux.
* Improved macOS and Linux support.
* Added JS220 GPO support.
* Added JS220 firmware update support.


## 0.10.6

2022 Oct 24

* Fixes for linux and Qt6.
* Added JS220 tooltip info.
* Added downsampling support.
* Updated to pyjoulescope 1.0.7 for improved JS110 support.
* Updated GitHub issue templates to include macOS 13 and UI 0.10.6.
* Clarified tooltips for JS110 and JS220.


## 0.10.5

2022 Oct 12

* Improved dual marker performance while streaming.


## 0.10.4

2022 Oct 9

* Disabled firmware/gateware updates since not working in release.


## 0.10.3

2022 Oct 8

* Fixed automatic UI update (Windows only for now).


## 0.10.2

2022 Oct 8

* Added automatic UI update (Windows only for now).
* Added JS220 firmware update. 


## 0.10.1

2022 Oct 4

* Updated to latest pyjoulescope
  * Added power computation to JS220.
  * Improved statistics performance.
* Fixed copy and save waveform widget image.
* Fixed duplicate selections in Single Value Widget "Statistic" combobox.


## 0.10.0

2022 Sep 29

* Upgraded from Pyside2 (5.15) to PySide6 (6.3.0).
  Blocking [QTBUG-101047](https://bugreports.qt.io/browse/QTBUG-101047) fixed in 6.3.0. 
* Fixed CSV time precision to match reduction_frequency #159
* Upgraded from pyinstaller 4.9 to 5.x.
* Added support for joulescope v1 driver using joulescope_driver backend.
* Added automatic updates, Windows only for now.
* Updated waveform ranges to support JS220.
* Updated requirements.

---

## 0.9.11

2022 Feb 22

* Fixed waveform context menu (QtGui.QMenu -> QtWidgets.QMenu).
* Fixed range tools on JLS v2 files (except for export) #131
* Added "General/window_on_top" preference #138
* Made y-axis markers consistent #124
* Addressed OSX Data loss while running in background #139 using appnope package.
* Fixed incorrect instantiation of Qt Thread from a python thread.  May fix #132.
* Added "Widgets/Waveform/scale" property for default waveform scale #135
* Unsubscribed Single Value Widget when closed.
* Fixed JLS open not updating view to full-resolution waveform #143
* Added macOS signature and notarization #18


## 0.9.10

2021 Nov 19

* Added "--window_state" command line argument
* Fixed USB Inrush test #134
* Fixed data_path_type "Use fixed data_path" #136


## 0.9.9

2021 Jul 7

*   Fixed dual marker stats and waveform right-side stats (pyjls 0.3.2).  


## 0.9.8

2021 May 11

*   Added firmware 1.3.4 to support 2021B1 units. 


## 0.9.7

2021 Apr 14

*   Fixed annotation save when exporting data range. 


## 0.9.6

2021 Apr 12

*   Added text annotation fix.  Thank you Selmen Dridi!
*   Fixed crash when logging is disabled #120.
*   Added waveform pan when holding shift while scrolling #123.
*   Improved waveform right-click context menu.
*   Added annotation save/load #41.
*   Added macOS packaging support for new homebrew distribution.


## 0.9.5

2021 Mar 9

*   Fixed delta time computation (dual markers) for JLS v2.
*   Fixed crash on viewing JLS v2 signal with no data.
*   Fixed min/max fill color.
*   Added annotation group_id support.
*   Fixed race condition when start UI with JLS file argument.
*   Load base recording if user selects an annotation file.


## 0.9.4

2021 Feb 27

*   Fixed Tools → Clear Accumulator #111
*   Copied Single Value Widget value to clipboard on mouse click #113
*   Used PySide.QtCore.Qt instead of PySide.QtGui.Qt #115
*   Added error handling to log file cleanup.
*   Fixed crash on invalid window_state #116
*   Reduced exception catching from "except:" to "except Exception:"
*   Fixed clear accumulators also affecting CSV capture #117
*   Added JLS v2 file format reader.
*   Added text annotations.
*   Added support for separate JLS files containing annotations.


## 0.9.3

2020 Nov 20

*   Fixed y-axis marker text value when in logarithmic mode #104.
*   Fixed y-axis markers during linear <-> logarithmic mode switch.
*   Fixed dependencies and README.
*   Improved JLS read performance for downsampled files using joulescope 0.9.3 #102
*   Added waveform hotkeys for zoom all and clear all markers #105
*   Added path option as fixed, most recently, used or most recently saved #92
*   Clear energy and charge on JLS file open and "disable" device #99
*   Fixed multimeter value to work on units and names #89
*   Fixed display artifact on x-axis timescale #97
*   Added elapse time display formatting option as Units → elapsed_time #88
*   Added click on multimeter accumulate text to copy.
*   Fixed automatic "play" when switching between Joulescopes #94
*   Forced waveform update on streaming stop #109
*   Modified Joulescope UI to work with MacOS 11.0.1, Big Sur #108


## 0.9.2

2020 Aug 13

*   Reverted macOS to PySide2 5.14.2.3 to avoid the QT bug:
    https://bugreports.qt.io/browse/QTBUG-84879.
*   No change for Windows & Linux which still used 5.15.0.


## 0.9.1

2020 Aug 12

*   Added "system", "dark", and "light" theme options #72.
*   Added frequency analysis that computes the Welch periodogram.
*   Improved range tool exception handling.
*   Fixed y-axis markers.
*   Fixed firmware upgrade crashed after completion (stuck at 99%).
*   Fixed firmware upgrade progress bar update event spamming.
*   Added raw processor preference-based configuration for files.
*   Added marker statistics display to left, right, or off.
*   Fixed y-axis scale setting to update correctly when changed.
*   Added Help → Changelog display.


## 0.9.0

2020 Aug 2

*   Modified Control widget to display accumulator time and selected field.
*   Renamed Tools → Clear Energy to Clear Accumulators and added undo.
*   Added move markers on click & drag #35.
*   Added dual markers "Scale to fit" feature #66.
*   Added keyboard movement/zoom of waveform display #11.
*   Added marker colors #57.
*   Migrated to official pyqtgraph 0.11.0.
*   Added save waveform as image #81
*   Added save/export current waveform buffer #10
*   Fixed dragging the endpoints of the top x-axis scroll bar #24
*   Added marker name text to flag and changed dual marker flag shape.
*   Added keybinding "S" and "D" to add single and dual markers, respectively #9.
*   Fixed pixelated button icons in oscilloscope view by using SVG icons #1.
*   Added subtle "blink" to record button when active.
*   Added File → Open Recent #43.
*   Added "active marker" so most recently used marker is clickable.
*   Fixed undo for marker move.
*   Added "revert" if right-click while moving marker.
*   Added algorithm to place new markers in open space #59.
*   Added copy waveform to clipboard #81
*   Added save entire buffer to file #82.
*   Removed export dialog.  Directly bring up save file dialog.
*   Bound markers to the waveform area.  Restrict from y-axis & statistics.
*   Fixed current range "zoom out" when output switch is "off".
*   Added on/off switch #84.
*   Added horizontal markers to the waveform widget #37.
*   Added statistics on/off for all vertical markers #12.
*   Improved multimeter view grid layout.
*   Clear accumulator immediately even when not streaming #86.
*   Added click to copy multimeter value to clipboard #87.
*   Added record statistics to CSV option #85.
*   Fixed multimeter view to display elapsed seconds, no SI prefix.
*   Added accumulator start time to multimeter view.
*   Updated to pyjoulescope 0.9.0 with support for firmware 1.3.0.


## 0.8.16

2020 May 29

*   Fixed dragging y-axis range #65.
*   Mapped space bar keyboard shortcut to toggle device run/pause #78.
*   Updated to PySide2 5.15.0 and pyqraph development latest.
*   Add workaround to prevent main Qt event thread blocking on Windows
    when using QFileDialog convenience functions.
*   Fixed race condition when stopping recording.
*   Fixed streaming stop not fully stopping any recording in progress.


## 0.8.14

2020 May 8

*   Added encoding='utf-8' to setup.py to fix package install on macOS.
*   Fixed momentary power OUT power glitch when reconnecting using 'auto'.
*   Fixed progress bar displaying while still configuring data export #77.
*   Fixed JLS load to better handle truncated files.
*   Modified dependencies to support both Python 3.7 and Python 3.8.


## 0.8.12

2020 Apr 27

*   Fixed plugin window instances become invalid #74.
*   Improved logging for multiprocessing.
*   Fixed downsampled JLS files display dropped samples as 0 #75.
*   Added preference to elevate Windows process priority, enabled by default.


## 0.8.11

2020 Apr 10

*   Fixed waveform Y-Axis zoom only zooms out with trackpad #70.
*   Fixed PySide2 imports #71.
*   Fixed Widgets to use Python float rather than numpy.float32/64.
*   Reverted to PySide 5.13.2.
*   Improved thread safety for main thread and range tool.
*   Fixed exporter to delete partial file when cancelled by user.


## 0.8.10

2020 Apr 2

*   Reduced CPU cycles when viewing JLS file with markers after streaming.
*   Fixed crash while running plugins #67.
*   Updated from PySide2 5.14.1 to PySide2 5.14.2.


## 0.8.9

2020 Mar 23

*   Fixed poor performance caused by GPIO Widget #60.
*   Added Preferences Dialog Help #52. 
*   Added marker Clear button to Waveform Control Widget #49.
*   Fixed "Add Single" marker button not working correctly. 
*   Added Waveform Control button to zoom out to full x-axis extents.
*   Added discrete Waveform Control buttons to toggle signal display #50.
*   Added device recovery rate limit.  Previous version was spamming the
    recovering device which caused more problems.
*   Modified command-line to accept all Joulescope package commands.
*   Fixed command-line filename argument support #62.
*   Fixed current ranging preferences #63.
*   Improved handling of empty JLS files and zero length data.
*   Resized waveform signal statistics text to fit #54.
*   Resized waveform marker text to fit.
*   Added feature to move both dual markers on CTRL left click #56.
*   Corrected widget heights for Control, Waveform Control, Single Value, GPIO.


## 0.8.6

2020 Feb 26

*   Fixed export to JLS not working #47.
*   Improved error handling on invalid config file and bad values #45.
*   Improved startup error handling and logging #45.
*   Improved startup error dialog with instructions and links #45.
*   Added charge and energy unit preferences #39.
*   Moved Δt to consistently be the last statistic in waveform view.
*   Added default filename for "Export data".
*   Fixed preferences UI profile "Reset" and "Reset to Defaults" #44.
*   Improved "General/data_path" error handling #32.
*   Added device reopen after changing critical device parameters #42.
    Parameters: buffer_duration, reduction_frequency, sampling_frequency.
*   Added support for the new joulescope 0.8.5 samples_get return format.


## 0.8.3

2020 Feb 19

*   Added downsampling support.
*   Changed i_range preference default to "auto" (was "off").
*   Modified marker statistics to use same font style as waveform statistics.


## 0.8.0

2020 Feb 18

*   Fixed firmware version check to work with untagged development builds.
*   Added support for joulescope 0.8.0 unified statistics data structure.
*   Fixed issue #40: Added ∫ and Δt back to dual marker statistics.
*   Added parameter to show/hide Δt dual marker statistic.
*   Reorganized device parameters into settings, extio and Current Ranging.
*   Updated PySide2 build process and version definition.  Removed VERSION.
*   Added color parameters for waveform mean/min/max/fill.
*   Fixed marker text position when y-axis scale changes.
*   Fixed y-axis range to auto not causing immediate autoscale #21


## 0.7.0

2019 Dec 4

*   Implemented Command pattern with preferences.  The application now supports
    undo/redo using the standard keys combinations: CTRL-Z & CTRL-Y on windows.
    Refactored code.
*   Fixed single value widget to display value in its own best unit scale.
*   Renamed "command" to "entry_point" to prevent confusion with UI "commands".
*   Addressed crashes on marker removal.
*   Updated Preferences dialog to support user-defined profiles.
*   Updated software to save and restore settings within each profile.
*   Added ability to set fonts and colors for Multimeter and Waveform widgets.
    Include Lato font by default for all platforms.
*   Added Help → View Logs...
*   Added software release channel selection: alpha, beta, stable.
*   Updated to Python 3.7.5 (was 3.7.3).
*   Added "Waveform Control" widget, part of the Oscilloscope View by default.
*   Run garbage collector on device disconnect, which ensures StreamBuffer
    is correctly freed.
*   Modified default paths to be more platform-friendly.


## 0.6.10

2019 Oct 23

*   Fixed current range glitch filter using invalid sample data.
    The glitch filter could occasionally use one sample of invalid data during
    the computation of the "pre" mean component.  The underlying cause was 
    that the pre mean value was computed over a FIFO that was rolling over 1 
    sample too late.  This injected up to one sample of undefined data. 
    For a length n pre value, this error occurred on roughly (n - 1) / 8 
    current range transitions.  Testing shows that we were lucky on 
    Win10 and the data was not a huge floating point number.
    Added unit test and fixed.
*   Added support for new download.joulescope.com site.
    Support new https://download.joulescope.com/joulescope_install/index.json 
    format.
    Modified URLS to point directly to https://download.joulescope.com rather 
    than https://www.joulescope.com.


## 0.6.8

2019 Oct 15

*   Fixed data-dependent single NaN sample insertion. Only occurred when
    i_range was 3 or 7 and current LSBs was saturated.
    Affects 0.6.0 through 0.6.7.
*   Added customizable current range switching filter available through 
    File → Preferences → Current Ranging.
*   Changed default current range switch filter from mean_0_3_1 to mean_1_n_1,
    which significantly reduces the displayed glitches on current ranging.
    If you like the old behavior, File → Preferences → Current Ranging to
    set type: mean, samples_pre: 0, samples_window: 3, samples_post: 1.
    The drawback is that up to 8 samples (4 µs) of data can be filtered out.


## 0.6.6

2019 Oct 9

* Fixed configuration to work on new installations (error introduced in 0.6.5).


## 0.6.5

2019 Oct 9

* Converted JSON5 config_def to python to improve start time.
* Updated to latest pyqtgraph.
* Improved waveform performance by only updating curve fill when needed.


## 0.6.4

2019 Oct 3

* Added NaN checks in multimeter when accumulating (Issue #2).
* Added configurable stream buffer duration (was fixed at 30 seconds).
* Added general-purpose input (GPI) support.
* Only update oscilloscope when visible (improve performance).


## 0.6.3

2019 Sep 22

*   Only display mean for signal markers when zoomed to single sample.


## 0.6.2

2019 Sep 20

*   Fixed log warning for on_fps_timer.
*   Fixed error that prevented "Export data" on open JLS file.
*   Sign macOS distribution and application.


## 0.6.1

2019 Sep 17

*   Fixed "record" function not working on Windows due to multiprocessing and
    pyinstaller EXE packaging.
*   Applied calibration to "zoomed-out" data on dual marker export. All existing
    files created with dual marker export are invalid when the view window is
    more than a couple seconds (actual duration varies), but the zoomed-in
    data is still valid.

## 0.6.0

2019 Sep 16

*   Added plugins and range_tool.  Refactored export & USB Inrush.
*   Added histogram-based plugins (author Axel Jacobsen).
*   Updated pyqtgraph
*   Added RangeToolInvocation methods marker_single_add and marker_dual_add.
*   Added check and UI status warning when device does not support dual markers.
*   Improved logging.
*   Added range_tool plugins submenus.
*   Added fault handler (such as segmentation faults) output to log.
*   Modified dual marker delta time to display in engineering notation.
*   Updated the getting started guide.
*   Persisted accumulated charge/energy across device disconnect/connect.
*   Fixed single marker to display "No data" over missing samples.
*   Fixed y-axis waveform autoranging when min/max traces are not shown.
*   Modified codebase to use new joulescope.Driver StreamProcessApi, 
    elimination of recording_start and recording_stop.
*   Implemented improved frame rate limiting.
*   Refactored to support new data_update format with integrated view details.
*   Added Δt indication for statistics computed over visible window.
*   Moved RecordingViewerDevice to operate in its own thread for improved 
    performance.  Allows software to condense multiple requests, such as
    during mouse click & drag.
*   Moved JLS recording to its own process so that OS file write stalls do
    not cause sample drops.


## 0.5.1

2019 Aug 11

*   Fixed show_min_max preferences change from off to lines.
*   Use default config value on invalid value & log error (not throw).
*   Added Device.on_close configurable behavior.
*   Fixed sensor programming when unprogrammed (see joulescope 0.5.1).


## 0.5.0

2019 Jul 26

*   Fixed energy not displaying in "Single Value Display".
*   Fixed "Tools -> Clear Energy" not clearing energy on multimeter view.
*   Added firmware update to 1.1.0.
    *   Fixed negative voltage current range oscillation.
    *   Improved USB enumeration and reliability issues (LPC silicon errata).
    *   Improved autoranging to use device calibration for consistent behavior
        across devices.
    *   Eliminated switching glitches between current auto ranging and manual ranging
*   Improved bootloader recovery handling.
*   Removed NaN injection that caused invalid multimeter displays.
*   Added logical USB suspend/resume support to correctly resume streaming.
*   Improved USB device robustness and error handling, particularly for macOS.
*   Fixed multimeter view showing 0 current by forcing current autoranging.
*   Added optional JLS filename command line argument & Windows file association.
*   Changed window title to match active source: device or file.
*   Improved macOS dmg file.


## 0.4.6

2019 Jul 15

*   Fixed .gitignore to exclude pyqtgraph git dependency download in place.
*   Added VSCode launch file.
*   Addressed pip install "ModuleNotFoundError: No module named 'pyside2uic'"
*   Updated README: pip install joulescope_ui does not work with forked pyqtgraph.
*   Defer device close on File->Open until correct file name provided. Cancel does not change operation.
*   Fixed recordings to capture the correct data in 5V range. Captures made with 
    previous versions will presume 15V range when zoomed in.
*   Added source indicator with USB streaming health in status bar.
*   Add new signal to each existing dual marker.
*   Apply i_range and v_range Preferences only on change.
*   Display total charge in addition to energy on multimeter view.
*   Updated to Qt5/PySide2 5.13.0.


## 0.4.5

2019 Jul 2

*   Added "Annotations" -> "Clear all" option.
*   Increased startup logging to isolate Qt show().
*   Added platform information to info.
*   Added link to User's Guide in Help menu.
*   Modified Multimeter View to automatically start device streaming.


## 0.4.4

2019 Jun 28

*   Fixed pyqtgraph dependency.
*   Updated "Quick Start" in README.md.


## 0.4.3

2019 Jun 28

*   Used new joulescope.bootloaders_run_application() for better error handling.
*   Improved logging to include header with joulescope and platform information.
*   Added "--file_log_level" command line option.
*   Display Qt Window when configuration initialization fails.


## 0.4.2

2019 Jun 24

*   Added more verbose console stdout log messages (include timestamp).
*   Removed default loggers when invoked as a joulescope command.
*   Improved joulescope device logging and error handling, particularly for 
    libusb (Linux/Mac), using joulescope 0.4.2.


## 0.4.1

2019 Jun 20

*   Use the Waveform preferences.
*   Added "fill" option for show_min_max.


## 0.4.0

2019 Jun 20

*   Improved file logging.
*   Improved application robustness.
    *   Added periodic device scan, because bad things happen.
    *   Catch and handle more exceptions.
    *   Automatically attempt to recover when a device is "lost".
    *   Eliminated repeated parameter initialization x number of device disconnects.
*   Added stdout console logging command line option.
*   Made manual rescan interval configurable and "off" by default.
*   Hide all oscilloscope traces on data clear.
*   Refactored statistics and added statistics_get to RecordingViewerDevice.
*   Added Help -> "Credits" to the user interface with credits & licenses.
*   Added marker right-click context menu.
*   Added dual marker data export to CSV.
*   Added dual marker data export to JLS.
*   Added dual marker data export to BIN.


## 0.3.0

2019 Apr 27

*   Improved error handling for underlying driver/fw/hw errors.
*   Added command-line option to specify the joulescope device name.
*   Added compliance testing mode.
*   Added logging to file.
*   Fixed Device.i_range and Device.v_range preferences.
*   Added alias values to the configuration.


## 0.2.7

2019 Mar 2

*   Improved device open error handling
*   Managed future features
*   Added waveform options: hide min/max signals, show grid, trace width.
*   Display Joulescope driver version in ABOUT.
*   Added support for older Mac OS X versions when packaged.
*   Automatically package Windows, Linux & Mac OS X applications.


## 0.2.6

2019 Feb 16

*   Use "joulescope" 0.2.6.
*   Added "power" plot.


## 0.2.5

2019 Feb 14

*   Addressed Win 10 issue with pyinstaller.
    See https://github.com/pyinstaller/pyinstaller/issues/4040
*   Do not display README.md on Windows install.


## 0.2.4

2019 Feb 10

*   Fixed buttons on oscilloscope plots - png icons instead of unicode text.
*   Disable left button action when no tool is selected on oscilloscope. 
    Was previously keeping the last selected tool.
*   Explicitly set statistics label widths to prevent resizing as value changes.
*   Added "Clear Energy" tool to reset energy to 0.0.


## 0.2.3

2019 Feb 8

*   Added y-axis oscilloscope autoranging by default.
*   Improved zoom ease of use.  Scroll wheel now better matches "expectations"
*   Always zoom in on right click & drag.
*   Add pan/move option for left click.  Enabled by default.
*   Suppress glitches (up to 2 samples) which occur on current range switches.
*   Fixed exception that prevented preferences from saving correctly.
*   Started "save", but still work in progress.


## 0.2.2

2019 Jan 27

*   Fixed file load.
*   Added single marker to oscilloscope widgets.


## 0.2.1

2019 Jan 25

*   Added linux support using libusb.
*   Added Mac OS X support using libusb.


## 0.1.0

2018 Oct 10

*   Initial public release.
