"""R23 (SPEC 2026-09-27): un stat fijo sin cumplir se BUSCA.

Daniel: "primero quiero que se tome como prioridad el set que se elige", y eligió que mientras el PJ
esté por debajo de un fijo (del set o de su kit) ese stat pese como Imprescindible hasta cumplirlo.
Caso real: Anby con 48,2 de Prob. Crítica y el 4pc de Monarca del Pináculo (≥ 50).
"""
from __future__ import annotations

import pytest

from app.core.scoring import PESO_FIJO_SIN_CUMPLIR, _pesos, ajustar_por_estado
from app.core.stats_fijos import lineas_que_lo_suben
from app.db.repositories import Agent, Archetype

ARCH = Archetype(
    id=1, code="STUN",
    substats_positivos={"ATK%": 0.6},
    substats_perjudiciales={"Prob. Crítica": -0.8, "HP": -0.5},
    threshold_stock=0.7,
)


def _pj(fijos=None, stats=None, pesos=None):
    return Agent(id=1, nombre="anby", arquetipo_primario_id=1, arquetipo_primario_code="STUN",
                 threshold_equip=0.75, threshold_upgrade=0.50,
                 substat_preferences=pesos if pesos is not None else
                 {"Prob. Crítica": 0.6, "Daño Crítico": 0.6, "ATK%": 0.8, "ATK": 0.4},
                 stats=stats or {}, stats_fijos=fijos or {})


def test_las_lineas_de_cada_fijo():
    assert lineas_que_lo_suben("prob_critico") == ("Prob. Crítica",)
    assert lineas_que_lo_suben("maestria_anomalia") == ("Maestría de Anomalía",)
    assert lineas_que_lo_suben("ataque") == ("ATK%",)          # el plano no
    assert lineas_que_lo_suben("pv") == ("HP%",)
    assert lineas_que_lo_suben("defensa") == ("DEF%",)
    for solo_principal in ("impacto", "tasa_perforacion", "tasa_anomalia", "rec_energia"):
        assert lineas_que_lo_suben(solo_principal) == ()


def test_por_debajo_sube_a_imprescindible():
    """Anby: 48,2 / 50 → la Prob. Crítica pesa como Imprescindible (el balance la dejaba abajo)."""
    p = ajustar_por_estado(_pj().substat_preferences,
                           _pj({"prob_critico": 50}, {"prob_critico": 48.2, "dano_critico": 69.2}))
    assert p["Prob. Crítica"] >= PESO_FIJO_SIN_CUMPLIR == 1.0


def test_imprescindible_es_el_tope_del_perfil():
    """Con los pesos reales de Anby (Prob. Crítica = Daño Crítico = 1,0), el balance le dejaba el
    Daño Crítico en 1,16: un 1,0 fijo no alcanzaba para que el motor buscara la Prob. Crítica."""
    pesos = {"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 0.8, "Perforación": 0.6, "ATK": 0.6}
    stats = {"prob_critico": 48.2, "dano_critico": 69.2}
    sin = ajustar_por_estado(pesos, _pj({}, stats, pesos))
    assert sin["Daño Crítico"] > 1.0 > sin["Prob. Crítica"]            # la premisa: el balance
    con = ajustar_por_estado(pesos, _pj({"prob_critico": 50}, stats, pesos))
    assert con["Prob. Crítica"] == max(con.values()) >= con["Daño Crítico"]


def test_al_cumplirlo_vuelve_el_nivel_elegido():
    stats = {"prob_critico": 50.0, "dano_critico": 69.2}
    con = ajustar_por_estado(_pj().substat_preferences, _pj({"prob_critico": 50}, stats))
    sin = ajustar_por_estado(_pj().substat_preferences, _pj({}, stats))
    assert con == sin and con["Prob. Crítica"] < 1.0


def test_sin_el_stat_leido_no_se_sube_nada():
    p = ajustar_por_estado(_pj().substat_preferences, _pj({"prob_critico": 50}, {}))
    assert p == _pj().substat_preferences


def test_el_atk_plano_no_sube():
    """Ju Fufu: 3.229 / 3.400 de ATK → ATK% a 1,0, el ATK plano queda en su nivel."""
    p = ajustar_por_estado(_pj().substat_preferences, _pj({"ataque": 3400}, {"ataque": 3229}))
    assert p["ATK%"] == 1.0 and p["ATK"] == 0.4


def test_un_stat_que_no_valoraba_se_busca_y_el_rol_deja_de_castigarlo():
    """Prob. Crítica valía 0 (el rol la castiga con -0,8); con un fijo sin cumplir se busca, y el
    castigo no puede seguir restando lo mismo que el fijo pide."""
    pj = _pj({"prob_critico": 50}, {"prob_critico": 40.0}, pesos={"ATK%": 0.8})
    pos, neg = _pesos(pj, ARCH)
    assert pos["Prob. Crítica"] == 1.0 and "Prob. Crítica" not in neg
    assert neg["HP"] == -0.5                                 # lo demás del rol, igual


@pytest.mark.parametrize("stat, valor", [("impacto", 150), ("tasa_perforacion", 60)])
def test_un_stat_de_principal_no_toca_los_pesos(stat, valor):
    p = ajustar_por_estado(_pj().substat_preferences, _pj({stat: valor + 50}, {stat: valor}))
    assert p == _pj().substat_preferences
