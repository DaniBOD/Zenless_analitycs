"""La decisión compara contra lo que el PJ ya tiene, y el set se mide en el BUILD (etapa 1, paso 3).

Las respuestas de Daniel fueron todas comparativas —"¿cuál le equipás?", "¿le gana al que
tiene?"— y el recomendador decidía por un umbral absoluto, sin mirar el slot del PJ. Además el set
entraba como un atributo del DISCO, cuando un set sólo vale algo al juntar 2 o 4 piezas en un build.

Reglas de Daniel que se cuidan acá:
  - R5 · el 4pc casi no se rompe ("salvo secundarios excelentes, y sería muy puntual");
  - R6/R7 · el 2pc sí se rompe, y es lo normal: "el 2pc son sólo stats";
  - R10 · un slot vacío se tapa con cualquier disco decente (el "relleno temporal").
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from app.core.recommender import VALOR_4PC_FRACCION, evaluar_cambio, recomendar, valor_sets
from app.core.score_normalizer import ScoringContext
from app.core.stats_vocab import VALOR_POR_MEJORA, bono_2pc_como_substat
from app.db.repositories import Agent, Archetype, Disc

CTX = ScoringContext()
DPS_ARCH = Archetype(
    id=1, code="ATK_DPS",
    substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0, "ATK": 0.4,
                        "Perforación": 0.7},
    substats_perjudiciales={"DEF": -0.8, "HP": -0.5},
    threshold_stock=0.7,
    mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"], mains_5=["ATK%"], mains_6=["ATK%"],
)
DPS = Agent(id=7, nombre="dps", arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
            threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={})

TECNO_PICIDO, METAL_POLAR, OTRO = 48, 38, 27
BONOS = {TECNO_PICIDO: ("Prob. Crítica", 8.0)}          # Metal polar (Daño Hielo) no es secundario


def _bono(set_id):
    return BONOS.get(set_id)


def _disco(slot, set_id, subs=(), main=None, nivel=15, disc_id=None, equipado=0, dueno=None):
    return Disc(id=disc_id if disc_id is not None else 100 + slot, set_id=set_id, slot=slot,
                main_stat=main, main_valor=None, main_unidad=None,
                subs=[(s, None, None, m) for s, m in subs], nivel=nivel, equipado=equipado,
                agente_asignado=dueno)


def _build_4_2(slot_mediocre_subs=(("HP", 2),)):
    """4pc Metal polar en 1-4 y 2pc Tecno Pícido en 5-6; el slot 2 con una línea muerta."""
    b = {s: _disco(s, METAL_POLAR) for s in (1, 3, 4)}
    b[2] = _disco(2, METAL_POLAR, subs=slot_mediocre_subs)
    b[5] = _disco(5, TECNO_PICIDO)
    b[6] = _disco(6, TECNO_PICIDO)
    return b


# --- el 2pc son stats (R7) ---------------------------------------------------------------

def test_el_2pc_vale_sus_stats_en_mejoras():
    """Tecno Pícido +8 % Prob. Crítica = 8 / 2,4 = 3,33 mejoras de CR, al peso que el PJ le da."""
    v, notas = valor_sets(Counter({TECNO_PICIDO: 2}), DPS, DPS_ARCH, _bono)
    assert v == pytest.approx(8.0 / 2.4 * 1.0)
    assert notas == []


def test_un_2pc_que_no_es_un_secundario_no_se_inventa_y_se_anota():
    v, notas = valor_sets(Counter({METAL_POLAR: 2}), DPS, DPS_ARCH, _bono)
    assert v == 0.0
    assert notas and "sin modelar" in notas[0]


def test_romper_el_2pc_se_paga_con_sus_stats():
    build = _build_4_2()
    nuevo = _disco(6, OTRO, subs=[("Prob. Crítica", 1)], main="ATK%")
    c = evaluar_cambio(DPS, DPS_ARCH, build, nuevo, CTX, _bono)
    assert c.delta_sets == pytest.approx(-8.0 / 2.4)
    assert not c.rompe_4pc


# --- el 4pc casi no se rompe (R5) --------------------------------------------------------

def test_romper_el_4pc_cuesta_una_fraccion_del_mejor_disco_posible():
    build = _build_4_2()
    nuevo = _disco(2, OTRO, subs=[("Prob. Crítica", 2), ("Daño Crítico", 2), ("ATK%", 1),
                                  ("Perforación", 0)])
    c = evaluar_cambio(DPS, DPS_ARCH, build, nuevo, CTX, _bono)
    mejor_posible = (1.0 + 1.0 + 1.0 + 0.7) + 5 * 1.0
    assert c.rompe_4pc
    assert c.delta_sets == pytest.approx(-VALOR_4PC_FRACCION * mejor_posible)


def test_completar_el_4pc_suma_lo_mismo_que_romperlo_resta():
    build = _build_4_2()
    build[4] = _disco(4, OTRO)                  # 3 piezas de Metal polar: sin 4pc
    nuevo = _disco(4, METAL_POLAR)
    c = evaluar_cambio(DPS, DPS_ARCH, build, nuevo, CTX, _bono)
    assert c.completa_4pc and not c.rompe_4pc
    assert c.delta_sets > 0


# --- el set se cuenta UNA vez: en el build ---------------------------------------------------

def test_el_disco_solo_no_cobra_su_set():
    """Si el disco también cobrara su set, un 4pc se contaría dos veces: en el disco y en el
    build. Dos discos iguales salvo el set valen lo mismo por sí mismos, aunque uno sea del 4pc
    del PJ."""
    from dataclasses import replace

    from app.core.recommender import valor_disco
    con_4pc = replace(DPS, set_4p_id=METAL_POLAR, set_2p_id=TECNO_PICIDO)
    subs = [("Prob. Crítica", 2), ("ATK%", 1)]
    assert valor_disco(_disco(2, METAL_POLAR, subs), con_4pc, DPS_ARCH, CTX) == \
        valor_disco(_disco(2, OTRO, subs), con_4pc, DPS_ARCH, CTX)


# --- el slot vacío (R10) -------------------------------------------------------------------

def test_un_slot_vacio_se_tapa_con_cualquier_disco_decente():
    build = _build_4_2()
    del build[3]
    nuevo = _disco(3, METAL_POLAR, subs=[("ATK%", 0)])
    c = evaluar_cambio(DPS, DPS_ARCH, build, nuevo, CTX, _bono)
    assert c.delta > 0


# --- recomendar() con builds ---------------------------------------------------------------

class _Repos:
    def __init__(self, agentes):
        self._a = agentes

    def get_all(self):
        return self._a

    def get_by_id(self, _):
        return DPS_ARCH

    def get_archetypes_for_set(self, _):
        return []

    def get_bonus(self, set_id):
        return ("CRIT Rate", "+8%", None) if set_id == TECNO_PICIDO else ("Ice DMG", "+10%", None)


def _reco(disco, build):
    repo = _Repos([DPS])
    return recomendar(disco, repo, _Repos([DPS_ARCH]), repo, CTX, builds=lambda _id: build)


def test_equipa_a_quien_mejora_y_dice_cuanto():
    nuevo = _disco(2, METAL_POLAR, subs=[("Prob. Crítica", 2), ("Daño Crítico", 2),
                                         ("ATK%", 1), ("Perforación", 0)], disc_id=999)
    rec = _reco(nuevo, _build_4_2())
    assert rec.tipo == "equipar" and rec.agente_id == DPS.id
    assert rec.movimiento is not None and rec.movimiento.delta > 0 and rec.movimiento.slot == 2


def test_bueno_pero_no_le_gana_a_nadie_es_reserva():
    """El ejemplo de Daniel: perfecto para un PJ futuro, no para los de hoy."""
    excelente = [("Prob. Crítica", 2), ("Daño Crítico", 2), ("ATK%", 1), ("Perforación", 0)]
    build = _build_4_2(slot_mediocre_subs=[("Prob. Crítica", 3), ("Daño Crítico", 2),
                                           ("ATK%", 0), ("Perforación", 0)])
    rec = _reco(_disco(2, METAL_POLAR, subs=excelente, disc_id=999), build)
    assert rec.tipo == "reserva", rec
    assert rec.movimiento is None


def test_malo_y_sin_nadie_a_quien_mejorar_es_descartar():
    build = _build_4_2(slot_mediocre_subs=[("Prob. Crítica", 3), ("Daño Crítico", 2),
                                           ("ATK%", 0), ("Perforación", 0)])
    rec = _reco(_disco(2, METAL_POLAR, subs=[("HP", 2), ("DEF", 2), ("ATK", 1)], disc_id=999), build)
    assert rec.tipo == "descartar"


def test_un_disco_que_lleva_otro_pj_no_se_mueve_todavia():
    """Mover un disco ajeno exige que el que lo tiene no pierda: eso es el paso 7. Hasta entonces
    un disco equipado por otro sigue por el camino viejo y no propone ningún movimiento."""
    ajeno = _disco(2, METAL_POLAR, subs=[("Prob. Crítica", 5)], disc_id=999, equipado=1, dueno=55)
    assert _reco(ajeno, _build_4_2()).movimiento is None


# --- el vocabulario ----------------------------------------------------------------------

@pytest.mark.parametrize("stat,valor,esperado", [
    ("CRIT Rate", "+8%", ("Prob. Crítica", 8.0)),
    ("CRIT DMG", "+16%", ("Daño Crítico", 16.0)),
    ("ATK", "+10%", ("ATK%", 10.0)),
    ("Anomaly Proficiency", "+30", ("Maestría de Anomalía", 30.0)),
    ("Ice DMG", "+10%", None),               # no es un secundario: no se inventa
    ("Energy Regen", "+20%", None),
    (None, None, None),
])
def test_bono_2pc_como_substat(stat, valor, esperado):
    assert bono_2pc_como_substat(stat, valor) == esperado


REAL_DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


@pytest.mark.skipif(not REAL_DB.is_file(), reason="sin la DB de dominio")
def test_el_valor_por_mejora_es_el_que_se_ve_en_el_inventario():
    """La tabla dice que fue MEDIDA sobre el inventario. Esto lo vuelve a medir (en sólo lectura)
    y exige que la moda de `valor / (1 + mejoras)` coincida para todo stat con ≥ 20 lecturas."""
    con = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    por: dict[str, Counter] = {}
    for fila in con.execute("SELECT sub1,val1,rolls1,sub2,val2,rolls2,sub3,val3,rolls3,"
                            "sub4,val4,rolls4 FROM inventory_discs"):
        for i in range(0, 12, 3):
            stat, val, mejoras = fila[i], fila[i + 1], fila[i + 2]
            if stat in VALOR_POR_MEJORA and val is not None and mejoras is not None:
                por.setdefault(stat, Counter())[round(float(val) / (1 + int(mejoras)), 3)] += 1
    con.close()
    medidos = {s: c.most_common(1)[0][0] for s, c in por.items() if sum(c.values()) >= 20}
    assert medidos, "el inventario no tiene lecturas suficientes"
    for stat, moda in medidos.items():
        assert moda == pytest.approx(VALOR_POR_MEJORA[stat]), (stat, moda)
