"""Migración 42: la prioridad de buildeo por PJ (alta / normal / baja), un ajuste de Daniel.

Daniel, 2026-09-23: "piper no la uso casi nada mientras que claret la quiero mejorar ahora"; y el
2026-09-24 eligió que la prioridad BLOQUEE mover un disco hacia un PJ de prioridad más baja, con 3
niveles, editable en la app. Esta migración es sólo la tabla; el motor y la UI van aparte.

Como en `test_ajustes_usuario.py`, se corre el `.sql` REAL sobre una COPIA de la DB de dominio (B1:
se prueba lo que se va a aplicar, no un DDL retipeado acá).
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_42 = RAIZ / "db" / "migrations" / "2026-09-24_42_prioridad_de_buildeo.sql"

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
    """Copia de la DB de dominio SIN la tabla (si ya se aplicó, se le quita) + la migración 42."""
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    c.execute("DROP TABLE IF EXISTS ajustes_usuario_prioridad")
    c.commit()
    c.close()
    assert _aplicar(MIG_42, copia) == 0
    c = sqlite3.connect(copia)
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def _id(con, nombre):
    return con.execute("SELECT id FROM agents WHERE nombre = ?", (nombre,)).fetchone()[0]


def test_nace_vacia_todos_en_normal(con):
    assert con.execute("SELECT COUNT(*) FROM ajustes_usuario_prioridad").fetchone()[0] == 0


def test_acepta_alta_y_baja(con):
    con.execute("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (?, 'alta')",
                (_id(con, "Claret Flint"),))
    con.execute("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (?, 'baja')",
                (_id(con, "Piper"),))
    filas = con.execute("SELECT prioridad, actualizado FROM ajustes_usuario_prioridad ORDER BY 1").fetchall()
    assert [f[0] for f in filas] == ["alta", "baja"]
    assert all(f[1] for f in filas), "el sello de cuándo se tocó se completa solo"


@pytest.mark.parametrize("valor", ["normal", "Alta", "media", ""])
def test_normal_no_se_guarda_y_nada_fuera_de_alta_baja(con, valor):
    """Normal es la AUSENCIA de fila: una sola forma de decirlo (B1)."""
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (?, ?)",
                    (_id(con, "Piper"), valor))


def test_una_sola_prioridad_por_pj(con):
    pid = _id(con, "Piper")
    con.execute("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (?, 'baja')", (pid,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (?, 'alta')", (pid,))


def test_no_acepta_un_pj_que_no_existe(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO ajustes_usuario_prioridad (agente_id, prioridad) VALUES (99999, 'alta')")


def test_no_toca_agents(tmp_path):
    """Es un ajuste del usuario: vive en su tabla, no en `agents` (que reescribe la captura)."""
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    c.execute("DROP TABLE IF EXISTS ajustes_usuario_prioridad")
    c.commit()
    antes = list(c.execute("SELECT * FROM agents ORDER BY id"))
    cols_antes = [r[1] for r in c.execute("PRAGMA table_info(agents)")]
    c.close()
    assert _aplicar(MIG_42, copia) == 0
    c = sqlite3.connect(copia)
    assert list(c.execute("SELECT * FROM agents ORDER BY id")) == antes
    assert [r[1] for r in c.execute("PRAGMA table_info(agents)")] == cols_antes
    c.close()
