"""R21 y la migración 45: un cambio no deja a un PJ por debajo del stat fijo que su kit necesita.

Caso 14 (SPEC, 2026-09-25): #151 a Gatillo (+1,06 por Daño Crítico) le bajaba 7,2 de Prob. Crítica,
que su habilidad adicional convierte en aturdimiento hasta 90 %. Daniel: "algunos PJ requieren un
stat fijo para aprovechar todo su potencial" (Astra Yao ATK, Zhao PV).
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from app.core.recommender import evaluar_cambio, evaluar_salida
from app.core.score_normalizer import ScoringContext
from app.core.stats_fijos import delta_conservador, rompe_stat_fijo
from app.db.repositories import AgentRepo, ArchetypeRepo, Disc

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
MIG_45 = RAIZ / "db" / "migrations" / "2026-09-25_45_stats_fijos_por_pj.sql"


def _d(slot, main, main_valor, subs=(), set_id=41, i=1):
    return Disc(id=i, set_id=set_id, slot=slot, main_stat=main, main_valor=main_valor, main_unidad=None,
                subs=[(n, v, None, r) for n, v, r in subs], nivel=15, equipado=1, agente_asignado=None)


# --- la cuenta ------------------------------------------------------------------------------

def test_prob_critica_suma_directo():
    antes = [_d(3, "DEF", 184, [("Prob. Crítica", 9.6, 3)])]
    despues = [_d(3, "DEF", 184, [("Prob. Crítica", 2.4, 0), ("Daño Crítico", 19.2, 3)])]
    assert delta_conservador("prob_critico", 75.4, antes, despues) == pytest.approx(-7.2)


def test_atk_porcentual_usa_una_cota_superior_de_la_base():
    """Total 3.419 con 30 % de ATK% y 316 plano en los discos → base ≤ (3419 − 316)/1,3 = 2.386,9;
    perder 6 % de ATK% se estima en −143,2 (la pérdida real sólo puede ser menor)."""
    antes = [_d(2, "ATK", 316), _d(5, "ATK%", 30, [("ATK%", 6.0, 1)])]
    despues = [_d(2, "ATK", 316), _d(5, "ATK%", 30)]
    base_max = (3419 - 316) / (1 + 0.36)
    assert delta_conservador("ataque", 3419, antes, despues) == pytest.approx(-0.06 * base_max)


def test_una_ganancia_porcentual_no_se_cuenta():
    antes = [_d(1, "HP", 2200, [("ATK", 38.0, 1)])]
    despues = [_d(1, "HP", 2200, [("ATK%", 9.0, 2)])]
    assert delta_conservador("ataque", 3000, antes, despues) == pytest.approx(-38.0)


class _PJ:
    def __init__(self, fijos, stats):
        self.stats_fijos, self.stats = fijos, stats


def test_rompe_si_baja_y_queda_por_debajo():
    antes = {3: _d(3, "DEF", 184, [("Prob. Crítica", 9.6, 3)])}
    despues = {3: _d(3, "DEF", 184, [("Prob. Crítica", 2.4, 0)])}
    assert rompe_stat_fijo(_PJ({"prob_critico": 90}, {"prob_critico": 75.4}), antes, despues) == "prob_critico"
    assert rompe_stat_fijo(_PJ({"prob_critico": 90}, {"prob_critico": 100.0}), antes, despues) is None
    assert rompe_stat_fijo(_PJ({"prob_critico": 90}, {"prob_critico": 75.4}), despues, antes) is None  # sube
    assert rompe_stat_fijo(_PJ({"prob_critico": 90}, {}), antes, despues) is None   # sin total: no juzga


# --- sobre la DB (copia con la migración 45) ------------------------------------------------

@pytest.fixture
def con(tmp_path):
    if not DB_REAL.is_file():
        pytest.skip("sin la DB de dominio")
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    c = sqlite3.connect(copia)
    c.execute("DROP TABLE IF EXISTS pj_stats_fijos")
    c.commit()
    c.close()
    sys.path.insert(0, str(RAIZ / "app" / "scripts" / "qa"))
    try:
        from apply_migration import aplicar
    finally:
        sys.path.pop(0)
    assert aplicar(MIG_45, copia, hacer_backup=False, dry_run=False) == 0
    c = sqlite3.connect(copia)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _agente(con, nombre):
    return next(a for a in AgentRepo(con).get_all() if a.nombre == nombre)


def test_la_migracion_carga_los_fijos_con_su_cuenta(con):
    filas = {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT a.nombre, f.stat, f.objetivo FROM pj_stats_fijos f JOIN agents a ON a.id = f.agente_id "
        "WHERE f.requiere_set_4p_id IS NULL")}
    assert filas[("Gatillo", "prob_critico")] == 90
    assert filas[("Astra Yao", "ataque")] == 3429
    assert filas[("Zhao", "pv")] == 27000
    assert con.execute("SELECT COUNT(*) FROM pj_stats_fijos WHERE cuenta = '' OR url = ''").fetchone()[0] == 0


def test_el_fijo_del_4pc_vale_solo_con_ese_4pc_objetivo(con):
    """Monarca del Pináculo pide 50 % de Prob. Crítica: Lycaon lo lleva; Gatillo (Armonía umbría,
    declarado) no, y le queda sólo el de su kit."""
    assert _agente(con, "Lycaon").stats_fijos == {"prob_critico": 50}
    assert _agente(con, "Gatillo").stats_fijos == {"prob_critico": 90}
    assert _agente(con, "Dialyn").stats_fijos["prob_critico"] == 100      # el mayor de los dos
    # Pulchra tiene Monarca en su guía pero su 4pc objetivo es otro (lo equipado): sin fijo.
    pulchra = _agente(con, "Pulchra")
    assert pulchra.set_4p_id != con.execute("SELECT id FROM disc_sets WHERE nombre = 'Monarca del Pináculo'").fetchone()[0]
    assert pulchra.stats_fijos == {}


def test_elegir_no_toma_un_cambio_que_rompe_un_fijo():
    from app.core.recommender import Cambio, _elegir

    class A:
        prioridad = "normal"
    rompe = Cambio(agente_id=1, agente_nombre="x", slot=3, delta=5.0, delta_disco=5.0, delta_sets=0.0,
                   rompe_stat_fijo="prob_critico")
    sano = Cambio(agente_id=2, agente_nombre="y", slot=3, delta=1.0, delta_disco=1.0, delta_sets=0.0)
    assert _elegir([(A(), None, rompe)]) is None
    assert _elegir([(A(), None, rompe), (A(), None, sano)])[2] is sano


def test_caso_14_no_se_le_baja_la_prob_critica_a_gatillo(con):
    gatillo = _agente(con, "Gatillo")
    arch = ArchetypeRepo(con).get_by_id(gatillo.arquetipo_primario_id)
    s4, s2 = gatillo.set_4p_id, gatillo.set_2p_id
    build = {1: _d(1, "HP", 2200, set_id=s4, i=1), 2: _d(2, "ATK", 316, set_id=s4, i=2),
             3: _d(3, "DEF", 184, [("Prob. Crítica", 9.6, 3), ("Perforación", 27.0, 2)], set_id=s4, i=3),
             4: _d(4, "Prob. Crítica", 24, set_id=s4, i=4), 5: _d(5, "ATK%", 30, set_id=s2, i=5),
             6: _d(6, "Impacto", 18, set_id=s2, i=6)}
    nuevo = _d(3, "DEF", 184, [("Daño Crítico", 19.2, 3), ("Prob. Crítica", 2.4, 0), ("ATK", 38.0, 1)],
               set_id=s4, i=151)
    cambio = evaluar_cambio(gatillo, arch, build, nuevo, ScoringContext(), lambda _: None)
    assert cambio.rompe_stat_fijo == "prob_critico"


def test_al_origen_no_se_le_saca_lo_que_le_sostiene_el_fijo(con):
    gatillo = _agente(con, "Gatillo")
    arch = ArchetypeRepo(con).get_by_id(gatillo.arquetipo_primario_id)
    s4 = gatillo.set_4p_id
    # El disco RESTA en puntaje (DEF% y PV que a Gatillo no le sirven): vaciar el slot "mejoraría",
    # pero le saca 2,4 de Prob. Crítica estando por debajo de 90.
    cr = _d(3, "DEF", 184, [("Prob. Crítica", 2.4, 0), ("DEF%", 14.4, 2), ("HP", 448.0, 3)], set_id=s4, i=3)
    build = {3: cr}
    salida = evaluar_salida(cr, gatillo, arch, build, [], ScoringContext(), lambda _: None)
    assert salida.mejor_delta < 0


def test_rebuild_la_conserva():
    sys.path.insert(0, str(RAIZ / "app" / "scripts"))
    try:
        import rebuild_account_db as r
    finally:
        sys.path.pop(0)
    assert "pj_stats_fijos" in r.INVESTIGACION
