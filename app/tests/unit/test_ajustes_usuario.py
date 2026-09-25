"""Dos capas: los defaults (Prydwen…) y los ajustes de Daniel encima (etapa 1, paso 5 — mig 40).

Daniel: "Prydwen es una base, sí, pero de ahí puedo pulirlas yo a mano (estos serían los defaults
para todos los usuarios)". Las tablas de default no se tocan; los ajustes viven en tablas propias y
el repositorio los mezcla: **el ajuste gana, y si se borra la fila, vuelve el default**.

Los tests corren la migración 40 REAL sobre una COPIA de la DB de dominio (671 KB): así se prueba
el `.sql` que se va a aplicar, no un DDL retipeado en el test (B1).
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from app.db.repositories import (AgentRepo, ArchetypeRepo, Archetype, aplicar_ajustes_arquetipo,
                                 mezclar_pesos, rango_default)

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_40 = RAIZ / "db" / "migrations" / "2026-09-22_40_ajustes_del_usuario.sql"

pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


def _aplicar(sql: Path, db: Path) -> int:
    sys.path.insert(0, str(RAIZ / "app" / "scripts" / "qa"))
    try:
        from apply_migration import aplicar
    finally:
        sys.path.pop(0)
    return aplicar(sql, db, hacer_backup=False, dry_run=False)


@pytest.fixture
def db_sin_mig(tmp_path):
    """Copia de la DB de dominio TAL COMO ESTÁ: si ya tiene la migración 40, se le quitan las
    tablas, para probar las dos situaciones desde el mismo punto de partida."""
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    con = sqlite3.connect(copia)
    for t in ("ajustes_usuario_rangos", "ajustes_usuario_pesos", "ajustes_usuario_arquetipo"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.commit()
    con.close()
    return copia


@pytest.fixture
def db_con_mig(db_sin_mig):
    assert _aplicar(MIG_40, db_sin_mig) == 0, "la migración 40 falló sobre la copia"
    return db_sin_mig


def _con(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


def _agente(db: Path, nombre: str):
    return next(a for a in AgentRepo(_con(db)).get_all() if a.nombre == nombre)


def _arquetipo(db: Path, code: str) -> Archetype:
    return ArchetypeRepo(_con(db)).get_by_code(code)


# --- la mezcla ------------------------------------------------------------------------------

def test_el_ajuste_de_arquetipo_de_daniel_gana():
    """Caso 6: los disruptores en slot 4 = sólo Prob. Crítica y Daño Crítico (sale el PV %)."""
    default = Archetype(id=2, code="HP_DISRUPT", substats_positivos={}, substats_perjudiciales={},
                        threshold_stock=0.7, mains_4=["Prob. Crítica", "Daño Crítico", "HP%"])
    ajustado = aplicar_ajustes_arquetipo(default, {"mains_4": ["Prob. Crítica", "Daño Crítico"]})
    assert ajustado.mains_4 == ["Prob. Crítica", "Daño Crítico"]
    assert default.mains_4[-1] == "HP%", "el default NO se muta: es la otra capa"


def test_un_campo_que_no_es_ajustable_no_se_aplica():
    default = Archetype(id=1, code="X", substats_positivos={"ATK%": 1.0}, substats_perjudiciales={},
                        threshold_stock=0.7)
    assert aplicar_ajustes_arquetipo(default, {"substats_positivos": {}}) == default


def test_ajustar_un_peso_no_borra_los_demas():
    """Un PJ SIN pesos propios usa los de su arquetipo. Si se le ajusta UN stat y la base fuera
    'sus pesos propios' (vacíos), quedaría con ese único stat y todo lo demás valdría 0."""
    del_arquetipo = {"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0}
    assert mezclar_pesos({}, del_arquetipo, {"ATK%": 0.6}) == \
        {"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 0.6}


def test_sin_ajustes_los_pesos_quedan_como_estaban():
    assert mezclar_pesos({}, {"ATK%": 1.0}, {}) == {}          # el scoring cae solo al arquetipo
    assert mezclar_pesos({"ATK%": 0.8}, {"ATK%": 1.0}, {}) == {"ATK%": 0.8}


@pytest.mark.parametrize("fila,esperado", [
    ((2400, 2800, None), (2400, 2800)),       # Prydwen casi nunca da el máximo: el óptimo es techo
    ((2400, 2800, 3000), (2400, 3000)),
    ((None, None, None), None),
    ((60, None, None), (60, None)),
])
def test_rango_default(fila, esperado):
    assert rango_default(*fila) == esperado


# --- sobre la DB real ------------------------------------------------------------------------

def test_sin_la_migracion_todo_sigue_como_antes(db_sin_mig):
    """Una DB anterior a la 40 no rompe nada: sólo defaults."""
    assert "HP%" in _arquetipo(db_sin_mig, "HP_DISRUPT").mains_4
    assert _agente(db_sin_mig, "Ellen").rangos["ataque"] == (2400, 2800)


def test_con_la_migracion_ganan_los_ajustes(db_con_mig):
    assert _arquetipo(db_con_mig, "HP_DISRUPT").mains_4 == ["Prob. Crítica", "Daño Crítico"]
    assert _agente(db_con_mig, "Ellen").rangos["ataque"] == (3000, 3200)


def test_borrar_el_ajuste_devuelve_el_default(db_con_mig):
    """La promesa de las dos capas: el default nunca se perdió, sólo quedó tapado."""
    con = sqlite3.connect(db_con_mig)
    con.execute("DELETE FROM ajustes_usuario_rangos")
    con.execute("DELETE FROM ajustes_usuario_arquetipo")
    con.commit()
    con.close()
    assert _agente(db_con_mig, "Ellen").rangos["ataque"] == (2400, 2800)
    assert "HP%" in _arquetipo(db_con_mig, "HP_DISRUPT").mains_4


def test_un_ajuste_de_peso_llega_al_agente_sin_borrar_el_resto(db_con_mig):
    # Contra los pesos de ANTES del ajuste, no contra números fijos: la base es la guía del PJ
    # (mig 43) y cambia cuando se recaptura. Lo que se cuida es que un ajuste pise SU stat y nada más.
    antes = _agente(db_con_mig, "Ellen").substat_preferences
    con = sqlite3.connect(db_con_mig)
    ellen_id = con.execute("SELECT id FROM agents WHERE nombre='Ellen'").fetchone()[0]
    con.execute("INSERT INTO ajustes_usuario_pesos (agente_id, substat, peso) VALUES (?, 'ATK%', 1.0)",
                (ellen_id,))
    con.commit()
    con.close()
    pesos = _agente(db_con_mig, "Ellen").substat_preferences
    assert antes["ATK%"] != 1.0 and pesos["ATK%"] == 1.0
    assert {k: v for k, v in pesos.items() if k != "ATK%"} == {k: v for k, v in antes.items() if k != "ATK%"}
    assert "Prob. Crítica" in pesos and "Perforación" in pesos


@pytest.mark.parametrize("sql", [
    "INSERT INTO ajustes_usuario_rangos (agente_id, stat, minimo, maximo) VALUES (1, 'x', 3200, 3000)",
    "INSERT INTO ajustes_usuario_rangos (agente_id, stat, minimo, maximo) VALUES (1, 'x', NULL, NULL)",
    "INSERT INTO ajustes_usuario_pesos (agente_id, substat, peso) VALUES (1, 'ATK%', 1.5)",
    "INSERT INTO ajustes_usuario_arquetipo (code, campo, valor_json) VALUES ('ATK_DPS', 'threshold_stock', '[1]')",
    "INSERT INTO ajustes_usuario_arquetipo (code, campo, valor_json) VALUES ('ATK_DPS', 'mains_4', '\"ATK%\"')",
])
def test_la_db_rechaza_un_ajuste_invalido(db_con_mig, sql):
    """Las reglas viven en el esquema, no en quien lee: piso ≤ techo, algún borde, peso en
    [-1, 1], sólo campos ajustables, y una LISTA de principales."""
    con = sqlite3.connect(db_con_mig)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(sql)
    con.close()


def test_rebuild_conserva_los_ajustes():
    """`rebuild_account_db` falla a propósito si una tabla no está clasificada; éstas son
    declaraciones del usuario y vaciarlas sería perder sus decisiones."""
    sys.path.insert(0, str(RAIZ / "app" / "scripts"))
    try:
        import rebuild_account_db as rb
    finally:
        sys.path.pop(0)
    for t in ("ajustes_usuario_rangos", "ajustes_usuario_pesos", "ajustes_usuario_arquetipo"):
        assert t in rb.DECLARADO, t
        assert t not in rb.VACIAR
