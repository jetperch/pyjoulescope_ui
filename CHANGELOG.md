
# CHANGELOG

This file contains the list of changes made to pyjoulescope_ui.


## 0.5.0-dev

2019 Jul 15

*   Fixed energy not displaying in "Single Value Display".
*   Fixed "Tools -> Clear Energy" not clearing energy on multimeter view.


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
