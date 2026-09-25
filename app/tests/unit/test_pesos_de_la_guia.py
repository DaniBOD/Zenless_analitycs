"""Los pesos de los substats salen de la guía de CADA PJ (mig 43), no de su rol.

Caso 13 (SPEC, 2026-09-25): el motor le mandaba a Nangong Yu un disco de crítico (+6,12) porque la
trataba como aturdidora estándar (perfil STUN, Prob. Crítica 1,13). Su guía: "Anomaly Proficiency >
ATK% > PEN > ATK", ni un crítico. Daniel aceptó la escala 1,0 / 0,8 / 0,6 / 0,4 por nivel y que lo que
la guía no nombra valga 0; sus ajustes (`ajustes_usuario_pesos`) siguen ganando.

Sobre una COPIA de la DB de dominio (la guía cargada el 2026-09-25).
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.core.scoring import _pesos
from app.db.repositories import AgentRepo, ArchetypeRepo, pesos_de_la_guia, peso_de_nivel

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


def test_escala_por_nivel():
    assert [peso_de_nivel(n) for n in (1, 2, 3, 4, 7)] == [1.0, 0.8, 0.6, 0.4, 0.4]


def test_vale_la_primera_build_de_la_guia():
    """César trae dos builds sin rótulo (crítico / anomalía): vale la primera."""
    filas = [(5, "variante 1", 1, "Prob. Crítica"), (5, "variante 1", 2, "ATK%"),
             (5, "variante 2", 1, "Maestría de Anomalía"), (5, "variante 2", 2, "ATK%")]
    assert pesos_de_la_guia(filas) == {5: {"Prob. Crítica": 1.0, "ATK%": 0.8}}


@pytest.fixture
def con(tmp_path):
    if not DB_REAL.is_file():
        pytest.skip("sin la DB de dominio")
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    c.execute("DELETE FROM ajustes_usuario_pesos")
    c.commit()
    yield c
    c.close()


def _agente(con, nombre):
    return next(a for a in AgentRepo(con).get_all() if a.nombre == nombre)


def test_nangong_yu_sin_critico(con):
    """Caso 13: los pesos de Nangong son los de su guía; el crítico no suma."""
    p = _agente(con, "Nangong Yu").substat_preferences
    assert p == {"Maestría de Anomalía": 1.0, "ATK%": 0.8, "Perforación": 0.6, "ATK": 0.4}


def test_el_rol_no_penaliza_lo_que_la_guia_valora(con):
    """STUN castiga la Competencia de Anomalía (-0,8) y DEFENSE el ATK% (-0,8); a Nangong y a Pan
    Yinhu su guía se los pone primeros."""
    arqs = ArchetypeRepo(con)
    nangong, pan = _agente(con, "Nangong Yu"), _agente(con, "Pan Yinhu")
    _, neg_n = _pesos(nangong, arqs.get_by_id(nangong.arquetipo_primario_id))
    _, neg_p = _pesos(pan, arqs.get_by_id(pan.arquetipo_primario_id))
    assert "Maestría de Anomalía" not in neg_n and "DEF%" in neg_n
    assert "ATK%" not in neg_p


def test_sin_substats_en_la_guia_sigue_el_default(con):
    """Zhao: su guía no da prioridad de substats (hueco, RNF-02). No tiene pesos propios y el
    scoring usa los de su rol: no queda sin pesos."""
    zhao = _agente(con, "Zhao")
    assert zhao.substat_preferences == {}
    pos, _ = _pesos(zhao, ArchetypeRepo(con).get_by_id(zhao.arquetipo_primario_id))
    assert pos and max(pos.values()) > 0


def test_el_ajuste_de_daniel_gana_sobre_la_guia(con):
    nangong = _agente(con, "Nangong Yu")
    con.execute("INSERT INTO ajustes_usuario_pesos (agente_id, substat, peso) VALUES (?, 'DEF%', 0.5)",
                (nangong.id,))
    con.commit()
    p = _agente(con, "Nangong Yu").substat_preferences
    assert p["DEF%"] == 0.5 and p["Maestría de Anomalía"] == 1.0   # la base es la guía, no el rol
