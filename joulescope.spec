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
import subprocess
import shutil

block_cipher = None
specpath = os.path.dirname(os.path.abspath(SPEC))
PATHEX = []
sys.path.insert(0, specpath)
import joulescope_ui
from joulescope_ui import firmware_manager
VERSION_STR = joulescope_ui.__version__.replace('.', '_')


def firmware_get():
    p = firmware_manager.cache_path()
    return firmware_manager.cache_fill(p)


def find_site_packages():
    for p in sys.path:
        if p.endswith('site-packages'):
            return p
    raise RuntimeError('Could not find site-packages')


if sys.platform.startswith('win'):
    EXE_NAME = 'joulescope'
    BINARIES = [  # uses winusb which comes with Windows
        ('C:\\Windows\\System32\\msvcp100.dll', '.'),
        ('C:\\Windows\\System32\\msvcr100.dll', '.'),
        ('C:\\Windows\\System32\\msvcp140.dll', '.'),
    ]
    PATHEX.append(os.path.join(find_site_packages(), 'shiboken2'))
elif sys.platform.startswith('darwin'):
    from joulescope_ui.libusb_mac import mac_binaries
    EXE_NAME = 'joulescope_launcher'
    BINARIES = [(x, '.') for x in mac_binaries()]
else:
    EXE_NAME = 'joulescope_launcher'
    BINARIES = []  # sudo apt install libusb-1

a = Analysis(
    ['joulescope_ui/__main__.py'],
    pathex=PATHEX,
    binaries=BINARIES,
    datas=[
        ('joulescope_ui/getting_started.html', 'joulescope_ui'),
        ('joulescope_ui/preferences.html', 'joulescope_ui'),
        ('CREDITS.html', 'joulescope_ui'),
        (firmware_get(), 'joulescope_ui/firmware/js110'),
    ],
    hiddenimports=[
        'joulescope.decimators',
        'joulescope.filter_fir',
        'joulescope.pattern_buffer',
        'numpy.core._dtype_ctypes',
        'pkg_resources.py2_warn',
        'psutil',
        'secrets', 
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False, )

pyz = PYZ(
    a.pure, 
    a.zipped_data,
    cipher=block_cipher, )

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
    icon='joulescope_ui/resources/icon.ico', )

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='joulescope', )


if sys.platform.startswith('darwin'):
    # https://blog.macsales.com/28492-create-your-own-custom-icons-in-10-7-5-or-later
    # iconutil --convert icns joulescope_ui/resources/icon.iconset
    # hdiutil create ./dist/joulescope.dmg -srcfolder ./dist/joulescope.app -ov
    app = BUNDLE(
        coll,
        name='joulescope.app',
        icon='joulescope_ui/resources/icon.icns',
        bundle_identifier='com.jetperch.joulescope',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'CFBundleName': 'Joulescope',
            'CFBundleVersion': joulescope_ui.VERSION,
            'ATSApplicationFontsPath': 'Fonts/',
            'NSHighResolutionCapable': 'True',
        })

    # copy over the fonts so they work with QFontDialog
    font_src_path = os.path.join(specpath, 'joulescope_ui', 'fonts')
    font_dst_path = os.path.join(specpath, 'dist', 'joulescope.app', 'Contents', 'Resources', 'Fonts')
    if os.path.isdir(font_dst_path):
        shutil.rmtree(font_dst_path)
    shutil.copytree(font_src_path, font_dst_path)

    print('sign app')
    subprocess.run(['codesign', '-s', 'Developer ID Application: Jetperch LLC (WFRS3L8Y7Y)', 
                    '--deep', './dist/joulescope.app'],
                   cwd=specpath)
    # subprocess.run(['hdiutil', 'create', './dist/joulescope_%s.dmg' % VERSION_STR,
    #                 '-srcfolder', './dist/joulescope.app', '-ov'],
    #                 cwd=specpath)
    print('create dmg')
    subprocess.run(['appdmg', 'appdmg.json', 'dist/joulescope_%s.dmg' % VERSION_STR])

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

