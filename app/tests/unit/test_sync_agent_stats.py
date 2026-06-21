"""Sync EN VIVO de stats base de agente (S18 → agents, RF-04).

Cubre: conversión de unidades (fracción→porcentaje ×100), update PARCIAL solo de
campos cambiados (dedup), no NULL-ear campos que el OCR dropea, y abstención
(RNF-02) por identidad fuera de roster / readonly / frame de transición.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.core.parser_agent_stats import AgentStatsParsed
from app.core.sync_agent_stats import AgentStatsSyncer

_SCHEMA = """
CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL,
    nivel INTEGER, pv INTEGER, ataque INTEGER, defensa INTEGER, impacto INTEGER,
    prob_critico REAL, dano_critico REAL,
    tasa_anomalia INTEGER, maestria_anomalia INTEGER,
    tasa_perforacion REAL, rec_energia REAL,
    protected_build INTEGER NOT NULL DEFAULT 0
);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    """DB temporal con un Pyrois Nv1 (stats provisorios) y readonly OFF."""
    monkeypatch.delenv("DANIBOD_READONLY", raising=False)
    p = tmp_path / "t.db"
    con = sqlite3.connect(str(p))
    con.executescript(_SCHEMA)
    con.execute(
        "INSERT INTO agents (nombre, nivel, pv, ataque, defensa, impacto, "
        "prob_critico, dano_critico, tasa_anomalia, maestria_anomalia, "
        "tasa_perforacion, rec_energia, protected_build) VALUES "
        "('Pyrois', 1, 2985, 557, 235, 94, 27.8, 114.0, 94, 129, 0.0, 1.2, 0)"
    )
    con.commit(); con.close()
    return p


def _row(p: Path, nombre="Pyrois"):
    con = sqlite3.connect(str(p)); con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM agents WHERE nombre=?", (nombre,)).fetchone()
    con.close()
    return r


def test_sube_de_nivel_actualiza_y_convierte_unidades(db):
    # Pyrois Nv1 -> Nv50: PV/ATK suben, CR=0.55 (fracción) -> 55.0 (%), CD=2.0 -> 200.0.
    s = AgentStatsParsed(
        nivel=50, pv=9700, ataque=1850, defensa=720, impacto=120,
        prob_crit=0.55, dano_crit=2.0, tasa_anomalia=120, maestria_anomalia=140,
        tasa_perforacion=0.24, recuperacion_energia=1.2, agente_nombre="Pyrois",
    )
    n = AgentStatsSyncer(db).sync(s)
    r = _row(db)
    assert r["nivel"] == 50 and r["pv"] == 9700 and r["ataque"] == 1850
    assert r["prob_critico"] == 55.0          # 0.55 -> 55.0 (×100)
    assert r["dano_critico"] == 200.0         # 2.0  -> 200.0
    assert r["tasa_perforacion"] == 24.0      # 0.24 -> 24.0
    assert r["rec_energia"] == 1.2            # multiplicador crudo, sin ×100
    assert n is not None and n >= 7           # varios campos actualizados


def test_dedup_sin_cambios_no_escribe(db):
    # Mismos valores que la DB (en unidades del parser) -> 0 updates -> None.
    s = AgentStatsParsed(
        nivel=1, pv=2985, ataque=557, defensa=235, impacto=94,
        prob_crit=0.278, dano_crit=1.14, tasa_anomalia=94, maestria_anomalia=129,
        tasa_perforacion=0.0, recuperacion_energia=1.2, agente_nombre="Pyrois",
    )
    assert AgentStatsSyncer(db).sync(s) is None


def test_update_parcial_no_nullea_campo_dropeado(db):
    # El OCR dropeó ER (None) y solo cambió el PV: ER en la DB NO se toca.
    s = AgentStatsParsed(pv=9700, ataque=557, recuperacion_energia=None,
                         agente_nombre="Pyrois")
    n = AgentStatsSyncer(db).sync(s)
    r = _row(db)
    assert r["pv"] == 9700
    assert r["rec_energia"] == 1.2            # preservado, no NULL
    assert n == 1                             # solo el PV cambió


def test_jitter_bajo_tolerancia_no_escribe(db):
    # CR 27.8 -> 27.85 (jitter < 0.1%): no debe re-escribir.
    s = AgentStatsParsed(pv=2985, ataque=557, prob_crit=0.2785, agente_nombre="Pyrois")
    assert AgentStatsSyncer(db).sync(s) is None


def test_agente_fuera_de_db_no_escribe(db):
    s = AgentStatsParsed(pv=9000, ataque=1800, agente_nombre="NoExisteEsteAgente")
    assert AgentStatsSyncer(db).sync(s) is None


def test_nombre_fuera_de_roster_abstiene(db):
    s = AgentStatsParsed(pv=9000, ataque=1800, agente_nombre="Pyrois",
                         notas=["nombre_fuera_de_roster"])
    assert AgentStatsSyncer(db).sync(s) is None
    assert _row(db)["pv"] == 2985             # intacto


def test_frame_de_transicion_sin_pv_ni_atk_abstiene(db):
    s = AgentStatsParsed(pv=None, ataque=None, defensa=999, agente_nombre="Pyrois")
    assert AgentStatsSyncer(db).sync(s) is None
    assert _row(db)["defensa"] == 235         # intacto


def test_readonly_no_escribe(db, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    s = AgentStatsParsed(pv=9700, ataque=1850, agente_nombre="Pyrois")
    assert AgentStatsSyncer(db).sync(s) is None
    assert _row(db)["pv"] == 2985             # intacto


def test_protected_build_tambien_se_actualiza(db):
    # Decisión del usuario: actualizar a TODOS, incluso protected_build=1.
    con = sqlite3.connect(str(db))
    con.execute("UPDATE agents SET protected_build=1 WHERE nombre='Pyrois'")
    con.commit(); con.close()
    s = AgentStatsParsed(pv=9700, ataque=1850, agente_nombre="Pyrois")
    assert AgentStatsSyncer(db).sync(s) == 2
    assert _row(db)["pv"] == 9700