# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# --- 1. Safely read the generated version file at compile time ---
# Changed SPEC_FILE to spec_file here:
SPEC_DIR = SPECPATH
version_file = os.path.join(SPEC_DIR, 'src', '_version.py')

version_str = "Dev-Snapshot"
if os.path.exists(version_file):
    version_globals = {}
    with open(version_file, "r", encoding="utf-8") as f:
        exec(f.read(), version_globals)
    if "__version__" in version_globals:
        version_str = version_globals["__version__"]

# Construct the versioned application name
app_name = f"VoiceVis-{version_str}"


# --- 2. Copy resource folders into the application tree ---
for folder in ['targets', 'docs']:
    folder_path = os.path.join(SPEC_DIR, folder)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    datas.append((folder_path, folder))

# Collect third-party package resources
tmp_ret = collect_all('opensmile')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('audresample')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


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