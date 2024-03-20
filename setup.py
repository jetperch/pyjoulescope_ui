# Copyright 2018-2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Joulescope python setuptools module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
import setuptools
from setuptools.command.sdist import sdist
from setuptools.command.develop import develop
import os
import platform
import sys
import subprocess
import shutil


MYPATH = os.path.abspath(os.path.dirname(__file__))
VERSION_PATH = os.path.join(MYPATH, 'joulescope_ui', 'version.py')


def qt_rcc_path():
    # As of PySide 5.15.0, the pySide6-rcc executable ignores the --binary flag
    import PySide6
    path = os.path.dirname(PySide6.__file__)
    fname = [n for n in os.listdir(path) if n.startswith('rcc')]
    if len(fname) == 1:
        fname = os.path.join(path, fname[0])
        if os.path.isfile(fname):
            return fname
    if platform.system() in ['Darwin', 'Linux']:
        fname = os.path.join(path, 'Qt', 'libexec', 'rcc')
        if os.path.isfile(fname):
            return fname
    raise ValueError('Could not find rcc executable')


def convert_qt_ui():
    uic_path = shutil.which('pyside6-uic')
    rcc_path = qt_rcc_path()
    path = os.path.join(MYPATH, 'joulescope_ui')
    ignore_filename = os.path.join(path, '.gitignore')
    with open(ignore_filename, 'w', encoding='utf-8') as ignore:
        ignore.write('# Automatically generated.  DO NOT EDIT\n')
        for root, d_names, f_names in os.walk(path):
            for source in f_names:
                _, ext = os.path.splitext(source)
                if ext == '.ui':
                    source = os.path.join(root, source)
                    target = os.path.splitext(source)[0] + '.py'
                    print(f'Generate {os.path.relpath(target, MYPATH)}')
                    rc = subprocess.run([uic_path, source], stdout=subprocess.PIPE)
                    s = rc.stdout.replace(b'\r\n', b'\n').decode('utf-8')
                    s = s.replace('\nimport joulescope_rc\n', '\nfrom joulescope_ui import joulescope_rc\n')
                    with open(target, 'w', encoding='utf-8') as ftarget:
                        ftarget.write(s)
                elif ext == '.qrc':
                    src = os.path.join(root, source)
                    target = os.path.join(os.path.dirname(root), source)
                    target = os.path.splitext(target)[0] + '.rcc'
                    print(f'Generate {os.path.relpath(target, MYPATH)}')
                    rc = subprocess.run([rcc_path, src, '--binary', '--threshold', '33', '-o', target])
                    if rc.returncode:
                        raise RuntimeError('failed on .qrc file')
                else:
                    continue
                ignore_entry = os.path.relpath(target, path).replace('\\', '/')
                ignore.write('%s\n' % ignore_entry)


def _version_get():
    with open(VERSION_PATH, 'r', encoding='utf-8') as fv:
        for line in fv:
            if line.startswith('__version__'):
                return line.split('=')[-1].strip()[1:-1]
    raise RuntimeError('VERSION not found!')


def update_inno_iss():
    version = _version_get()
    path = os.path.join(MYPATH, 'joulescope.iss')
    with open(path, 'r', encoding='utf-8') as fv:
        lines = fv.readlines()
    version_underscore = version.replace('.', '_')
    for idx, line in enumerate(lines):
        if line.startswith('#define MyAppVersionUnderscores'):
            lines[idx] = f'#define MyAppVersionUnderscores "{version_underscore}"\n'
        elif line.startswith('#define MyAppVersion'):
            lines[idx] = f'#define MyAppVersion "{version}"\n'
    with open(path, 'w', encoding='utf-8') as fv:
        fv.write(''.join(lines))


class CustomDevelopCommand(develop):
    """Custom develop command to build Qt resource file and Qt user interface modules."""
    def run(self):
        develop.run(self)
        convert_qt_ui()


class CustomSdistCommand(sdist):
    def run(self):
        update_inno_iss()
        convert_qt_ui()
        sdist.run(self)


if sys.platform.startswith('win'):
    PLATFORM_INSTALL_REQUIRES = ['pywin32']
else:
    PLATFORM_INSTALL_REQUIRES = []


# Get the long description from the README file
with open(os.path.join(MYPATH, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


setuptools.setup(
    name='joulescope_ui',
    version=_version_get(),
    description='Joulescope™ graphical user interface',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://www.joulescope.com',
    author='Jetperch LLC',
    author_email='joulescope-dev@jetperch.com',
    license='Apache 2.0',

    cmdclass={
        'develop': CustomDevelopCommand,
        'sdist': CustomSdistCommand,
    },

    # Classifiers help users find your project by categorizing it.
    #
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[  # Optional
        'Development Status :: 5 - Production/Stable',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Science/Research',

        # Pick your license as you wish
        'License :: OSI Approved :: Apache Software License',

        # Natural Language
        'Natural Language :: English',

        # Operating systems
        'Operating System :: Microsoft :: Windows :: Windows 10',
        'Operating System :: Microsoft :: Windows :: Windows 11',
        'Operating System :: MacOS',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX :: Linux',

        # Supported Python versions
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',

        # Topics
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Embedded Systems',
        'Topic :: Software Development :: Testing',
        'Topic :: Utilities',
    ],

    keywords='joulescope ui gui "user interface"',

    packages=setuptools.find_packages(exclude=['docs', 'test', 'dist', 'build']),

    include_package_data=True,

    # See https://packaging.python.org/guides/distributing-packages-using-setuptools/#python-requires
    python_requires='~=3.10',
    
    # See https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        'appnope>=0.1.2',
        'fs',
        'pyjoulescope_driver>=1.4.10,<2.0.0',
        'joulescope>=1.1.12,<2.0.0',
        'markdown',
        'psutil',
        'pyjls>=0.9.2',
        'pyopengl',
        "pywin32>=223; platform_system == 'Windows'",
        'pyqtgraph>=0.13.3',
        'PySide6>=6.6.2,<7.0.0',
        'PySide6-QtAds>=4.2.1,<5.0.0',
        'python-dateutil>=2.7.3',
        'QtPy',
        'requests>=2.0.0,<3.0.0',
    ] + PLATFORM_INSTALL_REQUIRES,
    
    extras_require={
        'dev': ['check-manifest', 'coverage', 'Cython', 'pyinstaller', 'wheel'],
    },

    entry_points={
        'gui_scripts': [
            'joulescope_ui=joulescope_ui.main:run',
        ],
    },
    
    project_urls={
        'Bug Reports': 'https://github.com/jetperch/pyjoulescope_ui/issues',
        'Funding': 'https://www.joulescope.com',
        'Twitter': 'https://twitter.com/joulescope',
        'Source': 'https://github.com/jetperch/pyjoulescope_ui/',
    },
)
