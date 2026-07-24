# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# Read version file
version_file = os.path.join(SPECPATH, 'src', '_version.py')

# Fallback version string
version_str = "Dev-Snapshot-Undefined-Version"

if os.path.exists(version_file):
    version_globals = {}
    with open(version_file, "r", encoding="utf-8") as f:
        exec(f.read(), version_globals)
    if "__version__" in version_globals:
        version_str = version_globals["__version__"]

# Construct the versioned application name
app_name = f"VoiceVis-{version_str}"

# These packages requires manual handling to include all required dependencies
for package in ['opensmile', 'audresample']:
    ret = collect_all(package)
    datas += ret[0]
    binaries += ret[1]
    hiddenimports += ret[2]

a = Analysis(
    ['src\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    exclude_binaries=True,
    name=app_name,  # Updates the main executable filename
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=app_name,  # Updates the parent folder directory name inside dist/
)


print("*** Running post-processing to copy external folders ***")
for folder in ['resources']:
    src_folder = os.path.join(SPECPATH, folder)
    dest_folder = os.path.join(DISTPATH, app_name, folder)

    # Create the source folder locally if it doesn't exist
    if not os.path.exists(src_folder):
        os.makedirs(src_folder)

    # If rebuilding, delete the old destination folder first
    if os.path.exists(dest_folder):
        shutil.rmtree(dest_folder)

    # Copy the folder to the final build directory, next to the .exe
    shutil.copytree(src_folder, dest_folder)
    print(f"Copied {folder} directly next to the executable.")