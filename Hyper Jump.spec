from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project_root = Path.cwd()
panda3d_root = project_root / ".venv" / "lib" / "python3.14" / "site-packages" / "panda3d"
data_files = [
    (str(project_root / "alien sound.mp3"), "."),
    (str(project_root / "boss sound.mp3"), "."),
    (str(project_root / "human hit.mp3"), "."),
    (str(project_root / "laser shot.mp3"), "."),
    (str(project_root / "missile shot.mp3"), "."),
    (str(panda3d_root / "etc" / "Config.prc"), "panda3d/etc"),
    (str(panda3d_root / "etc" / "Confauto.prc"), "panda3d/etc"),
]
panda3d_binaries = collect_dynamic_libs("panda3d")
panda3d_data_files = collect_data_files(
    "panda3d",
    includes=["models/**/*.egg.pz", "models/**/*.rgb", "models/**/*.rgba", "models/**/*.png", "models/**/*.jpg", "models/**/*.gif"],
)

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=panda3d_binaries,
    datas=data_files + panda3d_data_files,
    hiddenimports=[],
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
    exclude_binaries=True,
    name="Hyper Jump",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Hyper Jump",
)
