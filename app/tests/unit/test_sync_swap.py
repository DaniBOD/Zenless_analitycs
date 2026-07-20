"""Swap de disco entre PJs persistido DENTRO de `DiscSyncer.persist_s17_disc` (rediseño 2026-07-19).

La corrección de la DB ya NO cuelga de atrapar el diálogo S23: cuando S17 ve un disco entrante que
ya existe equipado por OTRO PJ, la persistencia MUEVE esa fila (sin duplicar) en vez de insertar.
Origen: hint del diálogo S23 (cierto, `swap_origin_hint`) o, si no lo vimos, match por identidad
exacta ÚNICA. `moved`/`moved_from_nombre`/`swap_fresh` en el SyncResult guían el toast REEMPLAZADO.

Regresión del bug del 2026-07-18: Jazz de Jane → Velina insertaba filas nuevas (368/369) duplicando.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.parser_disc import DiscParsed, SubstatParsed

_SCHEMA = """
CREATE TABLE disc_archetypes (id INTEGER PRIMARY KEY, code TEXT UNIQUE);
CREATE TABLE agents (
    id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, rol TEXT DEFAULT 'Ataque',
    set_4p_id INTEGER, set_2p_id INTEGER, protected_build INTEGER DEFAULT 0
);
CREATE TABLE agent_score_thresholds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, agente_id INTEGER,
    threshold_equip REAL DEFAULT 0.75, threshold_upgrade REAL DEFAULT 0.50
);
CREATE TABLE agent_substat_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT, agente_id INTEGER, substat TEXT, peso REAL
);
CREATE TABLE disc_sets (
    id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, nombre_en TEXT,
    bonus_2p_stat TEXT, bonus_2p_valor TEXT, bonus_4p_desc TEXT
);
CREATE TABLE disc_set_archetype (set_id INTEGER, archetype_id INTEGER, prioridad INTEGER DEFAULT 1);
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
INSERT INTO disc_archetypes VALUES (1, 'ATK_DPS');
INSERT INTO disc_sets VALUES (1, 'Jazz caótico', 'Chaotic Jazz', 'Maestría de Anomalía', '+30', 'Al golpear...');
INSERT INTO disc_sets VALUES (2, 'Salón huracanado', 'Wuthering Salon', 'Daño Viento', '+10%', 'Wind...');
INSERT INTO agents (id, nombre, rol) VALUES (3, 'Jane', 'Anomalía');
INSERT INTO agents (id, nombre, rol) VALUES (5, 'Ellen', 'Ataque');
INSERT INTO agents (id, nombre, rol) VALUES (48, 'Velina', 'Anomalía');
INSERT INTO agent_score_thresholds (agente_id) VALUES (3), (5), (48);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    """DB temp con esquema mínimo + is_readonly=False. Copia el patrón de test_s17_avatar."""
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: False)
    path = tmp_path / "swap.db"
    con = sqlite3.connect(str(path))
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    return path


def _syncer(path):
    from app.core.sync_equip import DiscSyncer
    return DiscSyncer(db_path=path)


def _sub(name, val, rolls, unidad="flat"):
    return SubstatParsed(name, name, val, unidad, rolls, 0.95)


def _jazz(agent=None, fresh=False, hint=None):
    """Disco Jazz caótico slot 1 maduro, opcionalmente asignado + con hint de swap."""
    d = DiscParsed(
        set_name_raw="Jazz caótico", set_name_canon="Jazz caótico", slot=1,
        main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad="flat",
        nivel=15, rareza="S",
        subs=[_sub("ATK", 38.0, 1), _sub("Daño Crítico", 9.6, 1, "%"),
              _sub("Perforación", 27.0, 2), _sub("Maestría de Anomalía", 9.0, 0)],
        confianza_global=0.95,
    )
    if agent:
        d.agente_asignado_nombre = agent
        d.agente_asignado_conf = 0.95
    d.swap_fresh = fresh
    d.swap_origin_hint = hint
    return d


def _salon(agent=None):
    d = DiscParsed(
        set_name_raw="Salón huracanado", set_name_canon="Salón huracanado", slot=1,
        main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad="flat",
        nivel=15, rareza="S", subs=[_sub("ATK", 19.0, 0)], confianza_global=0.95,
    )
    if agent:
        d.agente_asignado_nombre = agent
        d.agente_asignado_conf = 0.95
    return d


def _rows(path):
    con = sqlite3.connect(str(path)); con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute(
        "SELECT id, set_id, slot, agente_asignado, equipado FROM inventory_discs ORDER BY id")]
    con.close()
    return out


def _count(path):
    con = sqlite3.connect(str(path))
    n = con.execute("SELECT COUNT(*) FROM inventory_discs").fetchone()[0]
    con.close()
    return n


def _insert_jazz_row(path, agente_id):
    """Inserta directo (bypass persist) un Jazz idéntico al de `_jazz()` equipado por `agente_id`.
    Necesario para armar 'dos PJs con disco idéntico' (persist los MOVERÍA en vez de duplicar)."""
    con = sqlite3.connect(str(path))
    cur = con.execute(
        "INSERT INTO inventory_discs (set_id, slot, main_stat, main_valor, "
        "sub1, val1, rolls1, sub2, val2, rolls2, sub3, val3, rolls3, sub4, val4, rolls4, "
        "nivel, equipado, agente_asignado) VALUES (1,1,'HP',2200.0, "
        "'ATK',38.0,1, 'Daño Crítico',9.6,1, 'Perforación',27.0,2, 'Maestría de Anomalía',9.0,0, "
        "15,1,?)", (agente_id,),
    )
    con.commit(); did = cur.lastrowid; con.close()
    return did


# --- hint del diálogo S23 (swap fresco) -------------------------------------

def test_swap_via_hint_mueve_sin_duplicar(db):
    """Jane tiene el Jazz; Velina tiene Salón. Con hint 'Jane' fresco → mover la fila de Jane a
    Velina (sin duplicar), desequipar el Salón de Velina, toast fresco."""
    s = _syncer(db)
    try:
        r_jane = s.persist_s17_disc(_jazz(agent="Jane"))     # Jane equipa Jazz
        s.persist_s17_disc(_salon(agent="Velina"))           # Velina equipa Salón
        assert _count(db) == 2
        # Velina ahora muestra el Jazz de Jane (hint del diálogo).
        res = s.persist_s17_disc(_jazz(agent="Velina", fresh=True, hint="Jane"))
    finally:
        s.close()
    assert res is not None and res.moved is True
    assert res.trigger == "s17_move"
    assert res.moved_from_nombre == "Jane" and res.swap_fresh is True
    assert res.disc_id == r_jane.disc_id                     # la MISMA fila, no una nueva
    assert _count(db) == 2, "no se creó fila nueva (no duplicó)"
    by_id = {r["id"]: r for r in _rows(db)}
    assert by_id[r_jane.disc_id]["agente_asignado"] == 48 and by_id[r_jane.disc_id]["equipado"] == 1
    # el Salón desplazado de Velina quedó desequipado
    salon = [r for r in _rows(db) if r["set_id"] == 2][0]
    assert salon["equipado"] == 0


def test_swap_fresh_dispara_flag_toast(db):
    """El hint fresco marca swap_fresh=True (el controller dispara el toast)."""
    s = _syncer(db)
    try:
        s.persist_s17_disc(_jazz(agent="Jane"))
        res = s.persist_s17_disc(_jazz(agent="Velina", fresh=True, hint="Jane"))
    finally:
        s.close()
    assert res.moved and res.swap_fresh


# --- respaldo por identidad (swap hecho fuera de la app, sin diálogo) --------

def test_swap_via_identidad_unica_sin_hint(db):
    """Sin hint (swap en otra sesión): identidad exacta ÚNICA → mover igual, pero NO fresco
    (no dispara toast; corrección tardía en silencio)."""
    s = _syncer(db)
    try:
        r_jane = s.persist_s17_disc(_jazz(agent="Jane"))
        res = s.persist_s17_disc(_jazz(agent="Velina"))       # sin hint
    finally:
        s.close()
    assert res.moved is True and res.disc_id == r_jane.disc_id
    assert res.moved_from_nombre == "Jane"
    assert res.swap_fresh is False, "sin hint → no es fresco → sin toast"
    assert _count(db) == 1


def test_identidad_ambigua_no_roba_inserta(db):
    """Dos PJs (Jane y Ellen) tienen el MISMO disco (identidad idéntica). Sin hint, mover sería
    robar al PJ equivocado → ambiguo → inserta fila nueva, deja los 2 intactos (RNF-02)."""
    jane_id = _insert_jazz_row(db, 3)
    ellen_id = _insert_jazz_row(db, 5)
    s = _syncer(db)
    try:
        assert _count(db) == 2
        res = s.persist_s17_disc(_jazz(agent="Velina"))       # sin hint → ambiguo
    finally:
        s.close()
    assert res.moved is False and res.trigger == "s17_insert"
    assert _count(db) == 3, "insertó (no robó)"
    by_id = {r["id"]: r for r in _rows(db)}
    assert by_id[jane_id]["agente_asignado"] == 3            # Jane intacta
    assert by_id[ellen_id]["agente_asignado"] == 5           # Ellen intacta


def test_hint_gana_a_ambiguedad(db):
    """Con Jane y Ellen ambos con el disco, el HINT 'Jane' desambigua → mueve el de Jane."""
    jane_id = _insert_jazz_row(db, 3)
    ellen_id = _insert_jazz_row(db, 5)
    s = _syncer(db)
    try:
        res = s.persist_s17_disc(_jazz(agent="Velina", fresh=True, hint="Jane"))
    finally:
        s.close()
    assert res.moved and res.disc_id == jane_id and res.moved_from_nombre == "Jane"
    assert {r["id"]: r["agente_asignado"] for r in _rows(db)}[ellen_id] == 5  # Ellen intacta


def test_hint_desactualizado_no_mueve_la_fila_equivocada(db):
    """RNF-02 · desde 2026-07-20 el pending S23 no expira por reloj, así que un hint viejo puede
    apuntar a un origen cuyo disco NO es el que estamos viendo (cancelaste el swap y después
    equipaste al destino OTRO disco del mismo set+slot). El hint solo vale si la fila del origen
    coincide por identidad COMPLETA; si no, se cae al respaldo, que sí acierta."""
    con = sqlite3.connect(str(db))
    # Jane tiene un Jazz slot 1 DISTINTO (nivel 9) — el hint apunta a esta fila.
    con.execute(
        "INSERT INTO inventory_discs (id, set_id, slot, main_stat, main_valor, "
        "sub1, val1, rolls1, nivel, equipado, agente_asignado) "
        "VALUES (600, 1, 1, 'HP', 2200.0, 'ATK', 38.0, 1, 9, 1, 3)"
    )
    con.commit(); con.close()
    ellen_id = _insert_jazz_row(db, 5)      # Ellen sí tiene EL disco que se está viendo
    s = _syncer(db)
    try:
        res = s.persist_s17_disc(_jazz(agent="Velina", fresh=True, hint="Jane"))
    finally:
        s.close()
    assert res.disc_id == ellen_id, "movió la fila del hint en vez de la que coincide de verdad"
    assert res.moved and res.moved_from_nombre == "Ellen"
    by_id = {r["id"]: r for r in _rows(db)}
    assert by_id[600]["agente_asignado"] == 3 and by_id[600]["equipado"] == 1  # Jane intacta


def test_reequipar_disco_propio_desplazado_no_duplica(db):
    """Velina tiene Jazz equipado y su Salón propio DESPLAZADO (equipado=0). Al re-equipar el
    Salón (sin diálogo S23 cross-PJ), se RE-EQUIPA la fila existente (no inserta), sin toast."""
    con = sqlite3.connect(str(db))
    # Salón desplazado de Velina (equipado=0, agente 48) idéntico al que se re-equipa.
    con.execute(
        "INSERT INTO inventory_discs (id, set_id, slot, main_stat, main_valor, "
        "sub1, val1, rolls1, nivel, equipado, agente_asignado) "
        "VALUES (500, 2, 1, 'HP', 2200.0, 'ATK', 19.0, 0, 15, 0, 48)"
    )
    con.commit(); con.close()
    s = _syncer(db)
    try:
        r_jazz = s.persist_s17_disc(_jazz(agent="Velina"))    # Velina equipa Jazz (nuevo)
        n0 = _count(db)
        res = s.persist_s17_disc(_salon(agent="Velina"))      # re-equipa su Salón desplazado
    finally:
        s.close()
    assert res.moved is False and res.trigger == "s17_reequip"
    assert res.disc_id == 500                                  # re-usó la fila existente
    assert _count(db) == n0, "no insertó duplicado"
    by_id = {r["id"]: r for r in _rows(db)}
    assert by_id[500]["equipado"] == 1                         # el Salón quedó equipado
    assert by_id[r_jazz.disc_id]["equipado"] == 0             # el Jazz quedó desplazado


def test_distinto_nivel_no_matchea_no_roba(db):
    """Jane tiene un Jazz idéntico pero a OTRO nivel → la identidad incluye nivel → no matchea →
    Velina inserta el suyo (no le roba a Jane el de distinto nivel)."""
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO inventory_discs (set_id, slot, main_stat, main_valor, "
        "sub1, val1, rolls1, sub2, val2, rolls2, sub3, val3, rolls3, sub4, val4, rolls4, "
        "nivel, equipado, agente_asignado) VALUES (1,1,'HP',2200.0, "
        "'ATK',38.0,1, 'Daño Crítico',9.6,1, 'Perforación',27.0,2, 'Maestría de Anomalía',9.0,0, "
        "9,1,3)"      # nivel 9 (el de Velina será nivel 15)
    )
    con.commit(); con.close()
    s = _syncer(db)
    try:
        res = s.persist_s17_disc(_jazz(agent="Velina"))       # nivel 15, sin hint
    finally:
        s.close()
    assert res.moved is False and res.trigger == "s17_insert"
    assert _count(db) == 2
    assert {r["id"]: r["agente_asignado"] for r in _rows(db)}[1] == 3   # el de Jane intacto


# --- casos de inserción / update normales (no-swap) --------------------------

def test_disco_genuinamente_nuevo_se_inserta(db):
    """Nadie más tiene el Jazz → alta normal (no move)."""
    s = _syncer(db)
    try:
        s.persist_s17_disc(_salon(agent="Velina"))
        res = s.persist_s17_disc(_jazz(agent="Velina"))       # Velina cambia Salón→Jazz nuevo
    finally:
        s.close()
    assert res.moved is False and res.trigger == "s17_swap"   # swap-out del Salón + insert Jazz
    assert _count(db) == 2


def test_re_ver_el_mismo_disco_no_duplica(db):
    """Regresión: re-ver el disco YA equipado por el destino → update, nunca move ni duplicado."""
    s = _syncer(db)
    try:
        r1 = s.persist_s17_disc(_jazz(agent="Velina"))
        res = s.persist_s17_disc(_jazz(agent="Velina"))       # mismo disco otra vez
    finally:
        s.close()
    assert res.moved is False and res.trigger == "s17_update"
    assert res.disc_id == r1.disc_id and _count(db) == 1


# --- gate readonly -----------------------------------------------------------

def test_readonly_no_mueve_ni_escribe(db, monkeypatch):
    import app.core.sync_equip as se
    s = _syncer(db)
    try:
        s.persist_s17_disc(_jazz(agent="Jane"))
        monkeypatch.setattr(se, "is_readonly", lambda: True)
        res = s.persist_s17_disc(_jazz(agent="Velina", fresh=True, hint="Jane"))
    finally:
        s.close()
    assert res is not None and res.trigger == "readonly" and res.moved is False
    assert _count(db) == 1                                    # nada nuevo
    assert _rows(db)[0]["agente_asignado"] == 3               # Jane intacta (no se movió)


# --- regresión del caso reportado -------------------------------------------

def test_regresion_jazz_de_jane_a_velina_no_duplica(db):
    """El caso exacto del 2026-07-18: Velina tenía Salón, se le equipa el Jazz de Jane. Antes
    salían 2 filas nuevas (368/369). Ahora: una sola fila se mueve, total constante."""
    s = _syncer(db)
    try:
        s.persist_s17_disc(_jazz(agent="Jane"))
        s.persist_s17_disc(_salon(agent="Velina"))
        n0 = _count(db)
        s.persist_s17_disc(_jazz(agent="Velina", fresh=True, hint="Jane"))   # swap-in
    finally:
        s.close()
    assert _count(db) == n0, "el total de discos no cambió (no duplicó)"
    # Exactamente un Jazz, equipado por Velina; ningún Jazz reclamado por Jane.
    jazz = [r for r in _rows(db) if r["set_id"] == 1]
    assert len(jazz) == 1 and jazz[0]["agente_asignado"] == 48 and jazz[0]["equipado"] == 1
