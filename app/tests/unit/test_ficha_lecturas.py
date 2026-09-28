"""Las lecturas de la página del PJ (SPEC 2026-09-28, parte 3) — sobre una COPIA de la DB real.

- `renglones_2pc`: los 2pc de la guía por 4pc, EN ORDEN de `grupo`, con el recomendado (el orden
  es el que usa R24; `leer_guia_pj` los guarda como conjunto y lo pierde).
- `fijos_de_la_ficha`: cada fijo con su origen (kit / set / tuyo), lo de la guía y lo leído. Los
  objetivos vivos tienen que ser EXACTAMENTE los que usa el motor (`agent.stats_fijos`, B1).
- `principales_validos`: los del slot, y en el 5 sólo el bono del elemento del PJ.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.core.ficha_pj import fijos_de_la_ficha, principales_validos, renglones_2pc
from app.core.stats_vocab import CANONICAL_MAINS_VARIABLE
from app.db.repositories import AgentRepo, agentes_cambiaron

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


@pytest.fixture
def copia(tmp_path):
    destino = tmp_path / "copia.db"
    shutil.copy(DB_REAL, destino)
    con = sqlite3.connect(destino)
    con.row_factory = sqlite3.Row
    agentes_cambiaron()
    yield con
    con.close()
    agentes_cambiaron()


def _ids(con) -> dict[str, int]:
    out = {r[1]: r[0] for r in con.execute("SELECT id, nombre FROM disc_sets")}
    out.update({r[1]: r[0] for r in con.execute("SELECT id, nombre FROM agents")})
    return out


def _fijos(con, nombre: str) -> dict:
    return {f.stat: f for f in fijos_de_la_ficha(con, AgentRepo(con).get_by_id(_ids(con)[nombre]))}


def test_renglones_de_ju_fufu_con_monarca(copia):
    ids = _ids(copia)
    r = renglones_2pc(copia, ids["Ju Fufu"])[ids["Monarca del Pináculo"]]
    assert [x.grupo for x in r] == [1, 2, 3, 4]
    assert r[0].recomendado == ids["Disco Sacudestrellas"] and r[0].sets == (ids["Disco Sacudestrellas"],)
    assert set(r[2].sets) == {ids["Voz Astral"], ids["Punk Hormonal"]} and r[2].recomendado is None


def test_el_fijo_del_set_con_su_origen_y_lo_leido(copia):
    f = _fijos(copia, "Anby")["prob_critico"]
    assert (f.objetivo, f.origen, f.de_la_guia, f.actual) == (50, "set", 50, 48.2)


def test_kit_y_set_vale_el_mayor_con_ese_origen(copia):
    f = _fijos(copia, "Dialyn")["prob_critico"]          # 100 del kit, 50 de Monarca
    assert (f.objetivo, f.origen, f.de_la_guia) == (100, "kit", 100)


def test_empate_entre_kit_y_set_se_muestra_como_del_kit(copia):
    """Ningún PJ real empata hoy: se arma en la copia (Anby con un kit de Prob. Crítica 50)."""
    a = _ids(copia)["Anby"]
    copia.execute("INSERT INTO pj_stats_fijos (agente_id, stat, objetivo, cuenta, fuente, url, capturado) "
                  "VALUES (?, 'prob_critico', 50, 'prueba', 'prueba', 'prueba', '2026-09-28')", (a,))
    agentes_cambiaron()
    f = _fijos(copia, "Anby")["prob_critico"]
    assert (f.objetivo, f.origen) == (50, "kit")


def test_el_fijo_del_4pc_solo_vale_para_el_rol_que_lo_gobierna(copia):
    """Monarca pide Prob. Crítica 50 sólo a un Aturdimiento. Todos los que lo usan hoy lo son: se
    declara Monarca a Ellen (Ataque) en la copia."""
    ids = _ids(copia)
    copia.execute("INSERT INTO ajustes_usuario_build (agente_id, set_4p_id, set_2p_id) VALUES (?, ?, NULL)",
                  (ids["Ellen"], ids["Monarca del Pináculo"]))
    agentes_cambiaron()
    ellen = AgentRepo(copia).get_by_id(ids["Ellen"])
    assert ellen.set_4p_id == ids["Monarca del Pináculo"]
    assert "prob_critico" not in {f.stat for f in fijos_de_la_ficha(copia, ellen)}


def test_el_del_usuario_reemplaza_y_el_desactivado_queda_listado(copia):
    a = _ids(copia)["Anby"]
    copia.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'prob_critico', NULL)", (a,))
    copia.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'ataque', 2000)", (a,))
    agentes_cambiaron()
    f = _fijos(copia, "Anby")
    assert (f["prob_critico"].objetivo, f["prob_critico"].origen, f["prob_critico"].de_la_guia) == (None, "set", 50)
    assert (f["ataque"].objetivo, f["ataque"].origen, f["ataque"].de_la_guia) == (2000, "tuyo", None)


def test_un_objetivo_del_usuario_sobre_la_guia_es_tuyo_y_recuerda_la_guia(copia):
    a = _ids(copia)["Anby"]
    copia.execute("INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, 'prob_critico', 55)", (a,))
    agentes_cambiaron()
    f = _fijos(copia, "Anby")["prob_critico"]
    assert (f.objetivo, f.origen, f.de_la_guia) == (55, "tuyo", 50)


def test_una_sola_autoridad_con_el_motor(copia):
    agentes = AgentRepo(copia).get_all()
    assert len(agentes) >= 52
    for a in agentes:
        vivos = {f.stat: f.objetivo for f in fijos_de_la_ficha(copia, a) if f.objetivo is not None}
        assert vivos == a.stats_fijos, a.nombre


def test_principales_validos_por_elemento():
    hielo = principales_validos(5, "Hielo")
    assert "Bono Daño Hielo" in hielo
    assert [p for p in hielo if p.startswith("Bono Daño")] == ["Bono Daño Hielo"]
    assert not any(p.startswith("Bono Daño") for p in principales_validos(5, "Lumen"))
    assert principales_validos(4, None) == tuple(sorted(CANONICAL_MAINS_VARIABLE[4]))
    assert principales_validos(6, "Hielo") == tuple(sorted(CANONICAL_MAINS_VARIABLE[6]))
