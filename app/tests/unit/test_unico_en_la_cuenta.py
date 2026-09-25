"""R22: el único disco de su tipo (set, slot, principal) que le sirve a alguien no se tira.

Daniel (2026-09-25), por el #157 (Armonía umbría · slot 5 · Bono Daño Eléctrico, terminado, que se
descartaba): "si no hay ningún disco del mismo set que posea esos stats es mejor guardarlo [...]
aunque se tenga un substat no preferible, ya que la pasiva del set va bien con los stats".
"""
from __future__ import annotations

from app.core.recommender import recomendar, unico_en_la_cuenta
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
SET = 900
FLOJO = [("HP", 1), ("DEF", 1), ("HP%", 1), ("ATK%", 1)]
BUENO = [("Prob. Crítica", 2), ("Daño Crítico", 2), ("ATK%", 1), ("Perforación", 0)]
DOS_MUERTAS = [("DEF", 0), ("HP", 0), ("ATK%", 0), ("Daño Crítico", 0)]


def _pj(sets_guia=frozenset({SET})):
    return Agent(id=1, nombre="hielo", arquetipo_primario_id=1, arquetipo_primario_code="ATK_DPS",
                 threshold_equip=0.75, threshold_upgrade=0.50, substat_preferences={},
                 elemento="Hielo", sets_guia=sets_guia)


def _disco(disc_id, subs, nivel, dueno=None, set_id=SET, slot=5, main="Bono Daño Hielo"):
    return Disc(id=disc_id, set_id=set_id, slot=slot, main_stat=main, main_valor=None,
                main_unidad=None, subs=[(s, None, None, m) for s, m in subs], nivel=nivel,
                equipado=1 if dueno else 0, agente_asignado=dueno)


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


def _reco(disco, pj, lleva, libres):
    """`lleva`: el disco que el PJ tiene equipado en el slot 5 (de OTRO set, para que el de este
    set no sea su gemelo salvo que el test lo pida)."""
    repo = _Repos([pj])
    return recomendar(disco, repo, _Repos([ARCH]), repo, CTX,
                      builds=lambda i: {5: lleva} if i == pj.id else {}, libres=libres)


LLEVA_OTRO_SET = _disco(50, BUENO, 15, dueno=1, set_id=901)


# --- la regla ---------------------------------------------------------------------------------

def test_unico_sin_gemelos():
    d = _disco(1, FLOJO, 15)
    assert unico_en_la_cuenta(d, [d, _disco(2, FLOJO, 15, slot=4, main="ATK%")])


def test_un_gemelo_equipado_lo_cubre():
    d = _disco(1, FLOJO, 15)
    assert not unico_en_la_cuenta(d, [d, _disco(2, FLOJO, 0, dueno=1)])


def test_entre_libres_gemelos_se_conserva_uno_solo():
    """Si no, dos gemelos flojos se cubrirían entre sí y se tirarían los dos."""
    a, b, c = _disco(1, FLOJO, 15), _disco(2, FLOJO, 15), _disco(3, FLOJO, 9)
    inv = [a, b, c]
    assert [d.id for d in inv if unico_en_la_cuenta(d, inv)] == [1]   # más nivel; empate, el más antiguo


# --- en el recomendador -------------------------------------------------------------------------

def test_terminado_unico_que_sirve_va_a_reserva():
    d = _disco(1, FLOJO, 15)
    assert _reco(d, _pj(), LLEVA_OTRO_SET, [d]).tipo == "reserva"


def test_terminado_con_gemelo_equipado_se_descarta():
    """La premisa del de arriba: sin R22 este disco se descarta (no le gana a nadie y queda bajo el
    umbral de reserva). Si esto pasa a reserva por otro motivo, el test de arriba no prueba nada."""
    d = _disco(1, FLOJO, 15)
    gemelo = _disco(2, BUENO, 15, dueno=1)
    assert _reco(d, _pj(), gemelo, [d]).tipo == "descartar"


def test_si_su_set_no_esta_en_la_guia_de_nadie_se_descarta():
    """"La pasiva del set va bien con los stats": un set que ningún PJ al que le sirve el principal
    usa no se conserva por ser único (el #368, Floración del alba con Bono Daño Físico)."""
    d = _disco(1, FLOJO, 15)
    assert _reco(d, _pj(sets_guia=frozenset({901})), LLEVA_OTRO_SET, [d]).tipo == "descartar"


def test_sin_terminar_unico_se_guarda_sin_subir_aunque_tenga_dos_muertas():
    """El #380 (Metal polar · slot 5 · Bono Daño Hielo, con PV y PV%): no se le invierte (R13),
    pero es el único de su tipo."""
    d = _disco(1, DOS_MUERTAS, 0)
    assert _reco(d, _pj(), LLEVA_OTRO_SET, [d]).tipo == "guardar"
    gemelo = _disco(2, BUENO, 15, dueno=1)
    assert _reco(d, _pj(), gemelo, [d]).tipo == "descartar"


def test_sin_inventario_no_se_juzga():
    """En vivo (sin builds ni libres) no se sabe si es único: sigue la regla de antes (B2)."""
    d = _disco(1, DOS_MUERTAS, 0)
    repo = _Repos([_pj()])
    assert recomendar(d, repo, _Repos([ARCH]), repo, CTX).tipo == "descartar"


def test_el_repo_carga_los_sets_de_la_guia(tmp_path):
    """`sets_guia` = los 4pc y los 2pc de la guía (mig 43) más el build objetivo. Sobre una COPIA."""
    import shutil
    import sqlite3
    from pathlib import Path

    import pytest

    from app.db.repositories import AgentRepo

    real = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    if not real.is_file():
        pytest.skip("sin la DB de dominio")
    copia = tmp_path / "copia.db"
    shutil.copy(real, copia)
    con = sqlite3.connect(copia)
    con.row_factory = sqlite3.Row
    try:
        esperado = {}
        for a, s in con.execute("SELECT agente_id, set_id FROM pj_sets_4pc "
                                "UNION SELECT agente_id, set_id FROM pj_sets_2pc"):
            esperado.setdefault(a, set()).add(s)
        agentes = AgentRepo(con).get_all()
        con_guia = [a for a in agentes if a.id in esperado]
        assert len(con_guia) >= 50
        for a in con_guia:
            objetivo = {s for s in (a.set_4p_id, a.set_2p_id) if s is not None}
            assert a.sets_guia == frozenset(esperado[a.id] | objetivo), a.nombre
    finally:
        con.close()
