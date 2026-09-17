"""S18 del rol Armero (v3.2, Claret Flint): laceración, afiladura y lo que dejan de ser.

La ficha del Armero cambia dos celdas respecto del resto: donde va ATK dice "Daño de laceración"
y donde va Recup. Energía dice "Acumulación Automática de afiladura". Antes de este parser, sobre la
captura real (`atributos_base_ejemplo_17`) pasaban dos cosas medidas:

- el rescate por ROI de Recup. Energía leía la celda de la afiladura y metía **1.5 en ER**;
- laceración y afiladura no se leían, así que el sistema no veía el stat que multiplica su crit.

Los textos de abajo son el OCR REAL de Paddle sobre esa captura (con su "Dafo" por "Daño").
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from app.core import parser_agent_stats as p
from app.core.parser_agent_stats import (
    AgentStatsAggregator,
    AgentStatsParsed,
    missing_stat_labels,
    required_stat_keys,
    stats_completos,
)

REPO = Path(__file__).resolve().parents[3]
CAPTURA = REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_17.png"
DB = REPO / "db" / "danibod_zzz_v2.db"

#: OCR full-frame de Paddle sobre atributos_base_ejemplo_17 (2026-09-17), tal cual.
OCR_CLARET = (
    "1 Ciudad WNINFLUENCES $ Taller Flint de Roscaelifer Claret Flint HOLLOWS ARE AN APOCALYP THE "
    "INTERNAL SPACE-TIME E Claret MAX Nivel 60 Eléctrico Z Armero PV 8360 Dafo de laceración 150 % "
    "Defensa 927 Impacto 93 Probabilidad de 95.2 % Dano Critico 93.2 % Critico Tasa de Anomalia 86 "
    "Maestria de Anomalia 79 Acumulación Automätica Tasa de Perforacion 32 % 1.5 de afiladura "
    "Recomendación de mejora Preparación prioritaria: Amplificador para el combate CINENA 0/6 "
    "Atributos base Habilidades Equipamiento"
)


def _frame():
    return np.zeros((1440, 2560, 3), np.uint8)


class _Ocr:
    """psm=7 es la llamada del rescate por ROI; cualquier otra, el full-frame."""

    def __init__(self, full: str, roi: str = ""):
        self.full, self.roi, self.rois_pedidos = full, roi, 0

    def text(self, img, psm=None):
        if psm == 7:
            self.rois_pedidos += 1
            return (self.roi, 1.0 if self.roi else 0.0)
        return (self.full, 0.97)


# --- regex sobre el texto real -----------------------------------------------------------------

def test_la_regex_lee_laceracion_y_afiladura_del_ocr_real():
    ex = p._extract_by_regex(OCR_CLARET)
    assert ex["laceracion"] == "150"
    assert ex["afiladura"] == "1.5"
    assert ex["tasa_perforacion"] == "32", "el 32 % pegado sigue siendo TP"
    assert ex["recup_energia"] is None


def test_la_afiladura_no_se_come_el_porcentaje_de_tp():
    """La ventana del valor-antes excluye '%': sin eso '32 % 1.5 de afiladura' podía dar 32."""
    ex = p._extract_by_regex("tasa de perforacion 32 % de afiladura")
    assert ex["afiladura"] is None


def test_los_otros_roles_no_leen_laceracion_ni_afiladura():
    ex = p._extract_by_regex("ataque 2531 tasa de perforacion 0 % 1.2 energia")
    assert ex["laceracion"] is None and ex["afiladura"] is None


# --- el parse completo -------------------------------------------------------------------------

def test_claret_sale_completa_y_la_afiladura_no_cae_en_er():
    if not DB.exists():
        pytest.skip("sin DB de dominio")
    r = p.parse_agent_stats(_frame(), _Ocr(OCR_CLARET, roi="1.5"))
    assert r.agente_nombre == "Claret Flint" and r.rol == "Armero"
    assert r.dano_laceracion == pytest.approx(1.5)      # 150 % como fracción, igual que CR
    assert r.acumulacion_afiladura == pytest.approx(1.5)
    assert r.recuperacion_energia is None, "la celda de la afiladura no es ER"
    assert r.ataque is None
    assert r.tasa_perforacion == pytest.approx(0.32)
    assert stats_completos(r), missing_stat_labels(r)


def test_afiladura_sin_digito_se_rescata_por_roi_como_afiladura():
    """El caso que antes daba ER=1.5: el full-frame ve el label pero no el valor, y el rescate de
    esa celda tiene que ir a la afiladura, no a Recup. Energía."""
    full = OCR_CLARET.replace("32 % 1.5 de afiladura", "32 % de afiladura")
    ocr = _Ocr(full, roi="1.5")
    r = p._parse_via_full_frame(_frame(), ocr)
    assert r.acumulacion_afiladura == pytest.approx(1.5)
    assert r.recuperacion_energia is None
    assert "af_rescatada_roi" in r.notas, r.notas


def test_la_laceracion_prueba_el_rol_aunque_la_db_diga_otro(monkeypatch):
    monkeypatch.setattr(p, "_extract_agent_info",
                        lambda text, stats=None: ("Claret Flint", "Ataque", "Eléctrico", []))
    r = p._parse_via_full_frame(_frame(), _Ocr(OCR_CLARET))
    assert r.rol == "Armero"
    assert any(n.startswith("rol_corregido_por_laceracion") for n in r.notas), r.notas


def test_un_ataque_leido_en_la_ficha_del_armero_se_descarta(monkeypatch):
    monkeypatch.setattr(p, "_extract_agent_info",
                        lambda text, stats=None: ("Claret Flint", "Armero", "Eléctrico", []))
    r = p._parse_via_full_frame(_frame(), _Ocr(OCR_CLARET.replace("PV 8360", "PV 8360 Ataque 999")))
    assert r.ataque is None
    assert "atk_ignorado_armero" in r.notas


def test_el_banner_de_la_ficha_nombra_el_rol_armero():
    """El texto entre MAX y PV del OCR real: 'Nivel 60 Eléctrico Z Armero'."""
    assert p._canon_rol("Nivel 60 Eléctrico Z Armero") == "Armero"
    assert p._canon_elemento("Nivel 60 Eléctrico Z Armero") == "Eléctrico"


# --- completitud por rol -----------------------------------------------------------------------

def test_el_armero_pide_sus_once_y_no_atk_ni_er():
    keys = required_stat_keys(AgentStatsParsed(rol="Armero"))
    assert len(keys) == 11
    assert {"dano_laceracion", "tasa_perforacion", "acumulacion_afiladura"} <= set(keys)
    assert not {"ataque", "recuperacion_energia", "fuerza_bruta", "acumulacion_adrenalina"} & set(keys)


def test_el_aggregator_conserva_laceracion_y_afiladura():
    agg = AgentStatsAggregator()
    agg.merge(AgentStatsParsed(agente_nombre="Claret Flint", rol="Armero", pv=8360,
                               dano_laceracion=1.5, acumulacion_afiladura=1.5))
    r = agg.merge(AgentStatsParsed(agente_nombre="Claret Flint", rol="Armero", pv=8360))
    assert r.dano_laceracion == pytest.approx(1.5) and r.acumulacion_afiladura == pytest.approx(1.5)


# --- contra la captura y la DB reales ----------------------------------------------------------

@pytest.mark.skipif(not CAPTURA.exists(), reason="captura de Claret no presente")
def test_la_captura_real_coincide_con_la_fila_de_la_migracion():
    """El cruce que en Aria se hizo a mano, automático: si el parser y la migración 35 dejan de
    coincidir, uno de los dos está leyendo otra cosa."""
    pytest.importorskip("paddleocr")
    if not DB.exists():
        pytest.skip("sin DB de dominio")
    import cv2
    from app.core.ocr_paddle import PaddleBackend
    img = cv2.imdecode(np.fromfile(str(CAPTURA), dtype=np.uint8), cv2.IMREAD_COLOR)
    r = p.parse_agent_stats(img, PaddleBackend())
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        fila = con.execute("SELECT * FROM agents WHERE nombre = 'Claret Flint'").fetchone()
    finally:
        con.close()
    assert fila is not None
    assert (r.agente_nombre, r.rol, r.nivel) == ("Claret Flint", "Armero", fila["nivel"])
    assert (r.pv, r.defensa, r.impacto) == (fila["pv"], fila["defensa"], fila["impacto"])
    assert (r.tasa_anomalia, r.maestria_anomalia) == (fila["tasa_anomalia"], fila["maestria_anomalia"])
    assert round(r.prob_crit * 100, 1) == fila["prob_critico"]
    assert round(r.dano_crit * 100, 1) == fila["dano_critico"]
    assert round(r.tasa_perforacion * 100, 1) == fila["tasa_perforacion"]
    assert round(r.dano_laceracion * 100, 1) == fila["dano_laceracion"]
    assert round(r.acumulacion_afiladura, 2) == fila["acumulacion_afiladura"]
    assert r.ataque is None and fila["ataque"] is None
    assert r.recuperacion_energia is None and fila["rec_energia"] is None
    assert stats_completos(r)
