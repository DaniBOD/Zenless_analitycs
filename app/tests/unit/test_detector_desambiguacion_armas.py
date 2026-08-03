"""Las pantallas de W-Engine dejan de hacerse pasar por pantallas de disco (S29 + blindaje S9).

Hasta este hito, dos pantallas del flujo de armas caían en estados de disco:

| pantalla                  | caía en | conf        | verificación |
|---------------------------|---------|-------------|--------------|
| diálogo de reemplazo      | **S23** | 0.999       | pasaba       |
| inventario de amplificad. | **S9**  | 0.855-0.864 | *ninguna*    |

El primero ya tenía consecuencia visible: `parse_sustitucion` se abstenía —lo correcto, un arma
no tiene slot— y el monitor volcaba un PNG a `audit/s23_parse_fallo/` por cada reemplazo. Ese
volcado existe para investigar diálogos de disco que *deberían* parsear, así que la basura además
disfrazaba los fallos reales (QA 2026-07-30).

El segundo todavía no rompía nada porque el handler de S9 nunca se cableó. Ese es exactamente el
motivo de blindarlo ahora: el día que se cablee, el pipeline de DISCOS estaría parseando armas y
nada avisaría.

## Lo medido

El discriminante del diálogo es el **sufijo de slot**, que el juego imprime para un disco y no
para un arma. Con Tesseract sobre los fixtures: 7/7 discos con `(N)`, 4/4 armas sin él.

    disco → "Yixuan equipa actualmente Balada de la rama y la espada (2). ¿Deseas sustituirlo?"
    arma  → "Ben equipa actualmente Cilindro neumático de Bigger. ¿Deseas sustituirlo?"

El del inventario es el **título**: "Pistas de disco [339/3000]" vs "Amplificadores [57/2000]".
Ojo con el ancla: el OCR nunca lee "Amplificadores" limpio, y lo rompe de dos formas distintas
("Amoplificadores" ×4, "Amolificadores" ×2), así que ni "Ampl" ni la "p" sirven. El primer intento
de este hito ancló en `plificador` y falló 2 de 6 — la cola `lificador` es lo que sobrevive.

## El riesgo de compartir template, y cómo se contiene

Igual que con S23/S25: `_verify_s29` **falla cerrado** sin OCR. De los dos diálogos, el que tiene
consecuencias reales es S23 —mueve un disco entre PJs y escribe la DB—, así que sin Tesseract S29
no existe y S23 queda exactamente como estaba (RNF-01/02).

Y exigirle el slot a `_verify_s23` **no abre un modo de fallo nuevo**: un frame de disco cuyo
"(N)" el OCR arruine ya hoy cae en S23, el parser se abstiene y el swap no ocurre. Con el cambio
cae en S29 y el swap tampoco ocurre. Cambia la etiqueta, no el desenlace — y eso está fijado abajo
como test.

Los fixtures de `Engines_Triggers/` son locales (gitignoreados, ~150 MB) ⇒ skip-if-absent.
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
    _verify_s9,
    _verify_s23,
    _verify_s29,
    polling_cadence_ms,
    ScreenState,
)

_ROOT = Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
_ENG = _ROOT / "Engines_Triggers"
_DISC = _ROOT / "Discos_Triggers"

_ARMA_DIALOGO = sorted((_ENG / "Reemplazo_engine").glob("Ejemplo_*.png"))
_ARMA_INVENTARIO = sorted((_ENG / "Inventario_general_engines").glob("Ejemplo_*.png"))
_DISCO_DIALOGO = sorted((_DISC / "15_sustitucion_disco_confirmacion").glob("Ejemplo_*.png"))
_DISCO_INVENTARIO = sorted((_DISC / "09_Inventario_discos_general").glob("Ejemplo_*.png"))
_FP = _ROOT / "Triggers_Generales" / "Falsos_positivos"


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def det():
    return ScreenDetector(use_state_machine=False)


# --- Registro ---------------------------------------------------------------------------------

def test_s29_esta_registrado():
    assert "S29" in STATE_DESCRIPTIONS
    assert "S29" in THRESHOLD_BY_STATE
    assert "S29" in NON_CAPTURE_STATES, "un diálogo no expone disco parseable"
    assert "S29" in _VALID_TRANSITIONS, "sin transiciones declaradas"
    assert "S29" in det_mod._VERIFICATION_REGISTRY, "sin verify → el template genérico sería un FP"
    assert polling_cadence_ms(ScreenState("S29", 1.0, "")) > 0


def test_s29_se_alcanza_desde_el_flujo_de_equipamiento():
    """El diálogo se abre desde la grilla de selección de arma (que cae a S12) o desde S26."""
    assert "S29" in _VALID_TRANSITIONS["S26"]
    assert "S29" in _VALID_TRANSITIONS["S12"]
    assert "S26" in _VALID_TRANSITIONS["S29"]


def test_s9_ahora_tiene_verificacion():
    """Antes de este hito S9 no tenía ninguna: cualquier grilla parecida entraba."""
    assert "S9" in det_mod._VERIFICATION_REGISTRY


# --- El diálogo del arma ya no es S23 ----------------------------------------------------------

@pytest.mark.skipif(not _ARMA_DIALOGO, reason="capturas del reemplazo de arma no presentes")
@pytest.mark.parametrize("fx", _ARMA_DIALOGO, ids=lambda p: p.stem)
def test_el_dialogo_de_arma_da_s29(fx, det):
    st = det.classify(_load(fx))
    assert st.code == "S29", f"{fx.name}: {st.code} conf={st.confidence:.3f}"


@pytest.mark.skipif(not _ARMA_DIALOGO, reason="capturas del reemplazo de arma no presentes")
@pytest.mark.parametrize("fx", _ARMA_DIALOGO, ids=lambda p: p.stem)
def test_verify_s23_rechaza_el_dialogo_de_arma(fx):
    """El corazón del hito: es lo que corta el volcado de PNGs de `audit/s23_parse_fallo/`."""
    ok, detalle = _verify_s23(_load(fx))
    assert ok is False, f"{fx.name}: _verify_s23 lo aceptó"
    assert detalle == "txt=sin-slot"


# --- ...y el de disco sigue siendo S23 (el que ESCRIBE la DB) ----------------------------------

@pytest.mark.skipif(not _DISCO_DIALOGO, reason="capturas del swap de disco no presentes")
@pytest.mark.parametrize("fx", _DISCO_DIALOGO, ids=lambda p: p.stem)
def test_el_dialogo_de_disco_sigue_dando_s23(fx, det):
    """No-regresión del único de los tres diálogos que tiene consecuencias reales."""
    st = det.classify(_load(fx))
    assert st.code == "S23", f"{fx.name}: {st.code} conf={st.confidence:.3f}"


@pytest.mark.skipif(not _DISCO_DIALOGO, reason="capturas del swap de disco no presentes")
@pytest.mark.parametrize("fx", _DISCO_DIALOGO, ids=lambda p: p.stem)
def test_verify_s29_rechaza_el_dialogo_de_disco(fx):
    ok, detalle = _verify_s29(_load(fx))
    assert ok is False, f"{fx.name}: _verify_s29 se robó un swap de disco"
    assert detalle == "txt=con-slot"


def test_verify_s29_falla_cerrado_sin_ocr(monkeypatch):
    """Mismo criterio que `_verify_s25`: sin OCR no se pueden separar los dos diálogos, y ante la
    duda gana el que hace algo (S23 escribe la DB)."""
    if not _ARMA_DIALOGO:
        pytest.skip("capturas del reemplazo de arma no presentes")
    monkeypatch.setattr(det_mod, "_get_dialog_verify_ocr", lambda: None)
    ok, detalle = _verify_s29(_load(_ARMA_DIALOGO[0]))
    assert ok is False
    assert detalle and "ocr" in detalle.lower()


def test_verify_s23_sigue_fallando_abierto_sin_ocr(monkeypatch):
    """La contracara: sin Tesseract, S23 queda exactamente como estaba antes del hito."""
    if not _DISCO_DIALOGO:
        pytest.skip("capturas del swap de disco no presentes")
    monkeypatch.setattr(det_mod, "_get_dialog_verify_ocr", lambda: None)
    ok, _ = _verify_s23(_load(_DISCO_DIALOGO[0]))
    assert ok is True


# --- El slot como discriminante ---------------------------------------------------------------

@pytest.mark.parametrize(
    "texto, es_disco",
    [
        ("Yixuan equipa actualmente Balada de la rama y la espada (2). ¿Deseas sustituirlo?", True),
        ("Grace equipa actualmente Jazz caótico (4). ¿Deseas sustituirlo?", True),
        # El "(" que el OCR se come: `parser_sustitucion` lo tolera, así que el ruteo también.
        ("Sporos equipa actualmente Floración del alba 6). ¿Deseas sustituirlo?", True),
        # Alias de dígito de la variante laxa (visto en vivo 2026-07-20: "(1)" leído "(i)").
        ("Ellen equipa actualmente Salón huracanado (i). ¿Deseas sustituirlo?", True),
        ("Ben equipa actualmente Cilindro neumático de Bigger. ¿Deseas sustituirlo?", False),
        ("Zhu Yuan equipa actualmente Rotor de cañón. ¿Deseas sustituirlo?", False),
    ],
)
def test_el_sufijo_de_slot_separa_disco_de_arma(texto, es_disco):
    """El criterio de ruteo tiene que aceptar TODO lo que `parser_sustitucion` sabe leer: si el
    parser puede sacar un slot de ahí, es un disco y el frame le pertenece a S23. Los dos casos
    tolerantes (paréntesis comido, dígito confundido con letra) están ahí porque ya pasaron en
    vivo, no por hipótesis."""
    assert bool(det_mod._RE_S23_SLOT.search(texto)) is es_disco


# --- El inventario de amplificadores deja de ser S9 --------------------------------------------

@pytest.mark.skipif(not _ARMA_INVENTARIO, reason="capturas del inventario de armas no presentes")
@pytest.mark.parametrize("fx", _ARMA_INVENTARIO, ids=lambda p: p.stem)
def test_el_inventario_de_armas_no_da_s9(fx, det):
    """Todavía no tiene estado propio (eso es el tramo siguiente); lo que importa acá es que no se
    haga pasar por el inventario de DISCOS."""
    st = det.classify(_load(fx))
    assert st.code != "S9", f"{fx.name}: sigue cayendo en S9 (conf={st.confidence:.3f})"


@pytest.mark.skipif(not _ARMA_INVENTARIO, reason="capturas del inventario de armas no presentes")
@pytest.mark.parametrize("fx", _ARMA_INVENTARIO, ids=lambda p: p.stem)
def test_verify_s9_rechaza_el_inventario_de_armas(fx):
    ok, detalle = _verify_s9(_load(fx))
    assert ok is False, f"{fx.name}: _verify_s9 lo aceptó"
    assert detalle == "txt=amplificadores"


@pytest.mark.parametrize(
    "texto, es_arma",
    [
        # Las 3 lecturas REALES de Tesseract sobre los 6 fixtures, tal cual salieron.
        ("Amoplificadores [57/2000]1", True),
        ("Amolificadores [57/2000]", True),
        ("Amplificadores [57/2000]", True),
        ("Pistas de disco [ 339 /30001", False),
    ],
)
def test_el_ancla_del_titulo_sobrevive_al_ocr(texto, es_arma):
    """El ancla se fija con las lecturas crudas y no con la palabra ideal, porque el ideal es
    justamente lo que el OCR nunca devuelve."""
    assert bool(det_mod._RE_S9_ARMAS.search(texto)) is es_arma


@pytest.mark.skipif(not _DISCO_INVENTARIO, reason="capturas del inventario de discos no presentes")
@pytest.mark.parametrize("fx", _DISCO_INVENTARIO[:6], ids=lambda p: p.stem)
def test_el_inventario_de_discos_sigue_dando_s9(fx, det):
    st = det.classify(_load(fx))
    assert st.code == "S9", f"{fx.name}: {st.code} conf={st.confidence:.3f}"


def test_verify_s9_no_bloquea_si_el_ocr_no_dice_nada(monkeypatch):
    """Solo bloquea cuando VE el título de armas. Con OCR ilegible deja pasar: hasta ahora S9 no
    tenía verificación ninguna y esto es un blindaje contra una pantalla concreta, no una
    recalibración de S9."""
    if not _DISCO_INVENTARIO:
        pytest.skip("capturas del inventario de discos no presentes")

    class _Mudo:
        def text(self, *a, **kw):
            return ("", 0.0)

    monkeypatch.setattr(det_mod, "_get_dialog_verify_ocr", lambda: _Mudo())
    ok, detalle = _verify_s9(_load(_DISCO_INVENTARIO[0]))
    assert ok is True
    assert detalle is None


# --- Anti-FP ----------------------------------------------------------------------------------

@pytest.mark.skipif(not _FP.exists(), reason="corpus de negativos no presente")
def test_ningun_negativo_dispara_s29(det):
    for p in sorted(_FP.glob("*.png")):
        fr = _load(p)
        if fr is None:
            continue
        st = det.classify(fr)
        assert st.code != "S29", f"{p.name} disparó S29 (conf={st.confidence:.3f})"
