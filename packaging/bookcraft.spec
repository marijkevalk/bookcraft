# PyInstaller spec — build a double-click Bookcraft bundle.
#
# IMPORTANT: build ON the target OS. A Windows .exe must be built on Windows,
# a macOS .app on a Mac. This spec is not (and cannot be) built on the Linux
# VPS. It is provided ready-to-build so a one-file bundle can be produced later
# on Kristiaan's own machine (or in CI) without any code changes.
#
# Build:
#   pip install pyinstaller
#   pyinstaller packaging/bookcraft.spec
# Result: dist/Bookcraft (a folder with the launcher; zip and share it).
#
# One-time notes:
#   - Windows: the produced Bookcraft.exe is unsigned; SmartScreen may warn on
#     first run ("More info" -> "Run anyway").
#   - macOS: the produced Bookcraft.app is unsigned/unnotarised; first run needs
#     right-click -> Open (Gatekeeper). Sign/notarise later for a clean launch.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Ship the bundled template + any docxtpl package data.
datas = [("../src/bookcraft/assets/template.docx", "bookcraft/assets")]
datas += collect_data_files("docxtpl")
datas += collect_data_files("docx")

hiddenimports = ["bookcraft.webui"] + collect_submodules("flask")

a = Analysis(
    ["launch_bookcraft.py"],
    pathex=["../src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["playwright"],  # not needed by the UI/format path
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Bookcraft",
    console=True,  # keep a small window so the user can see the local URL
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Bookcraft",
)
