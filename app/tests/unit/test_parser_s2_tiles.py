"""Geometría de tiles de la grilla S2 (`tile_boxes`, `crop_tile_center`, `crop_tile_slot`).

En S2 la grilla de recompensas es 4 columnas × 2 filas visibles. `tile_boxes` localiza los
tiles con disco (por su franja de rareza) y los crops aíslan el dígito de slot (arriba-izq.) y
el arte del disco (centro, para el matcher de sets). Calibrado 2026-07 contra las franjas de
rareza de los 7 fixtures S2 (todos exponen los 8 tiles).

Este test valida la GEOMETRÍA (determinista, sin OCR). La lectura del slot por OCR y el match
del set son parte de la QA en vivo (el gap render-package vs tile-in-game es riesgo §8.1).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_s2 import TileBox, tile_boxes, crop_tile_center, crop_tile_slot, read_tile_slot

REPO = Path(__file__).resolve().parents[3]
_S2 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "01_Pantalla_Resultado_Desafio"
_FIXTURES = sorted(_S2.glob("Ejemplo_*.png"))


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.skipif(not _FIXTURES, reason="capturas S2 no presentes")
@pytest.mark.parametrize("fx", _FIXTURES, ids=lambda p: p.name)
def test_tile_boxes_encuentra_los_8_tiles(fx):
    fr = _load(fx)
    boxes = tile_boxes(fr)
    assert len(boxes) == 8, f"{fx.name}: {len(boxes)} tiles"
    # 2 filas × 4 columnas, orden row-major.
    assert [(b.row, b.col) for b in boxes] == [(r, c) for r in range(2) for c in range(4)]
    H, W = fr.shape[:2]
    for b in boxes:
        assert 0 <= b.x0 < b.x1 <= W and 0 <= b.y0 < b.y1 <= H


@pytest.mark.skipif(not _FIXTURES, reason="capturas S2 no presentes")
def test_crops_no_vacios_y_slot_arriba_izquierda():
    fr = _load(_FIXTURES[0])
    box = tile_boxes(fr)[0]
    center = crop_tile_center(fr, box)
    slot = crop_tile_slot(fr, box)
    assert center.size > 0 and slot.size > 0
    # el crop de slot es la esquina superior-izquierda del tile → más chico que el tile
    assert slot.shape[0] < (box.y1 - box.y0) and slot.shape[1] < (box.x1 - box.x0)
    # el centro es mayor que el slot (contiene el arte del disco)
    assert center.size > slot.size


@pytest.mark.skipif(not _FIXTURES, reason="capturas S2 no presentes")
def test_read_tile_slot_lee_discos_conservados():
    """El dígito de slot (hexágono arriba-izq.) solo está en los discos CONSERVADOS (S). Los
    marcados para auto-desmontaje (ícono reciclar, sin dígito) → None. Verifica que el OCR
    binarizado lee los conservados (que el crudo devolvía vacío)."""
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    ocr = PaddleBackend()
    fr = _load(_S2 / "Ejemplo_1.png")
    slots = [read_tile_slot(fr, b, ocr) for b in tile_boxes(fr)]
    # Ejemplo_1: fila 0 conserva discos S en slots 1 y 4; el resto es auto-desmontaje → None.
    assert slots[0] == 1, slots
    assert slots[1] == 4, slots


def test_tile_boxes_frame_vacio():
    assert tile_boxes(np.zeros((1439, 2559, 3), dtype=np.uint8)) == []
    assert tile_boxes(None) == []


def test_tilebox_es_dataclass_con_pixeles():
    b = TileBox(row=0, col=1, x0=10, y0=20, x1=50, y1=80)
    assert (b.row, b.col, b.x0, b.y0, b.x1, b.y1) == (0, 1, 10, 20, 50, 80)
