"""El asesor de coherencia de la ficha (SPEC 2026-09-27, parte 3): avisa, nunca bloquea.

Daniel (2026-09-25): "si el usuario ajusta una substat de Ellen a DEF% como prioritario lo puede
hacer, pero que el sistema le diga 'Oye, esto no te beneficia en nada, te recomiendo Daño y
Probabilidad crítica'". Y sus builds propias de Grace y Gatillo tienen que "tener sentido".
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from app.core.coherencia import AVISO, INFO, EleccionPJ, GuiaPJ, avisos
from app.core.ficha_pj import avisos_de
from app.db.repositories import AgentRepo, CondicionSet, agentes_cambiaron

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_46 = RAIZ / "db" / "migrations" / "2026-09-27_46_ficha_sets_y_stats.sql"

GUIA_ELLEN = GuiaPJ(niveles={"Daño Crítico": 1, "Prob. Crítica": 2, "ATK%": 3, "ATK": 4, "Perforación": 4},
                    principales={4: {"Daño Crítico"}, 5: {"Tasa de Perforación", "Bono Daño Hielo"},
                                 6: {"ATK%"}},
                    sets_4pc=(38, 24), dos_por_4pc={38: {40}, 24: {38}})
NANA, MONARCA, FIRMAMENTO = 35, 34, 53
CONDS = [CondicionSet(NANA, "rol", rol="Soporte", alcance="todo"),
         CondicionSet(MONARCA, "rol", rol="Aturdimiento", alcance="todo"),
         CondicionSet(MONARCA, "stat", stat="prob_critico", umbral=50, alcance="parte"),
         CondicionSet(FIRMAMENTO, "elemento", elemento="Éter", alcance="parte", texto="Daño Crítico +30 %")]


def _a(eleccion=None, guia=GUIA_ELLEN, **kw):
    base = dict(rol="Ataque", elemento="Hielo", set_4p_id=38, set_2p_id=40, condiciones=CONDS,
                stats={}, stats_fijos={}, sets={38: "Metal polar", 24: "Voz Astral", 35: "Nana",
                                                  34: "Monarca", 53: "Firmamento", 40: "Tecno"})
    base.update(kw)
    return avisos("Ellen", guia, eleccion or EleccionPJ(), **base)


def _tipos(avs, severidad=None):
    return [a.tipo for a in avs if severidad is None or a.severidad == severidad]


def test_sin_elecciones_no_hay_avisos():
    assert _a() == []


def test_ellen_con_def_pct_imprescindible():
    avs = _a(EleccionPJ(niveles={"DEF%": 1}))
    assert _tipos(avs) == ["substat_no_te_beneficia"] and avs[0].severidad == AVISO
    assert "DEF% no le suma nada a Ellen" in avs[0].texto
    assert "Daño Crítico y Prob. Crítica" in avs[0].texto          # "te recomiendo Daño y Prob."


def test_no_sirve_a_un_imprescindible():
    assert _tipos(_a(EleccionPJ(niveles={"Daño Crítico": 0}))) == ["imprescindible_descartado"]


def test_bajar_un_nivel_no_es_un_aviso():
    """Poner la Prob. Crítica en "Bueno" es una decisión, no un error."""
    assert _a(EleccionPJ(niveles={"Prob. Crítica": 3, "ATK": 0})) == []


def test_descartar_lo_que_la_guia_no_nombra_es_coherente():
    """DEF% en "no sirve" para Ellen: coincide con la guía, no hay nada que avisar."""
    assert _a(EleccionPJ(niveles={"DEF%": 0, "HP": 0})) == []


def test_principal_fuera_de_la_guia():
    avs = _a(EleccionPJ(principales={4: ("DEF%", "Daño Crítico")}))
    assert _tipos(avs, AVISO) == ["principal_fuera_de_guia"] and "DEF%" in avs[0].texto


def test_un_4pc_de_otro_rol_no_se_activa():
    assert "4pc_no_se_activa" in _tipos(_a(set_4p_id=NANA), AVISO)
    assert _a(set_4p_id=NANA, rol="Soporte") == []


def test_un_4pc_a_medias_es_informativo():
    avs = _a(set_4p_id=FIRMAMENTO)
    assert _tipos(avs) == ["4pc_a_medias"] and avs[0].severidad == INFO and "Daño Crítico +30 %" in avs[0].texto


def test_un_build_fuera_de_la_guia_es_informativo():
    avs = _a(EleccionPJ(set_4p_id=41, set_2p_id=48), set_4p_id=41, set_2p_id=48)
    assert _tipos(avs) == ["set_fuera_de_guia"] and avs[0].severidad == INFO
    avs = _a(EleccionPJ(set_4p_id=38, set_2p_id=24), set_2p_id=24)       # 4pc de la guía, 2pc no
    assert _tipos(avs) == ["set_fuera_de_guia"]


def test_la_condicion_del_set_y_el_fijo_que_se_busca():
    avs = _a(rol="Aturdimiento", set_4p_id=MONARCA, stats={"prob_critico": 48.2},
             stats_fijos={"prob_critico": 50})
    assert _tipos(avs, INFO) == ["condicion_como_fijo", "fijo_se_busca"] and not _tipos(avs, AVISO)
    assert "48,2 de 50 (faltan 1,8)" in avs[1].texto


def test_un_pj_sin_guia_solo_ve_lo_del_set():
    avs = _a(EleccionPJ(niveles={"DEF%": 1}), guia=GuiaPJ(), set_4p_id=NANA)
    assert _tipos(avs) == ["4pc_no_se_activa"]


# --- con los datos reales (copia) ---------------------------------------------------------------

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


@pytest.mark.parametrize("nombre", ["Grace", "Gatillo"])
def test_los_builds_de_daniel_tienen_sentido(con, nombre):
    """Sus builds declarados (fuera de la guía) dan sólo informativos, ningún "no te beneficia"."""
    avs = avisos_de(con, _pj(con, nombre))
    assert not [a for a in avs if a.severidad == AVISO], avs
    assert "set_fuera_de_guia" in _tipos(avs, INFO)


def test_ellen_real_con_def_pct(con):
    ellen = _pj(con, "Ellen")
    con.execute("INSERT INTO ajustes_usuario_substats (agente_id, substat, nivel) VALUES (?, 'DEF%', 1)",
                (ellen.id,))
    con.commit()
    avs = avisos_de(con, _pj(con, "Ellen"))
    no_sirve = [a for a in avs if a.tipo == "substat_no_te_beneficia"]
    assert len(no_sirve) == 1 and "Daño Crítico" in no_sirve[0].texto
