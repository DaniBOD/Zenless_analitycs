"""La mejora de un disco LIBRE actualiza su propia fila en vez de crear una segunda.

Segundo verbo del ciclo de vida (2026-09-06). El equipado ya estaba resuelto desde siempre: la
S17 posterior a la mejora lo reescribe por su clave natural `(PJ, slot)`. El libre no tiene esa
clave, y ahí está la fuga que documentó la hoja de ruta:

    "Subir de nivel cambia la identidad. Un drop a Nv0 tiene 3 substats (el 4º se desbloquea a
     +3). La identidad de dedup incluye nivel y substats, así que el mismo disco físico a Nv15
     con 4 substats no matchea su propia fila ⇒ segunda fila."

Con el verbo 1 (el drop entra) y sin este, cada disco farmeado que se mejora deja DOS filas: el
fantasma a Nivel 0 y el real. La DB crece con discos que no existen.

⚠️ **El match exige identidad ∧ VALORES, no sólo identidad.** Es la misma lección que la baja por
desmontaje, y acá pega más fuerte todavía: lo que se mejora VIENE de Nivel 0, donde todos los
rolls valen 0 y la firma de identidad colapsa a (set, slot, main, nombres de substat). Farmeando
el mismo nodo se juntan pilas de discos que comparten esa firma; actualizar al gemelo equivocado
le pisa los datos a un disco que el usuario sí tiene.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.parser_disc import DiscParsed, SubstatParsed
from app.db.repositories import Disc, InventoryDiscRepo

_SCHEMA = """
CREATE TABLE agents (
    id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, rol TEXT DEFAULT 'Ataque',
    set_4p_id INTEGER, set_2p_id INTEGER, protected_build INTEGER DEFAULT 0
);
CREATE TABLE disc_sets (
    id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, nombre_en TEXT,
    bonus_2p_stat TEXT, bonus_2p_valor TEXT, bonus_4p_desc TEXT
);
CREATE TABLE disc_archetypes (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL);
CREATE TABLE disc_set_archetype (set_id INTEGER, archetype_id INTEGER, prioridad INTEGER DEFAULT 1);
CREATE TABLE agent_score_thresholds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, agente_id INTEGER,
    threshold_equip REAL DEFAULT 0.75, threshold_upgrade REAL DEFAULT 0.50
);
CREATE TABLE agent_substat_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT, agente_id INTEGER, substat TEXT, peso REAL
);
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
INSERT INTO disc_sets VALUES (1, 'Rosa espinosa', 'Thorned Rose', 'DEF', '+16%', 'DMG +15%...');
INSERT INTO agents (id, nombre) VALUES (5, 'Ellen');
INSERT INTO agent_score_thresholds (agente_id) VALUES (5);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: False)
    p = tmp_path / "mejora.db"
    con = sqlite3.connect(str(p))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    return p


def _syncer(p):
    from app.core.sync_equip import DiscSyncer
    return DiscSyncer(db_path=p)


def _sub(n, v, r=0, u="flat"):
    return SubstatParsed(n, n, v, u, r, 0.95)


# Un drop de Rosa espinosa slot 2, tal como entra por S3: Nivel 0, 3 substats, todos con 0 rolls.
_SUBS_PRE = [_sub("DEF%", 4.8, 0, "%"), _sub("HP", 112.0, 0), _sub("Perforación", 9.0, 0)]
# El mismo disco a +3: se desbloqueó el 4º substat y uno ganó roll.
_SUBS_POST = [_sub("DEF%", 9.6, 1, "%"), _sub("HP", 112.0, 0), _sub("Perforación", 9.0, 0),
              _sub("Prob. Crítica", 2.4, 0, "%")]


def _disco(nivel, subs, *, slot=2, main_valor=79.0):
    return DiscParsed(
        set_name_raw="Rosa espinosa", set_name_canon="Rosa espinosa", slot=slot,
        main_stat_raw="ATK", main_stat_canon="ATK", main_valor=main_valor, main_unidad="flat",
        nivel=nivel, rareza="S", subs=subs, confianza_global=0.95,
    )


def _fila(p, *, subs=None, nivel=0, slot=2, main_valor=79.0, agente=None, equipado=0,
          descartado=0, notas=None, set_id=1):
    subs = _SUBS_PRE if subs is None else subs
    con = sqlite3.connect(str(p))
    cols = ("set_id, slot, main_stat, main_valor, nivel, agente_asignado, equipado, "
            "descartado, notas")
    vals = [set_id, slot, "ATK", main_valor, nivel, agente, equipado, descartado, notas]
    for i, s in enumerate(subs, start=1):
        cols += f", sub{i}, val{i}, rolls{i}"
        vals += [s.nombre_canon, s.valor, s.rolls]
    marcas = ",".join("?" * len(vals))
    cur = con.execute(
        f"INSERT INTO inventory_discs ({cols}) VALUES ({marcas})", vals)
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def _filas(p):
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute(
        "SELECT id, nivel, main_valor, unidad_main, sub1, rolls1, val1, sub4, "
        "agente_asignado, descartado "
        "FROM inventory_discs ORDER BY id")]
    con.close()
    return out


# --- el caso que existe para arreglar ---------------------------------------------------------

def test_la_mejora_migra_la_fila_en_vez_de_dejar_un_fantasma(db):
    """Es LA razón del verbo: sin esto quedan dos filas, la de Nivel 0 para siempre."""
    rid = _fila(db)
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) == rid
    filas = _filas(db)
    assert len(filas) == 1, "la mejora NO puede crear una segunda fila"
    assert filas[0]["id"] == rid and filas[0]["nivel"] == 3
    # El 4º substat que se desbloquea a +3 quedó escrito: es justo el que rompía la identidad.
    assert filas[0]["sub4"] == "Prob. Crítica"
    assert filas[0]["rolls1"] == 1


# --- el valor del main, que sube con el nivel -------------------------------------------------

def test_la_mejora_actualiza_el_valor_del_main(db):
    """⚠️ El main NO es fijo: es función determinista de (slot, main, nivel). ATK en slot 2 vale
    79 a Nv0 y 316 a Nv15 — medido sobre el inventario real, exacto en los 60 discos a Nv15.
    Hasta el 2026-09-06 ningún UPDATE lo escribía, así que una fila migrada a Nv15 conservaba el
    79 y el scoring la puntuaba con un ataque cuatro veces menor al real."""
    rid = _fila(db, main_valor=79.0)
    sync = _syncer(db)
    post = _disco(15, _SUBS_POST, main_valor=316.0)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), post) == rid
    fila = _filas(db)[0]
    assert fila["nivel"] == 15
    assert fila["main_valor"] == 316.0, "la fila quedó a Nv15 con el main de Nv0"


def test_un_main_sin_leer_no_pisa_el_valor_que_ya_estaba(db):
    """`None` es falta de lectura, no un dato. Pisar con él borraría lo que ya estaba bien — y el
    modal de mejora devolvió `main_valor=None` en vivo el 2026-09-06."""
    rid = _fila(db, main_valor=79.0)
    sync = _syncer(db)
    post = _disco(15, _SUBS_POST, main_valor=None)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), post) == rid
    fila = _filas(db)[0]
    assert fila["nivel"] == 15, "el nivel sí se actualiza"
    assert fila["main_valor"] == 79.0, "un main sin leer no puede borrar el que había"


# --- identidad ∧ valores: el gemelo de Nivel 0 ------------------------------------------------

def test_en_nivel_0_los_valores_deciden_cual_de_los_gemelos_se_actualiza(db):
    """Dos discos libres con la MISMA identidad (a Nivel 0 los rolls son todos 0) y distinto
    valor en un substat. Sin comparar valores, el update caería en cualquiera de los dos."""
    otros = [_sub("DEF%", 4.8, 0, "%"), _sub("HP", 112.0, 0), _sub("Perforación", 15.0, 0)]
    gemelo = _fila(db, subs=otros)      # mismo (set, slot, main, nombres) — sólo cambia un valor
    mio = _fila(db, subs=_SUBS_PRE)
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) == mio
    filas = {f["id"]: f for f in _filas(db)}
    assert filas[mio]["nivel"] == 3
    assert filas[gemelo]["nivel"] == 0, "se actualizó el disco equivocado"


def test_ante_dos_libres_indistinguibles_no_actualiza_ninguno(db):
    """Idénticos también en valores: elegir sería acertar la mitad de las veces (RNF-02)."""
    a = _fila(db)
    b = _fila(db)
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) is None
    assert [f["nivel"] for f in _filas(db)] == [0, 0]
    assert {f["id"] for f in _filas(db)} == {a, b}


def test_un_valor_ausente_no_rechaza_el_match(db):
    """El modal de mejora a veces no lee el valor del main (visto en vivo el 2026-09-06). Falta
    de evidencia no es evidencia de diferencia: el match sigue en pie."""
    rid = _fila(db)
    sync = _syncer(db)
    pre_sin_main = _disco(0, _SUBS_PRE, main_valor=None)
    assert sync.actualizar_por_mejora(pre_sin_main, _disco(3, _SUBS_POST)) == rid


# --- los que NO son error y no hay que tocar --------------------------------------------------

def test_el_disco_equipado_lo_resuelve_la_s17(db):
    """Con dueño, la clave correcta es (PJ, slot) y la S17 posterior ya lo hace. Tocar la fila
    acá sería una segunda autoridad sobre la misma pregunta."""
    rid = _fila(db, agente=5, equipado=1)
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) is None
    assert _filas(db)[0]["nivel"] == 0 and _filas(db)[0]["id"] == rid


def test_la_fila_marcada_dueno_incierto_no_cuenta_como_libre(db):
    """La marca AFIRMA que alguien lo tiene y no se pudo leer quién. Dueño NULL, pero no libre."""
    _fila(db, notas="dueno_no_identificado_2026-09-01")
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) is None
    assert _filas(db)[0]["nivel"] == 0


def test_una_fila_dada_de_baja_no_revive(db):
    _fila(db, descartado=1)
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) is None
    assert _filas(db)[0]["nivel"] == 0 and _filas(db)[0]["descartado"] == 1


def test_si_el_disco_nunca_se_capturo_no_escribe_nada(db):
    """0 candidatos NO es un error: se mejoró algo que la DB nunca vio. Entra en la próxima
    captura — insertarlo acá sería adivinar el estado previo."""
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) is None
    assert _filas(db) == []


def test_no_actualiza_si_el_nivel_no_subio(db):
    rid = _fila(db, nivel=3, subs=_SUBS_POST)
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(3, _SUBS_POST), _disco(3, _SUBS_POST)) is None
    assert _filas(db)[0]["id"] == rid and _filas(db)[0]["nivel"] == 3


def test_set_desconocido_no_escribe(db):
    _fila(db)
    sync = _syncer(db)
    pre = _disco(0, _SUBS_PRE)
    pre.set_name_raw = "Set que no existe"
    pre.set_name_canon = None
    post = _disco(3, _SUBS_POST)
    post.set_name_raw = "Set que no existe"
    post.set_name_canon = None
    assert sync.actualizar_por_mejora(pre, post) is None
    assert _filas(db)[0]["nivel"] == 0


def test_readonly_no_escribe(db, monkeypatch):
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: True)
    _fila(db)
    sync = _syncer(db)
    assert sync.actualizar_por_mejora(_disco(0, _SUBS_PRE), _disco(3, _SUBS_POST)) is None
    assert _filas(db)[0]["nivel"] == 0


# --- el predicado de valores, solo ------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    con = sqlite3.connect(str(tmp_path / "r.db"))
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    con.commit()
    yield InventoryDiscRepo(con)
    con.close()


_SUBS_FILA = [("DEF%", 4.8, "%", 0), ("HP", 112.0, "flat", 0), ("Perforación", 9.0, "flat", 0)]


def _disc_row(*, main_valor=79.0, subs=None):
    return Disc(id=1, set_id=1, slot=2, main_stat="ATK", main_valor=main_valor,
                main_unidad="flat", subs=_SUBS_FILA if subs is None else subs,
                nivel=0, equipado=0, agente_asignado=None, notas=None)


def test_valores_iguales_coinciden(repo):
    assert repo.row_matches_parsed_values(_disc_row(), _disco(0, _SUBS_PRE))


def test_un_substat_con_otro_valor_no_coincide(repo):
    d = _disc_row(subs=[("DEF%", 4.8, "%", 0), ("HP", 112.0, "flat", 0),
                        ("Perforación", 15.0, "flat", 0)])
    assert not repo.row_matches_parsed_values(d, _disco(0, _SUBS_PRE))


def test_main_con_otro_valor_no_coincide(repo):
    assert not repo.row_matches_parsed_values(_disc_row(main_valor=93.0), _disco(0, _SUBS_PRE))


def test_none_de_cualquier_lado_no_rechaza(repo):
    assert repo.row_matches_parsed_values(_disc_row(main_valor=None), _disco(0, _SUBS_PRE))
    assert repo.row_matches_parsed_values(_disc_row(), _disco(0, _SUBS_PRE, main_valor=None))
