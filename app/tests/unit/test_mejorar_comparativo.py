"""MEJORAR es comparativo: un disco sin terminar se sube si, en lo esperable, le gana a lo que el
PJ ya lleva en ese slot (R12).

Caso de Daniel del 2026-09-23 (#369, Floración del alba · slot 5 · Bono Daño Hielo · Nv 0 · DEF,
ATK%, Daño Crítico): el motor lo descartaba porque su valor esperado, normalizado, daba 0,468 contra
un umbral fijo de 0,50. Pero subido le gana al slot 5 actual de Soukaku y de Lycaon. Daniel: "no
está bien el descarte actual de ese disco".
"""
from __future__ import annotations

from app.core.recommender import recomendar
from app.core.score_normalizer import ScoringContext
from app.db.repositories import Agent, Archetype, Disc

CTX = ScoringContext()
ARCH = Archetype(
    id=1, code="ATK_DPS",
    substats_positivos={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 1.0, "ATK": 0.4,
                        "Perforación": 0.7},
    substats_perjudiciales={"DEF": -0.8, "HP": -0.5, "DEF%": -0.8, "HP%": -0.5},
    threshold_stock=0.7, mains_4=["Prob. Crítica", "Daño Crítico", "ATK%"],
    mains_5=["Bono Daño Hielo", "ATK%"], mains_6=["ATK%"],
)


def _pj(pj_id, nombre):
    return Agent(id=pj_id, nombre=nombre, arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
                 threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={},
                 elemento="Hielo")


def _disco(disc_id, subs, nivel, dueno=None):
    return Disc(id=disc_id, set_id=900, slot=5, main_stat="Bono Daño Hielo", main_valor=None,
                main_unidad=None, subs=[(s, None, None, m) for s, m in subs], nivel=nivel,
                equipado=1 if dueno else 0, agente_asignado=dueno)


#: El #369: tres líneas, una muerta (DEF) y ninguna mejora gastada todavía.
D369 = [("DEF", 0), ("ATK%", 0), ("Daño Crítico", 0)]
FLOJO = [("HP", 1), ("DEF", 1), ("HP%", 1), ("DEF%", 1)]                       # le RESTA
BUENO = [("Prob. Crítica", 2), ("Daño Crítico", 2), ("ATK%", 1), ("Perforación", 0)]


class _Repos:
    def __init__(self, agentes):
        self._a = agentes

    def get_all(self):
        return self._a

    def get_by_id(self, _):
        return ARCH

    def get_archetypes_for_set(self, _):
        return []

    def get_bonus(self, _):
        return (None, None, None)


def _reco(disco, builds, agentes):
    repo = _Repos(agentes)
    return recomendar(disco, repo, _Repos([ARCH]), repo, CTX,
                      builds=None if builds is None else (lambda i: builds.get(i, {})))


def test_sin_builds_el_369_no_llega_al_umbral_fijo():
    """La premisa: con el umbral absoluto se descarta. Si esto cambia, el test de abajo ya no
    discrimina nada."""
    rec = _reco(_disco(1, D369, 0), None, [_pj(1, "flojo")])
    assert rec.tipo == "descartar" and rec.score_norm < 0.50


def test_se_mejora_si_lo_esperable_le_gana_a_lo_que_lleva():
    flojo, bueno = _pj(1, "con_flojo"), _pj(2, "con_bueno")
    builds = {1: {5: _disco(10, FLOJO, 15, dueno=1)}, 2: {5: _disco(20, BUENO, 15, dueno=2)}}
    rec = _reco(_disco(1, D369, 0), builds, [flojo, bueno])
    assert rec.tipo == "mejorar" and rec.agente_id == flojo.id


def test_no_se_mejora_si_no_le_gana_a_nadie():
    bueno = _pj(2, "con_bueno")
    builds = {2: {5: _disco(20, BUENO, 15, dueno=2)}}
    assert _reco(_disco(1, D369, 0), builds, [bueno]).tipo == "descartar"


def test_se_compara_lo_ESPERADO_no_lo_que_vale_hoy():
    """El actual vale 3,2: más que el #369 hoy (2,2), menos que lo que se espera de él (4,51)."""
    medio = _pj(1, "con_medio")
    actual = [("ATK%", 1), ("Daño Crítico", 0), ("HP", 0), ("DEF", 0)]
    builds = {1: {5: _disco(10, actual, 15, dueno=1)}}
    assert _reco(_disco(1, D369, 0), builds, [medio]).tipo == "mejorar"


DEF_ARCH = Archetype(
    id=2, code="DEFENSE",
    substats_positivos={"DEF": 1.0, "HP": 1.0, "ATK%": 0.1, "Daño Crítico": 0.1},
    substats_perjudiciales={}, threshold_stock=0.7, mains_4=["DEF%"],
    mains_5=["Bono Daño Hielo", "DEF%"], mains_6=["DEF%"],
)


class _RepoPorId(_Repos):
    def get_by_id(self, arch_id):
        return {1: ARCH, 2: DEF_ARCH}[arch_id]


def test_las_guardas_valen_por_pj_aunque_otro_pj_lo_tenga_sano():
    """Con DEF y PV muertas para el atacante, y vivas para el defensor. Al defensor le sirve pero
    no le gana a lo que lleva; al atacante le "ganaría" (lleva un disco que resta), pero para él
    tiene dos muertas → nadie lo sube. Para el defensor sirve y lo esperable alcanza su umbral de
    reserva: desde 2026-09-25 se GUARDA sin subir, no se tira."""
    atacante = _pj(1, "atacante")
    defensor = Agent(id=2, nombre="defensor", arquetipo_primario_id=2, arquetipo_primario_code="DEFENSE",
                     threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={},
                     elemento="Hielo")
    builds = {1: {5: _disco(10, FLOJO, 15, dueno=1)},
              2: {5: _disco(20, [("DEF", 3), ("HP", 2), ("ATK%", 0), ("Daño Crítico", 0)], 15,
                            dueno=2)}}
    dos_muertas = [("DEF", 0), ("HP", 0), ("ATK%", 0), ("Daño Crítico", 0)]
    repo = _Repos([atacante, defensor])
    rec = recomendar(_disco(1, dos_muertas, 0), repo, _RepoPorId([ARCH, DEF_ARCH]), repo, CTX,
                     builds=lambda i: builds.get(i, {}))
    assert rec.tipo == "guardar", (rec.tipo, rec.agente_nombre)
    assert rec.agente_id is None


def test_dos_lineas_muertas_se_descartan_aunque_le_gane_a_un_disco_malo():
    """R13 sigue por encima de la comparación: contra un disco que resta, casi todo "gana"."""
    flojo = _pj(1, "con_flojo")
    builds = {1: {5: _disco(10, FLOJO, 15, dueno=1)}}
    dos_muertas = [("DEF", 0), ("HP", 0), ("ATK%", 0), ("Daño Crítico", 0)]
    assert _reco(_disco(1, dos_muertas, 0), builds, [flojo]).tipo == "descartar"


def test_una_mejora_gastada_en_la_muerta_frena_aunque_le_gane():
    """Caso 7 / D1a: la DEF ya se llevó una mejora → frenar, por flojo que sea lo que tiene."""
    flojo = _pj(1, "con_flojo")
    builds = {1: {5: _disco(10, FLOJO, 15, dueno=1)}}
    gastada = [("DEF", 1), ("ATK%", 0), ("Daño Crítico", 0), ("Prob. Crítica", 0)]
    assert _reco(_disco(1, gastada, 3), builds, [flojo]).tipo == "descartar"
