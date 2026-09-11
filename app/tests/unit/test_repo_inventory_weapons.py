"""`InventoryWeaponRepo` / `WeaponRepo` — el inventario de armas, que hasta hoy nadie escribía.

`inventory_weapons` existía desde la Fase 1 con **0 filas** y sin un solo repo ni syncer que la
tocara. La migración `_26` la reconstruyó antes de que entrara la primera fila; estos tests fijan
lo que esa reconstrucción compró.

⚠️ **El esquema se lee del `.sql` de la migración, no se retipea.** Retipear el DDL en el test lo
convertiría en una segunda autoridad del esquema (B1): la migración podría cambiar y los tests
seguirían verdes contra una tabla que ya no existe así.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.db.repositories import InventoryWeaponRepo, WeaponRepo
from app.tests.conftest import _MIG_INVW, ddl_inventory_weapons


def test_la_migracion_sigue_teniendo_de_donde_sacar_el_esquema():
    """Guarda del propio helper: si la migración se renombra o se reescribe, el resto de los tests
    correría contra una tabla vacía de reglas y pasaría igual. Eso es A2 en estado puro — el
    silencio pareciendo un aprobado."""
    assert _MIG_INVW.exists(), f"falta la migración: {_MIG_INVW}"
    ddl = ddl_inventory_weapons()
    assert len(ddl) == 3, f"esperaba CREATE TABLE + 2 índices, salieron {len(ddl)}"


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        "CREATE TABLE weapons (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL,"
        " nombre_en TEXT, rareza TEXT);"
        "CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE);"
        "INSERT INTO weapons VALUES (1,'Engranaje infernal','Hellfire Gears','S');"
        "INSERT INTO weapons VALUES (2,'Aguijón agudo','Sharpened Stinger','S');"
        "INSERT INTO agents VALUES (5,'Ellen');"
        "INSERT INTO agents VALUES (6,'Jane');"
    )
    for st in ddl_inventory_weapons():
        c.execute(st)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def repo(con):
    return InventoryWeaponRepo(con)


# --- las libres (2026-09-11) --------------------------------------------------------------------

def _libre(repo, *, nivel=60, refinamiento=5, weapon_id=1):
    return repo.insert(weapon_id, nivel=nivel, refinamiento=refinamiento, agente_asignado=None,
                       equipado=0, origen_evidencia="s30_libre")


def test_find_free_trae_solo_las_libres_de_esa_clave_en_orden(repo):
    """Una libre no tiene PJ que la identifique: su clave es (arma, nivel, refinamiento), y las
    copias de esa clave se distinguen por ORDEN. Las equipadas del mismo modelo no cuentan."""
    a, b = _libre(repo), _libre(repo)
    repo.insert(1, nivel=60, refinamiento=5, agente_asignado=5, equipado=1,
                origen_evidencia="s30_badge")
    _libre(repo, nivel=0, refinamiento=1)
    _libre(repo, weapon_id=2)
    assert [w.id for w in repo.find_free(1, nivel=60, refinamiento=5)] == [a, b]


def test_find_free_compara_el_refinamiento_ilegible_con_IS(repo):
    """Con `=`, NULL no es igual a nada: una libre de refinamiento ilegible no se encontraría
    nunca y cada lectura insertaría otra fila."""
    a = _libre(repo, refinamiento=None)
    assert [w.id for w in repo.find_free(1, nivel=60, refinamiento=None)] == [a]


# --- lo que la migración compró ---------------------------------------------------------------

def test_un_pj_no_puede_tener_dos_armas_equipadas(repo, con):
    """La clave natural del inventario de armas, como restricción y no como premisa.

    Es el equivalente de `(PJ, slot)` en discos. Sin el índice único parcial, un error del matcher
    de badges deja dos filas reclamando el mismo PJ y nadie se entera — en discos, el caso análogo
    pasó dos días sin verse y apareció consultando a mano.
    """
    repo.insert(1, nivel=60, refinamiento=1, agente_asignado=5, equipado=1,
                origen_evidencia="s30_badge")
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert(2, nivel=60, refinamiento=1, agente_asignado=5, equipado=1,
                    origen_evidencia="s30_badge")


def test_el_indice_no_estorba_lo_legitimo(repo, con):
    """Las tres esquinas que un índice sin el `WHERE` habría roto."""
    repo.insert(1, nivel=60, refinamiento=1, agente_asignado=5, equipado=1,
                origen_evidencia="s30_badge")
    # El arma VIEJA del mismo PJ, ya desequipada, sigue siendo suya.
    repo.insert(2, nivel=60, refinamiento=5, agente_asignado=5, equipado=0,
                origen_evidencia="s26_desequipar")
    # Dos armas libres, sin dueño: los duplicados son normales acá (material de refinamiento).
    repo.insert(2, nivel=0, refinamiento=1, agente_asignado=None, equipado=0,
                origen_evidencia="s30_badge")
    repo.insert(2, nivel=0, refinamiento=1, agente_asignado=None, equipado=0,
                origen_evidencia="s30_badge")
    con.commit()
    assert len(repo.find_by_weapon(2)) == 3


def test_refinamiento_ilegible_queda_NULL(repo, con):
    """`read_refinamiento` se abstiene cuando no ve las 5 estrellas y devuelve `None` — sin las
    cinco no se distingue una estrella gris de un recorte corrido. La fila tiene que guardar ese
    `None` tal cual."""
    rid = repo.insert(1, nivel=60, refinamiento=None, agente_asignado=None, equipado=0,
                      origen_evidencia="s30_badge")
    con.commit()
    fila = con.execute("SELECT refinamiento FROM inventory_weapons WHERE id=?", (rid,)).fetchone()
    assert fila["refinamiento"] is None


def test_omitir_las_columnas_las_deja_en_NULL_y_no_las_inventa(con):
    """⚠️ Este es el test que de verdad cubre los DEFAULT, y hubo que corregirlo.

    Los dos de arriba pasan las columnas EXPLÍCITAS, y un `DEFAULT` sólo actúa cuando la columna se
    OMITE del INSERT — así que con ellos solos, restaurar `DEFAULT 0`/`DEFAULT 1` en la migración
    no rompía nada y el sabotaje pasaba en verde (A3: verificar el efecto, no la intención).

    Medido sobre el esquema viejo: `INSERT INTO … (weapon_id) VALUES (2)` devolvía
    `nivel=0, refinamiento=1` — dos datos inventados. Con 0 siendo un nivel legítimo (un arma
    recién sacada) y P1 un refinamiento legítimo, quedaban indistinguibles de una lectura real.
    """
    con.execute("INSERT INTO inventory_weapons (weapon_id, equipado) VALUES (1, 0)")
    con.commit()
    fila = con.execute("SELECT nivel, refinamiento FROM inventory_weapons").fetchone()
    assert fila["nivel"] is None, "un nivel omitido no puede aparecer como 0"
    assert fila["refinamiento"] is None, "un refinamiento omitido no puede aparecer como P1"


def test_nivel_ilegible_queda_NULL_y_no_cero(repo, con):
    """0 es un nivel VÁLIDO (un arma recién sacada), así que 'no leído' y 'nivel cero' tienen que
    poder distinguirse en la fila."""
    rid = repo.insert(1, nivel=None, refinamiento=1, agente_asignado=None, equipado=0,
                      origen_evidencia="s30_badge")
    con.commit()
    fila = con.execute("SELECT nivel FROM inventory_weapons WHERE id=?", (rid,)).fetchone()
    assert fila["nivel"] is None


def test_el_refinamiento_sigue_acotado_a_1_5(repo, con):
    """Admitir NULL no puede haber aflojado el rango."""
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert(1, nivel=60, refinamiento=9, agente_asignado=None, equipado=0,
                    origen_evidencia="s30_badge")


# --- búsquedas ---------------------------------------------------------------------------------

def test_encuentra_el_arma_equipada_por_un_pj(repo, con):
    rid = repo.insert(1, nivel=60, refinamiento=2, agente_asignado=5, equipado=1,
                      origen_evidencia="s26_desequipar")
    con.commit()
    hallada = repo.find_equipped_by_agent(5)
    assert hallada is not None and hallada.id == rid
    assert hallada.refinamiento == 2 and hallada.origen_evidencia == "s26_desequipar"
    assert repo.find_equipped_by_agent(6) is None


def test_find_by_weapon_devuelve_todas_las_copias(repo, con):
    """Los duplicados son normales: se guardan copias como material de refinamiento. Devolver la
    primera escondería el resto."""
    ids = [repo.insert(2, nivel=0, refinamiento=1, agente_asignado=None, equipado=0,
                       origen_evidencia="s30_badge") for _ in range(3)]
    con.commit()
    assert [w.id for w in repo.find_by_weapon(2)] == ids
    assert repo.find_by_weapon(1) == []


def test_una_fila_descartada_no_aparece_en_ninguna_busqueda(repo, con):
    rid = repo.insert(1, nivel=60, refinamiento=1, agente_asignado=5, equipado=1,
                      origen_evidencia="s26_desequipar")
    con.execute("UPDATE inventory_weapons SET descartado=1 WHERE id=?", (rid,))
    con.commit()
    assert repo.find_equipped_by_agent(5) is None
    assert repo.find_by_weapon(1) == []


# --- update_estado: un None no pisa lo que ya estaba -------------------------------------------

def test_el_update_refresca_nivel_y_refinamiento(repo, con):
    rid = repo.insert(1, nivel=0, refinamiento=1, agente_asignado=None, equipado=0,
                      origen_evidencia="s30_badge")
    repo.update_estado(rid, nivel=60, refinamiento=3)
    con.commit()
    w = repo.find_by_weapon(1)[0]
    assert (w.nivel, w.refinamiento) == (60, 3)


def test_un_dato_sin_leer_no_borra_el_que_ya_estaba(repo, con):
    """`None` es falta de lectura, no evidencia de cambio (RNF-02). En discos esta misma regla hubo
    que arreglarla en vivo cuando el valor del main quedó viejo; acá nace puesta."""
    rid = repo.insert(1, nivel=60, refinamiento=3, agente_asignado=None, equipado=0,
                      origen_evidencia="s30_badge")
    repo.update_estado(rid, nivel=None, refinamiento=None)
    con.commit()
    w = repo.find_by_weapon(1)[0]
    assert (w.nivel, w.refinamiento) == (60, 3)


def test_update_assignment_mueve_el_arma(repo, con):
    rid = repo.insert(1, nivel=60, refinamiento=1, agente_asignado=None, equipado=0,
                      origen_evidencia="s30_badge")
    repo.update_assignment(rid, 6, 1)
    con.commit()
    assert repo.find_equipped_by_agent(6).id == rid


# --- el catálogo no se da de alta ---------------------------------------------------------------

def test_el_catalogo_resuelve_por_nombre_exacto(con):
    cat = WeaponRepo(con)
    assert cat.get_id_by_nombre("Engranaje infernal") == 1
    assert cat.get_by_id(1).rareza == "S"


def test_un_arma_fuera_del_catalogo_no_resuelve_y_no_se_da_de_alta(con):
    """`WeaponRepo` es sólo lectura a propósito. El catálogo tiene 42 armas de menos y completarlo
    es una pasada curada aparte: `weapons.nombre` es el nombre ESPAÑOL in-game, que ninguna wiki
    accesible publica. Dar de alta con lo que devuelva el OCR repetiría el pecado original del
    catálogo, que fue emparejar por parecido."""
    cat = WeaponRepo(con)
    antes = con.execute("SELECT COUNT(*) FROM weapons").fetchone()[0]
    assert cat.get_id_by_nombre("Arma que no existe") is None
    assert cat.get_id_by_nombre(None) is None
    assert cat.get_id_by_nombre("") is None
    assert con.execute("SELECT COUNT(*) FROM weapons").fetchone()[0] == antes


def test_el_catalogo_no_resuelve_por_parecido(con):
    """Sin fuzzy acá a propósito: el parser ya canoniza con `match_catalogo` (difflib 0.84 + el
    colapso i/l/1 que impide que 'Modelo III' resuelva a 'Modelo II'). Repetirlo sería una segunda
    autoridad, y peor (B1)."""
    cat = WeaponRepo(con)
    assert cat.get_id_by_nombre("Engranaje infernaI") is None   # I mayúscula, no l
    assert cat.get_id_by_nombre("engranaje infernal") is None   # el catálogo distingue mayúsculas
