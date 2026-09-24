"""El estado del PJ entra al peso: balance del crítico y rangos (etapa 1, paso 6).

Caso 3 de Daniel: con Ellen en CR 65 / DC 175 prefiere el disco de CR "porque ya tenemos harto
daño crítico y lo que importa es disminuir la lotería". La cuenta le da la razón: el multiplicador
medio del crítico es 1 + CR·DC, así que una mejora de CR (2,4 %) vale 0,024·DC y una de DC (4,8 %)
vale 0,048·CR. Caso 8: pasado el techo de un rango, el stat "rinde menos pero sigue sumando".

Nada de esto funciona sin los stats ACTUALES del PJ, que hoy la DB tiene en 1 de 52 PJs: sin
ellos el motor cae a pesos fijos — y lo tiene que decir.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

import app.db.repositories as repos
from app.core.recommender import _pesos_pj
from app.core.scoring import _pesos, ajustar_por_estado, factor_rango
from app.db.repositories import Agent, AgentRepo, Archetype

ARQ = Archetype(id=1, code="ATK_DPS",
                substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0,
                                    "ATK": 0.4},
                substats_perjudiciales={}, threshold_stock=0.7)
PJ = Agent(id=1, nombre="pj", arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
           threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={})
BASE = dict(ARQ.substats_positivos)


def _con(**stats):
    return replace(PJ, stats=stats)


# --- balance del crítico ------------------------------------------------------------------

def test_con_dano_critico_de_sobra_pesa_mas_la_prob():
    """Caso 3: CR 65 / DC 175. Una mejora de CR vale 0,024·175 = 4,2; una de DC, 0,048·65 = 3,12."""
    p = ajustar_por_estado(BASE, _con(prob_critico=65, dano_critico=175))
    assert p["Prob. Crítica"] > p["Daño Crítico"]
    assert p["Prob. Crítica"] / p["Daño Crítico"] == pytest.approx((0.024 * 175) / (0.048 * 65), rel=1e-6)


def test_en_la_proporcion_1_a_2_pesan_igual():
    p = ajustar_por_estado(BASE, _con(prob_critico=50, dano_critico=100))
    assert p["Prob. Crítica"] == pytest.approx(p["Daño Crítico"])


def test_el_balance_reparte_el_mismo_peso_total():
    """Cambia la proporción, no la escala: si no, el crítico entero pesaría más o menos que el ATK
    según el estado del PJ, y eso es otra decisión."""
    p = ajustar_por_estado(BASE, _con(prob_critico=40, dano_critico=210))
    assert p["Prob. Crítica"] + p["Daño Crítico"] == pytest.approx(2.0)


def test_con_la_prob_al_tope_no_suma_mas_prob():
    p = ajustar_por_estado(BASE, _con(prob_critico=100, dano_critico=150))
    assert p["Prob. Crítica"] == 0.0 and p["Daño Crítico"] == pytest.approx(2.0)


def test_sin_stats_los_pesos_quedan_fijos():
    assert ajustar_por_estado(BASE, PJ) == BASE


# --- rangos ------------------------------------------------------------------------------

@pytest.mark.parametrize("actual,techo,esperado", [
    (3000, 3200, 1.0),            # dentro
    (2900, 3200, 1.0),            # por debajo: bordes blandos (caso 1)
    (3350, 3200, 3200 / 3350),    # pasado: rinde menos…
    (6400, 3200, 0.5),
    (3350, None, 1.0),            # sin techo no hay "pasado"
])
def test_factor_rango(actual, techo, esperado):
    assert factor_rango(actual, techo) == pytest.approx(esperado)


def test_pasado_el_techo_rinde_menos_pero_suma():
    """Caso 8 (R16): nunca 0."""
    p = ajustar_por_estado(BASE, replace(PJ, stats={"ataque": 3350}, rangos={"ataque": (3000, 3200)}))
    assert 0 < p["ATK%"] < BASE["ATK%"] and 0 < p["ATK"] < BASE["ATK"]
    assert p["Prob. Crítica"] == BASE["Prob. Crítica"], "el rango de ATK no toca el crítico"


def test_un_rango_sin_el_stat_actual_no_hace_nada():
    assert ajustar_por_estado(BASE, replace(PJ, rangos={"ataque": (3000, 3200)})) == BASE


# --- una sola autoridad --------------------------------------------------------------------

def test_el_recomendador_usa_los_mismos_pesos_que_el_scoring():
    """Los bonos de set se valuaban con una copia propia de los pesos, sin el estado del PJ."""
    pj = _con(prob_critico=65, dano_critico=175)
    assert _pesos_pj(pj, ARQ) == _pesos(pj, ARQ)[0]


# --- el repositorio ------------------------------------------------------------------------

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


@pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")
def test_el_repo_carga_los_stats_y_avisa_cuantos_faltan(tmp_path, caplog, monkeypatch):
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    con = sqlite3.connect(copia)
    con.execute("UPDATE agents SET prob_critico=65, dano_critico=175, ataque=3150 WHERE nombre='Ellen'")
    # Los demás SIN crítico, en la copia: el test no puede depender de cuántos PJs tengan stats en
    # la DB viva (con la pasada por S18 del 2026-09-24 pasaron a 52/52 y el aviso desapareció).
    con.execute("UPDATE agents SET prob_critico=NULL, dano_critico=NULL WHERE nombre<>'Ellen'")
    con.commit()
    con.close()
    monkeypatch.setattr(repos, "_AVISO_SIN_STATS_DADO", False)
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    with caplog.at_level(logging.WARNING, logger=repos.__name__):
        agentes = AgentRepo(c).get_all()
    ellen = next(a for a in agentes if a.nombre == "Ellen")
    assert ellen.stats["prob_critico"] == 65 and ellen.stats["dano_critico"] == 175
    avisos = [r.getMessage() for r in caplog.records if "sin Prob./Daño Crítico" in r.getMessage()]
    assert len(avisos) == 1, avisos
