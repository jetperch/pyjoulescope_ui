# -*- mode: python -*-

# Configuration file for PyInstaller
# See https://pyinstaller.readthedocs.io/en/stable/index.html
# > pip install pyinstaller
# > pyinstaller joulescope.spec

# Mac OS X
# https://kivy.org/doc/stable/guide/packaging-osx.html
# hdiutil create ./dist/joulescope.dmg -srcfolder ./dist/joulescope.app -ov

import sys
import os
import pyqtgraph
import subprocess
import shutil
import time

block_cipher = None
specpath = os.path.dirname(os.path.abspath(SPEC))
PATHEX = []
sys.path.insert(0, specpath)
import joulescope_ui
VERSION_STR = joulescope_ui.__version__.replace('.', '_')
MACOS_CODE_SIGN = 'Developer ID Application: Jetperch LLC (WFRS3L8Y7Y)'
PYQTGRAPH_PATH = os.path.dirname(pyqtgraph.__file__)


def find_site_packages():
    for p in sys.path:
        if p.endswith('site-packages'):
            return p
    raise RuntimeError('Could not find site-packages')


def parse_manifest():
    add_files = [
        ('CREDITS.html', 'joulescope_ui'),
        ('CHANGELOG.md', 'joulescope_ui'),
    ]
    with open(os.path.join(specpath, 'MANIFEST.in'), 'r', encoding='utf-8') as f:
        for line in f.readlines():
            line = line.strip()
            print(line)
            if not line.startswith('include'):
                continue
            path = line.split(None, maxsplit=1)[-1].strip()
            if '/' in path:
                tgt = os.path.dirname(path)
            else:
                tgt = '.'
            add_files.append((path, tgt))
    return add_files


DATA = [
    # Force pyqtgraph icon include, which were not automatically found on mac OS 12 & Ubuntu for 0.9.11
    [os.path.join(PYQTGRAPH_PATH, 'icons', '*.png'), 'pyqtgraph/icons'],
    [os.path.join(PYQTGRAPH_PATH, 'icons', '*.svg'), 'pyqtgraph/icons'],
]


if sys.platform.startswith('win'):
    EXE_NAME = 'joulescope'
    HIDDEN_IMPORTS = []
    BINARIES = [  # uses winusb which comes with Windows
        ('C:\\Windows\\System32\\msvcp100.dll', '.'),
        ('C:\\Windows\\System32\\msvcr100.dll', '.'),
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
            'CFBundleVersion': joulescope_ui.VERSION,
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

    # subprocess.run(['hdiutil', 'create', './dist/joulescope_%s.dmg' % VERSION_STR,
    #                 '-srcfolder', './dist/joulescope.app', '-ov'],
    #                 cwd=specpath)
    print('create dmg')
    dmg_file = 'dist/joulescope_%s.dmg' % VERSION_STR
    subprocess.run(['./node_modules/appdmg/bin/appdmg.js', 'appdmg.json', dmg_file])

    # xcrun altool --notarize-app --primary-bundle-id "com.jetperch.joulescope" --username "matt.liberty@jetperch.com" --password "@keychain:Developer-altool" --file "dist/joulescope_0_9_11.dmg"
    # xcrun altool --notarization-info "7c927036-3c17-4f03-ba24-d49420b1e81d" --username "matt.liberty@jetperch.com" --password "@keychain:Developer-altool"
    # spctl -a -t open --context context:primary-signature dmg_file
    # xcrun stapler staple dist/joulescope_0_9_11.dmg

elif sys.platform == 'win32':
    subprocess.run(['C:\Program Files (x86)\Inno Setup 6\ISCC.exe', 
                    'joulescope.iss'],
                    cwd=specpath)

elif sys.platform == 'linux':
    os.rename(os.path.join(specpath, 'dist/joulescope'),
              os.path.join(specpath, 'dist/joulescope_%s' % VERSION_STR))
    subprocess.run(['tar', 'czvf',
                    'joulescope_%s.tar.gz' % VERSION_STR,
                    'joulescope_%s/' % VERSION_STR],
                    cwd=os.path.join(specpath, 'dist'))

