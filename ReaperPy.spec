# -*- mode: python ; coding: utf-8 -*-
# ReaperPy - PyInstaller-Spezifikation (Ordner-Version).  Bauen: build_exe.bat (erzeugt vorher version_info.txt).
import glob
import os

from PyInstaller.utils.hooks import collect_all

ROOT = SPECPATH

# ALLE Module des Projekts mitnehmen: tools_gui laedt die Tabs per __import__(name) - das findet PyInstaller nicht von allein.
# (Tests, Build-Skripte und der Icon-Generator gehoeren nicht in die EXE.)
hiddenimports = sorted(
    os.path.splitext(os.path.basename(f))[0]
    for f in glob.glob(os.path.join(ROOT, '*.py'))
    if not os.path.basename(f).startswith(('test_', 'build', 'icon_art'))
)
datas = [(os.path.join(ROOT, 'assets'), 'assets')]
for doc in ('LICENSE', 'NOTICE', 'README.md'):
    datas.append((os.path.join(ROOT, doc), '.'))
datas.append((os.path.join(ROOT, 'licenses'), 'licenses'))
binaries = []
for pkg in ('keystone', 'capstone'):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gui.py'],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ReaperPy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'assets', 'reaperpy.ico'),
    version=os.path.join(ROOT, 'version_info.txt'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ReaperPy',
)
