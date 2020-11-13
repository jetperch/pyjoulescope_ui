
# CHANGELOG

This file contains the list of changes made to pyjoulescope_ui.


## 0.9.3

2020 Nov 11 [in progress]

*   Fixed y-axis marker text value when in logarithmic mode #104.
*   Fixed y-axis markers during linear <-> logarithmic mode switch.
*   Fixed dependencies and README.
*   Improved JLS read performance for downsampled files using joulescope 0.9.3 #102


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
