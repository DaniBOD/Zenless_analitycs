"""Parser del diálogo de sustitución de disco entre PJs (S23), `parse_sustitucion`.

Devuelve los campos CRUDOS (origen/set/slot) del texto "{PJ} equipa actualmente {Set} ({slot})";
la resolución a IDs la hace el monitor. OCR REAL con PaddleOCR (el backend de la app): Tesseract
vía `text_with_bboxes` no devuelve cajas usables sobre esta banda, y la app corre Paddle.

Ground-truth de los 7 fixtures (leído de los screenshots):
    E1 Yixuan / Balada de la rama y la espada / 2   E2 Jane / Jazz caótico / 2
    E3 Billy / Voz astral / 2                        E4 Dialyn / Tecno pícido / 2
    E5 Sporos / Floración del alba / 6               E6 Ellen / Balada de la rama y la espada / 6
    E7 Grace / Jazz caótico / 4
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core import parser_sustitucion as ps

_FX = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
       / "Discos_Triggers" / "15_sustitucion_disco_confirmacion")

# (archivo): (substring esperado del set crudo, slot). El origen se valida aparte (no-vacío).
_TRUTH = {
    "Ejemplo_1.png": ("rama", 2),
    "Ejemplo_2.png": ("jazz", 2),
    "Ejemplo_3.png": ("astral", 2),
    "Ejemplo_4.png": ("tecno", 2),
    "Ejemplo_5.png": ("floraci", 6),
    "Ejemplo_6.png": ("rama", 6),
    "Ejemplo_7.png": ("jazz", 4),
}


def _load(name: str) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(_FX / name), np.uint8), cv2.IMREAD_COLOR)


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@pytest.mark.skipif(not _FX.exists(), reason="capturas S23 no presentes")
@pytest.mark.parametrize("name", sorted(_TRUTH))
def test_parsea_origen_set_y_slot(name):
    if not (_FX / name).exists():
        pytest.skip(f"falta {name}")
    set_sub, slot = _TRUTH[name]
    d = ps.parse_sustitucion(_load(name), _paddle())
    assert d is not None, f"{name}: no parseó"
    assert d.slot == slot, f"{name}: slot {d.slot} != {slot}"
    assert set_sub in d.set_raw.lower(), f"{name}: set {d.set_raw!r} no contiene {set_sub!r}"
    assert d.origin_raw.strip(), f"{name}: origen vacío"


def test_regex_arma_origen_set_slot():
    """El regex separa PJ / set / slot y tolera el '(' comido por el OCR (deja '2)')."""
    m = ps._RE_SUSTITUCION.search("Yixuan equipa actualmente Balada de la rama y la espada (2)")
    assert m and m.group("pj") == "Yixuan" and m.group("slot") == "2"
    assert "rama" in m.group("set").lower()
    # PJ con espacio + "(" comido por el OCR
    m2 = ps._RE_SUSTITUCION.search("Nangong Yu equipa actualmente Tecno pícido 2)")
    assert m2 and m2.group("pj") == "Nangong Yu" and m2.group("slot") == "2"


def test_texto_sin_patron_no_inventa():
    """Otro diálogo Cancelar/Confirmar sin 'equipa actualmente' → None (RNF-02)."""
    assert ps._RE_SUSTITUCION.search("¿Deseas descartar este disco?") is None


def test_none_sin_frame():
    assert ps.parse_sustitucion(None, object()) is None
