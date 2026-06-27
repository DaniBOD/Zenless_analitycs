"""Parser ESPACIAL del modal de detalle de drop (S3), 2 columnas.

S3 ("Detalle del disco desde resultado") es el modal centrado que aparece al abrir un disco
farmeado. Tiene los MISMOS headers que S17/S9 ("Atributo principal/secundarios", "Efecto de
conjunto") pero los substats están en una GRILLA 2×2 (2 columnas), no en una sola columna. El
parser per-ROI viejo (`parse_modal_detalle`) leía mal (cada celda capturaba la columna vecina,
valores en None, slot 0). Este parser reusa la maquinaria endurecida de `parser_disc_s17`
(headers, valor/canon, rescates de rolls/valor, maturity) con pairing por columna.

Tests end-to-end sobre los 4 fixtures reales (PaddleOCR); se saltean si Paddle no está.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_disc_s17 import disc_is_mature

REPO = Path(__file__).resolve().parents[3]
_S3 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "02_Detalle_Disco_Desde_Resultado"


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


def _load(name):
    return cv2.imdecode(np.fromfile(str(_S3 / name), np.uint8), cv2.IMREAD_COLOR)


def _subs_completos(d):
    return [s for s in d.subs if s.nombre_canon and s.valor is not None]


@pytest.mark.skipif(not (_S3 / "Ejemplo_1.png").exists(), reason="capturas S3 no presentes")
def test_s3_ejemplo_1_fabula_slot1():
    from app.core.parser_disc_s3 import parse_disc_s3_full
    d = parse_disc_s3_full(_load("Ejemplo_1.png"), _paddle())
    assert "yunkui" in (d.set_name_raw or "").lower()
    assert d.slot == 1
    assert d.nivel == 0
    assert d.main_stat_canon == "HP"
    assert d.main_valor == 550
    # 3 substats limpios (nivel 0): Ataque 19, Defensa 4.8%, Daño Crítico 4.8%
    completos = _subs_completos(d)
    assert len(completos) >= 3, [(s.nombre_canon, s.valor, s.unidad) for s in d.subs]
    canons = {s.nombre_canon for s in completos}
    assert "ATK" in canons        # Ataque 19 (flat)
    assert "DEF%" in canons       # Defensa 4.8%
    assert disc_is_mature(d)


@pytest.mark.skipif(not (_S3 / "Ejemplo_4.png").exists(), reason="capturas S3 no presentes")
def test_s3_ejemplo_4_nana_slot6_main_atkpct():
    from app.core.parser_disc_s3 import parse_disc_s3_full
    d = parse_disc_s3_full(_load("Ejemplo_4.png"), _paddle())
    assert "nana" in (d.set_name_raw or "").lower()
    assert d.slot == 6
    assert d.main_stat_canon == "ATK%"      # Ataque 7.5% (porcentual → ATK%)
    assert len(_subs_completos(d)) >= 3
    assert disc_is_mature(d)


@pytest.mark.skipif(not (_S3 / "Ejemplo_3.png").exists(), reason="capturas S3 no presentes")
def test_s3_ejemplo_3_floracion_slot4():
    from app.core.parser_disc_s3 import parse_disc_s3_full
    d = parse_disc_s3_full(_load("Ejemplo_3.png"), _paddle())
    assert "floraci" in (d.set_name_raw or "").lower()
    assert d.slot == 4
    assert d.nivel == 0
    assert len(_subs_completos(d)) >= 2


@pytest.mark.skipif(not (_S3 / "Ejemplo_6.png").exists(), reason="capturas S3 no presentes")
def test_s3_ejemplo_6_firmamento_slot2():
    """Set NUEVO 'Firmamento llameante' (Éter). slot 2, main ATK 79 (rescate de valor full-frame).
    'Probabilidad de Crítico' se lee envuelto a 2 líneas → debe coalescer a UN substat."""
    from app.core.parser_disc_s3 import parse_disc_s3_full
    d = parse_disc_s3_full(_load("Ejemplo_6.png"), _paddle())
    assert "firmamento" in (d.set_name_raw or "").lower()
    assert d.slot == 2
    assert d.main_stat_canon == "ATK"
    assert d.main_valor == 79                    # rescate del valor chico del main
    canons = {s.nombre_canon for s in _subs_completos(d)}
    assert "Prob. Crítica" in canons             # nombre envuelto coalescido
    assert "Perforación" in canons
    assert disc_is_mature(d)


@pytest.mark.skipif(not (_S3 / "Ejemplo_7.png").exists(), reason="capturas S3 no presentes")
def test_s3_ejemplo_7_firmamento_slot4():
    from app.core.parser_disc_s3 import parse_disc_s3_full
    d = parse_disc_s3_full(_load("Ejemplo_7.png"), _paddle())
    assert "firmamento" in (d.set_name_raw or "").lower()
    assert d.slot == 4
    assert d.main_stat_canon == "HP%"
    assert "Prob. Crítica" in {s.nombre_canon for s in _subs_completos(d)}
    assert disc_is_mature(d)


@pytest.mark.skipif(not (_S3 / "Ejemplo_5.png").exists(), reason="capturas S3 no presentes")
def test_s3_ejemplo_5_coalesce_maestria_anomalia():
    """'Maestría de Anomalía' se lee envuelto a 2 líneas ('Maestría de' / 'Anomalía') → debe
    coalescer a UN substat, no partirse en dos fantasmas."""
    from app.core.parser_disc_s3 import parse_disc_s3_full
    d = parse_disc_s3_full(_load("Ejemplo_5.png"), _paddle())
    assert "huracanado" in (d.set_name_raw or "").lower()
    assert d.slot == 1
    assert d.main_stat_canon == "HP" and d.main_valor == 550
    raws = {(s.nombre_canon or s.nombre_raw) for s in d.subs}
    assert "Maestría de Anomalía" in {s.nombre_canon for s in d.subs}
    # no quedaron las mitades sueltas como substats fantasma
    assert "Anomalía" not in raws and "Maestría de" not in raws
