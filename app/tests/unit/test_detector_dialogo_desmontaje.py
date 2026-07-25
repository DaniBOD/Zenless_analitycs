"""Detección del diálogo de confirmación del desmontaje (S25).

## Por qué existe, si antes decidimos NO detectarlo

La decisión original (documentada en `test_detector_desmontaje`) fue dejar este diálogo cayendo a
S12: solo aparece cuando la selección incluye grado S, así que no sirve como disparador del
commit. **Eso sigue siendo cierto y S25 NO commitea nada.**

Lo que cambió lo trajo el QA en vivo del 2026-07-25: el diálogo **tapa el header**, y ahí el
contador `N/300` —la única autoridad del conteo— se vuelve ilegible. El log lo mostró tal cual
(`no se pudo leer el contador`). Atravesar ese tramo a ciegas es justamente lo que no queremos:
detectarlo permite **congelar el conteo declarado** en el último valor bueno y decirle al usuario
que el sistema lo sigue viendo.

## Lo medido (no asumido)

El template de S23 es la fila genérica "Cancelar/Confirmar" de ZZZ, y matchea este diálogo a
**0.996** (frame en vivo 2560×1440) y **0.998** (fixture). El `0.699` que decía el comentario
viejo era la confianza que reportaba el estado ya degradado a S12, no el score del template.

Por eso S25 **comparte el template de S23** y se distingue por el verify de texto, igual que S23.

## El riesgo que esto introduce, y cómo se contiene

Dos estados sobre el mismo template significa que un verify demasiado permisivo puede robarle la
pantalla al otro — y S23 **escribe la DB** (mueve un disco de PJ), mientras S25 es display-only.
Por eso `_verify_s25` **falla cerrado** si no hay OCR, al revés que `_verify_s23`. Sin Tesseract
(el caso del .exe distribuido) S25 simplemente no existe y S23 queda como estaba.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core import detector as det_mod
from app.core.detector import (
    NON_CAPTURE_STATES,
    STATE_DESCRIPTIONS,
    THRESHOLD_BY_STATE,
    ScreenDetector,
    _VALID_TRANSITIONS,
    _verify_s25,
)

REPO = Path(__file__).resolve().parents[3]
_TRIG = REPO / "Documentacion" / "Screenshots_Triggers"
_DESM = _TRIG / "Discos_Triggers" / "12_Desmontaje"
_SUST = _TRIG / "Discos_Triggers" / "15_sustitucion_disco_confirmacion"
_FP = _TRIG / "Triggers_Generales" / "Falsos_positivos"

# Dos muestras INDEPENDIENTES del mismo diálogo: el fixture original y un frame cosechado en vivo
# durante el QA del 2026-07-25 (misma pantalla, otra sesión, otro contenido detrás del blur).
_DIALOGOS = ("Ejemplo_8_(Confirmacion).png", "Ejemplo_9_(Confirmacion_2560).png")


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def det():
    return ScreenDetector(use_state_machine=False)


# --- Registro -------------------------------------------------------------------------------

def test_s25_esta_registrado():
    assert "S25" in STATE_DESCRIPTIONS
    assert "S25" in THRESHOLD_BY_STATE
    assert "S25" in NON_CAPTURE_STATES, "un diálogo no expone disco parseable"
    assert "S25" in _VALID_TRANSITIONS, "sin transiciones declaradas"


def test_s25_se_alcanza_desde_la_grilla_y_lleva_al_obtenido():
    """El camino real: S11 → S25 → S24. Cancelar vuelve a S11."""
    assert "S25" in _VALID_TRANSITIONS["S11"]
    assert "S24" in _VALID_TRANSITIONS["S25"]
    assert "S11" in _VALID_TRANSITIONS["S25"]


# --- Lo que S25 debe detectar ------------------------------------------------------------------

@pytest.mark.skipif(not (_DESM / _DIALOGOS[0]).exists(), reason="capturas no presentes")
@pytest.mark.parametrize("name", _DIALOGOS, ids=lambda n: n.split("_(")[1].rstrip(").png"))
def test_el_dialogo_de_grado_s_da_s25(name, det):
    p = _DESM / name
    if not p.exists():
        pytest.skip(f"{name} no presente")
    st = det.classify(_load(p))
    assert st.code == "S25", f"{name}: {st.code} conf={st.confidence:.3f} tmpl={st.template_name}"


# --- Que no le robe la pantalla a S23 (que SÍ escribe la DB) ----------------------------------

@pytest.mark.skipif(not _SUST.exists(), reason="capturas de sustitución no presentes")
def test_s23_no_queda_tapado_por_s25(det):
    """El riesgo estructural de compartir template. S23 mueve un disco entre PJs: si S25 se lo
    come, el usuario pierde un WRITE que sí quería."""
    fixtures = sorted(_SUST.glob("*.png"))
    if not fixtures:
        pytest.skip("sin fixtures de S23")
    for p in fixtures:
        st = det.classify(_load(p))
        assert st.code == "S23", f"{p.name}: {st.code} tmpl={st.template_name}"


@pytest.mark.skipif(not _SUST.exists(), reason="capturas de sustitución no presentes")
def test_verify_s25_rechaza_el_dialogo_de_sustitucion():
    fixtures = sorted(_SUST.glob("*.png"))
    if not fixtures:
        pytest.skip("sin fixtures de S23")
    for p in fixtures:
        ok, _ = _verify_s25(_load(p))
        assert ok is False, f"{p.name}: _verify_s25 lo aceptó"


def test_verify_s25_falla_cerrado_sin_ocr(monkeypatch):
    """Al revés que `_verify_s23`. Sin OCR no se puede distinguir un diálogo del otro, y ante la
    duda gana el que tiene consecuencias reales (S23)."""
    monkeypatch.setattr(det_mod, "_get_dialog_verify_ocr", lambda: None)
    p = _DESM / _DIALOGOS[0]
    if not p.exists():
        pytest.skip("fixture no presente")
    ok, detalle = _verify_s25(_load(p))
    assert ok is False
    assert detalle and "ocr" in detalle.lower()


# --- No-regresión del resto del flujo ---------------------------------------------------------

@pytest.mark.skipif(not (_DESM / "Ejemplo_1.png").exists(), reason="capturas no presentes")
@pytest.mark.parametrize("name", ("Ejemplo_1.png", "Ejemplo_3.png", "Ejemplo_6.png"))
def test_la_grilla_no_dispara_s25(name, det):
    st = det.classify(_load(_DESM / name))
    assert st.code == "S11", f"{name}: {st.code}"


@pytest.mark.skipif(not (_DESM / "Ejemplo_5_(Post_demontaje).png").exists(), reason="no presente")
@pytest.mark.parametrize("name", ("Ejemplo_5_(Post_demontaje).png", "Ejemplo_7_(Post_demontaje).png"))
def test_el_obtenido_sigue_siendo_s24(name, det):
    st = det.classify(_load(_DESM / name))
    assert st.code == "S24", f"{name}: {st.code}"


@pytest.mark.skipif(not _FP.exists(), reason="corpus de negativos no presente")
def test_ningun_negativo_dispara_s25(det):
    for p in sorted(_FP.glob("*.png")):
        fr = _load(p)
        if fr is None:
            continue
        st = det.classify(fr)
        assert st.code != "S25", f"{p.name} disparó S25 (conf={st.confidence:.3f})"
