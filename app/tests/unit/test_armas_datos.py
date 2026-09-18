"""Datos de la pantalla Armas — funciones puras, sin Qt.

El diseño (`engines-screen.jsx` / `engines-data.jsx` de Claude Design) se dibujó cuando sólo 5
armas tenían datos leídos y el resto iba en ámbar como "tenencia sin leer". El censo cerró: hoy las
56 tienen nivel, refinamiento y dueño. Lo que se porta del diseño es el **criterio**, no sus datos:

- una celda por arma FÍSICA (decisión de Daniel), con el `×n` de copias del mismo modelo;
- "sin leer" y "por subir" son contadores **separados**: un nivel que no se leyó no es un nivel bajo;
- refinamiento mínimo 1 — cinco estrellas vacías se leerían como 0, que no existe en el juego.
"""
from __future__ import annotations

import pytest

from app.ui.armas.datos import (
    FilaArma, auditoria, conteos, filtrar, leer_armas, ordenar, pjs_sin_arma,
)


def _arma(con, inv_id, weapon_id, *, nivel=60, refin=5, agente=None, equipado=0, descartado=0):
    con.execute("INSERT INTO inventory_weapons (id, weapon_id, nivel, refinamiento, agente_asignado,"
                " equipado, descartado) VALUES (?,?,?,?,?,?,?)",
                (inv_id, weapon_id, nivel, refin, agente, equipado, descartado))


@pytest.fixture
def con(db_esquema_real):
    c = db_esquema_real
    c.executescript("""
        INSERT INTO weapons (id, nombre, nombre_en, rareza, tipo_especialidad, stat_base_valor,
                             stat_base_tipo, stat_secundario, stat_secundario_valor) VALUES
            (1, 'Llanto mielgo', 'Weeping Gemini', 'A', 'Anomalía', 594, 'ATK', 'ATK%', '25%'),
            (2, 'Sol exuvia', 'Sol Exuvia', 'S', 'Ataque', 713, 'ATK', 'ATK%', '30%'),
            (3, 'Arma sin arte', 'Weapon Without Art', 'S', NULL, NULL, NULL, 'Impact', NULL);
        INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, protected_build) VALUES
            (1, 'Yanagi', 'S', 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6', 0),
            (2, 'Pyrois', '∞', 'Éter', 'Ataque', 'Faetón', 0),
            (3, 'Anby', 'A', 'Eléctrico', 'Aturdimiento', 'Cunning Hares', 0),
            (4, 'Billy Estelar', 'S', 'Físico', 'Disruptivos', 'Cunning Hares', 0);
    """)
    _arma(c, 10, 1, agente=1, equipado=1)            # Llanto mielgo · Yanagi
    _arma(c, 11, 1, nivel=30, refin=2)               # otra copia, libre y a medio subir
    _arma(c, 12, 1, descartado=1)                    # descartada: no existe para la UI
    _arma(c, 13, 2, agente=2, equipado=1)            # Sol exuvia · Pyrois
    _arma(c, 14, 3, nivel=50, refin=1)               # ficticia: sin ícono ni especialidad, libre
    return c


def _ids(filas):
    return [f.id for f in filas]


def test_trae_las_activas_con_su_copia_y_su_dueno(con):
    f = {x.id: x for x in leer_armas(con)}
    assert sorted(f) == [10, 11, 13, 14], "la descartada no está"
    assert f[10].dueno == "Yanagi" and f[10].equipado and f[10].dueno_id == 1
    assert f[11].dueno is None and f[11].libre
    assert f[10].copias == 2 and f[11].copias == 2, "dos copias activas del mismo modelo"
    assert f[13].copias == 1
    assert f[10].nombre == "Llanto mielgo" and f[10].rareza == "A"
    assert f[14].especialidad is None, "sin dato: no se inventa"


def test_el_stat_base_llega_con_su_tipo(con):
    """La UI tiene que saber QUÉ stat es el base, no sólo el número: un engine de Armero tiene
    DEF base, y mostrarlo bajo un rótulo fijo de ATK es la misma mentira que tenía el parser."""
    f = {x.id: x for x in leer_armas(con)}
    assert (f[10].stat_base_valor, f[10].stat_base_tipo) == (594, "ATK")
    assert (f[14].stat_base_valor, f[14].stat_base_tipo) == (None, None), "sin dato: no se inventa"


def test_el_icono_falta_sin_inventar_otro(con):
    f = {x.id: x for x in leer_armas(con)}
    assert f[10].icono and f[10].icono.endswith("W-Engine_Weeping_Gemini.webp")
    # Un arma sin archivo de arte: ficticia a propósito. Hasta el 2026-09-15 este test usaba Sol
    # exuvia y Tetera esmeraldina, que no tenían ícono; Daniel los descargó y el test pasó a depender
    # de qué hay en la carpeta. Una ficticia no se "arregla" sola.
    assert f[14].icono is None, "sin archivo: hueco, no el ícono de otra arma"


def test_orden_s_primero_despues_alfabetico(con):
    assert [x.nombre for x in ordenar(leer_armas(con))] == [
        "Arma sin arte", "Sol exuvia", "Llanto mielgo", "Llanto mielgo"]


def test_conteos_del_header(con):
    k = conteos(leer_armas(con))
    assert k == {"armas": 4, "modelos": 3, "equipadas": 2, "libres": 2, "s": 2, "a": 2,
                 "sin_icono": 1, "sin_especialidad": 1}


def test_filtros_se_combinan(con):
    filas = leer_armas(con)
    assert sorted(_ids(filtrar(filas, {"rareza": {"A"}}))) == [10, 11]
    assert sorted(_ids(filtrar(filas, {"estado": {"libre"}}))) == [11, 14]
    assert sorted(_ids(filtrar(filas, {"rareza": {"A"}, "estado": {"libre"}}))) == [11]
    assert sorted(_ids(filtrar(filas, {"dueno": {"Yanagi"}}))) == [10]
    assert sorted(_ids(filtrar(filas, {"especialidad": {"Anomalía"}}))) == [10, 11]
    assert len(filtrar(filas, {})) == 4


def test_auditoria_separa_sin_leer_de_por_subir(con):
    """El criterio que el diseño remarca: un dato que no se leyó NO es un dato bajo."""
    filas = leer_armas(con)
    a = auditoria(filas)
    assert _ids(a["nivel_bajo"]) == [11, 14], "Nv 30 y Nv 50, leídos"
    assert _ids(a["refin_bajo"]) == [11, 14], "P2 y P1, leídos"
    assert a["nivel_sin_leer"] == [] and a["refin_sin_leer"] == []
    assert _ids(a["libres"]) == [11, 14]
    assert _ids(a["sin_icono"]) == [14]

    con.execute("UPDATE inventory_weapons SET nivel = NULL, refinamiento = NULL WHERE id = 11")
    a2 = auditoria(leer_armas(con))
    assert _ids(a2["nivel_sin_leer"]) == [11] and _ids(a2["refin_sin_leer"]) == [11]
    assert _ids(a2["nivel_bajo"]) == [14], "el sin leer NO cuenta como bajo"


def test_pjs_sin_arma_sale_del_roster(con):
    """Los 5 del diseño eran del roster viejo: la lista se calcula, no se copia."""
    # Billy (el PJ base del atuendo) se agrega acá y no en la fixture: con su propia arma equipada
    # no entra a la lista, y la regla del atuendo necesita que el nombre base exista.
    con.execute("INSERT INTO agents (id, nombre, rango, elemento, rol, faccion, protected_build)"
                " VALUES (5, 'Billy', 'A', 'Físico', 'Ataque', 'Cunning Hares', 0)")
    con.execute("INSERT INTO weapons (id, nombre, nombre_en, rareza) VALUES (4, 'Cúter', 'Box Cutter', 'A')")
    _arma(con, 15, 4, agente=5, equipado=1)

    sin = pjs_sin_arma(con)
    assert [p["nombre"] for p in sin] == ["Anby", "Billy Estelar"], "Billy sí tiene arma"
    assert sin[1]["variante_de"] == "Billy", "el atuendo se marca, como en el Roster"
    assert sin[0]["nivel"] is None, "nivel sin leer: no se inventa"
    assert sin[0]["elemento"] == "Eléctrico" and sin[0]["rol"] == "Aturdimiento"
