"""Migración 41: la Tasa de Perforación sirve de principal del slot 5 para atacantes y soportes.

Daniel, 2026-09-23, sobre #213 (Voz Astral · slot 5 · Tasa de Perforación), que el motor descartaba
con puntaje 0: "le sirve a atacantes como opción secundaria y de momento a los armeros … los
supports/apoyo se pueden beneficiar, por eso lo guardé (Rina por ejemplo) aunque es de nicho".

Es un AJUSTE de Daniel (capa de la migración 40): el default de `disc_archetypes` no cambia, y
borrar el ajuste lo devuelve. Todo sobre una COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from app.core.scoring import principal_valido
from app.db.repositories import AgentRepo, ArchetypeRepo, Disc
from app.tests.unit.test_optimizer_build_actual import REAL_DB_PATH

TDP = "Tasa de Perforación"


@pytest.fixture
def con(tmp_path):
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    copia = tmp_path / "danibod_zzz_v2.db"
    shutil.copy2(REAL_DB_PATH, copia)
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _arch(con, code):
    return next(a for a in ArchetypeRepo(con).get_all() if a.code == code)


def _disco_tdp():
    return Disc(id=1, set_id=1, slot=5, main_stat=TDP, main_valor=None, main_unidad=None,
                subs=[], nivel=15, equipado=0, agente_asignado=None)


@pytest.mark.parametrize("code, acepta", [
    ("ATK_DPS", True), ("SUPPORT_ER", True), ("ARMORER_DEF", True),
    ("ANOMALY", False), ("STUN", False), ("HP_DISRUPT", False), ("DEFENSE", False),
])
def test_quien_acepta_tasa_de_perforacion_en_el_slot_5(con, code, acepta):
    assert (TDP in _arch(con, code).mains_5) is acepta


def test_el_default_no_se_toco(con):
    filas = dict(con.execute(
        "SELECT code, mains_5 LIKE '%Tasa de Perforación%' FROM disc_archetypes "
        "WHERE code IN ('ATK_DPS', 'SUPPORT_ER', 'ARMORER_DEF')").fetchall())
    assert filas == {"ATK_DPS": 0, "SUPPORT_ER": 0, "ARMORER_DEF": 1}


def test_el_ajuste_es_el_default_mas_tasa_de_perforacion(con):
    """Ni se perdió un Bono Daño del default ni se coló otra cosa."""
    for code in ("ATK_DPS", "SUPPORT_ER"):
        import json
        default = json.loads(con.execute("SELECT mains_5 FROM disc_archetypes WHERE code=?",
                                         (code,)).fetchone()[0])
        assert _arch(con, code).mains_5 == default + [TDP]


def test_le_sirve_a_rina_y_a_un_atacante(con):
    agentes = {a.nombre: a for a in AgentRepo(con).get_all()}
    repo = ArchetypeRepo(con)
    for nombre in ("Rina", "Nekomata"):
        pj = agentes[nombre]
        assert principal_valido(_disco_tdp(), repo.get_by_id(pj.arquetipo_primario_id), pj), nombre


def test_borrar_el_ajuste_devuelve_el_default(con):
    with con:
        con.execute("DELETE FROM ajustes_usuario_arquetipo WHERE code='ATK_DPS' AND campo='mains_5'")
    assert TDP not in _arch(con, "ATK_DPS").mains_5
    assert TDP in _arch(con, "SUPPORT_ER").mains_5
