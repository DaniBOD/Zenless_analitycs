"""R24 (SPEC 2026-09-27): un fijo vital puede cambiar el 2pc por el siguiente de la guía, nunca el 4pc.

Daniel: "si cumple el set 2pc obvio debe cumplir la stat fijada y el set 2pc que esté en segunda
recomendación de la lista". Eligió armar el 2pc alternativo (una sugerencia de a DOS discos) y "el
siguiente disponible" de la lista. Caso real: Anby con 48,2 de Prob. Crítica y Monarca (≥ 50).
"""
from __future__ import annotations

from app.core.recommender import MEJORA_MINIMA, buscar_par_2pc
from app.core.score_normalizer import ScoringContext
from app.db.repositories import Agent, Archetype, Disc

CTX = ScoringContext()
MONARCA, SACUDE, JAZZ_OSC, VOZ, PUNK = 34, 43, 45, 24, 32
ARCH = Archetype(id=1, code="STUN", substats_positivos={"ATK%": 0.6}, substats_perjudiciales={},
                 threshold_stock=0.7, mains_4=["Prob. Crítica"], mains_5=["ATK%"], mains_6=["ATK%"])


class _Sets:
    def get_bonus(self, _):
        return (None, None, None)


def _d(i, slot, set_id, subs, nivel=15, main="ATK%", main_valor=30.0):
    if slot <= 3:
        main, main_valor = {1: ("HP", 2200.0), 2: ("ATK", 316.0), 3: ("DEF", 184.0)}[slot]
    elif slot == 4:
        main, main_valor = "Prob. Crítica", 24.0
    return Disc(id=i, set_id=set_id, slot=slot, main_stat=main, main_valor=main_valor, main_unidad=None,
                subs=[(n, v, None, r) for n, v, r in subs], nivel=nivel, equipado=1, agente_asignado=1)


def _build(dos=SACUDE, piezas_4pc=4, subs_2pc=(("ATK%", 3.0, 0), ("HP", 112.0, 0))):
    b = {s: _d(s, s, MONARCA if s <= piezas_4pc else 99, [("ATK", 19.0, 0)]) for s in range(1, 5)}
    b[5] = _d(5, 5, dos, list(subs_2pc))
    b[6] = _d(6, 6, dos, list(subs_2pc))
    return b


def _anby(fijos=None, stats=None, alternativas=((JAZZ_OSC,), (VOZ, PUNK))):
    return Agent(id=1, nombre="Anby", arquetipo_primario_id=1, arquetipo_primario_code="STUN",
                 threshold_equip=0.75, threshold_upgrade=0.5,
                 substat_preferences={"Prob. Crítica": 1.0, "Daño Crítico": 1.0, "ATK%": 0.8, "ATK": 0.6},
                 set_4p_id=MONARCA, set_2p_id=SACUDE, elemento="Eléctrico", rol="Aturdimiento",
                 stats=stats if stats is not None else {"prob_critico": 48.2, "dano_critico": 69.2},
                 stats_fijos=fijos if fijos is not None else {"prob_critico": 50},
                 alternativas_2pc=alternativas)


def _libre(i, slot, set_id, subs, nivel=15):
    d = _d(i, slot, set_id, subs, nivel)
    d.equipado, d.agente_asignado = 0, None
    return d


PAR_JAZZ = [_libre(101, 5, JAZZ_OSC, [("Prob. Crítica", 4.8, 1), ("ATK%", 6.0, 1)]),
            _libre(102, 6, JAZZ_OSC, [("Prob. Crítica", 2.4, 0), ("ATK%", 3.0, 0)])]


def _buscar(agent, build, libres):
    return buscar_par_2pc(agent, ARCH, build, libres, CTX, _Sets())


def test_arma_el_2pc_siguiente_y_alcanza_el_fijo():
    par = _buscar(_anby(), _build(), PAR_JAZZ)
    assert par is not None and par.set_id == JAZZ_OSC and par.slots == (5, 6)
    assert [d.id for d in par.discos] == [101, 102]
    assert par.stat == "prob_critico" and par.despues_min >= 50 > par.antes
    assert par.delta >= MEJORA_MINIMA


def test_si_solo_acerca_no_rompe_el_2pc():
    """48,2 + 7,2 = 55,4 no llega a 60: perder el 2pc por quedarse igual por debajo no paga."""
    assert _buscar(_anby(fijos={"prob_critico": 60}), _build(), PAR_JAZZ) is None


def test_el_siguiente_disponible_de_la_lista():
    voz = [_libre(201, 5, VOZ, [("Prob. Crítica", 7.2, 2), ("ATK%", 9.0, 2)]),
           _libre(202, 6, VOZ, [("Prob. Crítica", 4.8, 1), ("Daño Crítico", 9.6, 1)])]
    # El renglón 1 (Jazz Oscilante) tiene un par válido: gana aunque el de Voz Astral mejore más.
    assert _buscar(_anby(), _build(), PAR_JAZZ + voz).set_id == JAZZ_OSC
    # Sin discos de Jazz Oscilante, el siguiente renglón.
    assert _buscar(_anby(), _build(), voz).set_id == VOZ


def test_nunca_toca_el_4pc():
    """Con el 4pc incompleto no hay "los dos slots del 2pc": no se sugiere nada."""
    assert _buscar(_anby(), _build(piezas_4pc=3), PAR_JAZZ) is None


def test_sin_el_stat_leido_no_se_juzga():
    assert _buscar(_anby(stats={}), _build(), PAR_JAZZ) is None


def test_un_2pc_fuera_de_la_lista_no_entra():
    assert _buscar(_anby(alternativas=((VOZ, PUNK),)), _build(), PAR_JAZZ) is None


def test_una_ganancia_porcentual_no_prueba_que_llega():
    """Ju Fufu: 3.229 / 3.400 de ATK. Con ATK% la base es desconocida: no se puede probar que llega."""
    fijos, stats = {"ataque": 3400}, {"ataque": 3229}
    con_pct = [_libre(301, 5, JAZZ_OSC, [("ATK%", 9.0, 2)]), _libre(302, 6, JAZZ_OSC, [("ATK%", 9.0, 2)])]
    assert _buscar(_anby(fijos, stats), _build(subs_2pc=()), con_pct) is None
    con_plano = [_libre(303, 5, JAZZ_OSC, [("ATK", 95.0, 4)]), _libre(304, 6, JAZZ_OSC, [("ATK", 76.0, 3)])]
    par = _buscar(_anby(fijos, stats), _build(subs_2pc=()), con_plano)
    assert par is not None and par.stat == "ataque" and par.despues_min >= 3400


def test_no_le_baja_otro_fijo():
    """El 2pc actual le da PV% que sostiene otro fijo: el par lo dejaría por debajo."""
    fijos = {"prob_critico": 50, "pv": 20000}
    stats = {"prob_critico": 48.2, "dano_critico": 69.2, "pv": 20500}
    build = _build(subs_2pc=(("HP%", 6.0, 1),))
    assert _buscar(_anby(fijos, stats), build, PAR_JAZZ) is None


def test_discos_sin_terminar_no_entran():
    sin_terminar = [_libre(401, 5, JAZZ_OSC, [("Prob. Crítica", 4.8, 1)], nivel=9),
                    _libre(402, 6, JAZZ_OSC, [("Prob. Crítica", 2.4, 0)], nivel=9)]
    assert _buscar(_anby(), _build(), sin_terminar) is None


def test_si_el_par_empeora_el_puntaje_no_se_sugiere():
    """Alcanza el fijo, pero lo que lleva hoy vale mucho más: la mejora mínima lo frena."""
    bueno = (("Daño Crítico", 19.2, 3), ("ATK%", 9.0, 2), ("ATK", 57.0, 2))
    flojo = [_libre(501, 5, JAZZ_OSC, [("Prob. Crítica", 4.8, 1), ("HP", 112.0, 0)]),
             _libre(502, 6, JAZZ_OSC, [("Prob. Crítica", 2.4, 0), ("DEF", 15.0, 0)])]
    assert _buscar(_anby(), _build(subs_2pc=bueno), flojo) is None


# --- en el reporte: un par toma DOS slots y DOS discos -------------------------------------------

def _sm():
    import sys
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(raiz / "app" / "scripts"))
    try:
        import sugerir_movimientos as sm
    finally:
        sys.path.pop(0)
    return sm


def test_el_par_entra_entero_o_queda_en_conflicto():
    sm = _sm()
    par = sm.Sugerencia("armar_2pc", 101, "par", "Anby", 1, 5, delta=3.0, disc_id_2=102, slot_2=6)
    equipar_6 = sm.Sugerencia("equipar", 300, "x", "Anby", 1, 6, delta=1.0)
    otro_con_102 = sm.Sugerencia("equipar", 102, "y", "Lucy", 2, 6, delta=0.5)
    sm.resolver_conflictos([par, equipar_6, otro_con_102])
    assert par.conflicto is None
    assert "slot" in equipar_6.conflicto                # el slot 6 ya lo toma el par
    assert "#102" in otro_con_102.conflicto             # su segundo disco también


def test_si_pierde_el_par_no_toma_ningun_slot():
    sm = _sm()
    equipar_6 = sm.Sugerencia("equipar", 300, "x", "Anby", 1, 6, delta=5.0)
    par = sm.Sugerencia("armar_2pc", 101, "par", "Anby", 1, 5, delta=3.0, disc_id_2=102, slot_2=6)
    equipar_5 = sm.Sugerencia("equipar", 400, "z", "Anby", 1, 5, delta=1.0)
    sm.resolver_conflictos([equipar_6, par, equipar_5])
    assert par.conflicto is not None and equipar_5.conflicto is None
