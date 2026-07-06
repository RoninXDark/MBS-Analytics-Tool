# Build with:
#   pyinstaller --clean --noconfirm packaging/MBSAnalytics.spec
#
# This is intentionally an onedir console build for beta packaging. Console
# mode keeps CLI/nightly errors visible and scheduler logs easy to diagnose.
# The application itself defaults to the desktop GUI when launched without
# command-line arguments, so double-clicking MBSAnalytics.exe opens the app.

from pathlib import Path

project_root = Path(SPECPATH)
if project_root.name == "packaging":
    project_root = project_root.parent

datas = [
    (str(project_root / "config"), "config"),
    (str(project_root / "docs"), "docs"),
    (str(project_root / "examples"), "examples"),
    (str(project_root / "sample_data"), "sample_data"),
]

hiddenimports = [
    "matplotlib.backends.backend_tkagg",
    "openpyxl",
    "ttkbootstrap",
]

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "streamlit",
        # Heavy optional packages from the developer environment. The app does
        # not use them, and excluding them keeps beta exe builds practical.
        "IPython",
        "jupyter",
        "notebook",
        "onnxruntime",
        "pyarrow",
        "tensorflow",
        "torch",
        "torchaudio",
        "torchvision",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MBSAnalytics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    name="MBSAnalytics",
)
