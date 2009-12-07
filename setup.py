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
    setup(
        app=APP,
        data_files=DATA_FILES,
        options={'py2app': OPTIONS},
        setup_requires=['py2app'],
    )
