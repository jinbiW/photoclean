from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    get_package_paths,
)


datas = collect_data_files("lpips") + collect_data_files("pillow_heif")
_, torchvision_dir = get_package_paths("torchvision")
binaries = collect_dynamic_libs("torchvision") + [
    (str(Path(torchvision_dir) / "_C_stable.pyd"), "torchvision"),
    (str(Path(torchvision_dir) / "image_stable.pyd"), "torchvision"),
]
hiddenimports = (
    collect_submodules("lpips")
    + collect_submodules("torchvision.models")
    + [
        "pythoncom",
        "pywintypes",
        "win32com.client",
        "win32com.shell.shell",
        "win32com.shell.shellcon",
    ]
)

a = Analysis(
    ["photoclean_launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["photoclean_runtime_hook.py"],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
# The Codex workspace runtime adds Poppler's ICU 78 DLLs to PATH. Qt on Windows
# expects the system ICU forwarder; bundling Poppler's copies causes WinError 127.
a.binaries = [
    item
    for item in a.binaries
    if Path(item[0]).name.casefold() not in {"icuuc.dll", "icudt78.dll"}
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoClean",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PhotoClean",
)
