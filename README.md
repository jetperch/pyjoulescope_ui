
# Joulescope UI

Welcome to Joulescope™!  Joulescope is an affordable, precision DC energy
analyzer that enables you to build better products.
Joulescope™ accurately and simultaneously measures the voltage and current
supplied to your target device, and it then computes power and energy.
For more information on Joulescope, see
[www.joulescope.com](https://www.joulescope.com).

This repository contains the Joulescope graphical user interface (UI).
The UI runs on a host computer and communicates with the Joulescope device
over USB.  The application source code is available at
https://github.com/jetperch/pyjoulescope_ui.  

For the list of changes by release, see the [Changelog](CHANGELOG.md).

The Joulescope UI is under active development, and many features remain
outstanding. See the [future features document](features_future.md) for details.


## Quick start using official distribution

We provide an official distribution that is prebuit for Windows, macOS and
Ubuntu 20.04LTS.
[Download](https://www.joulescope.com/download) the application distribution
for your platform and install it.  


## Run as python package

The Joulescope UI is a python package which you can install for pypi or
run directly from source.


### Install Python

The Joulescope User Interface requires Python 3.8 or newer.
We recommend Python 3.8 or 3.9.
Install [Python 3.8+](https://www.python.org/) on your system and then verify
your python version at the terminal or command line:

    > python3 -VV
    Python 3.9.0 (tags/v3.9.0:9cf6752, Oct  5 2020, 15:34:40) [MSC v.1927 64 bit (AMD64)]

Ensure that you have Python 3.8 or newer and 64-bit.


### Configure virtualenv [optional]

Although not required, using
[virtualenv](https://virtualenv.pypa.io/en/latest/)
avoids dependency conflicts, especially if you use your python installation for
other programs.  Using virtualenv ensures that
the Joulescope software has the right dependencies without changing the rest
of your system.


#### For Windows:

Install virtualenv and create a new virtual environment:

    pip3 install -U virtualenv
    virtualenv c:\venv\joulescope

Activate the virtual environment whenever you start a new terminal:

    c:\venv\joulescope\Scripts\activate


#### For POSIX including (Linux, Mac OS X with homebrew):

Install virtualenv and create a new virtual environment:

    pip3 install -U virtualenv
    virtualenv ~/venv/joulescope

Activate the virtual environment whenever you start a new terminal:

    source ~/venv/joulescope/bin/activate


### Option 1: Install from pypi

Installation from pypi is easy:

    pip3 install -U joulescope_ui
    
If you just want to run the latest released version of the UI, use this option!


### Option 2: Clone, install and run from source

Clone and configure the Joulescope UI from the terminal or command line:

    git clone https://github.com/jetperch/pyjoulescope_ui.git
    cd pyjoulescope_ui
    pip3 install -U -r requirements.txt

Make any optional modifications you want to the source code.  Then build and
install the source:

    python3 setup.py sdist
    pip3 install dist/joulescope_ui-{version}.tar.gz

You can then run from any directory:

    python3 -m joulescope_ui

If you see an error importing win32api on Windows, you should try running this
command from an Administrator command prompt:

   python {path_to_python}\scripts\pywin32_postinstall.py -install


### Option 3: Develop the UI

Clone and configure the Joulescope UI from the terminal or command line:

    git clone https://github.com/jetperch/pyjoulescope_ui.git
    cd pyjoulescope_ui
    pip3 install -U -r requirements.txt

Build the QT resources:

    python3 setup.py qt

As long as the current directory is the source directory, you can run:

    python3 -m joulescope_ui

If you want to run from another directory, you will need to add the source
to your PYTHONPATH environment variable.  On Windows:

    set PYTHONPATH={C:\path\to\repos}\pyjoulescope_ui

and on POSIX (Linux, Mac OS X with homebrew):

    export PYTHONPATH={path/to/repos}/pyjoulescope_ui


To also distribute the UI on macOS, you need to install XCode and then
configure node:

    brew install node
    npm install

You will also need to install the signing certificate using
Applications/Utilities/Keychain Access.


### Option 4: Develop both UI and driver

If you also want to simultaneously develop the Joulescope UI and the
Joulescope driver:

    pip3 uninstall joulescope
    cd {path/to/repos}
    git clone https://github.com/jetperch/pyjoulescope.git
    cd pyjoulescope
    pip3 install -U -r requirements.txt    
    python3 setup.py build_ext --inplace

You should then modify your python path to find both the UI and driver
source paths. On Windows:

    set PYTHONPATH={C:\path\to\repos}\pyjoulescope;{C:\path\to\repos}\pyjoulescope_ui

and on POSIX (Linux, Mac OS X with homebrew):

    export PYTHONPATH={path/to/repos}/pyjoulescope:{path/to/repos}/pyjoulescope_ui

Follow the instructions from Option 3 to configure and run the UI.


## License

All pyjoulescope_ui code is released under the permissive Apache 2.0 license.
See the [License File](LICENSE.txt) for details.
