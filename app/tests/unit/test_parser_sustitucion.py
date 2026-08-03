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


class _OcrFijo:
    """OCR de mentira que devuelve un texto dado (una sola caja), para testear el parseo puro."""
    def __init__(self, texto):
        self._t = texto

    def text_with_bboxes(self, _crop):
        return [(self._t, 0.94, (0, 0, 100, 20))]


def test_rescata_el_slot_cuando_el_ocr_lee_1_como_i():
    """REGRESIÓN QA en vivo 2026-07-20: PaddleOCR leyó '(1)' como '(i)' y el parser devolvía
    None → sin pending S23, sin toast, y en silencio. El rescate lo recupera como slot 1."""
    import numpy as np
    real = "Jane equipa actualmente Salón huracanado (i). cDeseas sustituirlo?"
    d = ps.parse_sustitucion(np.zeros((1439, 2559, 3), dtype=np.uint8), _OcrFijo(real))
    assert d is not None, "el rescate no recuperó el slot"
    assert d.slot == 1 and d.origin_raw == "Jane"
    assert "huracanado" in d.set_raw.lower()


def test_el_rescate_exige_parentesis_para_no_comerse_el_set():
    """Sin '(' el rescate NO corre: si no, la última letra del nombre del set podría colarse
    como slot (p.ej. '...pícidos)' → slot 5). RNF-02: antes None que inventar."""
    import numpy as np
    txt = "Yixuan equipa actualmente Tecno pícidos)"     # 's' final, sin paréntesis de apertura
    assert ps.parse_sustitucion(np.zeros((10, 10, 3), dtype=np.uint8), _OcrFijo(txt)) is None


def test_texto_sin_patron_no_inventa():
    """Otro diálogo Cancelar/Confirmar sin 'equipa actualmente' → None (RNF-02)."""
    assert ps._RE_SUSTITUCION.search("¿Deseas descartar este disco?") is None


def test_none_sin_frame():
    assert ps.parse_sustitucion(None, object()) is None


# --- El gemelo del arma (S29) -----------------------------------------------------------------
# Mismo diálogo, sin sufijo de slot. Es DISPLAY-ONLY: no arma pending ni escribe nada; existe
# para que el log del estado nuevo diga PJ + arma, que el juego imprime en texto plano y es la
# única verdad de tierra del dueño que no depende de la librería de badges.

_ARMA_FX = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
            / "Engines_Triggers" / "Reemplazo_engine")

_TRUTH_ARMA = {
    "Ejemplo_1.png": ("Ben", "cilindro"),
    "Ejemplo_2.png": ("Zhu Yuan", "rotor"),
    "Ejemplo_3.png": ("Billy Estelar", "herciano"),
    "Ejemplo_4.png": ("César", "celuloide"),
}


@pytest.mark.skipif(not _ARMA_FX.exists(), reason="capturas del reemplazo de arma no presentes")
@pytest.mark.parametrize("name", sorted(_TRUTH_ARMA))
def test_parsea_origen_y_arma(name):
    p = _ARMA_FX / name
    if not p.exists():
        pytest.skip(f"falta {name}")
    pj_sub, arma_sub = _TRUTH_ARMA[name]
    frame = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    d = ps.parse_sustitucion_arma(frame, _paddle())
    assert d is not None, f"{name}: no parseó"
    assert arma_sub in d.weapon_raw.lower(), f"{name}: arma {d.weapon_raw!r}"
    assert pj_sub.split()[0].lower() in d.origin_raw.lower(), f"{name}: origen {d.origin_raw!r}"


def test_el_parser_de_arma_se_abstiene_ante_un_dialogo_de_disco():
    """Si un frame de disco llega acá es porque el ruteo falló. Leerlo como arma taparía el
    problema; abstenerse lo deja visible (RNF-02)."""
    import numpy as np
    txt = "Yixuan equipa actualmente Balada de la rama y la espada (2). ¿Deseas sustituirlo?"
    assert ps.parse_sustitucion_arma(np.zeros((10, 10, 3), dtype=np.uint8), _OcrFijo(txt)) is None


def test_el_parser_de_arma_tolera_el_eguipa_de_paddle():
    """PaddleOCR lee "eguipa" en 2 de los 4 fixtures (confusión q↔g). Sin esta tolerancia el
    estado quedaba mudo la mitad de las veces."""
    import numpy as np
    txt = "Zhu Yuan eguipa actualmente Rotor de cañón. Deseas sustituirlo?"
    d = ps.parse_sustitucion_arma(np.zeros((10, 10, 3), dtype=np.uint8), _OcrFijo(txt))
    assert d is not None and d.origin_raw == "Zhu Yuan"
    assert d.weapon_raw == "Rotor de cañón"


def test_el_parser_de_arma_no_se_come_la_pregunta():
    """El punto que abre '¿Deseas sustituirlo?' es el ancla de cierre del nombre. Sin él, el
    `.+?` lazy se llevaría la pregunta entera adentro del nombre del arma."""
    import numpy as np
    txt = "Ben equipa actualmente Cilindro neumático de Bigger. ¿Deseas sustituirlo?"
    d = ps.parse_sustitucion_arma(np.zeros((10, 10, 3), dtype=np.uint8), _OcrFijo(txt))
    assert d is not None
    assert d.weapon_raw == "Cilindro neumático de Bigger"
    assert d.origin_raw == "Ben"


def test_parser_de_arma_none_sin_frame():
    assert ps.parse_sustitucion_arma(None, object()) is None
