"""Parser del modal de MEJORA (upgrade) de disco (S10).

Verifica el parseo espacial sobre las 3 capturas reales del mismo disco (Fábula
Yunkui slot 1, main PV) en tres estados: nivel 0 (PRE), nivel 12 (PRE) y nivel 15
(MAX). El foco es: nivel de la barra, main escalado, y los substats con sus rolls
(+N) en la grilla 2×2 — la base del tracking PRE→POST (RF-05).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[3]
_BASE = _ROOT / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
_SHOTS = {
    "nivel0": _BASE / "05_Upgrade_PRE_nivel0" / "Ejemplo_1.png",
    "nivel12": _BASE / "06_Upgrade_PRE_nivel3_6_9_12" / "Ejemplo_1_(nivel12).png",
    "max15": _BASE / "07_Upgrade_POST_animacion_confirmacion" / "Ejemplo_1(detallado).png",
}
# Estado "pre-15-max": materiales de EXP ya cargados ("Añadir todo") pero SIN tocar
# "Mejorar" → la barra muestra pill_izq=nivel actual, pill_der=nivel PROYECTADO (15).
# Frame estable (a diferencia del MAX real que auto-cierra) → fuente del "antes→después".
_PREMAX = {
    "Ejemplo_1(pre-15-max).png": {"slot": 2, "nivel": 0, "target": 15},
    "Ejemplo_2(pre-15-max).png": {"slot": 6, "nivel": 0, "target": 15},
    "Ejemplo_3(pre-15-max).png": {"slot": 4, "nivel": 0, "target": 15},
    # Targets BAJOS: la pill proyectada cae sobre el olivo oscuro (barra poco llena) y la
    # detección de PaddleOCR sobre el frame COMPLETO la pierde → exige rescate por recorte.
    "Ejemplo_4(pre-0a5).png":  {"slot": 1, "nivel": 0, "target": 5},   # regresión del bug (leía nada/3)
    "Ejemplo_5(pre-0a8).png":  {"slot": 1, "nivel": 0, "target": 8},
    "Ejemplo_6(pre-8a11).png": {"slot": 1, "nivel": 8, "target": 11},  # nivel ACTUAL != 0
}


def _ocr_or_skip():
    try:
        from app.core.ocr_paddle import PaddleBackend
        return PaddleBackend()
    except Exception:
        pytest.skip("PaddleOCR no disponible")


def _load(name: str) -> np.ndarray:
    p = _SHOTS[name]
    if not p.exists():
        pytest.skip(f"screenshot S10 no presente: {p.name}")
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def _subs_map(parsed):
    """canon -> (valor, rolls) para los substats con canon resuelto."""
    return {s.nombre_canon: (s.valor, s.rolls) for s in parsed.subs if s.nombre_canon}


def test_s10_nivel0_pre():
    from app.core.parser_disc_s10 import parse_disc_s10
    ocr = _ocr_or_skip()
    d = parse_disc_s10(_load("nivel0"), ocr)
    assert "Yunkui" in d.set_name_raw
    assert d.slot == 1
    assert d.main_stat_canon == "HP" and d.main_valor == 550
    assert d.nivel == 0
    assert "s10_pre" in d.notas and "s10_max" not in d.notas
    subs = _subs_map(d)
    assert subs.get("ATK") == (19, 0)
    assert subs.get("DEF%") == (4.8, 0)
    assert subs.get("Daño Crítico") == (4.8, 0)
    # A nivel 0 el 4º substat está EMPTY → 3 substats reales.
    assert "Perforación" not in subs


def test_s10_nivel12_pre():
    from app.core.parser_disc_s10 import parse_disc_s10
    ocr = _ocr_or_skip()
    d = parse_disc_s10(_load("nivel12"), ocr)
    assert d.slot == 1
    assert d.main_stat_canon == "HP" and d.main_valor == 1870
    assert d.nivel == 12
    assert "s10_pre" in d.notas
    subs = _subs_map(d)
    assert subs.get("ATK") == (19, 0)
    assert subs.get("DEF%") == (9.6, 1)          # ganó +1 roll (4.8→9.6)
    assert subs.get("Daño Crítico") == (4.8, 0)
    assert subs.get("Perforación") == (27, 2)    # nuevo substat, +2 rolls


def test_s10_max15():
    from app.core.parser_disc_s10 import parse_disc_s10
    ocr = _ocr_or_skip()
    d = parse_disc_s10(_load("max15"), ocr)
    assert d.slot == 1
    assert d.main_stat_canon == "HP" and d.main_valor == 2200
    assert d.nivel == 15
    assert "s10_max" in d.notas
    subs = _subs_map(d)
    assert subs.get("ATK") == (19, 0)
    assert subs.get("DEF%") == (9.6, 1)
    assert subs.get("Daño Crítico") == (4.8, 0)
    assert subs.get("Perforación") == (36, 3)    # +3 al maxear


def test_s10_fixtures_existentes_sin_target():
    """nivel0/nivel12/max NO tienen materiales cargados (pill_der == pill_izq) → sin target."""
    from app.core.parser_disc_s10 import parse_disc_s10
    ocr = _ocr_or_skip()
    for name in ("nivel0", "nivel12", "max15"):
        d = parse_disc_s10(_load(name), ocr)
        assert not any(n.startswith("s10_target") for n in d.notas), (name, d.notas)


@pytest.mark.parametrize("fname,exp", _PREMAX.items())
def test_s10_pre_max_preview_lee_nivel_proyectado(fname, exp):
    """Materiales cargados: pill_izq=nivel actual, pill_der=proyectado → nota s10_target:N.
    El nivel del disco sigue siendo el ACTUAL, no el proyectado. Targets bajos (p.ej. 5)
    exigen el rescate por recorte de la pill (la detección full-frame los pierde)."""
    from app.core.parser_disc_s10 import parse_disc_s10
    p = _BASE / "19_Upgrade_PRE_materiales_cargados" / fname
    if not p.exists():
        pytest.skip(f"screenshot no presente: {fname}")
    ocr = _ocr_or_skip()
    frame = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    d = parse_disc_s10(frame, ocr)
    assert d.slot == exp["slot"]
    assert d.nivel == exp["nivel"]          # nivel ACTUAL, no el proyectado
    assert "s10_pre" in d.notas and "s10_max" not in d.notas
    assert f"s10_target:{exp['target']}" in d.notas, d.notas
