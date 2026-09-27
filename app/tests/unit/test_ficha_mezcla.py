"""La ficha del PJ se vuelve motor (SPEC 2026-09-27, parte 2): niveles → pesos, principales por slot,
fijos del kit + del set + del usuario, y los 2pc alternativos de la guía (R24).

Daniel: "el usuario no es que toque el motor, sino que al seleccionar un set y los stats deseados
influyen en los pesos de forma interna".
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from app.db.repositories import (AgentRepo, CondicionSet, _alternativas_2pc, agentes_cambiaron,
                                 cumple_condiciones_4pc, fijos_del_pj, peso_de_nivel_usuario)

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_46 = RAIZ / "db" / "migrations" / "2026-09-27_46_ficha_sets_y_stats.sql"

MONARCA = 34
CONDS = [
    CondicionSet(MONARCA, "rol", rol="Aturdimiento", alcance="todo"),
    CondicionSet(MONARCA, "stat", stat="prob_critico", umbral=50, alcance="parte"),
    CondicionSet(53, "elemento", elemento="Éter", alcance="parte"),
]


# --- funciones puras -----------------------------------------------------------------------------

def test_niveles_a_pesos():
    assert [peso_de_nivel_usuario(n) for n in (1, 2, 3, 4, 0)] == [1.0, 0.8, 0.6, 0.4, 0.0]


def test_el_fijo_del_set_vale_si_cumple_el_rol():
    assert fijos_del_pj({}, CONDS, {}, MONARCA, "Aturdimiento") == {"prob_critico": 50}
    assert fijos_del_pj({}, CONDS, {}, MONARCA, "Ataque") == {}          # Monarca no se activa
    assert fijos_del_pj({}, CONDS, {}, 41, "Aturdimiento") == {}          # otro 4pc objetivo


def test_kit_y_set_el_mayor():
    """Dialyn: 100 por su kit, 50 por Monarca → 100."""
    assert fijos_del_pj({"prob_critico": 100}, CONDS, {}, MONARCA, "Aturdimiento") == {"prob_critico": 100}


def test_el_usuario_pone_cambia_y_desactiva():
    kit = {"ataque": 3429}
    assert fijos_del_pj(kit, CONDS, {"ataque": 3200}, None) == {"ataque": 3200}
    assert fijos_del_pj(kit, CONDS, {"ataque": None}, None) == {}
    assert fijos_del_pj(kit, CONDS, {"pv": 20000}, None) == {"ataque": 3429, "pv": 20000}
    assert fijos_del_pj({}, CONDS, {"prob_critico": None}, MONARCA, "Aturdimiento") == {}


def test_una_condicion_de_parte_no_apaga_el_4pc():
    """Firmamento: el elemento gobierna sólo una PARTE; no decide si el 4pc "vale"."""
    assert cumple_condiciones_4pc(CONDS, 53, "Ataque", "Fuego")
    assert not cumple_condiciones_4pc(CONDS, MONARCA, "Ataque", "Fuego")
    assert cumple_condiciones_4pc(CONDS, MONARCA, None, None)          # sin dato no se juzga


def test_alternativas_2pc_en_orden_sin_el_actual():
    """Ju Fufu con Monarca: 1 Disco Sacudestrellas (rec), 2 Tecno Pícido, 3 Voz Astral / Punk
    Hormonal, 4 Jazz Oscilante."""
    dos = [(3, 24, False), (1, 43, True), (4, 45, False), (2, 48, False), (3, 32, False)]
    assert _alternativas_2pc(dos, 43) == ((48,), (24, 32), (45,))
    assert _alternativas_2pc(dos, 48) == ((43,), (24, 32), (45,))
    assert _alternativas_2pc([], None) == ()


# --- sobre la DB (copia con la 46) ---------------------------------------------------------------

@pytest.fixture
def con(tmp_path):
    if not DB_REAL.is_file():
        pytest.skip("sin la DB de dominio")
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    ya = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'set_condiciones_4pc'").fetchone()[0]
    c.close()
    if not ya:
        sys.path.insert(0, str(RAIZ / "app" / "scripts" / "qa"))
        try:
            from apply_migration import aplicar
        finally:
            sys.path.pop(0)
        assert aplicar(MIG_46, copia, hacer_backup=False, dry_run=False) == 0
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    for t in ("ajustes_usuario_substats", "ajustes_usuario_principales", "ajustes_usuario_fijos"):
        c.execute(f"DELETE FROM {t}")
    c.commit()
    yield c
    c.close()


def _pj(con, nombre):
    agentes_cambiaron()
    return next(a for a in AgentRepo(con).get_all() if a.nombre == nombre)


def test_monarca_sigue_dando_su_fijo_desde_la_condicion(con):
    """Lo que antes eran 8 copias en `pj_stats_fijos` sale ahora de `set_condiciones_4pc`."""
    assert _pj(con, "Lycaon").stats_fijos == {"prob_critico": 50}
    assert _pj(con, "Dialyn").stats_fijos["prob_critico"] == 100
    assert _pj(con, "Gatillo").stats_fijos == {"prob_critico": 90}      # Armonía umbría, no Monarca


def test_el_nivel_del_usuario_pisa_a_la_guia_y_borrarlo_la_devuelve(con):
    ellen = _pj(con, "Ellen")
    guia = dict(ellen.substat_preferences)
    con.execute("INSERT INTO ajustes_usuario_substats (agente_id, substat, nivel) VALUES (?, 'DEF%', 1)",
                (ellen.id,))
    con.commit()
    assert _pj(con, "Ellen").substat_preferences["DEF%"] == 1.0
    con.execute("DELETE FROM ajustes_usuario_substats")
    con.commit()
    assert _pj(con, "Ellen").substat_preferences == guia


def test_los_principales_del_usuario_reemplazan_ese_slot(con):
    ellen = _pj(con, "Ellen")
    slot5 = ellen.mains.get(5)
    con.execute("INSERT INTO ajustes_usuario_principales (agente_id, slot, valor_json) "
                "VALUES (?, 4, '[\"Prob. Crítica\"]')", (ellen.id,))
    con.commit()
    despues = _pj(con, "Ellen").mains
    assert despues[4] == ("Prob. Crítica",) and despues.get(5) == slot5


def test_el_fijo_del_usuario_llega_al_motor(con):
    astra = _pj(con, "Astra Yao")
    con.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'ataque', NULL)",
                (astra.id,))
    con.commit()
    assert "ataque" not in _pj(con, "Astra Yao").stats_fijos


def test_el_agente_trae_rol_y_alternativas(con):
    anby = _pj(con, "Anby")
    assert anby.rol == "Aturdimiento"
    assert anby.set_2p_id not in {s for g in anby.alternativas_2pc for s in g}
