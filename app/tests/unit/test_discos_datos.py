"""Datos de la pantalla Discos y del modal de disco — funciones puras, sin Qt.

Lo que se protege:

1. **Todos los discos activos**: la tabla vieja tenía `LIMIT 200` y mostraba 200 de 385 sin avisar.
2. **Un disco con 3 substats tiene 3**, no una cuarta fila vacía (12 de 385 hoy).
3. **Nada de scoring**: ni `score_evaluacion` (0/385) ni orden por calidad. Las alternativas se
   ordenan libres primero y por nivel — no "mejor primero".
4. Los valores se muestran con la **unidad guardada** en la DB, y los substats con el mismo formato
   que la vista en vivo.
"""
from __future__ import annotations

import pytest

from app.ui.discos.datos import (
    alternativas, distribucion_por_set, filtrar, formatear_valor, leer_inventario, libres_por_slot,
)
from app.ui.formato import formatear_sub


def _disco(con, id_, set_id, slot, *, agente=None, equipado=0, descartado=0, nivel=15, subs=4,
           main="ATK%", main_valor=30.0, unidad_main="%"):
    s = [("Prob. Crítica", 2.4, 1, "%"), ("ATK", 38.0, 0, "flat"), ("Perforación", 9.0, 2, "flat"),
         ("Daño Crítico", 9.6, 1, "%")][:subs]
    cols = {"id": id_, "fecha_obtencion": "2026-09-01", "set_id": set_id, "slot": slot,
            "main_stat": main, "main_valor": main_valor, "unidad_main": unidad_main, "nivel": nivel,
            "agente_asignado": agente, "equipado": equipado, "descartado": descartado}
    for i, (n, v, r, u) in enumerate(s, start=1):
        cols.update({f"sub{i}": n, f"val{i}": v, f"rolls{i}": r, f"unidad{i}": u})
    con.execute(f"INSERT INTO inventory_discs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                list(cols.values()))


@pytest.fixture
def con(db_esquema_real):
    c = db_esquema_real
    c.executescript("""
        INSERT INTO disc_sets (id, nombre, nombre_en, bonus_2p_stat, bonus_2p_valor, bonus_4p_desc) VALUES
            (1, 'Jazz Caótico', 'Chaos Jazz', 'Maestría de Anomalía', '+30', 'Texto 4pc Jazz'),
            (2, 'Blues Libre', 'Freedom Blues', 'Maestría de Anomalía', '+30', 'Texto 4pc Blues');
        INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, protected_build) VALUES
            (1, 'Yanagi', 'S', 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6', 0);
    """)
    _disco(c, 10, 1, 4, agente=1, equipado=1)
    _disco(c, 11, 1, 4, nivel=9)                    # libre, mismo set y slot, nivel bajo
    _disco(c, 12, 1, 4, nivel=15)                   # libre, mismo set y slot
    _disco(c, 13, 1, 4, descartado=1)               # descartado: no existe para la UI
    _disco(c, 14, 1, 5, agente=1, equipado=1)       # otro slot
    _disco(c, 15, 2, 4, subs=3)                     # otro set, libre, 3 substats
    _disco(c, 16, 1, 4, agente=1, equipado=0)       # asignado a Yanagi pero no equipado: sin
    return c                                        # dueño visible, cuenta como libre


def _ids(filas):
    return [f.id for f in filas]


def test_trae_todos_los_activos_y_ninguno_descartado(con):
    assert sorted(_ids(leer_inventario(con))) == [10, 11, 12, 14, 15, 16]


def test_sin_tope_de_filas(con):
    for i in range(300):
        _disco(con, 1000 + i, 2, (i % 6) + 1)
    assert len(leer_inventario(con)) == 306, "la tabla vieja cortaba en 200 sin decirlo"


def test_un_disco_con_tres_substats_tiene_tres(con):
    f = {x.id: x for x in leer_inventario(con)}
    assert len(f[15].subs) == 3
    assert len(f[10].subs) == 4
    assert f[10].rolls_total == 4


def test_dueno_solo_si_esta_equipado(con):
    f = {x.id: x for x in leer_inventario(con)}
    assert f[10].dueno == "Yanagi" and f[10].equipado
    assert f[16].dueno is None and not f[16].equipado, "asignado sin equipar no es dueño a la vista"
    assert f[11].dueno is None


def test_un_nivel_NULL_llega_como_none_y_no_como_cero(con):
    """Fase 3: `int(r[24] or 0)` convertía el "no lo leí" en Nivel 0, que es un estado REAL y
    distinto (un disco recién dropeado). La pantalla tiene que poder decir los tres casos."""
    _disco(con, 20, 1, 4, nivel=None)
    _disco(con, 21, 1, 4, nivel=0)
    filas = {x.id: x for x in leer_inventario(con)}
    assert filas[20].nivel is None
    assert filas[21].nivel == 0


def test_formato_con_la_unidad_guardada():
    assert formatear_valor(30.0, "%") == "30%"
    assert formatear_valor(184.0, "flat") == "184"
    assert formatear_valor(None, "%") == "—"
    assert formatear_sub("Prob. Crítica", 2.4, "%", 1) == "Prob. Crítica 2.4% (+1)"
    assert formatear_sub("ATK", 38.0, "flat", 0) == "ATK 38"


def test_filtros_se_combinan(con):
    filas = leer_inventario(con)
    assert sorted(_ids(filtrar(filas, {"slot": {4}}))) == [10, 11, 12, 15, 16]
    assert sorted(_ids(filtrar(filas, {"slot": {4}, "estado": {"libre"}}))) == [11, 12, 15, 16]
    assert sorted(_ids(filtrar(filas, {"set": {"Blues Libre"}, "slot": {4, 5}}))) == [15]
    assert sorted(_ids(filtrar(filas, {"dueno": {"Yanagi"}}))) == [10, 14]
    assert sorted(_ids(filtrar(filas, {"main": {"ATK%"}}))) == [10, 11, 12, 14, 15, 16]
    assert len(filtrar(filas, {})) == 6


def test_distribucion_y_libres_por_slot(con):
    filas = leer_inventario(con)
    assert distribucion_por_set(filas) == [("Jazz Caótico", 5), ("Blues Libre", 1)]
    assert libres_por_slot(filas) == {1: 0, 2: 0, 3: 0, 4: 4, 5: 0, 6: 0}


def test_alternativas_mismo_set_y_slot_libres_primero_sin_score(con):
    filas = leer_inventario(con)
    propio = next(f for f in filas if f.id == 10)
    alt = alternativas(filas, propio)
    assert 10 not in _ids(alt), "el propio disco no es alternativa de sí mismo"
    assert 15 not in _ids(alt) and 14 not in _ids(alt), "otro set u otro slot no cuentan"
    assert _ids(alt) == [12, 16, 11], "libres primero, después por nivel desc, después id"
