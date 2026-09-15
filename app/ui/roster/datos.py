"""Lo que la pantalla Roster sabe de cada PJ — funciones puras, sin Qt.

Cada marca visual de la celda tiene UNA fuente, y está acá y no en el widget:

- **le faltan datos** (esquina rayada ámbar) = no tiene filas en `agent_thresholds`. Medido el
  2026-09-13: son exactamente Aria, Pyrois, Remielle Dan y Velina, los cuatro que la especificación
  nombra como "onboarding a medias".
- **discos** = equipados y no descartados, igual que `InventoryDiscRepo.find_equipped_by_agent`.
- **arma** = `inventory_weapons` equipada y no descartada.
- **atuendo** = `roster_declaration._variantes_de_atuendo`, la regla del editor de roster: si acá
  se escribiera otra, las dos pantallas podrían discrepar sobre el mismo PJ.

El nivel se deja en `None` cuando no se leyó. Desde la reconstrucción de la DB (2026-08-17) está
vacío para los 51: la celda dice "sin leer", no 1 ni 60.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.core.roster_declaration import _variantes_de_atuendo
from app.ui.grilla import Grilla, calcular

#: Orden de rangos: `∞` primero (con 1 PJ, alfabético lo perdería entre 37 S), después S y A.
_ORDEN_RANGO = {"∞": 0, "S": 1, "A": 2}

#: Filtros de "estado de build". Son la banda ámbar que heredan las otras pestañas de catálogo:
#: responden "a qué le faltan datos", no son filtros genéricos.
ESTADOS = {
    "faltan_datos": "Le faltan datos",
    "discos_no_6": "Discos ≠ 6",
    "sin_arma": "Sin arma",
}


@dataclass(frozen=True)
class CeldaPJ:
    id: int
    nombre: str
    rango: str | None
    elemento: str | None
    rol: str | None
    faccion: str | None
    mindscape: int | None
    nivel: int | None
    discos: int
    tiene_arma: bool
    sin_thresholds: bool
    variante_de: str | None


def _tablas(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def leer_roster(con: sqlite3.Connection) -> list[CeldaPJ]:
    """Una celda por fila de `agents`. Cuatro consultas en total, no una por PJ."""
    tablas = _tablas(con)
    filas = con.execute(
        "SELECT id, nombre, rango, elemento, rol, faccion, mindscape, nivel FROM agents"
    ).fetchall()

    discos: dict[int, int] = {}
    if "inventory_discs" in tablas:
        discos = dict(con.execute(
            "SELECT agente_asignado, COUNT(*) FROM inventory_discs "
            "WHERE equipado = 1 AND descartado = 0 AND agente_asignado IS NOT NULL "
            "GROUP BY agente_asignado").fetchall())
    con_arma: set[int] = set()
    if "inventory_weapons" in tablas:
        con_arma = {r[0] for r in con.execute(
            "SELECT DISTINCT agente_asignado FROM inventory_weapons "
            "WHERE equipado = 1 AND descartado = 0 AND agente_asignado IS NOT NULL")}
    con_umbrales: set[int] = set()
    if "agent_thresholds" in tablas:
        con_umbrales = {r[0] for r in con.execute("SELECT DISTINCT agente_id FROM agent_thresholds")}

    variantes = _variantes_de_atuendo({str(f[1]) for f in filas})
    return [
        CeldaPJ(id=i, nombre=n, rango=rango, elemento=elem, rol=rol, faccion=fac,
                mindscape=m, nivel=nivel, discos=discos.get(i, 0), tiene_arma=i in con_arma,
                sin_thresholds=i not in con_umbrales, variante_de=variantes.get(n))
        for i, n, rango, elem, rol, fac, m, nivel in filas
    ]


def ordenar(celdas: Iterable[CeldaPJ]) -> list[CeldaPJ]:
    return sorted(celdas, key=lambda c: (_ORDEN_RANGO.get(c.rango or "", 9), c.nombre.casefold()))


def conteos_header(celdas: list[CeldaPJ], no_obtenidos: set[str]) -> dict[str, int]:
    """Varios números y no uno: "un solo número obligaría a elegir cuál mentira contar".

    `no_obtenidos` sale de la última declaración (`no_poseidos_declarados`) y se cuenta TAL CUAL:
    `Lichter` y `Lighter` son una grafía en conflicto y el editor tampoco las dedupea.
    """
    filas = len(celdas)
    atuendos = sum(1 for c in celdas if c.variante_de)
    distintos = filas - atuendos
    return {
        "filas": filas,
        "atuendos": atuendos,
        "distintos": distintos,
        "no_obtenidos": len(no_obtenidos),
        "conocidos": distintos + len(no_obtenidos),
        "sin_thresholds": sum(1 for c in celdas if c.sin_thresholds),
    }


def cumple_estado(c: CeldaPJ, estado: str) -> bool:
    if estado == "faltan_datos":
        return c.sin_thresholds
    if estado == "discos_no_6":
        return c.discos != 6
    if estado == "sin_arma":
        return not c.tiene_arma
    return False


def filtrar(celdas: Iterable[CeldaPJ], filtros: Mapping[str, set[str]]) -> list[CeldaPJ]:
    """Dentro de un eje las opciones SUMAN (Fuego o Hielo); entre ejes RESTAN (Fuego y S).

    Ejes: `elemento`, `rango`, `faccion`, `rol` (valores de la celda) y `estado` (claves de ESTADOS).
    Un eje vacío o ausente no filtra.
    """
    salida = []
    for c in celdas:
        ok = True
        for eje, valores in filtros.items():
            if not valores:
                continue
            if eje == "estado":
                ok = any(cumple_estado(c, e) for e in valores)
            else:
                ok = getattr(c, eje) in valores
            if not ok:
                break
        if ok:
            salida.append(c)
    return salida


# --- la grilla ---------------------------------------------------------------------------------
#
# El cálculo vive en `app/ui/grilla.py`: lo comparte con la pantalla Armas, que usa celdas de otro
# tamaño. Acá quedan los tamaños del diseño del Roster.

#: Tamaño de celda del diseño y cuánto puede estirarse o achicarse.
CELDA_W0, CELDA_H0 = 122, 96
GAP = 6
#: Tope de crecimiento. Era 1.3 y maximizada dejaba media pantalla de aire abajo; Daniel pidió
#: que las celdas crezcan (2026-09-13). El contenido crece con ellas (`CeldaRoster.set_escala`).
ESCALA_MAX = 2.2
#: Debajo de esto el nombre y el rango dejan de leerse. La celda esconde el motivo desde 0.8.
ESCALA_MIN = 0.6


def calcular_grilla(n: int, ancho: int, alto: int) -> Grilla:
    """La grilla del Roster que entra ENTERA en `ancho × alto`, sin scroll."""
    return calcular(n, ancho, alto, base_w=CELDA_W0, base_h=CELDA_H0, gap=GAP,
                    escala_max=ESCALA_MAX, escala_min=ESCALA_MIN)
