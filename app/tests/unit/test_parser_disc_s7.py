"""Vista individual del disco a pantalla completa (S6/S7) — detección + parser espacial.

Es la pantalla que se abre con "Ver" y desde la que se mejora el disco. Se llega desde TRES
flujos (tienda de música tras la afinación, "Obtenido" del farmeo por baterías, e inventario
general), no solo desde la tienda como sugerían los nombres viejos de S6/S7.

Dos regresiones que cubren estos tests (QA 2026-07-16):

1. DETECCIÓN. Los dos templates viejos matcheaban por accidente: `s7_tienda_detalle_full`
   incluye el texto "Nivel 15/MAX" (⇒ solo discos maxeados) y `s6_tienda_detalle_panel` es una
   banda oscura que matchea por el FONDO de Ejemplo_6. El Ejemplo_17 (Nivel 00, otro wallpaper)
   caía a S12. Y aun clasificando, la máquina de estados solo aceptaba llegar desde la tienda
   ⇒ viniendo del "Obtenido" (S22) la transición se rechazaba como FP → S12 → sin toast.

2. PARSER. `parse_modal_detalle` (per-ROI) leía mal esta pantalla igual que el modal S3: cada
   celda se comía la columna vecina y los nombres largos envueltos a 2 líneas se partían en
   substats fantasma, uno de ellos con un valor RESCATADO de otra fila (inventado → RNF-02).

Los tests corren con PaddleOCR real (el backend de la app); se saltean si no está.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_D = (REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
      / "04_Inventario_Disco_Vista_Individual")

# Las 3 capturas de la vista individual. El resto del folder son S17 (disco equipado).
_E6 = "Ejemplo_6(vista_detallada_tienda_musica).png"
_E7 = "Ejemplo_7(vista_detallada_tienda_musica).png"
_E17 = "Ejemplo_17(vista_detallada_tienda_musica).png"
_VISTA_INDIVIDUAL = [_E6, _E7, _E17]


def _load(name):
    p = _D / name
    if not p.exists():
        return None
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


def _subs_completos(d):
    return [s for s in d.subs if s.nombre_canon and s.valor is not None]


# ---- Detección -------------------------------------------------------------------------

@pytest.mark.skipif(not _D.exists(), reason="capturas de la vista individual no presentes")
@pytest.mark.parametrize("name", _VISTA_INDIVIDUAL)
def test_vista_individual_se_clasifica(name):
    """Las 3 capturas deben reconocerse como la vista individual (S6 o S7 — misma pantalla,
    mismas ROIs). El Ejemplo_17 (Nivel 00) daba S12 antes del template de iconos."""
    from app.core.detector import ScreenDetector
    frame = _load(name)
    if frame is None:
        pytest.skip(f"falta {name}")
    st = ScreenDetector(use_state_machine=False).classify(frame)
    assert st.code in ("S6", "S7"), f"{name} → {st.code} (conf={st.confidence:.2f})"


@pytest.mark.skipif(not _D.exists(), reason="capturas no presentes")
def test_template_iconos_no_eclipsa_s17():
    """El resto del folder 04 es la vista del disco EQUIPADO (S17). El template de la vista
    individual es el cluster papelera/candado/R/T, que S17 no tiene: no debe robarle frames."""
    from app.core.detector import ScreenDetector
    det = ScreenDetector(use_state_machine=False)
    otros = [p.name for p in _D.glob("Ejemplo_*.png") if p.name not in _VISTA_INDIVIDUAL]
    if not otros:
        pytest.skip("no hay capturas S17 en el folder")
    for name in otros:
        frame = _load(name)
        if frame is None:
            continue
        st = det.classify(frame)
        assert st.code == "S17", f"{name} → {st.code} (conf={st.confidence:.2f})"


def test_transiciones_alcanzan_la_vista_desde_los_tres_flujos():
    """Regresión del bug del toast: la vista se alcanza con "Ver" desde la tienda (S5), el
    "Obtenido" del farmeo por baterías (S22) y el inventario (S9), y lleva a la mejora (S10).
    Antes solo se aceptaba desde la tienda ⇒ desde S22 la transición se rechazaba → S12."""
    from app.core.detector import _VALID_TRANSITIONS
    for origen in ("S5", "S9", "S22"):
        assert _VALID_TRANSITIONS[origen] & {"S6", "S7"}, f"{origen} no alcanza la vista individual"
    for vista in ("S6", "S7"):
        assert "S10" in _VALID_TRANSITIONS[vista], f"{vista} no llega a la mejora (S10)"
        # y se puede volver por donde se vino
        assert {"S5", "S9", "S22"} <= _VALID_TRANSITIONS[vista], f"{vista} no puede volver"


# ---- Parser ----------------------------------------------------------------------------

@pytest.mark.skipif(not (_D / _E17).exists(), reason="falta Ejemplo_17")
def test_e17_firmamento_slot2_nombre_envuelto_no_se_parte():
    """Firmamento llameante (2) · Nivel 00 · main Ataque 79 · subs: Prob. Crítico 2.4 %
    (nombre ENVUELTO a 2 líneas), Perforación 9 (columna B), PV 112.
    El per-ROI daba 'Probabilidad de' + 'Critico' como DOS substats, el 2º con valor inventado."""
    from app.core.parser_disc_s3 import parse_disc_s7
    d = parse_disc_s7(_load(_E17), _paddle())
    assert "firmamento" in (d.set_name_raw or "").lower()
    assert d.slot == 2
    assert d.nivel == 0
    assert d.main_stat_canon == "ATK"
    assert d.main_valor == 79
    completos = _subs_completos(d)
    canons = {s.nombre_canon for s in completos}
    assert canons == {"Prob. Crítica", "Perforación", "HP"}, [
        (s.nombre_raw, s.nombre_canon, s.valor) for s in d.subs]
    # el nombre envuelto quedó en UN solo substat, con su valor real
    prob = next(s for s in completos if s.nombre_canon == "Prob. Crítica")
    assert (prob.valor, prob.unidad) == (2.4, "%")
    # Perforación vive en la columna B (la que el per-ROI ni miraba)
    assert next(s for s in completos if s.nombre_canon == "Perforación").valor == 9


@pytest.mark.skipif(not (_D / _E6).exists(), reason="falta Ejemplo_6")
def test_e6_nana_slot4_maestria_envuelta():
    """Nana a la luz cenicienta (4) · main Daño Crítico 12 % · subs: Perforación 9,
    Maestría de Anomalía 9 (envuelta a 2 líneas, columna B), Defensa 4.8 %."""
    from app.core.parser_disc_s3 import parse_disc_s7
    d = parse_disc_s7(_load(_E6), _paddle())
    assert "nana" in (d.set_name_raw or "").lower()
    assert d.slot == 4
    assert d.nivel == 0
    assert d.main_stat_canon == "Daño Crítico"
    assert d.main_valor == 12
    canons = {s.nombre_canon for s in _subs_completos(d)}
    assert canons == {"Perforación", "Maestría de Anomalía", "DEF%"}, [
        (s.nombre_raw, s.nombre_canon, s.valor) for s in d.subs]


@pytest.mark.skipif(not (_D / _E7).exists(), reason="falta Ejemplo_7")
def test_e7_nana_slot3_main_def_plano():
    """Nana a la luz cenicienta (3) · main Defensa 46 (PLANO → DEF, no DEF%) ·
    subs: Defensa 4.8 %, PV 112, Prob. Crítico 2.4 %."""
    from app.core.parser_disc_s3 import parse_disc_s7
    d = parse_disc_s7(_load(_E7), _paddle())
    assert "nana" in (d.set_name_raw or "").lower()
    assert d.slot == 3
    assert d.main_stat_canon == "DEF"       # plano, distinto del sub 'Defensa 4.8 %' (DEF%)
    assert d.main_valor == 46
    canons = {s.nombre_canon for s in _subs_completos(d)}
    assert canons == {"DEF%", "HP", "Prob. Crítica"}, [
        (s.nombre_raw, s.nombre_canon, s.valor) for s in d.subs]


@pytest.mark.skipif(not _D.exists(), reason="capturas no presentes")
@pytest.mark.parametrize("name", _VISTA_INDIVIDUAL)
def test_placeholder_empty_no_genera_substat_fantasma(name):
    """Los slots de substat vacíos dibujan un "EMPTY" que Paddle devuelve mutilado ('EMPT',
    'EUPT'…). Ninguno debe llegar como substat: un substat real SIEMPRE tiene valor."""
    from app.core.parser_disc_s3 import parse_disc_s7
    frame = _load(name)
    if frame is None:
        pytest.skip(f"falta {name}")
    d = parse_disc_s7(frame, _paddle())
    fantasmas = [s for s in d.subs if s.nombre_canon is None and s.valor is None]
    assert not fantasmas, [s.nombre_raw for s in fantasmas]
    assert len(d.subs) <= 4                     # un disco tiene MÁX 4 substats
    assert not d.notas, d.notas
