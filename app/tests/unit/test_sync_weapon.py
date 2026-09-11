"""`WeaponSyncer` — la primera escritura que `inventory_weapons` recibe en la vida del proyecto.

La tabla existía desde la Fase 1 con 0 filas y sin repo ni syncer. Estos tests fijan **qué se
escribe y, sobre todo, qué NO**.

⚠️ La regla de v1: **se escribe lo que se NOMBRA, nunca lo que se declara libre.** Sale de una
medición, no de una intuición: `test_s30_dueno_verdad_de_tierra.py` da 8/10 sobre el inventario, y
el desglose es lo que manda — los 6 que nombra salen los 6 bien, y el que falla AFIRMA que un arma
está libre siendo de Grace. Nombrar es fiable; negar dueño, no.

Y la guarda que en discos cubre ese caso —un libre que choca con una fila EQUIPADA se abstiene— no
sirve al principio de una pasada de censo, porque todavía no hay filas contra las cuales chocar.
Por eso acá la abstención es previa.

Los tests no necesitan capturas: el `WeaponParsed` se arma a mano, como hace `_disco()` en
`test_monitor_censo_discos.py`.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.core.parser_weapon_s26 import WeaponParsed
from app.tests.conftest import ddl_inventory_weapons

_BASE = (
    "CREATE TABLE weapons (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL,"
    " nombre_en TEXT, rareza TEXT);"
    "CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, rol TEXT DEFAULT 'Ataque');"
    "INSERT INTO weapons VALUES (1,'Engranaje infernal','Hellfire Gears','S');"
    "INSERT INTO weapons VALUES (2,'Aguijón agudo','Sharpened Stinger','S');"
    "INSERT INTO weapons VALUES (3,'Última cena','The Last Supper','A');"
    "INSERT INTO agents (id, nombre) VALUES (5,'Jane');"
    "INSERT INTO agents (id, nombre) VALUES (6,'Grace');"
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.core.sync_weapon as sw
    monkeypatch.setattr(sw, "is_readonly", lambda: False)
    p = tmp_path / "armas.db"
    con = sqlite3.connect(str(p))
    con.executescript(_BASE)
    for st in ddl_inventory_weapons():
        con.execute(st)
    con.commit()
    con.close()
    return p


def _syncer(p):
    from app.core.sync_weapon import WeaponSyncer
    return WeaponSyncer(db_path=p)


def _arma(nombre_canon="Engranaje infernal", *, dueno="Jane", nivel=60, refinamiento=2,
          nombre_raw=None):
    return WeaponParsed(
        nombre_raw=nombre_raw if nombre_raw is not None else (nombre_canon or "?"),
        nombre_canon=nombre_canon, nivel=nivel, nivel_max=60, atk_base=684,
        stat_avanzado_canon="Impacto", stat_avanzado_valor=18.0, stat_avanzado_unidad="%",
        rareza="S", refinamiento=refinamiento, dueno=dueno, tenencia="equipada",
        confianza=0.95,
    )


def _filas(p):
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute(
        "SELECT id, weapon_id, nivel, refinamiento, agente_asignado, equipado, origen_evidencia "
        "FROM inventory_weapons ORDER BY id")]
    con.close()
    return out


# --- lo que SÍ se escribe ----------------------------------------------------------------------

def test_un_arma_nombrada_entra_a_la_db(db):
    """Bucket D: la DB no la tenía."""
    res = _syncer(db).persist_s30_weapon(_arma())
    assert res is not None and res.trigger == "s30_insert"
    filas = _filas(db)
    assert len(filas) == 1
    assert filas[0]["weapon_id"] == 1 and filas[0]["agente_asignado"] == 5
    assert filas[0]["equipado"] == 1 and filas[0]["nivel"] == 60
    assert filas[0]["origen_evidencia"] == "s30_badge"


def test_volver_a_verla_actualiza_la_misma_fila(db):
    """Bucket A: la segunda pasada del censo no puede duplicar. La clave es el PJ."""
    sync = _syncer(db)
    primera = sync.persist_s30_weapon(_arma(nivel=50, refinamiento=1))
    segunda = sync.persist_s30_weapon(_arma(nivel=60, refinamiento=3))
    assert segunda is not None and segunda.trigger == "s30_update"
    assert segunda.inv_id == primera.inv_id
    filas = _filas(db)
    assert len(filas) == 1, "la segunda lectura NO puede crear otra fila"
    assert (filas[0]["nivel"], filas[0]["refinamiento"]) == (60, 3)


def test_un_dato_sin_leer_no_pisa_el_que_ya_estaba(db):
    """`None` es falta de lectura, no evidencia de cambio (RNF-02). `read_refinamiento` se abstiene
    cuando no ve las 5 estrellas, y eso no puede borrar un refinamiento ya conocido."""
    sync = _syncer(db)
    sync.persist_s30_weapon(_arma(nivel=60, refinamiento=3))
    sync.persist_s30_weapon(_arma(nivel=None, refinamiento=None))
    filas = _filas(db)
    assert (filas[0]["nivel"], filas[0]["refinamiento"]) == (60, 3)


# --- lo que NO se escribe, que es el punto de v1 ------------------------------------------------

def test_sin_dueno_y_sin_afirmar_libre_no_escribe(db):
    """"No sé de quién es" no es "es de nadie". Sólo una libre AFIRMADA se escribe sin dueño."""
    p = _arma(dueno=None)
    p.tenencia = "incierto"
    assert _syncer(db).persist_s30_weapon(p) is None
    assert _filas(db) == []


# --- las libres (2026-09-11) -------------------------------------------------------------------
#
# v1 no las escribía porque S30 afirmaba LIBRE el arma de Grace. Desde el 2026-09-11 LIBRE se afirma
# recién después de MEDIR el lugar del dueño (73× de gap sobre las 15 capturas), y ninguna de las 11
# con dueño lo produce. Una libre no tiene PJ que la identifique: su clave es (arma, nivel,
# refinamiento), y las copias idénticas se separan por el número de copia que calcula el monitor.

def _libre(nombre_canon="Última cena", *, nivel=60, refinamiento=5, copia=0):
    p = _arma(nombre_canon, dueno=None, nivel=nivel, refinamiento=refinamiento)
    p.tenencia, p.copia = "libre", copia
    return p


def test_una_libre_afirmada_entra_sin_dueno(db):
    res = _syncer(db).persist_s30_weapon(_libre())
    assert res is not None and res.trigger == "s30_libre_insert"
    [f] = _filas(db)
    assert f["weapon_id"] == 3 and f["agente_asignado"] is None and f["equipado"] == 0
    assert (f["nivel"], f["refinamiento"]) == (60, 5)
    assert f["origen_evidencia"] == "s30_libre"


def test_volver_a_ver_la_misma_libre_no_la_duplica(db):
    sync = _syncer(db)
    primera = sync.persist_s30_weapon(_libre(copia=0))
    segunda = sync.persist_s30_weapon(_libre(copia=0))
    assert segunda.trigger == "s30_libre_vista" and segunda.inv_id == primera.inv_id
    assert len(_filas(db)) == 1


def test_dos_copias_libres_son_dos_filas_y_otra_sesion_las_reusa(db):
    """Las dos Última cena libres de Daniel. La sesión siguiente ve las mismas dos y no agrega:
    el número de copia es por sesión, las filas son por clave."""
    s1 = _syncer(db)
    ids = [s1.persist_s30_weapon(_libre(copia=k)).inv_id for k in (0, 1)]
    s2 = _syncer(db)
    otra = [s2.persist_s30_weapon(_libre(copia=k)) for k in (0, 1)]
    assert [r.inv_id for r in otra] == ids
    assert {r.trigger for r in otra} == {"s30_libre_vista"}
    assert len(_filas(db)) == 2


def test_una_libre_no_toca_las_equipadas_del_mismo_modelo(db):
    """Las libres de Daniel son idénticas a las equipadas (Última cena Nv60 P5). Ni se confunden
    con ellas ni las mueven: la fila de Jane sigue siendo de Jane."""
    sync = _syncer(db)
    de_jane = sync.persist_s30_weapon(_arma("Última cena", dueno="Jane", nivel=60, refinamiento=5))
    antes = [f for f in _filas(db) if f["id"] == de_jane.inv_id][0]
    res = sync.persist_s30_weapon(_libre(copia=0))
    assert res.trigger == "s30_libre_insert" and res.inv_id != de_jane.inv_id
    assert [f for f in _filas(db) if f["id"] == de_jane.inv_id][0] == antes
    assert len(_filas(db)) == 2


def test_readonly_tampoco_escribe_libres(db, monkeypatch):
    import app.core.sync_weapon as sw
    monkeypatch.setattr(sw, "is_readonly", lambda: True)
    res = _syncer(db).persist_s30_weapon(_libre())
    assert res is not None and res.inv_id == -1
    assert _filas(db) == []


def test_un_dueno_que_no_resuelve_contra_el_roster_no_escribe(db):
    """El badge puede devolver una etiqueta con mojibake o un PJ que no está en el roster. Antes
    basura que un dato inventado (RNF-02)."""
    assert _syncer(db).persist_s30_weapon(_arma(dueno="N.º 11 con mojibake")) is None
    assert _filas(db) == []


def test_arma_fuera_de_catalogo_no_da_de_alta_el_catalogo(db):
    """El catálogo tiene 42 armas de menos y completarlo es una pasada CURADA aparte: el nombre
    español in-game no lo publica ninguna wiki accesible, y darlo de alta con lo que devuelva el
    OCR repetiría el pecado original del catálogo (emparejar por parecido)."""
    con = sqlite3.connect(str(db))
    antes = con.execute("SELECT COUNT(*) FROM weapons").fetchone()[0]
    con.close()
    p = _arma(nombre_canon=None, nombre_raw="Cilindro neumático")
    assert _syncer(db).persist_s30_weapon(p) is None
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT COUNT(*) FROM weapons").fetchone()[0] == antes
    con.close()
    assert _filas(db) == []


def test_canonizada_pero_sin_fila_en_weapons_no_escribe(db):
    """Coherencia entre el catálogo que usó el parser y el de la DB. Si no coinciden, la FK
    `weapon_id NOT NULL` reventaría; mejor abstenerse y avisar."""
    assert _syncer(db).persist_s30_weapon(_arma(nombre_canon="Arma que no está en weapons")) is None
    assert _filas(db) == []


# --- conflictos: se abstiene, no elige ----------------------------------------------------------

def test_el_pj_ya_figura_con_otra_arma_no_se_pisa(db):
    """Bucket B. Un PJ lleva un arma sola, así que dos tiles nombrando al mismo PJ significa que
    UNA de las dos lecturas está mal — y no hay forma de saber cuál."""
    sync = _syncer(db)
    primera = sync.persist_s30_weapon(_arma("Engranaje infernal", dueno="Jane"))
    assert sync.persist_s30_weapon(_arma("Aguijón agudo", dueno="Jane")) is None
    filas = _filas(db)
    assert len(filas) == 1 and filas[0]["id"] == primera.inv_id
    assert filas[0]["weapon_id"] == 1, "la fila que ya estaba no se toca"


def test_una_segunda_copia_del_mismo_engine_entra_como_fila_nueva(db):
    """Bucket C. Dos PJs con el MISMO W-Engine no es un conflicto: es tener dos copias.

    La v1 se abstenía acá, y la pasada en vivo del 2026-09-08 mostró el costo: Daniel tiene
    'Última cena' equipada por Gatillo, Koleda y Lycaon, y sólo se escribió la primera. Las
    otras dos se descartaron con un warning que decía 'una de las dos lecturas está mal'.

    Las armas son FUNGIBLES —dos copias son idénticas en todo campo observable— así que tener
    varias es lo normal en las A de gacha estándar. El invariante real es *un PJ lleva un arma
    sola*, y de ese ya se ocupan el bucket B y el índice único parcial; pedir además que un
    arma tenga un solo dueño es más estricto que el invariante.
    """
    sync = _syncer(db)
    de_jane = sync.persist_s30_weapon(_arma("Última cena", dueno="Jane"))
    de_grace = sync.persist_s30_weapon(_arma("Última cena", dueno="Grace"))
    assert de_grace is not None, "la segunda copia se escribe, no se descarta"
    assert de_grace.trigger == "s30_insert_copia", (
        "el trigger la distingue de un alta común: la pasada tiene que poder contarlas aparte")
    filas = _filas(db)
    assert len(filas) == 2
    assert {f["agente_asignado"] for f in filas} == {5, 6}
    assert de_jane.inv_id != de_grace.inv_id


def test_una_segunda_copia_no_le_saca_el_arma_al_primer_pj(db):
    """La garantía que TIENE que sobrevivir al cambio de arriba: insertar una copia no toca la
    fila que ya estaba. Mover sobre una lectura equivocada le sacaría el arma a un PJ que sí la
    tiene — destructivo e invisible. Insertar de más se corrige en el próximo censo."""
    sync = _syncer(db)
    de_jane = sync.persist_s30_weapon(_arma("Última cena", dueno="Jane", nivel=60,
                                            refinamiento=5))
    antes = [f for f in _filas(db) if f["id"] == de_jane.inv_id][0]
    sync.persist_s30_weapon(_arma("Última cena", dueno="Grace", nivel=10, refinamiento=1))
    despues = [f for f in _filas(db) if f["id"] == de_jane.inv_id][0]
    assert despues == antes, "la fila de Jane queda intacta, incluido su nivel/refinamiento"


# --- readonly ----------------------------------------------------------------------------------

def test_readonly_no_escribe(db, monkeypatch):
    import app.core.sync_weapon as sw
    monkeypatch.setattr(sw, "is_readonly", lambda: True)
    res = _syncer(db).persist_s30_weapon(_arma())
    assert res is not None and res.trigger == "readonly"
    assert res.inv_id == -1, "el placeholder readonly no es una fila"
    assert _filas(db) == []


def test_readonly_no_deja_rastro_en_el_archivo(db, monkeypatch):
    """El sha256 antes/después es la prueba que el proyecto usa para afirmar que una corrida
    read-only no escribió — el mismo criterio por el que el censo del roster vive en otra DB."""
    import hashlib

    import app.core.sync_weapon as sw
    monkeypatch.setattr(sw, "is_readonly", lambda: True)
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    _syncer(db).persist_s30_weapon(_arma())
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes
