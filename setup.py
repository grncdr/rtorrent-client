import os

APP = ['wrtc.py']
DATA_FILES = []
OPTIONS = {'argv_emulation': True}

if os.name == 'nt':
    from distutils.core import setup
    import py2exe
    setup(windows=APP)

elif os.uname()[0] == 'Darwin':
    from setuptools import setup

    plist = {
        'CFBundleName': 'wrTc',
        'CFBundleShortVersionString': '0.0.0.0',
        'CFBundleIdentifier': 'com.stephensugden.wrtc',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeExtensions': ['torrent'],
                'CFBundleTypeName': 'Bit Torrent File',
                'CFBundleTypeRole': 'Viewer',
            },
        ],
    }

    OPTIONS['plist'] = plist

    setup(
        app=APP,
        data_files=DATA_FILES,
        options={'py2app': OPTIONS},
        setup_requires=['py2app']
    )
