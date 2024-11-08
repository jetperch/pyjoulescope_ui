
# Future Features

This document captures the Joulescope™ User Interface (UI) future features. 
The UI is under active development, and many features remain outstanding. 


### Joulescope JS220

* UTC timesync using BNC trigger IN/OUT
* UART RX and TX


### Oscilloscope

*   Make the y-axis autoranging less confusing.  You lose context on the
    discrete jumps.  Perhaps animate the transition?
*   Add "comparison" mode to overlay multiple data captures so that the 
    user can compare changes over the development cycle (story 3).
*   Add a "triggered" mode that only captures on events, such as thresholds, 
    like a normal oscilloscope.  Note that triggering on an external signal
    is not included in this feature.
*   Show a visible "saturation" line (likely in a different color) where the 
    signal is above or below the current y-axis view range.
*   Move the selected, active marker using left/right arrow keys.
*   Add "Zoom to area" feature that zooms both x & y axes.


### Frequency analysis

*   Add real-time FFT display with max, min and average. Include controls for
    windowing, FFT length and window overlap %.
*   Add [spectrogram](https://en.wikipedia.org/wiki/Spectrogram).


### System integration

*   Add UART capture and display.
    *   Ensure that UART data is saved to and loaded from jls files.
    *   Use DTR as an external trigger.
*   Add logic analyzer integration.  Best path may be to integrate Joulescope
    with [sigrok](https://sigrok.org/), so not really a feature for the UI.
    This approach may also enable external triggers.
*   Add integration with hardware trace.  Ideally, display a heat-map of
    energy usage and allow navigation by code module, function and line.
*   Integrate with external low-data-rate sensors, especially temperature 
    sensors.  When enabled, can display in both multimeter view and 
    oscilloscope view.  Save/load sensor data to/from jls files.
*   Integrate a microcontroller software-based trace function, something
    like EE101 Insight-Pro.  Could try to integrate with them if their
    software didn't get such bad reviews.  Sigrok?  Or just in UI?
    

### Other

*   Measure and automate Joulescope code coverage.
*   Add automatic battery life estimation - may need to input battery 
    chemistry type & capacity.
*   Trigger on waveform: select a waveform.  Then trigger and overlay similar.
*   Automatically identify similar periodic processes and sleep power. 
    When done, feed estimation tool where you can set the period of each 
    identified process to estimate energy consumption per desired timescale
    or even battery life.

---

## Guiding stories

The development of any product requires choices.  The Joulescope developers
have used the following three stories to guide development.


### Terminology

*   **User** references anyone who uses Joulescope.  The primary target
    audience includes PCB designers, FPGA developers, electrical engineers,
    hardware engineers, firmware engineers, microcontroller engineers, 
    software engineers, software application developers, hobbyists and makers. 
    Joulescope can also be used as a general-purpose instrument by
    students and scientists.




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

As of 2023, we are finally starting to address this with multiple waveform
window support and multiple device support in the Joulescope UI 1.0.
