"""Persistir un disco SIN dueño — el 20 % del inventario que hasta acá se veía y se tiraba.

`persist_s17_disc` cortaba en seco cuando no había PJ confiable:

    if agente_id is None:
        return None

Y estaba bien mientras "sin dueño" significara "no sé quién": escribir con la clave `(PJ, slot)`
sin saber el PJ colisiona entre PJs (72 % de los discos comparten firma con otro). Pero desde que
S9 distingue **libre** de **no sé**, esos dos casos dejaron de ser uno solo, y sólo el segundo
justifica no escribir.

La regla queda: **se persiste lo que se AFIRMA, no lo que no se pudo leer.**

- `equip_libre=True` → hay evidencia positiva (se leyó la esquina del tile y no hay avatar) ⇒ se
  inserta con `agente_asignado = NULL`.
- sin dueño y sin afirmación → sigue sin escribirse. Ausencia de dato no es dato.

Y como para un disco libre no existe `(PJ, slot)`, la deduplicación sale por **identidad completa**
— la misma clave que se arregló el 2026-08-18 (`find_all_by_identity`).
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.parser_disc import DiscParsed, SubstatParsed

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
INSERT INTO disc_sets VALUES (1, 'Monarca del Pináculo', 'Peak Monarch', 'PV', '+10%', 'Al...');
INSERT INTO agents (id, nombre) VALUES (5, 'Ellen');
INSERT INTO agent_score_thresholds (agente_id) VALUES (5);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: False)
    p = tmp_path / "libre.db"
    con = sqlite3.connect(str(p))
    con.executescript(_SCHEMA)
    con.commit(); con.close()
    return p


def _syncer(p):
    from app.core.sync_equip import DiscSyncer
    return DiscSyncer(db_path=p)


def _sub(n, v, r, u="flat"):
    return SubstatParsed(n, n, v, u, r, 0.95)


_SUBS = [_sub("ATK", 38.0, 1), _sub("Daño Crítico", 9.6, 1, "%"),
         _sub("Perforación", 27.0, 2), _sub("Maestría de Anomalía", 9.0, 0)]
_OTROS = [_sub("PV", 320.0, 2), _sub("Prob. Crítica", 4.8, 1, "%"),
          _sub("DEF%", 12.0, 0, "%"), _sub("Impacto", 3.0, 1)]


def _disco(libre: bool, dueno: str | None = None, subs=None):
    d = DiscParsed(
        set_name_raw="Monarca del Pináculo", set_name_canon="Monarca del Pináculo", slot=3,
        main_stat_raw="DEF", main_stat_canon="DEF", main_valor=184.0, main_unidad="flat",
        nivel=15, rareza="S", subs=subs if subs is not None else _SUBS, confianza_global=0.95,
    )
    d.equip_libre = libre
    if dueno:
        d.agente_asignado_nombre = dueno
        d.agente_asignado_conf = 0.95
    return d


def _filas(p):
    con = sqlite3.connect(str(p)); con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute(
        "SELECT id, set_id, slot, equipado, agente_asignado FROM inventory_discs ORDER BY id")]
    con.close()
    return out


# --- lo que ahora sí se escribe ---------------------------------------------------------------

def test_un_disco_afirmado_LIBRE_se_persiste_sin_dueno(db):
    """El caso que desbloquea el censo. La fila queda con `agente_asignado = NULL` y
    `equipado = 0`: es lo que se vio, sin adornos."""
    r = _syncer(db).persist_s17_disc(_disco(libre=True))
    assert r is not None, "un disco libre ya no se descarta"
    filas = _filas(db)
    assert len(filas) == 1
    assert filas[0]["agente_asignado"] is None
    assert filas[0]["equipado"] == 0


def test_sin_dueno_y_SIN_afirmacion_sigue_sin_escribirse(db):
    """La mitad que no cambia, y es la que protege la DB: un badge que no se pudo leer no es un
    disco libre. Escribirlo sería convertir 'no sé' en un dato."""
    assert _syncer(db).persist_s17_disc(_disco(libre=False)) is None
    assert _filas(db) == []


def test_ver_el_MISMO_disco_libre_dos_veces_no_lo_duplica(db):
    """Sin `(PJ, slot)` la única clave posible es la identidad completa. Una pasada de scroll ve
    el mismo disco en varios frames: si cada uno insertara, el censo contaría de más."""
    s = _syncer(db)
    r1 = s.persist_s17_disc(_disco(libre=True))
    r2 = s.persist_s17_disc(_disco(libre=True))
    assert r1.disc_id == r2.disc_id
    assert len(_filas(db)) == 1


def test_dos_discos_libres_DISTINTOS_son_dos_filas(db):
    """Mismo set, slot, main y valor de main — sólo cambian los substats. Es exactamente el caso
    que la firma gruesa colapsaba."""
    s = _syncer(db)
    r1 = s.persist_s17_disc(_disco(libre=True))
    r2 = s.persist_s17_disc(_disco(libre=True, subs=_OTROS))
    assert r1.disc_id != r2.disc_id
    assert len(_filas(db)) == 2


# --- el borde que puede corromper -------------------------------------------------------------

def test_un_libre_cuya_identidad_coincide_con_uno_EQUIPADO_no_toca_esa_fila(db, caplog):
    """Dos lecturas posibles y ninguna verificable: o es el disco equipado que acaban de sacar, o
    es su gemelo (hay 22 pares indistinguibles en el inventario real).

    Actualizar la fila equipada la marcaría libre — un falso LIBRE, que es justo lo que habilita un
    reemplazo erróneo. Insertar duplicaría. Se abstiene y avisa (RNF-02)."""
    import logging
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO inventory_discs (set_id, slot, main_stat, main_valor, "
        "sub1, val1, rolls1, sub2, val2, rolls2, sub3, val3, rolls3, sub4, val4, rolls4, "
        "nivel, equipado, agente_asignado) VALUES (1,3,'DEF',184.0, 'ATK',38.0,1, "
        "'Daño Crítico',9.6,1, 'Perforación',27.0,2, 'Maestría de Anomalía',9.0,0, 15,1,5)")
    con.commit(); con.close()
    with caplog.at_level(logging.WARNING):
        r = _syncer(db).persist_s17_disc(_disco(libre=True))
    filas = _filas(db)
    assert len(filas) == 1, "no inserta un duplicado"
    assert filas[0]["agente_asignado"] == 5, "no desequipa la fila de Ellen"
    assert filas[0]["equipado"] == 1
    assert r is None, "no puede afirmar que persistió algo"
    assert any("equipad" in m.lower() for m in caplog.messages), \
        "la discrepancia tiene que quedar registrada"


def test_un_disco_CON_dueno_sigue_yendo_por_el_camino_de_siempre(db):
    """Guarda de no-regresión: la afirmación de libre no debe secuestrar el camino normal."""
    r = _syncer(db).persist_s17_disc(_disco(libre=False, dueno="Ellen"))
    assert r is not None
    filas = _filas(db)
    assert len(filas) == 1 and filas[0]["agente_asignado"] == 5 and filas[0]["equipado"] == 1


def test_en_readonly_el_disco_libre_tampoco_escribe(db, monkeypatch):
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: True)
    _syncer(db).persist_s17_disc(_disco(libre=True))
    assert _filas(db) == [], "read-only es read-only también por este camino"


# --- el TERCER desenlace: hay dueño, pero no se lo pudo nombrar --------------------------------
#
# Medido en la corrida real del 2026-08-20: 2 de 119 discos (1,7 %) se descartaban ENTEROS por
# esto — set, slot, nivel, main y los cuatro substats bien leídos, tirados por un solo campo.
# Sobre los 405 del inventario son ~7, y con la abstención medida del descriptor (4,3 %) el techo
# real es ~17.
#
# Se persisten con la FORMA de un libre (`agente_asignado = NULL`, `equipado = 0`) pero MARCADOS.
# La marca no es cosmética: sin ella la fila entra al bucket `libres` de `_persist_disco_libre` y
# el próximo disco genuinamente libre con la misma identidad la pisa con `update_from_parsed` —
# dos discos distintos fusionados en una fila, en silencio.

_MARCA = "dueno_no_identificado"


def _disco_dueno_incierto(subs=None):
    """Badge PRESENTE (hay avatar) pero el matcher no pudo nombrarlo. Distinto de `equip_libre`
    (no hay avatar) y distinto de un tile que no se pudo localizar (no se sabe nada)."""
    d = _disco(libre=False, subs=subs)
    d.equip_dueno_incierto = True
    return d


def _notas(p):
    con = sqlite3.connect(str(p))
    out = [r[0] for r in con.execute("SELECT notas FROM inventory_discs ORDER BY id")]
    con.close()
    return out


def test_un_disco_con_dueno_INNOMBRABLE_se_persiste_MARCADO(db):
    """Lo que hoy se pierde. La fila se escribe, y lleva la marca que dice por qué está sin dueño:
    no es lo mismo 'no lo tiene nadie' que 'no pude leer de quién es' (RNF-02)."""
    r = _syncer(db).persist_s17_disc(_disco_dueno_incierto())
    assert r is not None, "el disco ya no se descarta entero"
    filas = _filas(db)
    assert len(filas) == 1
    assert filas[0]["agente_asignado"] is None
    assert filas[0]["equipado"] == 0
    assert _MARCA in (_notas(db)[0] or ""), \
        "sin la marca la fila es indistinguible de un libre genuino"


def test_una_fila_MARCADA_no_es_pisada_por_un_libre_genuino(db):
    """**El test que justifica la marca.** Si la fila marcada entrara al bucket `libres`, este
    segundo disco —libre de verdad, misma identidad— la actualizaría y los dos quedarían como uno.
    Con 22 pares gemelos en el inventario real, es un caso alcanzable, no teórico."""
    _syncer(db).persist_s17_disc(_disco_dueno_incierto())
    _syncer(db).persist_s17_disc(_disco(libre=True))

    filas = _filas(db)
    assert len(filas) == 2, "el libre genuino pisó la fila marcada en vez de insertar la suya"
    notas = _notas(db)
    assert sum(_MARCA in (n or "") for n in notas) == 1, "la marca se propagó o se perdió"


def test_una_relectura_incierta_actualiza_la_fila_y_conserva_la_marca(db):
    """Dos lecturas inciertas con la misma identidad son ambiguas por construcción: puede ser el
    mismo disco re-visto (tras un re-arme o un reinicio) o su gemelo. No hay forma de saberlo.

    Se resuelve **igual que los libres**: se actualiza la fila que ya está. Inventar una regla
    distinta para este caso —insertar siempre— duplicaría en cada re-lectura, y haría que dos
    casos idénticos se comporten distinto según por qué rama entraron. El techo por gemelos ya lo
    reporta el censo; no se cierra a la fuerza acá.

    Lo que sí hay que verificar es que la actualización **no borre la marca**: si la borrara, la
    fila pasaría al bucket de libres en la próxima pasada y volvería a ser pisable."""
    _syncer(db).persist_s17_disc(_disco_dueno_incierto())
    _syncer(db).persist_s17_disc(_disco_dueno_incierto())
    assert len(_filas(db)) == 1, "una re-lectura no puede duplicar la fila"
    assert _MARCA in (_notas(db)[0] or ""),         "la actualización borró la marca — la fila volvería a parecer un libre genuino"


def test_sin_señal_de_badge_SIGUE_sin_escribirse(db):
    """No-regresión de la guarda que sí protege: un tile que no se pudo localizar no dice nada
    sobre el dueño. Escribirlo convertiría 'no sé' en dato — que es exactamente lo que la rama
    original evitaba, y con razón."""
    d = _disco(libre=False)          # ni libre, ni dueño incierto: sin señal
    assert _syncer(db).persist_s17_disc(d) is None
    assert _filas(db) == []


def test_la_marca_lleva_FECHA_para_poder_reconciliarlos_despues(db):
    """El valor de la marca no es sólo el flag: es poder listar 'los que quedaron pendientes de
    tal pasada'. Mismo formato que `no_visto_en_censo_<fecha>` de census_store."""
    import re
    _syncer(db).persist_s17_disc(_disco_dueno_incierto())
    assert re.search(rf"{_MARCA}_\d{{4}}-\d{{2}}-\d{{2}}", _notas(db)[0] or ""), \
        f"la nota no tiene la forma esperada: {_notas(db)[0]!r}"
