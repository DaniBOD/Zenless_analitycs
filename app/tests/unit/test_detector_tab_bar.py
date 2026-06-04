"""
Tests para `detect_active_tab` — Hito 2.8 Etapa 1 (2026-06-03).

El tab-bar de la familia "detalle de agente" (Atributos base | Habilidades |
Equipamiento) es el ancla determinista que distingue S18/S19/S8. Calibrado
sobre 24 capturas reales 2559×1439 → 24/24.

Cubre:
  - Frames sintéticos: pill amarillo en cada posición → estado correcto.
  - Sin pill / frame negro → None.
  - Smoke sobre capturas reales S8 (Equipamiento) y S18 (Atributos), si están.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.detector import (  # noqa: E402
    detect_active_tab,
    _TAB_CENTERS,
    _TAB_BAR_ROI,
)

REPO = Path(__file__).resolve().parents[3]
H, W = 1440, 2560


def _frame_with_pill(center_norm_x: float) -> np.ndarray:
    """Frame negro con un pill amarillo en la franja del tab-bar, centrado en x."""
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    _, y, _, rh = _TAB_BAR_ROI
    cy = int((y + rh / 2) * H)
    cx = int(center_norm_x * W)
    half_w, half_h = 150, 32   # ~300×64 px → ratio sobre el ROI > 0.12
    # Amarillo puro en BGR → HSV H≈30 (dentro de [20,45])
    cv2.rectangle(frame, (cx - half_w, cy - half_h), (cx + half_w, cy + half_h),
                  (0, 255, 255), thickness=-1)
    return frame


@pytest.mark.parametrize("expected", ["S18", "S19", "S8"])
def test_pill_en_cada_pestana_devuelve_estado(expected):
    """Un pill amarillo centrado en cada pestaña → el código de estado correcto."""
    frame = _frame_with_pill(_TAB_CENTERS[expected])
    assert detect_active_tab(frame) == expected


def test_frame_negro_devuelve_none():
    assert detect_active_tab(np.zeros((H, W, 3), dtype=np.uint8)) is None


def test_frame_vacio_y_none_devuelven_none():
    assert detect_active_tab(None) is None
    assert detect_active_tab(np.zeros((0, 0, 3), dtype=np.uint8)) is None


def test_amarillo_fuera_del_tabbar_no_cuenta():
    """Amarillo en zona superior (no el tab-bar) → no debe disparar."""
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    cv2.rectangle(frame, (1400, 50), (1700, 150), (0, 255, 255), thickness=-1)
    assert detect_active_tab(frame) is None


def test_pill_lima_tambien_se_detecta():
    """El pill de Equipamiento es amarillo-lima (H más alto) → igual se detecta."""
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    _, y, _, rh = _TAB_BAR_ROI
    cy = int((y + rh / 2) * H)
    cx = int(_TAB_CENTERS["S8"] * W)
    # Lima en BGR (0,255,180) → HSV H≈40 (dentro de [20,45])
    cv2.rectangle(frame, (cx - 150, cy - 32), (cx + 150, cy + 32),
                  (0, 255, 180), thickness=-1)
    assert detect_active_tab(frame) == "S8"


# ---------------------------------------------------------------------------
# Smoke sobre capturas reales (skip si no están en el repo)
# ---------------------------------------------------------------------------

_S8_DIR = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados"
_S18_DIR = REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente"


def _read(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


@pytest.mark.parametrize("path", sorted(_S8_DIR.glob("*.png")), ids=lambda p: p.stem)
def test_capturas_reales_s8_dan_equipamiento(path):
    frame = _read(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar {path}")
    assert detect_active_tab(frame) == "S8"


@pytest.mark.parametrize("path", sorted(_S18_DIR.glob("*.png")), ids=lambda p: p.stem)
def test_capturas_reales_s18_dan_atributos(path):
    frame = _read(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar {path}")
    assert detect_active_tab(frame) == "S18"
