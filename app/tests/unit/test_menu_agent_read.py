"""`read_menu_agent` — la lectura COMPLETA del nombre del PJ en S15.

`identify_menu_agent` devolvía 3 campos y tiraba dos cosas que el censo necesita:

1. **La confianza del OCR** (`text, _conf = ocr.text(...)`, con el `_conf` sin usar). Sin ella no
   hay con qué distinguir una lectura firme de una dudosa.
2. **El porqué de una abstención.** Cinco caminos distintos devolvían el mismo `(None,None,None)`:
   ROI que falla, ROI chico, OCR que revienta, OCR vacío, y *ningún match en el roster*. Ese
   último es la señal de un PJ que falta cargar; los otros cuatro son "no llegué a leer". Tratarlos
   igual impide censar.

Abstenerse nunca es inventar (RNF-02) — pero abstenerse **en silencio** tampoco sirve.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.census import _CONF_MIN_VISTO, _SCORE_MIN_VISTO
from app.core.parser_agent_stats import (
    _match_agent_scored,
    identify_menu_agent,
    read_menu_agent,
)

REPO = Path(__file__).resolve().parents[3]
_MENU = REPO / "Documentacion" / "Screenshots_Triggers" / "Triggers_Generales" / "Menu_Personajes"


class _StubOcr:
    def __init__(self, text="Nangong Yu", conf=0.99, boom=False):
        self._text, self._conf, self._boom = text, conf, boom

    def text(self, img, psm=6, lang="spa"):
        if self._boom:
            raise RuntimeError("OCR caído")
        return self._text, self._conf


def _frame():
    return np.zeros((1439, 2559, 3), np.uint8)


def _roster_o_skip():
    from app.core.parser_agent_stats import _get_roster
    if not _get_roster():
        pytest.skip("roster DB no disponible")


# --- los cinco motivos, que antes eran uno solo ---------------------------------------------

def test_ocr_vacio_dice_por_que_y_no_inventa_texto():
    r = read_menu_agent(_frame(), _StubOcr("", 0.0))
    assert r.motivo == "ocr_vacio"
    assert r.nombre is None and r.texto_crudo is None


def test_ocr_que_revienta_se_distingue_de_ocr_vacio():
    r = read_menu_agent(_frame(), _StubOcr(boom=True))
    assert r.motivo == "ocr_error" and r.nombre is None


def test_un_nombre_que_el_roster_no_resuelve_conserva_el_texto_crudo():
    """Es el camino del PJ que falta cargar: sin el texto no hay nada que reportar ni con qué
    dispararlo."""
    _roster_o_skip()
    r = read_menu_agent(_frame(), _StubOcr("Zzzarel", 0.93))
    assert r.motivo == "sin_match" and r.nombre is None
    assert r.texto_crudo == "Zzzarel"
    assert r.conf == 0.93


def test_una_lectura_buena_conserva_la_confianza_que_antes_se_tiraba():
    _roster_o_skip()
    r = read_menu_agent(_frame(), _StubOcr("Nangong Yu", 0.97))
    assert r.motivo == "ok" and r.nombre == "Nangong Yu"
    assert r.conf == 0.97
    assert r.score is not None and r.score >= _SCORE_MIN_VISTO


# --- las dos señales son distintas ----------------------------------------------------------

def test_conf_y_score_miden_cosas_distintas():
    """`conf` es qué tan seguro está el OCR de los CARACTERES; `score`, qué tan seguro está el
    sistema de la IDENTIDAD. Un OCR nítido de un nombre que no es de nadie tiene conf alta y
    score bajo — y ese caso tiene que poder detectarse."""
    _roster_o_skip()
    r = read_menu_agent(_frame(), _StubOcr("Zzzarel", 0.99))
    assert r.conf == 0.99
    assert r.score is not None and r.score < 0.55


def test_el_matcher_expone_al_mas_parecido_aunque_no_pase_el_umbral():
    """Medido: 'Hugo' —un PJ que no se posee— da 0.500 contra Zhao, por debajo del umbral de
    identificación (0.55). Exponer ese número es lo que permite separar 'no lo reconozco' de
    'lo leí mal': sin él, ambos son None."""
    _roster_o_skip()
    nombre, _rol, _elem, cand, sim = _match_agent_scored("Hugo")
    assert nombre is None, "no debería matchear a nadie"
    assert cand is not None and sim is not None
    assert 0.4 <= sim < 0.55


def test_cuando_hay_match_el_score_describe_al_elegido():
    _roster_o_skip()
    nombre, _r, _e, cand, sim = _match_agent_scored("Nangong Yu")
    assert nombre == "Nangong Yu" and cand == "Nangong Yu"
    assert sim == pytest.approx(1.0)


# --- compatibilidad -------------------------------------------------------------------------

def test_identify_menu_agent_sigue_devolviendo_tres_campos():
    """Es la API de los llamadores que solo identifican; `read_menu_agent` no la reemplaza."""
    _roster_o_skip()
    out = identify_menu_agent(_frame(), _StubOcr("Nangong Yu"))
    assert isinstance(out, tuple) and len(out) == 3
    assert out[0] == "Nangong Yu"


# --- calibración contra las capturas reales -------------------------------------------------

_REAL = {"Ejemplo_1": "Nangong Yu", "Ejemplo_2": "Astra Yao", "Ejemplo_3": "Jane",
         "Ejemplo_4": "Orfia y Magas", "Ejemplo_5": "César", "Ejemplo_7": "Billy Estelar",
         "Ejemplo_8": "N.º 0: Anby", "Ejemplo_9": "Pyrois", "Ejemplo_10": "Remielle Dan"}


@pytest.mark.skipif(not (_MENU / "Ejemplo_1.png").exists(),
                    reason="capturas del menú no presentes")
@pytest.mark.parametrize("name,esperado", list(_REAL.items()))
def test_los_umbrales_del_censo_no_rechazan_ninguna_lectura_correcta(name, esperado):
    """**Calibración, no afinado.** Los umbrales salen de esta medición (2026-08-16, 9/9):

        sim  mínimo correcto 0.925 ('Remielle &' → Remielle Dan)   umbral 0.75
        conf mínimo correcto 0.878 ('N.°0:Anby 0' → N.º 0: Anby)   umbral 0.80

    Si este test cae, o el OCR se degradó o alguien movió un umbral sin medir. El fallo es en la
    dirección segura —una lectura buena marcada DUDOSA solo pide repetir la selección—, pero
    igual hay que enterarse.
    """
    _roster_o_skip()
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:  # noqa: BLE001 — el import de Paddle falla de formas variadas; es un skip
        pytest.skip("PaddleOCR no disponible")
    p = _MENU / f"{name}.png"
    if not p.exists():
        pytest.skip(f"falta {name}")
    frame = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
    r = read_menu_agent(frame, PaddleBackend())
    assert r.nombre == esperado, f"{name}: esperaba {esperado}, salió {r.nombre} ({r.texto_crudo!r})"
    assert r.score >= _SCORE_MIN_VISTO, f"{name}: sim {r.score:.3f} < {_SCORE_MIN_VISTO}"
    assert r.conf >= _CONF_MIN_VISTO, f"{name}: conf {r.conf:.3f} < {_CONF_MIN_VISTO}"
