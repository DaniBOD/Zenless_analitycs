"""Detección del modal "Obtenido" post-desmontaje (S24) y no-regresión de sus vecinos.

## Por qué hace falta un estado nuevo

Medido antes de escribir una línea: los dos frames post-desmontaje caían a **S12 por
`dark_frame_filter`** — no los eclipsaba otro estado, simplemente **ningún template matcheaba**
(tampoco el de S22). Así que hoy el desmontaje se confirma solo si se le da template propio. El
filtro de frame oscuro no lo va a tapar, porque corre únicamente cuando nada matcheó.

## Los dos vecinos peligrosos

1. **S22** también se titula "Obtenido" (drops del farmeo por baterías). No colisionan por
   construcción: `_verify_s22` exige ≥6 franjas de rareza en su viewport y este modal muestra
   2-5 iconos de material centrados. Igual se verifica en ambos sentidos.
2. **S23** (diálogo de sustitución) es el vecino que casi se cruza de verdad: el diálogo de
   confirmación del desmontaje (`Ejemplo_8`) **matchea el template de S23 a 0.699** y solo lo
   salva `_verify_s23` al no encontrar "sustituir" en el texto. Por eso la decisión de diseño es
   **no detectar** ese diálogo: solo aparece cuando la selección incluye grado S (no es una señal
   confiable) y el commit lo da el "Obtenido". `Ejemplo_8` DEBE seguir cayendo a S12.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import (
    NON_CAPTURE_STATES,
    STATE_DESCRIPTIONS,
    THRESHOLD_BY_STATE,
    ScreenDetector,
    _VALID_TRANSITIONS,
)

REPO = Path(__file__).resolve().parents[3]
_TRIG = REPO / "Documentacion" / "Screenshots_Triggers"
_DESM = _TRIG / "Discos_Triggers" / "12_Desmontaje"
_BAT = _TRIG / "Discos_Triggers" / "20_Extraccion_Baterias"
_SUST = _TRIG / "Discos_Triggers" / "15_sustitucion_disco_confirmacion"
_FP = _TRIG / "Triggers_Generales" / "Falsos_positivos"

_POST = ("Ejemplo_5_(Post_demontaje).png", "Ejemplo_7_(Post_demontaje).png")
_GRILLA = ("Ejemplo_1.png", "Ejemplo_2.png", "Ejemplo_3.png", "Ejemplo_4.png", "Ejemplo_6.png")


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def det():
    return ScreenDetector(use_state_machine=False)


# --- Registro -------------------------------------------------------------------------------

def test_s24_esta_registrado_en_el_detector():
    assert "S24" in STATE_DESCRIPTIONS
    assert "S24" in THRESHOLD_BY_STATE
    assert "S24" in NON_CAPTURE_STATES, "el modal no expone un disco parseable"
    assert "S24" in _VALID_TRANSITIONS, "sin transiciones declaradas"
    # El commit viene de S11 (con el diálogo de confirmación cayendo a S12 en el medio).
    assert "S24" in _VALID_TRANSITIONS["S11"]
    assert "S24" in _VALID_TRANSITIONS["S12"]


# --- Lo que S24 debe detectar ---------------------------------------------------------------

@pytest.mark.skipif(not (_DESM / _POST[0]).exists(), reason="capturas no presentes")
@pytest.mark.parametrize("name", _POST, ids=lambda n: n.split("_(")[0])
def test_los_dos_post_desmontaje_dan_s24(name, det):
    st = det.classify(_load(_DESM / name))
    assert st.code == "S24", f"{name}: {st.code} conf={st.confidence:.3f} tmpl={st.template_name}"


# --- No-regresión de los vecinos ------------------------------------------------------------

@pytest.mark.skipif(not (_DESM / "Ejemplo_1.png").exists(), reason="capturas no presentes")
@pytest.mark.parametrize("name", _GRILLA, ids=lambda n: n.replace(".png", ""))
def test_la_grilla_sigue_dando_s11(name, det):
    st = det.classify(_load(_DESM / name))
    assert st.code == "S11", f"{name}: {st.code}"
    assert st.confidence >= 0.96, f"{name}: conf={st.confidence:.3f}"


@pytest.mark.skipif(not (_DESM / "Ejemplo_8_(Confirmacion).png").exists(), reason="captura no presente")
def test_el_dialogo_de_confirmacion_sigue_cayendo_a_s12(det):
    """Regresión EXPLÍCITA de una decisión de diseño, no un bug tolerado. Ese diálogo matchea el
    template de S23 y solo lo rechaza `_verify_s23`; darle estado propio arriesgaría S23 sin
    ganancia, porque solo aparece cuando hay grado S en la selección."""
    st = det.classify(_load(_DESM / "Ejemplo_8_(Confirmacion).png"))
    assert st.code == "S12", f"{st.code} conf={st.confidence:.3f} tmpl={st.template_name}"


@pytest.mark.skipif(not _BAT.exists(), reason="capturas de baterías no presentes")
def test_s22_no_se_confunde_con_s24(det):
    """El "Obtenido" de baterías tiene que seguir siendo S22: es el que SÍ expone discos."""
    fixtures = sorted(_BAT.glob("Resultados_discos*.png"))
    if not fixtures:
        pytest.skip("sin fixtures de S22")
    for p in fixtures:
        st = det.classify(_load(p))
        assert st.code == "S22", f"{p.name}: {st.code}"


@pytest.mark.skipif(not _SUST.exists(), reason="capturas de sustitución no presentes")
def test_s23_sigue_intacto(det):
    fixtures = sorted(_SUST.glob("*.png"))
    if not fixtures:
        pytest.skip("sin fixtures de S23")
    for p in fixtures:
        st = det.classify(_load(p))
        assert st.code == "S23", f"{p.name}: {st.code}"


@pytest.mark.skipif(not _FP.exists(), reason="corpus de negativos no presente")
def test_ningun_negativo_dispara_s24(det):
    """El corpus anti-FP: "Obtenido" es un título genérico de ZZZ (correo, login, pase)."""
    for p in sorted(_FP.glob("*.png")):
        fr = _load(p)
        if fr is None:
            continue
        st = det.classify(fr)
        assert st.code != "S24", f"{p.name} disparó S24 (conf={st.confidence:.3f})"
