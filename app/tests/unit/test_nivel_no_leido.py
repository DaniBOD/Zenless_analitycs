"""`nivel` de un disco: "no lo leí" (None) deja de ser "Nivel 0" (Fase 3, 2026-09-17).

Hasta hoy el parser iniciaba `nivel` en 0 y el merge hacía `if new.nivel:`, así que el 0 significaba
las dos cosas. El costo medido: **23 discos en Nivel 0** en el inventario, imposibles de verificar —
el cierre del censo del 2026-08-30 los dejó anotados como deuda.

Y el 0 NO es un valor imposible: un disco recién dropeado está en `Nivel 0/15`, y si es S puede traer
sus 4 substats de entrada (verificado en `17_…_libres/Ejemplo_7_(reemplazar).png`). Por eso no
alcanza con "el 0 es sospechoso": hay que separarlos.

El test central es el último de la primera sección: un 0 leído y un nivel no leído no pueden terminar
iguales en ningún punto de la cadena (parser → aggregator → DB → UI).
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.parser_disc import DiscParsed, SubstatParsed, _parse_nivel
from app.core.parser_disc_s17 import DiscAggregator, disc_is_mature


def _sub(nombre="ATK", valor=19.0, rolls=0):
    return SubstatParsed(nombre, nombre, valor, "flat", rolls, 0.95)


def _disco(nivel, n_subs=4, slot=3):
    return DiscParsed(
        set_name_raw="Monarca del Pináculo", set_name_canon="Monarca del Pináculo", slot=slot,
        main_stat_raw="DEF", main_stat_canon="DEF", main_valor=184.0, main_unidad="flat",
        nivel=nivel, rareza="S",
        # Nombres que viajan igual de ida y vuelta por `normalize_stat_name` (PV→HP no: el test
        # compararía su propia normalización, no la identidad).
        subs=[_sub(n) for n in ("ATK", "DEF", "Daño Crítico", "Prob. Crítica")[:n_subs]],
        confianza_global=0.95,
    )


# --- el parser se abstiene en vez de decir 0 ---------------------------------------------------

def test_parse_nivel_lee_el_cero_y_se_abstiene_sin_numero():
    assert _parse_nivel("Nivel 0/15") == 0          # valor REAL
    assert _parse_nivel("Nivel 12/15") == 12
    assert _parse_nivel("") is None                  # no leído
    assert _parse_nivel("Atributo principal") is None


def test_el_disco_sin_nivel_leido_no_madura():
    """Antes maduraba con el 0 puesto y se guardaba como Nivel 0. Ahora se sigue fusionando; si
    nunca se lee, la emisión igual ocurre al techo de ciclos, pero con NULL y marcada."""
    assert disc_is_mature(_disco(None)) is False


def test_un_disco_en_nivel_0_SI_madura():
    """Regresión del QA 2026-06-27 (Velina, Salón huracanado Nv0): exigir 4 substats dejaba a los
    discos de nivel bajo sin capturar nunca. El 0 es un nivel como cualquier otro."""
    assert disc_is_mature(_disco(0, n_subs=3)) is True
    assert disc_is_mature(_disco(0, n_subs=4)) is True   # un S puede salir con 4 desde Nv0


def test_un_cero_leido_y_un_nivel_no_leido_no_terminan_iguales():
    """EL test de la fase. Si esto cae, el 0 volvió a significar dos cosas."""
    agg = DiscAggregator()
    cero = agg.merge(_disco(0))
    assert cero.nivel == 0 and disc_is_mature(cero)
    agg2 = DiscAggregator()
    sin_leer = agg2.merge(_disco(None))
    assert sin_leer.nivel is None and not disc_is_mature(sin_leer)
    assert cero.nivel != sin_leer.nivel


# --- por el PARSER de verdad, no por un objeto armado a mano -----------------------------------
#
# Los tests de arriba construyen `DiscParsed` directo. Eso deja sin cubrir justo la línea que
# originó la fase (el `nivel = 0` con el que arrancaba el parser): un sabotaje que la revirtió pasó
# en VERDE. Estos dos van por `_parse_s17_from_lines`, con el OCR de una captura real.

def _lineas_de(nombre: str):
    import json
    from pathlib import Path
    fix = Path(__file__).resolve().parent.parent / "fixtures" / "s17_ocr" / nombre
    d = json.loads(fix.read_text(encoding="utf-8"))
    return [(txt, conf, tuple(bb)) for txt, conf, bb in d["lines"]], d["W"], d["H"]


def test_el_parser_lee_el_nivel_de_una_captura_real():
    from app.core.parser_disc_s17 import _parse_s17_from_lines
    lineas, w, h = _lineas_de("Ejemplo_1.json")
    assert _parse_s17_from_lines(lineas, w, h).nivel == 15


def test_el_parser_se_ABSTIENE_cuando_la_linea_del_nivel_no_esta():
    """Sin 'Nivel N/15' en el OCR, el parser tiene que devolver None — no 0."""
    from app.core.parser_disc_s17 import _parse_s17_from_lines
    import re
    lineas, w, h = _lineas_de("Ejemplo_1.json")
    # Sólo las del patrón del panel ('Nivel N/15'); los 'Nivel 15' sueltos son de la grilla y del
    # hexágono, y el parser ya los descarta por su banda en X.
    patron = re.compile(r"nivel\s*\d+\s*/\s*15", re.IGNORECASE)
    sin_nivel = [l for l in lineas if not patron.search(l[0])]
    assert len(sin_nivel) < len(lineas), "la captura tenía que traer alguna línea de nivel"
    r = _parse_s17_from_lines(sin_nivel, w, h)
    assert r.nivel is None, "el 0 de antes decía 'Nivel 0' de un disco que no se leyó"
    assert r.set_name_raw and r.subs, "el resto del disco se sigue leyendo (B2: no se tira todo)"


# --- el aggregator no pisa lo leído con una ausencia -------------------------------------------

def test_un_frame_sin_nivel_no_borra_el_que_ya_se_habia_leido():
    agg = DiscAggregator()
    agg.merge(_disco(12))
    r = agg.merge(_disco(None))
    assert r.nivel == 12


def test_un_cero_leido_despues_SI_entra():
    """`if new.nivel:` descartaba el 0 por falsy — un disco que baja a 0 no existe, pero sí uno
    cuyo primer frame no se leyó y el segundo sí."""
    agg = DiscAggregator()
    agg.merge(_disco(None))
    r = agg.merge(_disco(0))
    assert r.nivel == 0


# --- la DB: NULL, marca, y la salida de la marca ------------------------------------------------

_SCHEMA = """
CREATE TABLE disc_sets (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, nombre_en TEXT,
                        bonus_2p_stat TEXT, bonus_2p_valor TEXT, bonus_4p_desc TEXT);
CREATE TABLE inventory_discs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id INTEGER, slot INTEGER NOT NULL,
    main_stat TEXT, main_valor REAL, unidad_main TEXT,
    sub1 TEXT, val1 REAL, rolls1 INTEGER DEFAULT 0, unidad1 TEXT,
    sub2 TEXT, val2 REAL, rolls2 INTEGER DEFAULT 0, unidad2 TEXT,
    sub3 TEXT, val3 REAL, rolls3 INTEGER DEFAULT 0, unidad3 TEXT,
    sub4 TEXT, val4 REAL, rolls4 INTEGER DEFAULT 0, unidad4 TEXT,
    nivel INTEGER DEFAULT 0, equipado INTEGER DEFAULT 0,
    agente_asignado INTEGER, descartado INTEGER DEFAULT 0,
    score_evaluacion REAL, agentes_compatibles TEXT, notas TEXT
);
INSERT INTO disc_sets VALUES (1, 'Monarca del Pináculo', 'Peak Monarch', 'PV', '+10%', '...');
"""


@pytest.fixture
def repo():
    from app.db.repositories import InventoryDiscRepo
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return InventoryDiscRepo(con)


def _fila(repo, disc_id):
    return repo._con.execute("SELECT * FROM inventory_discs WHERE id=?", (disc_id,)).fetchone()


def test_sin_nivel_se_guarda_NULL_y_marcado(repo):
    from app.db.repositories import MARCA_NIVEL_NO_LEIDO
    disc_id = repo.insert_from_parsed(_disco(None), set_id=1)
    fila = _fila(repo, disc_id)
    assert fila["nivel"] is None, "un 0 acá sería inventar un valor que existe de verdad"
    assert MARCA_NIVEL_NO_LEIDO in fila["notas"]


def test_releer_el_mismo_disco_sin_nivel_no_duplica(repo):
    """`nivel=?` no matchea NULL ni contra otro NULL: cada re-lectura habría insertado una fila."""
    repo.insert_from_parsed(_disco(None), set_id=1)
    encontrados = repo.find_all_by_identity(_disco(None), set_id=1)
    assert len(encontrados) == 1


def test_un_nivel_leido_despues_ADOPTA_la_fila_provisional_y_le_saca_la_marca(repo):
    """B2: un estado provisional necesita salida. Sin esto, el disco quedaba duplicado — la fila
    vieja con NULL de fantasma y una nueva con el nivel."""
    from app.db.repositories import MARCA_NIVEL_NO_LEIDO
    disc_id = repo.insert_from_parsed(_disco(None), set_id=1)
    candidatos = repo.find_all_by_identity(_disco(15), set_id=1)
    assert [d.id for d in candidatos] == [disc_id], "la fila sin nivel es el mismo disco"
    repo.update_from_parsed(disc_id, _disco(15))
    fila = _fila(repo, disc_id)
    assert fila["nivel"] == 15
    assert not fila["notas"] or MARCA_NIVEL_NO_LEIDO not in fila["notas"]
    assert repo._con.execute("SELECT COUNT(*) FROM inventory_discs").fetchone()[0] == 1


def test_un_disco_de_otro_nivel_no_se_adopta(repo):
    """La adopción mira identidad completa; dos discos distintos no se pisan."""
    repo.insert_from_parsed(_disco(15), set_id=1)
    otros = repo.find_all_by_identity(_disco(12), set_id=1)
    assert otros == []


def test_una_relectura_sin_nivel_no_pisa_el_nivel_que_la_fila_ya_tenia(repo):
    disc_id = repo.insert_from_parsed(_disco(15), set_id=1)
    repo.update_from_parsed(disc_id, _disco(None))
    assert _fila(repo, disc_id)["nivel"] == 15, "un NULL encima de un 15 bueno es perder el dato"


def test_el_cero_leido_se_guarda_como_cero_sin_marca(repo):
    from app.db.repositories import MARCA_NIVEL_NO_LEIDO
    disc_id = repo.insert_from_parsed(_disco(0), set_id=1)
    fila = _fila(repo, disc_id)
    assert fila["nivel"] == 0
    assert not fila["notas"] or MARCA_NIVEL_NO_LEIDO not in fila["notas"]


# --- la UI dice "sin leer", no 0 ---------------------------------------------------------------

def test_la_tabla_distingue_sin_leer_de_nivel_0():
    from app.ui.discos.tabla import NIVEL_SIN_LEER
    assert NIVEL_SIN_LEER != "0"


def test_la_fila_de_la_ui_conserva_el_none():
    """`int(r[24] or 0)` convertía el NULL en 0 y volvía a colapsar los dos casos en la pantalla."""
    from app.ui.discos.datos import FilaDisco
    f = FilaDisco(id=1, set="x", set_id=1, set_en="x", slot=3, main="DEF", main_valor=184.0,
                  main_unidad="flat", subs=(), rolls_total=0, nivel=None, equipado=False,
                  dueno=None, dueno_id=None)
    assert f.nivel is None
