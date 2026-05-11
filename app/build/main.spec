# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — DaniBOD ZZZ Analytics (--onedir, --windowed).

Genera:
    app/build/dist/DaniBOD_ZZZ_Analytics/
        DaniBOD_ZZZ_Analytics.exe
        _internal/  (DLLs, assets, configs)

Comandos:
    pyinstaller app/build/main.spec --clean
    o:
    pyinstaller app/build/main.spec --clean --noconfirm
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

# El spec se ejecuta con cwd = directorio donde se invoca PyInstaller.
# Asumimos que se ejecuta desde la raíz del repo (cwd = repo root).
REPO = Path.cwd().resolve()

# Paquetes con carga dinámica de submódulos. collect_all es más robusto que
# hiddenimports porque captura también datas + binaries del paquete.
mss_datas, mss_binaries, mss_hiddenimports = collect_all("mss")
pyside_datas, pyside_binaries, pyside_hiddenimports = collect_all("PySide6")
pytess_datas, pytess_binaries, pytess_hiddenimports = collect_all("pytesseract")
pynput_datas, pynput_binaries, pynput_hiddenimports = collect_all("pynput")
win32_hiddenimports = collect_submodules("win32com") + collect_submodules("win32")

# ---------------------------------------------------------------------------
# Data files que tienen que ir adentro del bundle
# ---------------------------------------------------------------------------
datas = [
    # Templates del detector (PNG)
    (str(REPO / "app" / "resources" / "templates"), "app/resources/templates"),
    # Configuración (rois.toml + futuros)
    (str(REPO / "app" / "config"),                  "app/config"),
    # Icono
    (str(REPO / "app" / "resources" / "icon.ico"),  "app/resources"),
    # DB (sólo lectura desde el .exe; el usuario puede sobrescribirla)
    (str(REPO / "db" / "danibod_zzz_v2.db"),        "db"),
    # Assets para asset_resolver (Hito 2.7) — set logos, splash arts, avatares
    (str(REPO / "Documentacion" / "Interfaz" / "Set_Discos_Logo"), "Documentacion/Interfaz/Set_Discos_Logo"),
    (str(REPO / "Documentacion" / "Interfaz" / "splash_arts"),     "Documentacion/Interfaz/splash_arts"),
    (str(REPO / "Pj_stats"),                                       "Pj_stats"),
] + mss_datas + pyside_datas + pytess_datas + pynput_datas

binaries = mss_binaries + pyside_binaries + pytess_binaries + pynput_binaries

# ---------------------------------------------------------------------------
# Hidden imports — módulos que PyInstaller no detecta automáticamente
# ---------------------------------------------------------------------------
hiddenimports = mss_hiddenimports + pyside_hiddenimports + pytess_hiddenimports + pynput_hiddenimports + win32_hiddenimports + [
    # PySide6 plugins
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
    # Win32
    "win32gui",
    "win32api",
    "win32con",
    "win32event",
    # OpenCV
    "cv2",
    # App
    "app.core.ocr_tesseract",
    "app.core.ocr_paddle",
    "app.core.monitor",
    "app.core.detector",
    "app.core.parser_disc",
    "app.core.recommender",
    "app.core.scoring",
    "app.core.score_normalizer",
    "app.core.stats_vocab",
    "app.core.sync_equip",
    "app.core.sync_upgrade",
    "app.core.optimizer",
    "app.core.hotkeys",
    "app.core.capturer",
    "app.core.asset_resolver",
    "app.ui.tokens",
    "app.ui.toast",
    "app.ui.live_panel",
    "app.ui.controller",
    "app.db.connection",
    "app.db.repositories",
]

# ---------------------------------------------------------------------------
# Excluir módulos pesados que no usamos
# ---------------------------------------------------------------------------
excludes = [
    "matplotlib",
    "scipy",
    "pandas",
    "tkinter",
    "test",
    "tests",
    "pytest",
    "IPython",
    "jupyter",
]


a = Analysis(
    [str(REPO / "app" / "main.py")],
    pathex=[str(REPO)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DaniBOD_ZZZ_Analytics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                     # --windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(REPO / "app" / "resources" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,                         # UPX puede romper DLLs de PySide6
    upx_exclude=[],
    name="DaniBOD_ZZZ_Analytics",
)
