"""
Hito 2.4.5 — Captura de pantalla y recorte de ROI.
Usa mss para screenshots y win32gui para localizar la ventana del juego.
ROIs definidas en app/config/rois.toml (coordenadas normalizadas 0-1).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

# Nombres del ejecutable del juego (filtro principal — el más confiable).
# Verificado en QA 2026-05-11: el proceso del juego es "ZenlessZoneZero.exe".
ZZZ_EXECUTABLE_NAMES = (
    "ZenlessZoneZero.exe",
    "ZZZ.exe",
)

# Substrings que pueden aparecer en el título de la ventana de ZZZ.
# Filtro secundario solo si no podemos verificar el proceso.
ZZZ_WINDOW_TITLE_CANDIDATES = (
    "ZenlessZoneZero",
    "Zenless Zone Zero",
)

# Keywords que indican que la ventana NO es el juego (navegadores, editores
# que pueden tener "Zenless" en el título cuando muestran este repo).
EXCLUDED_TITLE_KEYWORDS = (
    "opera", "chrome", "firefox", "edge", "brave", "safari", "vivaldi",
    "code", "vscode", "visual studio", "github",
    "explorer", "explorador", "powershell", "cmd", "terminal",
    "discord", "telegram", "whatsapp", "spotify",
    "notepad", "bloc de notas",
)

_ROIS: dict | None = None


def _load_rois() -> dict:
    global _ROIS
    if _ROIS is None:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        rois_path = Path(__file__).parent.parent / "config" / "rois.toml"
        with open(rois_path, "rb") as f:
            _ROIS = tomllib.load(f)
    return _ROIS


class WindowBounds(NamedTuple):
    left: int
    top: int
    width: int
    height: int
    title: str = ""    # título real encontrado (para log/debug)
    hwnd: int = 0      # handle de la ventana (0 = desconocido). Usado para el gate de foco.


def get_foreground_window() -> int:
    """Handle (hwnd) de la ventana en primer plano, o 0 si no se puede determinar."""
    if sys.platform != "win32":
        return 0
    try:
        import win32gui
    except ImportError:
        return 0
    try:
        return int(win32gui.GetForegroundWindow())
    except Exception:
        return 0


def is_zzz_focused(foreground_hwnd: int, zzz_hwnd: int) -> bool:
    """True si la ventana del juego (zzz_hwnd) es la que está en primer plano.

    hwnd desconocido (0) → NO enfocado (conservador: ante duda no se captura la
    región, así evitamos el FP por ventana ajena superpuesta).
    """
    return zzz_hwnd != 0 and foreground_hwnd == zzz_hwnd


def list_all_visible_windows() -> list[tuple[int, str]]:
    """Devuelve [(hwnd, title)] de todas las ventanas visibles con título no vacío."""
    if sys.platform != "win32":
        return []
    try:
        import win32gui
    except ImportError:
        return []

    found: list[tuple[int, str]] = []

    def _enum_cb(hwnd: int, lparam: object) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                found.append((hwnd, title))
        return True

    win32gui.EnumWindows(_enum_cb, None)
    return found


def _get_window_exe_name(hwnd: int) -> str:
    """
    Devuelve el nombre del ejecutable (basename) del proceso dueño del hwnd.
    Vacío si no se puede determinar. Usa QueryFullProcessImageNameW (kernel32).
    """
    if sys.platform != "win32":
        return ""
    try:
        import os as _os
        import win32process
        import win32api
        import ctypes
        from ctypes import wintypes, byref, create_unicode_buffer

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == 0:
            return ""
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000 (funciona en procesos elevados)
        h_proc = win32api.OpenProcess(0x1000, False, pid)
        if not h_proc:
            return ""
        try:
            kernel32 = ctypes.windll.kernel32
            buf = create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            ok = kernel32.QueryFullProcessImageNameW(int(h_proc), 0, buf, byref(size))
            if not ok:
                return ""
            return _os.path.basename(buf.value)
        finally:
            win32api.CloseHandle(h_proc)
    except Exception:
        return ""


def _is_excluded_title(title: str) -> bool:
    """True si el título contiene keywords de navegadores/editores (no es el juego)."""
    title_l = title.lower()
    return any(kw in title_l for kw in EXCLUDED_TITLE_KEYWORDS)


def find_zzz_window(title_substrings: tuple[str, ...] = ZZZ_WINDOW_TITLE_CANDIDATES) -> WindowBounds | None:
    """
    Busca la ventana del juego. Estrategia:
    1. Enumerar TODAS las ventanas visibles.
    2. Para cada una, verificar si el ejecutable es ZenlessZoneZero.exe (filtro definitivo).
    3. Como fallback, si no podemos leer el proceso, filtrar por título y excluir
       navegadores/editores que pueden contener 'Zenless' en el título.
    """
    if sys.platform != "win32":
        return None
    try:
        import win32gui
    except ImportError:
        return None

    # Estrategia 1: buscar por nombre del proceso (más confiable)
    exe_candidates_lower = tuple(e.lower() for e in ZZZ_EXECUTABLE_NAMES)
    for hwnd, title in list_all_visible_windows():
        try:
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            if right - left < 400 or bottom - top < 300:
                continue
            exe = _get_window_exe_name(hwnd).lower()
            if exe and exe in exe_candidates_lower:
                return WindowBounds(left, top, right - left, bottom - top, f"{title} [{exe}]", hwnd)
        except Exception:
            continue

    # Estrategia 2 (fallback): match por título con exclusiones
    candidates_lower = tuple(s.lower() for s in title_substrings)
    for hwnd, title in list_all_visible_windows():
        if _is_excluded_title(title):
            continue
        title_l = title.lower()
        for sub in candidates_lower:
            if sub in title_l:
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect
                    if right - left < 400 or bottom - top < 300:
                        continue
                    return WindowBounds(left, top, right - left, bottom - top, title, hwnd)
                except Exception:
                    continue

    return None


def capture_window(window: WindowBounds | None = None) -> np.ndarray | None:
    """
    Captura la ventana del juego. Si window=None, busca la ventana de ZZZ.
    Devuelve numpy array BGR o None si la ventana no se encontró.
    """
    try:
        import mss
        import mss.tools
    except ImportError as exc:
        # En el .exe esto significa que faltó agregar submódulos a hiddenimports.
        # En modo dev significa que el usuario no instaló la dep.
        raise RuntimeError(
            f"No se pudo importar mss ({exc}). "
            f"Si estás en .exe: re-empaquetar con mss.tools/mss.base en hiddenimports. "
            f"Si estás en modo dev: pip install mss."
        )

    if window is None:
        window = find_zzz_window()
    if window is None:
        return None

    mon = {
        "left":   window.left,
        "top":    window.top,
        "width":  window.width,
        "height": window.height,
    }

    with mss.mss() as sct:
        screenshot = sct.grab(mon)

    # mss devuelve BGRA — convertir a BGR
    import cv2
    img = np.array(screenshot)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def crop_roi(
    img: np.ndarray,
    roi: list[float] | tuple[float, float, float, float],
) -> np.ndarray:
    """
    Recorta una ROI normalizada [x, y, w, h] (0-1) del frame.
    Devuelve el sub-array recortado.
    """
    h, w = img.shape[:2]
    x = int(roi[0] * w)
    y = int(roi[1] * h)
    rw = int(roi[2] * w)
    rh = int(roi[3] * h)
    return img[y:y + rh, x:x + rw]


def get_roi(section: str, key: str) -> list[float]:
    """Devuelve la ROI normalizada desde rois.toml."""
    rois = _load_rois()
    return rois[section][key]


def crop_named_roi(img: np.ndarray, section: str, key: str) -> np.ndarray:
    """Atajo: crop_roi(img, get_roi(section, key))."""
    return crop_roi(img, get_roi(section, key))
