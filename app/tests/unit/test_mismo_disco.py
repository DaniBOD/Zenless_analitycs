"""`es_el_mismo_disco`: la única regla de "¿es el mismo disco?" (SPEC 2026-10-02, puntos 4 y 6).

Quien llama ya comprobó set y slot. Los casos son los del QA en vivo del farmeo de Claret
(2026-10-02): dos Rosa espinosa del mismo slot se confundieron tres veces porque sólo se miraba
el set.
"""
from __future__ import annotations

import pytest

from app.core.mismo_disco import es_el_mismo_disco
from app.core.parser_disc import DiscParsed, SubstatParsed
from app.db.repositories import Disc


def _p(main, nivel, subs) -> DiscParsed:
    return DiscParsed(set_name_raw="Rosa espinosa", set_name_canon="Rosa espinosa", slot=1,
                      main_stat_raw=main, main_stat_canon=main, main_valor=None, main_unidad=None,
                      nivel=nivel, rareza="S",
                      subs=[SubstatParsed(n, n, None, None, r, 0.95) for n, r in subs])


def _d(main, nivel, subs) -> Disc:
    return Disc(id=1, set_id=55, slot=1, main_stat=main, main_valor=None, main_unidad=None,
                subs=[(n, None, None, r) for n, r in subs], nivel=nivel, equipado=0,
                agente_asignado=None)


# #408 antes de mejorarlo y #396, el Rosa espinosa slot 1 que llevaba Claret (00:01:16).
PRE_408 = [("Daño Crítico", 0), ("Maestría de Anomalía", 0), ("DEF", 0)]
EQUIPADO_396 = [("DEF%", 1), ("ATK", 0), ("DEF", 2), ("Prob. Crítica", 1)]


def test_otro_disco_del_mismo_set_y_slot_no_es_el_mismo():
    assert not es_el_mismo_disco(_p("HP", 0, PRE_408), _p("HP", 15, EQUIPADO_396))


def test_el_mismo_disco_mejorado_si():
    """#411 → #412: Hado emplumado slot 1, 0 → 3, se destraba el 4.º substat."""
    antes = [("Maestría de Anomalía", 0), ("Prob. Crítica", 0), ("DEF", 0)]
    ahora = antes + [("DEF%", 0)]
    assert es_el_mismo_disco(_p("HP", 0, antes), _p("HP", 3, ahora))


def test_el_cambio_de_slot_4_de_claret_no_es_un_refresco():
    """#402: S17 pisó la fila con otro Rosa espinosa slot 4 (00:22:26)."""
    viejo = _d("Prob. Crítica", 15, [("HP%", 1), ("ATK%", 0), ("DEF", 0), ("ATK", 2)])
    nuevo = _p("Prob. Crítica", 15, [("DEF%", 2), ("Maestría de Anomalía", 0), ("ATK%", 0),
                                      ("HP%", 2)])
    assert not es_el_mismo_disco(viejo, nuevo)


def test_un_refresco_tras_la_mejora_entre_la_db_y_lo_leido_si():
    fila = _d("HP", 0, PRE_408)
    leido = _p("HP", 15, [("Daño Crítico", 1), ("Maestría de Anomalía", 0), ("DEF", 1),
                          ("Perforación", 2)])
    assert es_el_mismo_disco(fila, leido)


@pytest.mark.parametrize("ahora, por_que", [
    (_p("HP", 0, [("Daño Crítico", 0), ("Maestría de Anomalía", 0), ("ATK", 0)]),
     "con el mismo nivel, un substat distinto"),
    (_p("HP", 0, PRE_408 + [("ATK", 0)]), "Nv 0 de 3 substats vs Nv 0 de 4"),
    (_p("HP", 15, [("Daño Crítico", 0), ("Maestría de Anomalía", 0), ("DEF", 0), ("ATK", 0)]),
     "nada creció pero subió 15 niveles: ok, se acepta (no hay roll que baje)"),
])
def test_casos_de_borde(ahora, por_que):
    antes = _p("HP", 0, PRE_408)
    esperado = por_que.startswith("nada creció")
    assert es_el_mismo_disco(antes, ahora) is esperado, por_que


def test_un_roll_que_baja_no_es_el_mismo():
    antes = _p("HP", 6, [("Daño Crítico", 2), ("DEF", 0), ("ATK", 0), ("DEF%", 0)])
    ahora = _p("HP", 15, [("Daño Crítico", 1), ("DEF", 2), ("ATK", 1), ("DEF%", 0)])
    assert not es_el_mismo_disco(antes, ahora)


def test_el_nivel_no_baja():
    assert not es_el_mismo_disco(_p("HP", 15, PRE_408), _p("HP", 0, PRE_408))


def test_main_distinto_no_es_el_mismo():
    assert not es_el_mismo_disco(_p("ATK%", 0, PRE_408), _p("DEF%", 0, PRE_408))


def test_sin_nivel_leido_compara_igual_los_substats():
    assert es_el_mismo_disco(_p("HP", None, PRE_408), _p("HP", 15, PRE_408 + [("ATK", 0)]))
    assert not es_el_mismo_disco(_p("HP", None, PRE_408), _p("HP", 15, EQUIPADO_396))


def test_tildes_y_mayusculas_del_ocr_no_separan():
    antes = _p("HP", 0, [("Daño Critico", 0), ("Maestria de Anomalia", 0), ("DEF", 0)])
    assert es_el_mismo_disco(antes, _p("HP", 0, PRE_408))
