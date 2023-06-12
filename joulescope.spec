# -*- mode: python -*-

# Configuration file for PyInstaller
# See https://pyinstaller.readthedocs.io/en/stable/index.html
# > pip install pyinstaller
# > pyinstaller joulescope.spec

# Mac OS X
# https://kivy.org/doc/stable/guide/packaging-osx.html
# hdiutil create ./dist/joulescope.dmg -srcfolder ./dist/joulescope.app -ov

import sys
import glob
import os
import pyqtgraph
import subprocess
import shutil
import time

block_cipher = None
specpath = os.path.dirname(os.path.abspath(SPEC))
PATHEX = []
sys.path.insert(0, specpath)
import pyjoulescope_driver
import joulescope_ui
VERSION_STR = joulescope_ui.__version__.replace('.', '_')
MACOS_CODE_SIGN = 'Developer ID Application: Jetperch LLC (WFRS3L8Y7Y)'
PYQTGRAPH_PATH = os.path.dirname(pyqtgraph.__file__)
PYJOULESCOPE_DRIVER_PATH = os.path.dirname(pyjoulescope_driver.__file__)
INNO_SETUP_PATH = r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'


def find_site_packages():
    for p in sys.path:
        if p.endswith('site-packages'):
            return p
    raise RuntimeError('Could not find site-packages')


def parse_manifest():
    add_files = []
    with open(os.path.join(specpath, 'MANIFEST.in'), 'r', encoding='utf-8') as f:
        for line in f.readlines():
            line = line.strip()
            if not len(line):
                continue
            parts = line.split()
            matches = []
            if parts[0] == 'include':
                search = os.path.join(specpath, parts[1])
                matches = glob.glob(search)
            elif line.startswith('recursive-include'):
                for pattern in parts[2:]:
                    search = os.path.join(specpath, parts[1], '**', pattern)
                    matches.extend(glob.glob(search, recursive=True))
            else:
                raise ValueError(f'unsupported MANIFEST.in line: {line}')

            for src in matches:
                tgt = os.path.dirname(os.path.relpath(src, specpath))
                if not(tgt):
                    add_files.append((src, '.'))
                    add_files.append((src, 'joulescope_ui'))
                else:
                    add_files.append((src, tgt))
    print(add_files)
    return add_files


DATA = [
    # Force pyqtgraph icon include, which were not automatically found on mac OS 12 & Ubuntu for 0.9.11
    [os.path.join(PYQTGRAPH_PATH, 'icons', '*.png'), 'pyqtgraph/icons'],
    [os.path.join(PYQTGRAPH_PATH, 'icons', '*.svg'), 'pyqtgraph/icons'],
    # Force pyjoulescope_driver image include
    [os.path.join(PYJOULESCOPE_DRIVER_PATH, '*.img'), 'pyjoulescope_driver'],
]


if sys.platform.startswith('win'):
    EXE_NAME = 'joulescope'
    HIDDEN_IMPORTS = []
    BINARIES = [  # uses winusb which comes with Windows
        ('C:\\Windows\\System32\\msvcp140.dll', '.'),
        ('C:\\Windows\\System32\\msvcp140_1.dll', '.'),
        ('C:\\Windows\\System32\\msvcp140_2.dll', '.'),
    ]
    DATA += []
elif sys.platform.startswith('darwin'):
    EXE_NAME = 'joulescope_launcher'
    HIDDEN_IMPORTS = []
    BINARIES = []
    DATA += [
        # copy over the fonts so they work with QFontDialog
        ['joulescope_ui/fonts/fonts.qrc', 'Fonts'],
        ['joulescope_ui/fonts/Lato/*', 'Fonts/Lato'],
    ]
else:
    EXE_NAME = 'joulescope_launcher'
    HIDDEN_IMPORTS = ['OpenGL.platform.egl']
    BINARIES = []
    DATA += []

a = Analysis(
    ['joulescope_ui/__main__.py'],
    pathex=PATHEX,
    binaries=BINARIES,
    datas=DATA + parse_manifest(),
    hiddenimports=[
        'html.parser',
        'joulescope.v0.decimators',
        'joulescope.v0.filter_fir',
        'joulescope.v0.pattern_buffer',
        'joulescope.units',
        'numpy.core._dtype_ctypes',
        'psutil',
        'secrets', 
    ] + HIDDEN_IMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure, 
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='joulescope_ui/resources/icon.ico',
    codesign_identity=MACOS_CODE_SIGN,
    target_arch='universal2' if sys.platform.startswith('darwin') else 'x86_64'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='joulescope',
)

os.makedirs('dist_installer', exist_ok=True)

if sys.platform.startswith('darwin'):
    # https://blog.macsales.com/28492-create-your-own-custom-icons-in-10-7-5-or-later
    # iconutil --convert icns joulescope_ui/resources/icon.iconset
    # hdiutil create ./dist/joulescope.dmg -srcfolder ./dist/joulescope.app -ov
    app = BUNDLE(
        coll,
        name='joulescope.app',
        icon='joulescope_ui/resources/icon.icns',
        bundle_identifier='com.jetperch.joulescope',
        version=joulescope_ui.__version__,
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'CFBundleName': 'Joulescope',
            'CFBundleVersion': joulescope_ui.__version__,
            'ATSApplicationFontsPath': 'Fonts/',
            'NSHighResolutionCapable': 'True',
        })

    print('unsign app')
    subprocess.run(['codesign', '--remove', '--all-architectures',
                   './dist/joulescope.app'],
                   cwd=specpath)

    print('sign app')
    subprocess.run(['codesign',
                    '-s', MACOS_CODE_SIGN,
                    '--options', 'runtime',
                    '--entitlements', './entitlements.plist',
                    '--deep', './dist/joulescope.app'],
                   cwd=specpath)

    print('create dmg')
    subprocess.run(['npm', 'install'])
    dmg_file = 'dist_installer/joulescope_%s.dmg' % VERSION_STR
    subprocess.run(['./node_modules/appdmg/bin/appdmg.js', 'appdmg.json', dmg_file])

elif sys.platform == 'win32':
    if os.environ.get('CI', 'false').lower() == 'true':
        print('Running from CI: produce ZIP archive')
        shutil.make_archive(f'dist_installer/joulescope_{VERSION_STR}', 'zip', 'dist/joulescope')
        # future: forward to installer maker?
    else:
        print('Create Inno Setup installer')
        subprocess.run([INNO_SETUP_PATH, 'joulescope.iss'],
                        cwd=os.path.join(specpath, 'dist', 'joulescope'))

elif sys.platform == 'linux':
    os.rename(os.path.join(specpath, 'dist/joulescope'),
              os.path.join(specpath, 'dist/joulescope_%s' % VERSION_STR))
    subprocess.run(['tar', 'czvf',
                    '../dist_installer/joulescope_%s.tar.gz' % VERSION_STR,
                    'joulescope_%s/' % VERSION_STR],
                    cwd=os.path.join(specpath, 'dist'))
