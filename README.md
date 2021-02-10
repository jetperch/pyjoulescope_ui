
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

The Joulescope User Interface requires Python 3.6 or newer.  We recommend Python 3.8 or 3.9.
Install [Python 3.8+](https://www.python.org/) on your system and then verify
your python version at the terminal or command line:

    > python3 -VV
    Python 3.9.0 (tags/v3.9.0:9cf6752, Oct  5 2020, 15:34:40) [MSC v.1927 64 bit (AMD64)]
    
Ensure that you have Python 3.6 or newer and 64-bit.


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

Installation from pypi is easy!

    pip3 install -U joulescope_ui


### Option 2: Clone and run from source

Clone and configure the Joulescope UI from the terminal or command line:

    git clone https://github.com/jetperch/pyjoulescope_ui.git
    cd pyjoulescope_ui
    pip3 install -U -r requirements.txt
    python3 setup.py qt
    
You can then run from this directory:

    python3 -m joulescope_ui
    
You can alternatively build and install from source:

    python3 setup.py sdist
    python3 install dist/joulescope_ui-{version}.tar.gz

If you see an error importing win32api on Windows, you should try running this
command from an Administrator command prompt:

   python {path_to_python}\scripts\pywin32_postinstall.py -install


### Simultaneously develop the Joulescope driver

If you also want to simultaneously develop the Joulescope UI and the 
Joulescope driver:

    pip3 uninstall joulescope
    cd {path/to/repos}
    git clone https://github.com/jetperch/pyjoulescope.git
    cd pyjoulescope
    pip3 install -U -r requirements.txt    
    python3 setup.py build_ext --inplace

You should then modify your python path. On Windows:

    set PYTHONPATH={C:\path\to\repos}\pyjoulescope;{C:\path\to\repos}\pyjoulescope_ui

and on POSIX (Linux, Mac OS X with homebrew):

    export PYTHONPATH={path/to/repos}/pyjoulescope:{path/to/repos}/pyjoulescope_ui

You should then be able to run the user interface from this directory:

    python3 -m joulescope_ui


## License

All pyjoulescope_ui code is released under the permissive Apache 2.0 license.
See the [License File](LICENSE.txt) for details.
