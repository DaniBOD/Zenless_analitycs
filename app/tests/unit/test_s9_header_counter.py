"""El contador del header del inventario: `Pistas de disco [339/3000]`.

Es el denominador que el censo de discos tiene y el del roster no. Misma doctrina que el `N/300`
del desmontaje: **el contador es la autoridad del conteo** y lo que se ve en la grilla sólo sirve
para aparear, porque el viewport no ve todo el inventario.

Y la misma regla dura: `None` significa **"no se pudo leer"**, jamás "cero". Quien lo consuma debe
declarar el total desconocido, no sustituirlo por lo que alcanzó a contar.

El `3000` se exige como ANCLA. Sin él, cualquier par de números de cualquier pantalla se leería
como un inventario.
"""
from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")

REPO = Path(__file__).resolve().parents[3]
_S9 = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general"
_FIXTURES = [f"Ejemplo_{i}" for i in range(1, 15)]


def _ocr():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except ImportError:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@pytest.fixture(scope="module")
def ocr():
    return _ocr()


def _frame(stem: str):
    p = _S9 / f"{stem}.png"
    if not p.exists():
        pytest.skip(f"falta {p.name}")
    return cv2.imread(str(p))


# --- el texto → número ------------------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("Pistas de disco [339/3000]", 339),
    ("Pistas de disco[339/3000]", 339),          # sin espacio: sale así en la mitad de los frames
    ("Pistas de disco [ 7 / 3000 ]", 7),
    ("Pistas de disco [3000/3000]", 3000),       # inventario lleno
])
def test_extrae_el_numerador(texto, esperado):
    from app.core.parser_disc_s17 import _s9_counter_from_text
    assert _s9_counter_from_text(texto) == esperado


@pytest.mark.parametrize("texto", [
    "",
    "Pistas de disco",
    "339",                                        # sin ancla: podría ser cualquier cosa
    "Pistas de disco [339/300]",                  # ese es el contador del DESMONTAJE, no éste
    "237/240",                                    # la batería del header superior
])
def test_sin_ancla_no_afirma_nada(texto):
    from app.core.parser_disc_s17 import _s9_counter_from_text
    assert _s9_counter_from_text(texto) is None


def test_un_numerador_mayor_que_la_capacidad_se_rechaza():
    """3001 de 3000 no existe; aceptarlo sería preferir un número roto a no tener número."""
    from app.core.parser_disc_s17 import _s9_counter_from_text
    assert _s9_counter_from_text("Pistas de disco [3001/3000]") is None


# --- contra las capturas reales ---------------------------------------------------------------

@pytest.mark.parametrize("stem", _FIXTURES)
def test_lee_el_contador_de_cada_captura(stem, ocr):
    """Las 14 capturas son de la misma cuenta y el mismo momento: el contador tiene que dar 339 en
    todas. Un fixture que difiera señalaría una ROI que se corre, no un inventario distinto."""
    from app.core.parser_disc_s17 import parse_s9_header_counter
    assert parse_s9_header_counter(_frame(stem), ocr) == 339


def test_un_frame_vacio_devuelve_None_y_no_explota(ocr):
    import numpy as np

    from app.core.parser_disc_s17 import parse_s9_header_counter
    assert parse_s9_header_counter(None, ocr) is None
    assert parse_s9_header_counter(np.zeros((0, 0, 3), np.uint8), ocr) is None


def test_una_pantalla_que_NO_es_el_inventario_no_da_contador(ocr):
    """El ancla `/3000` es lo que evita que el censo se ancle a un número de otra pantalla."""
    from app.core.parser_disc_s17 import parse_s9_header_counter
    otra = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/12_Desmontaje"
    cands = sorted(otra.glob("*.png")) if otra.exists() else []
    if not cands:
        pytest.skip("sin capturas de otra pantalla para el negativo")
    assert parse_s9_header_counter(cv2.imread(str(cands[0])), ocr) is None
