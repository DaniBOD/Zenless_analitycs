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

# Título de ventana del cliente ZZZ
ZZZ_WINDOW_TITLE = "ZenlessZoneZero"

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


def find_zzz_window(title: str = ZZZ_WINDOW_TITLE) -> WindowBounds | None:
    """Busca la ventana del juego por título. Devuelve None si no está abierta."""
    if sys.platform != "win32":
        return None
    try:
        import win32gui
        hwnd = win32gui.FindWindow(None, title)
        if not hwnd:
            return None
        rect = win32gui.GetWindowRect(hwnd)
        left, top, right, bottom = rect
        return WindowBounds(left, top, right - left, bottom - top)
    except ImportError:
        return None


def capture_window(window: WindowBounds | None = None) -> np.ndarray | None:
    """
    Captura la ventana del juego. Si window=None, busca la ventana de ZZZ.
    Devuelve numpy array BGR o None si la ventana no se encontró.
    """
    try:
        import mss
        import mss.tools
    except ImportError:
        raise RuntimeError("mss no instalado. Ejecutar: pip install mss")

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
