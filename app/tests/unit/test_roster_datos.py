"""Datos de la pantalla Roster (Parte B del diseño v1) — funciones puras, sin Qt.

La pantalla se apoya en marcas que traducen el estado de cada PJ, y cada marca tiene UNA fuente:

| marca | fuente |
|---|---|
| esquina rayada ámbar ("le faltan datos") | no tiene filas en `agent_thresholds` |
| discos ≠ 6 | `inventory_discs` equipados y no descartados |
| sin arma | `inventory_weapons` equipada y no descartada |
| atuendo | `roster_declaration._variantes_de_atuendo`, la regla que ya usa el editor |

Si alguna se calculara de otra forma en la celda, la pantalla y el editor de roster podrían
decir cosas distintas del mismo PJ.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.ui.roster.datos import (
    CeldaPJ, calcular_grilla, conteos_header, filtrar, leer_roster, ordenar,
)


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT, rango TEXT, nivel INTEGER,
            mindscape INTEGER, elemento TEXT, rol TEXT, faccion TEXT);
        CREATE TABLE agent_thresholds (id INTEGER PRIMARY KEY, agente_id INTEGER, stat TEXT);
        CREATE TABLE inventory_discs (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
            equipado INTEGER, descartado INTEGER);
        CREATE TABLE inventory_weapons (id INTEGER PRIMARY KEY, agente_asignado INTEGER,
            equipado INTEGER, descartado INTEGER);

        INSERT INTO agents VALUES
            (1, 'Yanagi', 'S', 60, 0, 'Eléctrico', 'Anomalía', 'Hollow Special Operations Section 6'),
            (2, 'Billy', 'A', NULL, 6, 'Físico', 'Ataque', 'Cunning Hares'),
            (3, 'Billy Estelar', 'S', NULL, 0, 'Físico', 'Disruptivos', 'Cunning Hares'),
            (4, 'Pyrois', '∞', 40, 0, 'Éter', 'Ataque', 'Faetón'),
            (5, 'Anby', 'A', NULL, 6, 'Eléctrico', 'Aturdimiento', 'Cunning Hares');

        -- umbrales: todos menos Pyrois
        INSERT INTO agent_thresholds (agente_id, stat) VALUES (1,'x'),(2,'x'),(3,'x'),(5,'x'),(5,'y');
    """)
    # Yanagi: 6 discos + 1 descartado + 1 libre (no cuentan). Billy: 5. Anby: 7.
    discos = [(1, 1, 0)] * 6 + [(1, 1, 1), (1, 0, 0)] + [(2, 1, 0)] * 5 + [(5, 1, 0)] * 7
    c.executemany("INSERT INTO inventory_discs (agente_asignado, equipado, descartado) VALUES (?,?,?)", discos)
    # Arma: Yanagi y Billy sí; Anby tiene una DESCARTADA (no cuenta); Pyrois y Billy Estelar no.
    c.executemany("INSERT INTO inventory_weapons (agente_asignado, equipado, descartado) VALUES (?,?,?)",
                  [(1, 1, 0), (2, 1, 0), (5, 1, 1)])
    yield c
    c.close()


def _por_nombre(celdas):
    return {c.nombre: c for c in celdas}


def test_las_marcas_salen_cada_una_de_su_fuente(con):
    c = _por_nombre(leer_roster(con))
    assert c["Yanagi"].discos == 6, "ni el descartado ni el libre cuentan"
    assert c["Billy"].discos == 5 and c["Anby"].discos == 7
    assert c["Yanagi"].tiene_arma and c["Billy"].tiene_arma
    assert not c["Anby"].tiene_arma, "un arma descartada no es un arma equipada"
    assert not c["Pyrois"].tiene_arma
    assert c["Pyrois"].sin_thresholds and not c["Yanagi"].sin_thresholds
    assert c["Billy Estelar"].variante_de == "Billy"
    assert c["Billy"].variante_de is None


def test_el_nivel_sin_leer_queda_none_y_no_se_inventa(con):
    c = _por_nombre(leer_roster(con))
    assert c["Billy"].nivel is None
    assert c["Pyrois"].nivel == 40


def test_infinito_ordena_primero_despues_s_despues_a_y_alfabetico(con):
    nombres = [c.nombre for c in ordenar(leer_roster(con))]
    assert nombres == ["Pyrois", "Billy Estelar", "Yanagi", "Anby", "Billy"]


def test_conteos_del_header_son_varios_numeros_no_uno(con):
    k = conteos_header(leer_roster(con), no_obtenidos={"Norma", "Hugo"})
    assert k == {"filas": 5, "atuendos": 1, "distintos": 4, "no_obtenidos": 2,
                 "conocidos": 6, "sin_thresholds": 1}


def test_filtros_se_combinan(con):
    celdas = leer_roster(con)
    assert {c.nombre for c in filtrar(celdas, {"elemento": {"Físico"}})} == {"Billy", "Billy Estelar"}
    assert {c.nombre for c in filtrar(celdas, {"elemento": {"Físico"}, "rango": {"S"}})} == {"Billy Estelar"}
    assert {c.nombre for c in filtrar(celdas, {"estado": {"sin_arma"}})} == {"Billy Estelar", "Pyrois", "Anby"}
    assert {c.nombre for c in filtrar(celdas, {"estado": {"discos_no_6"}})} == {"Billy", "Anby", "Billy Estelar", "Pyrois"}
    assert {c.nombre for c in filtrar(celdas, {"estado": {"faltan_datos"}})} == {"Pyrois"}
    # Dentro de un mismo eje las opciones SUMAN; entre ejes RESTAN.
    assert {c.nombre for c in filtrar(celdas, {"rol": {"Ataque", "Anomalía"}})} == {"Billy", "Pyrois", "Yanagi"}
    assert len(filtrar(celdas, {})) == 5


def test_tolera_una_db_sin_las_tablas_de_inventario():
    """Una DB recién reconstruida o de test puede no tener inventario: la pantalla no se cae."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT, rango TEXT, nivel INTEGER,"
              " mindscape INTEGER, elemento TEXT, rol TEXT, faccion TEXT)")
    c.execute("INSERT INTO agents VALUES (1, 'Ellen', 'S', NULL, 0, 'Hielo', 'Ataque', 'Victoria Housekeeping')")
    (celda,) = leer_roster(c)
    assert celda == CeldaPJ(id=1, nombre="Ellen", rango="S", elemento="Hielo", rol="Ataque",
                            faccion="Victoria Housekeeping", mindscape=0, nivel=None, discos=0,
                            tiene_arma=False, sin_thresholds=True, variante_de=None)


# --- la grilla sin scroll ------------------------------------------------------------------------
#
# Regla heredable del diseño: "si el catálogo no cabe, se comprime la celda; no se agrega scroll".
# El cuerpo de la pantalla en la ventana MÍNIMA (1320×820) mide ~1076×540: la ventana menos sidebar
# (220), barra de título (40), barra inferior (24), header (56), filtros (104), leyenda (32) y márgenes.

CUERPO_MINIMO = (1076, 540)


@pytest.mark.parametrize("n", [51, 60, 80])
def test_la_grilla_entra_sin_scroll_en_la_ventana_minima(n):
    g = calcular_grilla(n, *CUERPO_MINIMO)
    assert g.cabe
    filas = -(-n // g.columnas)
    assert g.columnas * g.celda_w + (g.columnas - 1) * g.gap <= CUERPO_MINIMO[0]
    assert filas * g.celda_h + (filas - 1) * g.gap <= CUERPO_MINIMO[1]


def test_con_espacio_de_sobra_la_celda_no_crece_sin_limite():
    g = calcular_grilla(4, 2400, 1300)
    assert g.celda_w <= 122 * 1.3 and g.celda_h <= 96 * 1.3


def test_maximizada_la_grilla_no_deja_media_pantalla_vacia():
    """Con la ventana maximizada (cuerpo ~2316×1116) varias cantidades de columnas llegan al tope
    de escala. Elegir la PRIMERA (7) dejaba la mitad derecha vacía — visto en la captura del
    2026-09-13. Entre empates gana la que más ancho usa."""
    ancho, alto = 2316, 1116
    g = calcular_grilla(51, ancho, alto)
    usado = g.columnas * g.celda_w + (g.columnas - 1) * g.gap
    assert usado >= 0.7 * ancho, (g, usado)
    filas = -(-51 // g.columnas)
    assert filas * g.celda_h + (filas - 1) * g.gap <= alto


def test_debajo_del_piso_lo_dice_en_vez_de_dibujar_celdas_ilegibles():
    g = calcular_grilla(500, *CUERPO_MINIMO)
    assert not g.cabe
    assert g.escala >= 0.6


def test_la_celda_conserva_la_proporcion_del_diseno():
    g = calcular_grilla(51, *CUERPO_MINIMO)
    assert abs(g.celda_w / g.celda_h - 122 / 96) < 0.05
