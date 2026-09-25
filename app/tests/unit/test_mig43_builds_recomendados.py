"""Migración 43: builds recomendados por PJ (Prydwen) y el build objetivo que declara Daniel.

Daniel, 2026-09-25, sobre dos sugerencias: "a Ye Shunguang no le sirve Armonía umbría porque no
genera réplicas"; "a Nangong no le sirve Balada porque las 2pc son para daño crítico". El motor no
sabía qué sets usa cada PJ (R18-R20 del SPEC). Esta migración es sólo el esquema; los datos van
aparte.

Como en `test_mig42_prioridad.py`, se corre el `.sql` REAL sobre una COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_43 = RAIZ / "db" / "migrations" / "2026-09-25_43_builds_recomendados_por_pj.sql"
TABLAS = ("pj_sets_2pc", "pj_sets_4pc", "pj_stats_recomendados", "ajustes_usuario_build")

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


def _aplicar(sql: Path, db: Path) -> int:
    sys.path.insert(0, str(RAIZ / "app" / "scripts" / "qa"))
    try:
        from apply_migration import aplicar
    finally:
        sys.path.pop(0)
    return aplicar(sql, db, hacer_backup=False, dry_run=False)


@pytest.fixture
def con(tmp_path):
    """Copia de la DB de dominio SIN las tablas (si ya se aplicó, se le quitan) + la migración 43."""
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    for t in TABLAS:
        c.execute(f"DROP TABLE IF EXISTS {t}")
    c.commit()
    c.close()
    assert _aplicar(MIG_43, copia) == 0
    c = sqlite3.connect(copia)
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def _agente(con, nombre):
    return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]


def _set(con, nombre_en):
    return con.execute("SELECT id FROM disc_sets WHERE nombre_en = ?", (nombre_en,)).fetchone()[0]


def _4pc(con, agente, set_id, orden=1):
    con.execute("INSERT INTO pj_sets_4pc (agente_id, set_id, orden, fuente, url, capturado) "
                "VALUES (?, ?, ?, 'prydwen', 'https://x', '2026-09-25')", (agente, set_id, orden))


def test_nacen_vacias(con):
    for t in TABLAS:
        assert con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t


def test_un_2pc_cuelga_de_un_4pc_de_ESE_pj(con):
    """El 2pc es "con este 4pc": sin el 4pc de ese PJ, la FK compuesta lo rechaza."""
    nangong, faeton, blues = _agente(con, "Nangong Yu"), _set(con, "Phaethon's Melody"), _set(con, "Freedom Blues")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO pj_sets_2pc (agente_id, set_4p_id, set_id, grupo) VALUES (?, ?, ?, 1)",
                    (nangong, faeton, blues))
    _4pc(con, nangong, faeton)
    con.execute("INSERT INTO pj_sets_2pc (agente_id, set_4p_id, set_id, grupo, recomendado) "
                "VALUES (?, ?, ?, 1, 1)", (nangong, faeton, blues))
    # El mismo 4pc en OTRO PJ no lo habilita.
    ye = _agente(con, "Ye Shunguang")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO pj_sets_2pc (agente_id, set_4p_id, set_id, grupo) VALUES (?, ?, ?, 1)",
                    (ye, faeton, blues))


def test_el_orden_no_se_repite_en_un_pj(con):
    nangong = _agente(con, "Nangong Yu")
    _4pc(con, nangong, _set(con, "Phaethon's Melody"), orden=1)
    with pytest.raises(sqlite3.IntegrityError):
        _4pc(con, nangong, _set(con, "Freedom Blues"), orden=1)


def test_un_stat_no_se_repite_en_la_misma_linea(con):
    """`variante` es NOT NULL: con NULL, el UNIQUE de SQLite aceptaría el mismo stat dos veces."""
    fila = ("INSERT INTO pj_stats_recomendados (agente_id, variante, linea, nivel, stat, texto_guia, "
            "fuente, url, capturado) VALUES (?, 'única', 'substat', ?, 'Maestría de Anomalía', "
            "'Anomaly Proficiency', 'prydwen', 'https://x', '2026-09-25')")
    nangong = _agente(con, "Nangong Yu")
    con.execute(fila, (nangong, 1))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(fila, (nangong, 2))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO pj_stats_recomendados (agente_id, variante, linea, nivel, stat, "
                    "texto_guia, fuente, url, capturado) VALUES (?, NULL, 'substat', 1, 'ATK%', "
                    "'ATK%', 'prydwen', 'https://x', '2026-09-25')", (nangong,))


def test_la_linea_es_una_de_cuatro(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO pj_stats_recomendados (agente_id, variante, linea, nivel, stat, "
                    "texto_guia, fuente, url, capturado) VALUES (?, 'única', 'principal_3', 1, 'DEF', "
                    "'DEF', 'prydwen', 'https://x', '2026-09-25')", (_agente(con, "Nangong Yu"),))


def test_build_objetivo_4pc_obligatorio_2pc_opcional_y_distinto(con):
    ye, wwb, puffer = _agente(con, "Ye Shunguang"), _set(con, "White Water Ballad"), _set(con, "Puffer Electro")
    con.execute("INSERT INTO ajustes_usuario_build (agente_id, set_4p_id) VALUES (?, ?)", (ye, wwb))
    con.execute("UPDATE ajustes_usuario_build SET set_2p_id = ? WHERE agente_id = ?", (puffer, ye))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE ajustes_usuario_build SET set_2p_id = set_4p_id WHERE agente_id = ?", (ye,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO ajustes_usuario_build (agente_id, set_4p_id) VALUES (?, NULL)",
                    (_agente(con, "Nangong Yu"),))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO ajustes_usuario_build (agente_id, set_4p_id) VALUES (?, 99999)",
                    (_agente(con, "Nangong Yu"),))


def test_rebuild_conserva_las_cuatro(con):
    """El conocimiento es INVESTIGACION (el censo no lo recupera) y el build objetivo, DECLARADO."""
    sys.path.insert(0, str(RAIZ / "app" / "scripts"))
    try:
        import rebuild_account_db as r
    finally:
        sys.path.pop(0)
    for t in ("pj_sets_4pc", "pj_sets_2pc", "pj_stats_recomendados"):
        assert t in r.INVESTIGACION, t
    assert "ajustes_usuario_build" in r.DECLARADO
