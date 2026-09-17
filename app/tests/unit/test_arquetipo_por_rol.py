"""Cada rol tiene su arquetipo — y un rol que no lo tiene deja de caer callado (2026-09-17).

`AgentRepo` elige el arquetipo de scoring por `agents.rol`. Un rol que no estaba en la tabla caía
**sin aviso** a `ATK_DPS`. Con Claret Flint (rol nuevo "Armero", v3.2) eso habría sido el peor error
posible: `ATK_DPS` penaliza DEF% con −1.0 y ella escala con DEF — el scorer le habría dicho que sus
mejores discos eran malos, y nada en el log lo habría delatado.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

import app.db.repositories as repos
from app.db.repositories import ARCHETYPES_BY_ROLE, AgentRepo

DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


def _db_real() -> sqlite3.Connection:
    if not DB.exists():
        pytest.skip("sin DB de dominio")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def test_claret_flint_usa_el_arquetipo_del_armero():
    con = _db_real()
    try:
        claret = AgentRepo(con).get_by_nombre("Claret Flint")
    finally:
        con.close()
    assert claret is not None, "falta la fila de la migración 35"
    assert claret.arquetipo_primario_code == "ARMORER_DEF"


def test_todo_rol_del_roster_tiene_arquetipo_y_el_arquetipo_existe():
    """Contrato contra la DB real: un PJ nuevo con un rol nuevo tiene que fallar ACÁ, con su nombre,
    y no aparecer semanas después como un scoring raro."""
    con = _db_real()
    try:
        roles = {r[0] for r in con.execute("SELECT DISTINCT rol FROM agents WHERE rol IS NOT NULL")}
        codigos = {r[0] for r in con.execute("SELECT code FROM disc_archetypes")}
    finally:
        con.close()
    assert not sorted(roles - set(ARCHETYPES_BY_ROLE)), "roles sin arquetipo en ARCHETYPES_BY_ROLE"
    assert not sorted(set(ARCHETYPES_BY_ROLE.values()) - codigos), "arquetipos que la DB no tiene"


def _db_minima(rol: str) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE disc_archetypes (id INTEGER PRIMARY KEY, code TEXT);
        CREATE TABLE agent_score_thresholds (agente_id INTEGER, threshold_equip REAL,
                                             threshold_upgrade REAL);
        CREATE TABLE agent_substat_preferences (agente_id INTEGER, substat TEXT, peso REAL);
        CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT, rol TEXT, set_4p_id INTEGER,
                             set_2p_id INTEGER, protected_build INTEGER DEFAULT 0);
        INSERT INTO disc_archetypes VALUES (1, 'ATK_DPS');
    """)
    con.execute("INSERT INTO agents (id, nombre, rol) VALUES (1, 'PJ del patch que viene', ?)", (rol,))
    return con


def test_un_rol_desconocido_avisa_una_vez_y_sigue_con_el_fallback(monkeypatch, caplog):
    monkeypatch.setattr(repos, "_ROLES_SIN_ARQUETIPO_AVISADOS", set())
    caplog.set_level(logging.WARNING, logger="app.db.repositories")
    for _ in range(2):                           # dos recargas del caché: un solo aviso
        a = AgentRepo(_db_minima("Especialidad inventada")).get_by_id(1)
        assert a.arquetipo_primario_code == "ATK_DPS", "el fallback se mantiene"
    avisos = [r for r in caplog.records if "sin arquetipo" in r.getMessage()]
    assert len(avisos) == 1, [r.getMessage() for r in caplog.records]
    assert "Especialidad inventada" in avisos[0].getMessage()


def test_un_rol_conocido_no_avisa(monkeypatch, caplog):
    monkeypatch.setattr(repos, "_ROLES_SIN_ARQUETIPO_AVISADOS", set())
    caplog.set_level(logging.WARNING, logger="app.db.repositories")
    AgentRepo(_db_minima("Ataque")).get_by_id(1)
    assert not [r for r in caplog.records if "sin arquetipo" in r.getMessage()]
