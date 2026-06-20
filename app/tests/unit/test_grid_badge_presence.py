"""Gate de presencia del badge del grid S17 (5R.L.7.2). Un tile EQUIPADO lleva un avatar
circular del dueño en la esquina; un tile LIBRE no (arte/candado/oscuro). El gate evita
que `crop_grid_selected_badge` entregue una esquina sin avatar al matcher → que la votaba
a un PJ (falso 'Cissia' en discos libres, QA 2026-06-20 · viola RNF-02).

Tests sintéticos (sin frames reales): un avatar = blob saturado + anillo (Hough); una
esquina vacía o arte saturado SIN círculo → no pasa. La no-regresión sobre 218 equipados
reales (0 rechazos) se valida en audit/free_disc_presence_diag.md."""
from __future__ import annotations

import cv2
import numpy as np

from app.core.detector import _grid_badge_present


def _avatar_crop(size: int = 64) -> np.ndarray:
    """Esquina con avatar: círculo saturado + anillo claro sobre fondo oscuro."""
    img = np.full((size, size, 3), 20, np.uint8)
    c, r = size // 2, int(0.34 * size)
    cv2.circle(img, (c, c), r, (40, 110, 210), -1)      # relleno naranja saturado
    cv2.circle(img, (c, c), r, (255, 255, 255), 2)      # anillo (borde para Hough)
    return img


def test_avatar_pasa_el_gate():
    assert _grid_badge_present(_avatar_crop()) is True


def test_esquina_vacia_no_pasa():
    """Fondo gris uniforme (sin saturación) = tile libre → no hay avatar → None."""
    empty = np.full((64, 64, 3), 35, np.uint8)
    assert _grid_badge_present(empty) is False


def test_arte_saturado_sin_circulo_no_pasa():
    """Arte de disco saturado pero NO circular (rectángulo): tiene blob pero no anillo →
    no es un avatar → rechazado. Es el caso que filtraba el falso 'Cissia'."""
    art = np.full((64, 64, 3), 20, np.uint8)
    cv2.rectangle(art, (5, 5), (58, 58), (40, 110, 210), -1)
    assert _grid_badge_present(art) is False


def test_none_y_vacio_no_rompen():
    assert _grid_badge_present(None) is False
    assert _grid_badge_present(np.zeros((0, 0, 3), np.uint8)) is False
