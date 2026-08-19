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
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

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

# --- PaddleOCR stack (Hito 2.8 — migración Python normal 2026-05-31) -----------
# PaddleOCR carga submódulos + DLLs nativas dinámicamente; collect_all es la única
# forma robusta de capturarlos. El path de inferencia real (verificado por trace)
# arrastra: paddle, paddleocr, shapely (GEOS dll), skimage, scipy, imgaug, pyclipper,
# lmdb. matplotlib/pandas NO se cargan en inferencia → siguen excluidos.
paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all("paddle")
paddleocr_datas, paddleocr_binaries, paddleocr_hiddenimports = collect_all("paddleocr")
shapely_datas, shapely_binaries, shapely_hiddenimports = collect_all("shapely")
skimage_datas, skimage_binaries, skimage_hiddenimports = collect_all("skimage")
scipy_datas, scipy_binaries, scipy_hiddenimports = collect_all("scipy")
imgaug_datas, imgaug_binaries, imgaug_hiddenimports = collect_all("imgaug")
# Cython: el stack de paddle (skimage/scipy/imgaug) lee plantillas de
# Cython/Utility/*.cpp en runtime. PyInstaller solo trae los .py por defecto;
# collect_all incluye los data files (.cpp/.pyx/.h) que faltaban → sin esto
# `import paddleocr` falla en el .exe con FileNotFoundError CppSupport.cpp.
cython_datas, cython_binaries, cython_hiddenimports = collect_all("Cython")
# imageio: paddleocr → imgaug → imageio, que lee su propia metadata
# (importlib.metadata.version) al importarse + carga plugins dinámicos.
# collect_all trae plugins; copy_metadata trae el .dist-info que faltaba
# → sin esto `import paddleocr` falla con PackageNotFoundError: imageio.
imageio_datas, imageio_binaries, imageio_hiddenimports = collect_all("imageio")
# Metadata (.dist-info) de paquetes que hacen importlib.metadata.version()
# en su import. Faltaba imageio; agrego los vecinos de la cadena por defensa.
metadata_datas = []
for _pkg in ("imageio", "imgaug", "scikit-image", "paddleocr", "paddlepaddle"):
    try:
        metadata_datas += copy_metadata(_pkg)
    except Exception:
        pass

# Deps externas que paddleocr importa en profundidad (ppocr.utils.network →
# requests + árbol). PyInstaller no las traza desde los módulos traídos por
# collect_all, así que las colecto explícitamente. certifi además trae su
# cacert.pem como data file. Sin esto: ModuleNotFoundError 'requests'.
net_datas, net_binaries, net_hiddenimports = [], [], []
for _dep in ("requests", "urllib3", "certifi", "charset_normalizer", "idna"):
    try:
        _d, _b, _h = collect_all(_dep)
        net_datas += _d
        net_binaries += _b
        net_hiddenimports += _h
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Data files que tienen que ir adentro del bundle
# ---------------------------------------------------------------------------
datas = [
    # La carpeta app/resources/ ENTERA: templates del detector, icon.ico, farm_nodes.toml,
    # avatar_refs/, avatar_reject{,_det}/, engine_refs/, slot_digits{,_s5,_extraccion}/,
    # badge_baselines/.
    # Enumerar carpeta por carpeta ya falló DOS veces: farm_nodes.toml quedó afuera
    # (2026-08-18 → FileNotFoundError en cada arranque cargando los nodos S13), y los
    # baselines de badges nunca estuvieron — vivían en audit/, que el .exe no alcanza, así
    # que el auto-restore de la librería de avatares no existía del lado empaquetado
    # (2026-08-19). Por eso va la carpeta entera: un recurso nuevo entra sin tocar el spec.
    # ~40 MB, de los cuales 34 son los tres baselines. Sobre 1335 MB de bundle es 3%, y
    # compra la red que evita que el grid vuelva a nombrar mal con confianza.
    (str(REPO / "app" / "resources"),               "app/resources"),
    # Configuración (rois.toml + defaults.toml)
    (str(REPO / "app" / "config"),                  "app/config"),
    # DB (sólo lectura desde el .exe; el usuario puede sobrescribirla)
    (str(REPO / "db" / "danibod_zzz_v2.db"),        "db"),
    # Assets para asset_resolver (Hito 2.7) — set logos, splash arts, avatares
    (str(REPO / "Documentacion" / "Interfaz" / "Set_Discos_Logo"), "Documentacion/Interfaz/Set_Discos_Logo"),
    (str(REPO / "Documentacion" / "Interfaz" / "splash_arts"),     "Documentacion/Interfaz/splash_arts"),
    (str(REPO / "Pj_stats"),                                       "Pj_stats"),
] + mss_datas + pyside_datas + pytess_datas + pynput_datas \
  + paddle_datas + paddleocr_datas + shapely_datas + skimage_datas + scipy_datas + imgaug_datas + cython_datas \
  + imageio_datas + metadata_datas + net_datas

binaries = mss_binaries + pyside_binaries + pytess_binaries + pynput_binaries \
    + paddle_binaries + paddleocr_binaries + shapely_binaries + skimage_binaries + scipy_binaries + imgaug_binaries + cython_binaries + imageio_binaries + net_binaries

# ---------------------------------------------------------------------------
# Hidden imports — módulos que PyInstaller no detecta automáticamente
# ---------------------------------------------------------------------------
hiddenimports = mss_hiddenimports + pyside_hiddenimports + pytess_hiddenimports + pynput_hiddenimports + win32_hiddenimports \
    + paddle_hiddenimports + paddleocr_hiddenimports + shapely_hiddenimports + skimage_hiddenimports + scipy_hiddenimports + imgaug_hiddenimports + cython_hiddenimports + imageio_hiddenimports + net_hiddenimports + [
    # PaddleOCR deps con carga dinámica que collect_all puede no resolver solo
    "pyclipper",
    "lmdb",
    "skimage.filters.rank.core_cy_3d",
    "scipy.special.cython_special",
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
    "app.core.parser_agent_stats",
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
    "matplotlib",   # no se carga en inferencia paddleocr (verificado por trace)
    "pandas",       # idem
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
