
# CHANGELOG

This file contains the list of changes made to pyjoulescope_ui.


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
    Support new https://download.joulescope.com/joulescope_install/index.json.
    Modifed URLS to point directly to https://download.joulescope.com rather 
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
