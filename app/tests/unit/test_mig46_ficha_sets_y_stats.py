"""Migración 46: la ficha del PJ (niveles, principales y fijos del usuario) y las condiciones del 4pc.

Daniel, 2026-09-27: "el usuario no es que toque el motor, sino que al seleccionar un set y los stats
deseados influyen en los pesos de forma interna". Se guarda lo que ELIGE (niveles), no pesos.

Se corre el `.sql` REAL sobre una COPIA de la DB de dominio, llevada al estado de antes de la 46
(si ya se aplicó, se le quita): así el test vale antes y después de aplicarla a la DB real.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIGS = RAIZ / "db" / "migrations"
MIG_45 = MIGS / "2026-09-25_45_stats_fijos_por_pj.sql"
MIG_46 = MIGS / "2026-09-27_46_ficha_sets_y_stats.sql"
NUEVAS = ("ajustes_usuario_substats", "ajustes_usuario_principales", "ajustes_usuario_fijos",
          "set_condiciones_4pc")

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


def _aplicar(sql: Path, db: Path) -> int:
    sys.path.insert(0, str(RAIZ / "app" / "scripts" / "qa"))
    try:
        from apply_migration import aplicar
    finally:
        sys.path.pop(0)
    return aplicar(sql, db, hacer_backup=False, dry_run=False)


def _antes_de_la_46(db: Path) -> None:
    c = sqlite3.connect(db)
    for t in NUEVAS:
        c.execute(f"DROP TABLE IF EXISTS {t}")
    c.execute("""CREATE TABLE IF NOT EXISTS ajustes_usuario_pesos (
        agente_id INTEGER NOT NULL REFERENCES agents(id), substat TEXT NOT NULL,
        peso REAL NOT NULL CHECK (peso BETWEEN -1.0 AND 1.0),
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (agente_id, substat))""")
    c.execute("DROP TABLE IF EXISTS pj_stats_fijos")      # la 45 la vuelve a crear, con Monarca
    c.commit()
    c.close()
    assert _aplicar(MIG_45, db) == 0


@pytest.fixture
def con(tmp_path):
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    _antes_de_la_46(copia)
    antes = sqlite3.connect(copia)
    assert antes.execute("SELECT COUNT(*) FROM pj_stats_fijos WHERE requiere_set_4p_id IS NOT NULL"
                         ).fetchone()[0] == 8, "la premisa: la 45 copia Monarca en 8 PJs"
    antes.close()
    assert _aplicar(MIG_46, copia) == 0
    c = sqlite3.connect(copia)
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def test_las_condiciones_verificadas(con):
    filas = {(r[0], r[1], r[2], r[3], r[4]) for r in con.execute(
        "SELECT s.nombre_en, c.tipo, COALESCE(c.stat, c.rol, c.elemento), c.umbral, c.alcance "
        "FROM set_condiciones_4pc c JOIN disc_sets s ON s.id = c.set_id")}
    assert ("King of the Summit", "rol", "Aturdimiento", None, "todo") in filas
    assert ("King of the Summit", "stat", "prob_critico", 50, "parte") in filas
    assert ("Branch & Blade Song", "stat", "tasa_anomalia", 115, "parte") in filas
    assert ("Thorned Rose", "stat", "defensa", 1800, "parte") in filas
    assert ("The Sky Ablaze", "elemento", "Éter", None, "parte") in filas
    assert len(filas) == 10
    assert con.execute("SELECT COUNT(*) FROM set_condiciones_4pc WHERE url NOT LIKE "
                       "'https://zenless-zone-zero.fandom.com/wiki/%'").fetchone()[0] == 0


def test_monarca_vive_una_sola_vez(con):
    """B1: las 8 copias de la condición de Monarca en `pj_stats_fijos` se van."""
    assert con.execute("SELECT COUNT(*) FROM pj_stats_fijos WHERE requiere_set_4p_id IS NOT NULL"
                       ).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM pj_stats_fijos").fetchone()[0] == 16


def test_se_retira_el_peso_crudo(con):
    assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'ajustes_usuario_pesos'"
                       ).fetchone()[0] == 0


def test_la_cuenta_de_yuzuha_dice_tasa(con):
    (cuenta,) = con.execute("SELECT f.cuenta FROM pj_stats_fijos f JOIN agents a ON a.id = f.agente_id "
                            "WHERE a.nombre = 'Yuzuha' AND f.stat = 'tasa_anomalia'").fetchone()
    assert cuenta.startswith("Tasa de Anomalía")


def _pj(con, nombre="Ellen"):
    return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]


@pytest.mark.parametrize("sql, args", [
    ("INSERT INTO ajustes_usuario_substats (agente_id, substat, nivel) VALUES (?, 'DEF%', 5)", ()),
    ("INSERT INTO ajustes_usuario_substats (agente_id, substat, nivel) VALUES (?, 'Impacto', 1)", ()),
    ("INSERT INTO ajustes_usuario_principales (agente_id, slot, valor_json) VALUES (?, 3, '[\"DEF%\"]')", ()),
    ("INSERT INTO ajustes_usuario_principales (agente_id, slot, valor_json) VALUES (?, 4, 'DEF%')", ()),
    ("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'velocidad', 1)", ()),
])
def test_los_check_rechazan_lo_que_el_motor_no_sabe_leer(con, sql, args):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(sql, (_pj(con), *args))


def test_lo_que_si_se_puede_declarar(con):
    pj = _pj(con)
    con.execute("INSERT INTO ajustes_usuario_substats (agente_id, substat, nivel) VALUES (?, 'DEF%', 0)", (pj,))
    con.execute("INSERT INTO ajustes_usuario_principales (agente_id, slot, valor_json) "
                "VALUES (?, 4, '[\"Daño Crítico\"]')", (pj,))
    con.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'ataque', NULL)", (pj,))
    con.commit()


def test_una_condicion_de_stat_sin_umbral_no_entra(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO set_condiciones_4pc (set_id, tipo, stat, alcance, texto, fuente, url, "
                    "capturado) VALUES (34, 'stat', 'prob_critico', 'parte', 'x', 'x', 'x', '2026-09-27')")
