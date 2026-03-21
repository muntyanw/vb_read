# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path.cwd()


def required_data_files(*names):
    datas = []
    missing = []
    for name in names:
        path = ROOT / name
        if path.exists():
            datas.append((str(path), "."))
        else:
            missing.append(name)

    if missing:
        raise SystemExit(
            "Missing required files for build: "
            + ", ".join(missing)
            + ". Put them in the project root before running PyInstaller."
        )

    return datas


def optional_data_files(*names):
    datas = []
    for name in names:
        path = ROOT / name
        if path.exists():
            datas.append((str(path), "."))
    return datas


def collect_tree(src_dir, dest_dir):
    src_path = ROOT / src_dir
    if not src_path.exists():
        raise SystemExit(
            f"Missing required directory for build: {src_dir}. "
            "Put it in the project root before running PyInstaller."
        )

    datas = []
    for path in src_path.rglob("*"):
        if path.is_file():
            rel_parent = path.relative_to(src_path).parent
            target_dir = Path(dest_dir) / rel_parent
            datas.append((str(path), str(target_dir)))
    return datas


datas = []
datas += required_data_files(
    "settings.json",
    "settings.yaml",
    "creds.json",
    "tg_channels.json",
    "region.json",
    "bot_session.session",
    "rus.traineddata",
    "ukr.traineddata",
)
datas += optional_data_files(
    "previous_text.txt",
    "texts.txt",
)
datas += collect_tree("images", "images")


a = Analysis(
    ["pwa.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["cv2"],
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
    name="pwa",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
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
    name="pwa",
)
