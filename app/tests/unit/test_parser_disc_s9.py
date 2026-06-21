"""Parser del disco SELECCIONADO en el INVENTARIO GLOBAL S9 (`parse_disc_s9`).

Reusa el parser espacial de S17 con el layout del panel derecho (`_S9_LAYOUT`). Los
tests corren OCR real (PaddleOCR) sobre las 6 capturas de
`09_Inventario_discos_general`; se saltean si Paddle o las capturas no están.
Validan el núcleo "replicar la captura de S17 en S9": set + slot + main + 4 substats.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_S9 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "09_Inventario_discos_general"

# (set substring esperado, slot, main canon, main valor) por ejemplo. Verificado
# contra las capturas reales (QA 2026-06-21). Los 5 maxeados; Ejemplo_6 es un disco
# de bajo nivel (3 substats) → no se asevera "4 substats".
_EXPECT = {
    "Ejemplo_1": ("conejo",  2, "ATK",  316.0),
    "Ejemplo_2": ("monarca", 3, "DEF",  184.0),
    "Ejemplo_3": ("faeton",  5, "ATK%",  30.0),
    "Ejemplo_4": ("vozastral", 2, "ATK", 316.0),
    "Ejemplo_5": ("punk",    6, "ATK%",  30.0),
}


def _norm(s: str) -> str:
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return "".join(c for c in s.lower() if c.isalnum())


@pytest.fixture(scope="module")
def _ocr():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
@pytest.mark.parametrize("name,expect", list(_EXPECT.items()))
def test_parse_disc_s9_frames_reales(name, expect, _ocr):
    from app.core.parser_disc_s17 import parse_disc_s9
    from app.core.detector import extract_s9_slot
    set_sub, slot, main_canon, main_val = expect
    fr = cv2.imdecode(np.fromfile(str(_S9 / f"{name}.png"), np.uint8), cv2.IMREAD_COLOR)
    d = parse_disc_s9(fr, _ocr, slot=extract_s9_slot(fr, _ocr))
    assert d.slot == slot, f"{name}: slot {d.slot} != {slot}"
    assert d.main_stat_canon == main_canon, f"{name}: main {d.main_stat_canon} != {main_canon}"
    assert d.main_valor == main_val, f"{name}: main_valor {d.main_valor} != {main_val}"
    assert len([s for s in d.subs if s.valor is not None]) == 4, f"{name}: substats {d.subs}"
    assert set_sub in _norm(d.set_name_raw), f"{name}: set {d.set_name_raw!r} sin '{set_sub}'"


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_parse_disc_s9_no_substats_fantasma(_ocr):
    """El header 'Efecto de conjunto' (que en S9 se OCR-ea como basura) NO debe
    generar un 5º substat: el cap a 4 lo evita."""
    from app.core.parser_disc_s17 import parse_disc_s9
    from app.core.detector import extract_s9_slot
    fr = cv2.imdecode(np.fromfile(str(_S9 / "Ejemplo_1.png"), np.uint8), cv2.IMREAD_COLOR)
    d = parse_disc_s9(fr, _ocr, slot=extract_s9_slot(fr, _ocr))
    assert len(d.subs) <= 4
