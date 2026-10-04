# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPEC).parent

a = Analysis(
    ["app/main.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "app" / "templates"), "app/templates"),
        (str(root / "app" / "static"), "app/static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AbsensiTPA", console=True)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AbsensiTPA",
)
