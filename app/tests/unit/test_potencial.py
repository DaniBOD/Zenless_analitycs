"""Un disco sin terminar se juzga por lo que puede llegar a ser (etapa 1, paso 4).

El motor normalizaba un Nivel 0 contra el máximo de un +15: ningún disco nuevo llegaba al
"mejorar", y descartaba justo el que Daniel subiría (caso 6_D1). Ahora se calcula el puntaje
ESPERADO en Nivel 15, y una línea muerta ya conocida descarta (R13, R15).

La afirmación fuerte es "exacto por linealidad". No se le cree al docstring: se compara contra
la ENUMERACIÓN de todos los finales posibles, puntuados uno por uno con `score_disco`.
"""
from __future__ import annotations

import itertools
from statistics import fmean

import pytest

from app.core.recommender import recomendar
from app.core.score_normalizer import ScoringContext
from app.core.scoring import (NIVELES_DE_MEJORA, mejoras_pendientes, potencial, score_disco)
from app.core.stats_vocab import CANONICAL_SUBSTATS
from app.db.repositories import Agent, Archetype, Disc

CTX = ScoringContext()
DPS_ARCH = Archetype(
    id=1, code="ATK_DPS",
    substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0, "ATK": 0.4,
                        "Perforación": 0.7},
    substats_perjudiciales={"DEF": -0.8, "DEF%": -1.0, "HP": -0.5, "HP%": -0.8,
                            "Maestría de Anomalía": -0.8},
    threshold_stock=0.7,
    mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"], mains_5=["ATK%"], mains_6=["ATK%"],
)
DPS = Agent(id=1, nombre="dps", arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
            threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={})


def _disco(subs, nivel, slot=4, main="Daño Crítico"):
    return Disc(id=1, set_id=999, slot=slot, main_stat=main, main_valor=None, main_unidad=None,
                subs=[(s, None, None, m) for s, m in subs], nivel=nivel, equipado=0,
                agente_asignado=None)


def _final(disc, subs):
    return score_disco(_disco(subs, 15, disc.slot, disc.main_stat), DPS, DPS_ARCH, CTX).score_raw


@pytest.mark.parametrize("nivel,pendientes", [(0, 5), (2, 5), (3, 4), (6, 3), (12, 1), (15, 0)])
def test_mejoras_pendientes(nivel, pendientes):
    assert mejoras_pendientes(nivel) == pendientes


def test_los_niveles_de_mejora_son_los_medidos():
    assert NIVELES_DE_MEJORA == (3, 6, 9, 12, 15)


def test_en_nivel_15_el_potencial_es_el_puntaje():
    d = _disco([("Prob. Crítica", 2), ("ATK%", 1), ("Perforación", 1), ("ATK", 1)], 15)
    assert potencial(d, DPS, DPS_ARCH, CTX).score_raw == pytest.approx(
        score_disco(d, DPS, DPS_ARCH, CTX).score_raw)


def test_con_4_lineas_es_EXACTO_contra_la_enumeracion():
    """Nivel 6: quedan 3 mejoras sobre 4 líneas → 4³ = 64 finales igual de probables."""
    subs = [("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 1), ("DEF", 0)]
    d = _disco(subs, 6)
    finales = []
    for elecciones in itertools.product(range(4), repeat=3):
        s = [list(x) for x in subs]
        for i in elecciones:
            s[i][1] += 1
        finales.append(_final(d, [tuple(x) for x in s]))
    assert potencial(d, DPS, DPS_ARCH, CTX).score_raw == pytest.approx(fmean(finales))


def test_con_3_lineas_es_EXACTO_contra_la_enumeracion_con_la_4a_uniforme():
    """Nivel 0 y 3 líneas: la primera mejora agrega la 4ª (uniforme entre las posibles) y quedan
    4 mejoras sobre 4 líneas. Se enumera TODO: cada 4ª posible × 4⁴ repartos."""
    subs = [("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 0)]
    d = _disco(subs, 0)
    posibles = sorted(set(CANONICAL_SUBSTATS) - {"Prob. Crítica", "ATK%", "Perforación", "Daño Crítico"})
    finales = []
    for cuarta in posibles:
        for elecciones in itertools.product(range(4), repeat=4):
            s = [list(x) for x in subs] + [[cuarta, 0]]
            for i in elecciones:
                s[i][1] += 1
            finales.append(_final(d, [tuple(x) for x in s]))
    pot = potencial(d, DPS, DPS_ARCH, CTX)
    assert pot.score_raw == pytest.approx(fmean(finales))
    assert pot.cuarta_linea_supuesta


def test_las_lineas_muertas_son_las_de_peso_cero_o_negativo():
    d = _disco([("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 1), ("DEF", 0)], 6)
    assert potencial(d, DPS, DPS_ARCH, CTX).lineas_muertas == ["DEF"]


def test_una_linea_que_no_suma_nada_tambien_es_muerta():
    """Daniel sobre la DEF de Ellen: "no sirve". No hace falta que reste: si no suma, ocupa un
    lugar (R1). Un stat que el rol ni premia ni castiga pesa exactamente 0."""
    sin_peso = Archetype(id=9, code="X", substats_positivos={"ATK%": 1.0},
                         substats_perjudiciales={}, threshold_stock=0.7)
    d = _disco([("ATK%", 0), ("Maestría de Anomalía", 0)], 6, slot=2, main="ATK")
    assert potencial(d, DPS, sin_peso, CTX).lineas_muertas == ["Maestría de Anomalía"]


# --- recomendar() para un disco sin terminar ----------------------------------------------

STUN_ARCH = Archetype(
    id=2, code="STUN",
    substats_positivos={"ATK%": 1.0, "ATK": 0.4, "Prob. Crítica": 0.8, "Daño Crítico": 0.8,
                        "Perforación": 0.6, "DEF": 0.3},
    substats_perjudiciales={"HP": -0.5},
    threshold_stock=0.7,
    mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"], mains_5=["ATK%"], mains_6=["Impacto"],
)
STUN = Agent(id=2, nombre="stun", arquetipo_primario_id=2, arquetipo_primario_code="STUN",
             threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={})


class _Repos:
    def __init__(self, agentes):
        self._a = agentes

    def get_all(self):
        return self._a

    def get_by_id(self, i):
        return {1: DPS_ARCH, 2: STUN_ARCH}[i]

    def get_archetypes_for_set(self, _):
        return []


def _reco(disco, agentes):
    return recomendar(disco, _Repos(agentes), _Repos([DPS_ARCH, STUN_ARCH]), _Repos([]), CTX)


def test_un_nivel_0_con_buen_principal_y_tres_lineas_utiles_se_mejora():
    """El caso 6_D1 de Daniel."""
    rec = _reco(_disco([("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 0)], 0), [DPS])
    assert rec.tipo == "mejorar" and rec.potencial is not None


def test_una_linea_muerta_conocida_frena():
    """El caso 7_D1a: la 4ª salió DEF a mitad de camino."""
    rec = _reco(_disco([("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 1), ("DEF", 0)], 6), [DPS])
    assert rec.tipo == "descartar"


def test_una_linea_muerta_de_origen_se_tolera():
    """Caso 9: Nivel 0, cuatro líneas de entrada, una muerta. "Se puede permitir uno muerto
    siempre y cuando las mejoras no apliquen a él": todavía no se gastó ninguna."""
    d = _disco([("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 0), ("DEF", 0)], 0)
    pot = potencial(d, DPS, DPS_ARCH, CTX)
    assert pot.lineas_muertas == ["DEF"] and not pot.mejora_en_linea_muerta
    assert _reco(d, [DPS]).tipo == "mejorar"


def test_si_una_mejora_sube_la_linea_muerta_se_frena():
    d = _disco([("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 0), ("DEF", 1)], 3)
    assert potencial(d, DPS, DPS_ARCH, CTX).mejora_en_linea_muerta
    assert _reco(d, [DPS]).tipo == "descartar"


def test_si_la_mejora_CREO_la_linea_muerta_tambien_se_frena():
    """Caso 7_D1a: Nivel 6 con una sola mejora repartida → arrancó con 3 líneas y la del +3 creó
    la 4ª. Si esa 4ª es muerta, ya se gastó una mejora en ella."""
    d = _disco([("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 1), ("DEF", 0)], 6)
    assert potencial(d, DPS, DPS_ARCH, CTX).mejora_en_linea_muerta


def test_la_misma_muerta_arriba_no_la_creo_una_mejora():
    """Mismo disco, pero la DEF no es la última línea: la agregada fue la Perforación (útil).
    Descansa en la premisa de que la línea agregada aparece al final."""
    d = _disco([("Prob. Crítica", 0), ("DEF", 0), ("ATK%", 1), ("Perforación", 0)], 6)
    assert not potencial(d, DPS, DPS_ARCH, CTX).mejora_en_linea_muerta


def test_dos_lineas_muertas_se_descartan_aunque_lo_esperable_alcance():
    """R13 (caso 6_D2): dos líneas basura, fuera. Hay que probarla AISLADA: con muertas que restan,
    el valor esperado ya queda bajo y el disco se descarta igual, así que la regla nunca se pone a
    prueba (un sabotaje que la apagaba pasaba en verde). Acá las dos muertas pesan exactamente 0
    —no restan— y el resto es bueno: sin la regla, este disco se MEJORARÍA."""
    sin_castigo = Archetype(
        id=1, code="ATK_DPS",
        substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0, "ATK": 0.4,
                            "Perforación": 0.7},
        substats_perjudiciales={}, threshold_stock=0.7,
        mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"])
    d = _disco([("Prob. Crítica", 0), ("ATK%", 0), ("HP", 0), ("DEF", 0)], 0)
    assert potencial(d, DPS, sin_castigo, CTX).score_norm >= DPS.threshold_upgrade, \
        "el ejemplo tiene que superar el umbral por sí solo, o no aísla la regla"

    class _Solo(_Repos):
        def get_by_id(self, _):
            return sin_castigo

    rec = recomendar(d, _Solo([DPS]), _Solo([sin_castigo]), _Solo([]), CTX)
    assert rec.tipo == "descartar"


def test_vale_el_mejor_rol_SIN_lineas_muertas():
    """Para el atacante la DEF es basura; para este aturdidor, no. Juzgado para la cuenta entera
    (R11), el disco sirve: se mejora para el aturdidor."""
    rec = _reco(_disco([("Prob. Crítica", 0), ("ATK%", 0), ("Perforación", 1), ("DEF", 0)], 6),
                [DPS, STUN])
    assert rec.tipo == "mejorar" and rec.agente_nombre == "stun"


def test_un_disco_sin_terminar_no_se_equipa_ni_se_reserva():
    """Primero se sube: aunque su potencial sea altísimo, la salida es MEJORAR."""
    rec = _reco(_disco([("Prob. Crítica", 3), ("ATK%", 0), ("Perforación", 0), ("ATK", 0)], 12), [DPS])
    assert rec.tipo == "mejorar"
