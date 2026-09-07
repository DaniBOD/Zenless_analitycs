"""El contador `N/M` del header de la mochila, compartido por los dos inventarios.

`Pistas de disco [339/3000]` (S9) y `Amplificadores [57/2000]` (S30) son **la misma línea de la
misma pantalla**, en la misma posición. Lo único que cambia es el rótulo —que no se usa— y la
capacidad, que es el ANCLA.

Los tests del lado de discos siguen viviendo en `test_s9_header_counter.py`: la delegación tiene
que dejarlos intactos, y que sigan verdes es parte de lo que se verifica acá.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_inventory_header import (
    CAPACIDAD_ARMAS,
    CAPACIDAD_DISCOS,
    counter_from_text,
    parse_inventory_counter,
)

_ROOT = Path(__file__).resolve().parents[3]
_ARMAS = (_ROOT / "Documentacion" / "Screenshots_Triggers" / "Engines_Triggers"
          / "Inventario_general_engines")


# --- el texto ----------------------------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("Amplificadores [57/2000]", 57),
    ("Amplificadores[54/2000]", 54),          # sin espacio: pasa seguido en el OCR real
    ("Amoplificadores [57/2000]", 57),        # el rótulo mal leído NO importa: no es el ancla
    ("[0/2000]", 0),
    ("2000/2000", 2000),
])
def test_lee_el_contador_de_armas(texto, esperado):
    assert counter_from_text(texto, CAPACIDAD_ARMAS) == esperado


@pytest.mark.parametrize("texto", [
    "",
    "Amplificadores",
    "237/240",           # la batería del header superior
    "339/300",           # el contador del desmontaje
    "2001/2000",         # imposible: mayor que la capacidad
])
def test_no_lee_lo_que_no_es_el_contador_de_armas(texto):
    assert counter_from_text(texto, CAPACIDAD_ARMAS) is None


def test_la_capacidad_impide_que_una_pantalla_se_haga_pasar_por_la_otra():
    """⚠️ La razón de que el ancla sea la capacidad y no el rótulo.

    Si el contador de armas se leyera con la capacidad de discos —o al revés— una pasada de censo
    anclaría su total en el inventario equivocado y la cobertura sería un número sin sentido, sin
    que nada avisara.
    """
    armas = "Amplificadores [57/2000]"
    discos = "Pistas de disco [339/3000]"
    assert counter_from_text(armas, CAPACIDAD_ARMAS) == 57
    assert counter_from_text(armas, CAPACIDAD_DISCOS) is None
    assert counter_from_text(discos, CAPACIDAD_DISCOS) == 339
    assert counter_from_text(discos, CAPACIDAD_ARMAS) is None


# --- el frame ----------------------------------------------------------------------------------

def _ocr_or_skip():
    try:
        from app.core.ocr_paddle import PaddleBackend
        return PaddleBackend()
    except Exception:
        pytest.skip("PaddleOCR no disponible")


def _frames_armas() -> list[Path]:
    return sorted(_ARMAS.glob("Ejemplo_*.png")) if _ARMAS.exists() else []


@pytest.mark.skipif(not _frames_armas(), reason="capturas del inventario de armas no presentes")
def test_lee_el_contador_en_las_capturas_reales_del_inventario_de_armas():
    """La ROI está calibrada sobre el header de DISCOS. Que contenga también el de armas no se
    puede suponer: se midió. 10 de 10, con dos valores distintos (57 y 54) porque las capturas son
    de sesiones distintas y el inventario se movió entre medio."""
    ocr = _ocr_or_skip()
    leidos = []
    for p in _frames_armas():
        frame = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
        leidos.append(parse_inventory_counter(frame, ocr, CAPACIDAD_ARMAS))
    assert all(n is not None for n in leidos), f"alguna captura no se leyó: {leidos}"
    assert set(leidos) == {57, 54}, f"valores inesperados: {sorted(set(leidos))}"


@pytest.mark.skipif(not _frames_armas(), reason="capturas del inventario de armas no presentes")
def test_el_inventario_de_armas_no_se_lee_como_uno_de_discos():
    """La misma guarda que arriba, pero contra el frame real y no contra un string."""
    ocr = _ocr_or_skip()
    frame = cv2.imdecode(np.fromfile(str(_frames_armas()[0]), np.uint8), cv2.IMREAD_COLOR)
    assert parse_inventory_counter(frame, ocr, CAPACIDAD_ARMAS) is not None
    assert parse_inventory_counter(frame, ocr, CAPACIDAD_DISCOS) is None


def test_un_frame_vacio_no_revienta():
    ocr = _ocr_or_skip()
    assert parse_inventory_counter(None, ocr, CAPACIDAD_ARMAS) is None
    assert parse_inventory_counter(np.zeros((0, 0, 3), np.uint8), ocr, CAPACIDAD_ARMAS) is None
