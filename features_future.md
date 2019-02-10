
# Future Features

This document captures the Joulescope™ User Interface (UI) future features. 
The UI is under active development, and many features remain outstanding. 


## Terminology

*   **User** references anyone who uses Joulescope.  The primary target
    audience includes PCB designers, FPGA developers, electrical engineers,
    hardware engineers, firmware engineers, microcontroller engineers, 
    software engineers, software application developers, hobbyists and makers. 
    Joulescope can also be used as a general-purpose instrument by
    students and scientists.


## Guiding stories

The development of any product requires choices.  The Joulescope developers
have used the following three stories to guide development.


### Story 1

> As a User, I want to quickly and easily see the immediate energy consumption
> of my target device so that I can measure its present operating state.

The Joulescope multimeter view fulfills the needs of this story. 
The multimeter view displays current, voltage, power and energy updated 
each 1/2 second time window. The multimeter view also displays statistics 
including standard deviation,
minimum, maximum and peak-to-peak over the same window.


### Story 2

> As a User, I want to see changes to current, voltage and power over time so
> that I can understand how changes to my target device's state affect
> power consumption.

The oscilloscope view intends to fulfill the needs of this story. Different
**Users** have slightly different needs. The Joulescope UI must successfully
balance ease of use and sufficient analytical features.


### Story 3

> As a User, I want to understand how changes that I make during development
> affect the target device's energy consumption so that I can develop quality,
> energy-efficient products.

As of Jan 2019, this story is still largely unfulfilled by the software. 
**Users** must manually record and compare their findings.


## Features

This section captures potential future features. Many features shown below
will be implemented before Joulescope general availability.


### Oscilloscope

*   Add y-axis log display in addition to linear.
*   Allow single marker to be turned on/off.
*   Add support for dual markers.  Display the t, Δt, mean, min, max, p2p and
    energy over the window.
*   Add ability to save either the entire buffer or the selected time range.
    The supported output formats should include jls, csv, npy, bin.
*   Add "comparison" mode to overlay multiple data captures so that the 
    user can compare changes over the development cycle (story 3).
*   Animate "pan" action (likely need to pause live view to be meaningful).


### Frequency analysis

*   Add real-time FFT display with max, min and average. Include controls for
    windowing, FFT length and window overlap %.
*   Add [spectrogram](https://en.wikipedia.org/wiki/Spectrogram).
*   Add off-line FFT display that analyzes the selected time window.
    Use markers to select time window.


### System integration

*   Add UART capture and display.  Ensure that UART data is saved to and
    loaded from jls files.
*   Add logic analyzer integration.  Best path may be to integrate Joulescope
    with [sigrok](https://sigrok.org/), so not really a feature for the UI.
    

### Other

*   Add soft-fuse configuration once implemented in Joulescope FPGA.
*   Automate build: [travis-ci](https://travis-ci.org/).
*   Measure and automate code coverage.
*   Automatically perform software update when required.  The existing
    implementation just directs the User to the Joulescope download page.
*   Automatically perform Joulescope firmware updates when required.

