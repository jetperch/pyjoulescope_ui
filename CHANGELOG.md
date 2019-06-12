
# CHANGELOG

This file contains the list of changes made to pyjoulescope_ui.


## 0.3.1

2019 Jun ??

*   Improved file logging.
*   Improved application robustness.
    *   Added periodic device scan, because bad things happen.
    *   Catch and handle more exceptions.
    *   Automatically attempt to recover when a device is "lost".
    *   Eliminated repeated parameter initialization x number of device disconnects.
*   Added stdout console logging command line option.
*   Made manual rescan interval configurable and "off" by default.
*   Hide all oscilloscope traces on data clear.


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
