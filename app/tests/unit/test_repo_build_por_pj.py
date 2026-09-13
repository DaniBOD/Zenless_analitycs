"""`InventoryDiscRepo.find_equipped_by_agent` — los 6 discos que un PJ tiene puestos.

Lo pide el hexágono de la pantalla en vivo: cuando se ve un disco cuyo dueño está escrito en
pantalla, se dibuja el build de ESE PJ con el slot del disco marcado.

La autoridad es `inventory_discs.agente_asignado` + `equipado`.

Existió un `AgentDiscRepo` documentado como *"build actual de cada PJ"* que leía `agent_discs`,
con **0 filas**: habría dibujado un hexágono vacío para siempre sin un solo error. En esta sesión se
lo borró creyendo que nadie lo usaba (un grep recortado) y hubo que restaurarlo: lo usaba el
optimizador, que medía el build actual contra esa tabla vacía. El optimizador se arregló en
`2fd8606` y ahí sí se borró el repo. Este método es la única autoridad del build de un PJ (B1).
"""
from __future__ import annotations

from app.db.repositories import InventoryDiscRepo


def _disco(con, id_, *, slot, agente=1, equipado=1, descartado=0, main="ATK%"):
    con.execute(
        "INSERT INTO inventory_discs (id, set_id, slot, main_stat, main_valor, nivel,"
        " equipado, agente_asignado, descartado) VALUES (?,1,?,?,30.0,15,?,?,?)",
        (id_, slot, main, equipado, agente, descartado),
    )


def test_devuelve_el_build_indexado_por_slot(mem_db):
    for s in range(1, 7):
        _disco(mem_db, 100 + s, slot=s)
    build = InventoryDiscRepo(mem_db).find_equipped_by_agent(1)
    assert sorted(build) == [1, 2, 3, 4, 5, 6]
    assert build[4].id == 104


def test_un_slot_vacio_no_aparece(mem_db):
    """Un PJ con 5 discos: el hueco es un hueco, no un None disfrazado ni un crash."""
    for s in (1, 2, 3, 5, 6):
        _disco(mem_db, 100 + s, slot=s)
    build = InventoryDiscRepo(mem_db).find_equipped_by_agent(1)
    assert 4 not in build
    assert len(build) == 5


def test_ignora_los_descartados(mem_db):
    """Una fila con baja lógica (desmontaje, fantasma corregido) ya no está en el PJ."""
    _disco(mem_db, 101, slot=1)
    _disco(mem_db, 102, slot=2, descartado=1)
    assert sorted(InventoryDiscRepo(mem_db).find_equipped_by_agent(1)) == [1]


def test_ignora_los_asignados_que_no_estan_equipados(mem_db):
    """`agente_asignado` sin `equipado=1` no es un disco puesto."""
    _disco(mem_db, 101, slot=1)
    _disco(mem_db, 102, slot=2, equipado=0)
    assert sorted(InventoryDiscRepo(mem_db).find_equipped_by_agent(1)) == [1]


def test_no_mezcla_pjs(mem_db):
    _disco(mem_db, 101, slot=1, agente=1)
    _disco(mem_db, 201, slot=1, agente=2)
    assert InventoryDiscRepo(mem_db).find_equipped_by_agent(1)[1].id == 101
    assert InventoryDiscRepo(mem_db).find_equipped_by_agent(2)[1].id == 201


def test_pj_sin_discos(mem_db):
    assert InventoryDiscRepo(mem_db).find_equipped_by_agent(99) == {}


def test_con_dos_filas_en_el_mismo_slot_gana_la_mas_reciente(mem_db):
    """No debería pasar (un PJ tiene un disco por slot), pero la DB lo permite. Se toma el id más
    alto —la fila más nueva— de forma DETERMINISTA y no se revienta: la vista no es el lugar para
    arreglar el invariante.

    Ojo, no es lo que hace `find_equipped_by_agent_slot`: su `LIMIT 1` no tiene `ORDER BY`, así que
    ante un duplicado devuelve la que SQLite encuentre primero."""
    _disco(mem_db, 101, slot=3)
    _disco(mem_db, 150, slot=3)
    assert InventoryDiscRepo(mem_db).find_equipped_by_agent(1)[3].id == 150
