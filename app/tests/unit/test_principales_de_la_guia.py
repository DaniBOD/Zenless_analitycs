"""Los principales de los discos 4-6 salen de la guía de CADA PJ (mig 43), con los ajustes de
Daniel al rol encima.

La guía de Nangong Yu (aturdidora) pide Competencia de Anomalía en el disco 4 y Anomaly Mastery en
el 6; el perfil STUN no los admitía, así que un disco que le sirve era "principal equivocado" (R9).
Los ajustes de Daniel siguen mandando: lo que agregó al rol se suma (mig 41, Tasa de Perforación en
el slot 5) y lo que le sacó se resta aunque la guía lo nombre (caso 6, PV % en el slot 4 de los
disruptores: la guía de Billy Estelar lo nombra).

Sobre una COPIA de la DB de dominio.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.core.scoring import principal_valido
from app.db.repositories import (
    AgentRepo, ArchetypeRepo, Disc, mezclar_principales, principales_de_la_guia,
)

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


def test_principales_de_la_guia_primera_build_todos_los_niveles():
    filas = [(5, "v1", "principal_4", "Prob. Crítica"), (5, "v1", "principal_4", "Maestría de Anomalía"),
             (5, "v1", "principal_6", "Impacto"), (5, "v2", "principal_4", "ATK%")]
    assert principales_de_la_guia(filas) == {5: {4: {"Prob. Crítica", "Maestría de Anomalía"}, 6: {"Impacto"}}}


def test_mezcla_suma_lo_agregado_y_resta_lo_quitado():
    guia = {"ATK%", "HP%", "Prob. Crítica"}
    default = ["HP%", "Prob. Crítica", "Daño Crítico"]
    ajustado = ["Prob. Crítica", "Daño Crítico", "Tasa de Perforación"]      # sacó HP%, agregó TP
    assert mezclar_principales(guia, default, ajustado) == ("ATK%", "Prob. Crítica", "Tasa de Perforación")
    assert mezclar_principales(guia, default, default) == tuple(sorted(guia))


@pytest.fixture
def con(tmp_path):
    if not DB_REAL.is_file():
        pytest.skip("sin la DB de dominio")
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _agente(con, nombre):
    return next(a for a in AgentRepo(con).get_all() if a.nombre == nombre)


def _disco(slot, main):
    return Disc(id=1, set_id=37, slot=slot, main_stat=main, main_valor=1.0, main_unidad=None,
                subs=[], nivel=15, equipado=0, agente_asignado=None)


def _valido(con, nombre, slot, main):
    a = _agente(con, nombre)
    return principal_valido(_disco(slot, main), ArchetypeRepo(con).get_by_id(a.arquetipo_primario_id), a)


def test_nangong_yu_su_disco_4_de_anomalia_sirve(con):
    assert _valido(con, "Nangong Yu", 4, "Maestría de Anomalía")
    assert _valido(con, "Nangong Yu", 6, "Tasa de Anomalía")
    assert not _valido(con, "Nangong Yu", 4, "Prob. Crítica")     # la guía no lo nombra


def test_lo_que_daniel_saco_al_rol_no_vuelve_por_la_guia(con):
    """Caso 6: sin PV % en el slot 4 de los disruptores, aunque la guía de Billy Estelar lo nombre."""
    assert not _valido(con, "Billy Estelar", 4, "HP%")
    assert _valido(con, "Billy Estelar", 4, "Prob. Crítica")


def test_lo_que_daniel_agrego_al_rol_se_suma(con):
    """Mig 41: Tasa de Perforación en el slot 5 de los atacantes. La guía de Harumasa no la nombra
    en el disco 5 ("ATK% > Electric DMG%") y se le suma igual."""
    harumasa = _agente(con, "Harumasa")
    guia = {r[0] for r in con.execute(
        "SELECT stat FROM pj_stats_recomendados WHERE agente_id = ? AND linea = 'principal_5'",
        (harumasa.id,))}
    assert guia == {"ATK%", "Bono Daño Eléctrico"}
    assert _valido(con, "Harumasa", 5, "Tasa de Perforación")
    assert not _valido(con, "Harumasa", 5, "HP%")


def test_sin_guia_del_slot_decide_el_rol(con):
    con.execute("DELETE FROM pj_stats_recomendados WHERE linea = 'principal_4' AND agente_id = "
                "(SELECT id FROM agents WHERE nombre = 'Nangong Yu')")
    con.commit()
    assert 4 not in _agente(con, "Nangong Yu").mains
    assert _valido(con, "Nangong Yu", 4, "Prob. Crítica")          # STUN admite crítico en el 4
