"""Lo que la pantalla Discos y el modal de disco saben del inventario — funciones puras, sin Qt.

Una consulta, **sin LIMIT**: la tabla anterior cortaba en 200 de 385 y no lo decía.

Nada de scoring: `score_evaluacion` está vacía (0/385) e `inventory_disc_evaluations` tiene 0 filas.
Por eso las alternativas de un disco NO se ordenan por calidad (eso sería una recomendación): van
los libres primero y después por nivel.

**Dueño a la vista** = equipado. Un disco con `agente_asignado` y `equipado = 0` no se muestra como
de nadie: el invariante del proyecto dice que esa fila no debería existir, y la pantalla no la
disfraza de "equipada".
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.ui.formato import formatear_sub, formatear_valor

__all__ = ["FilaDisco", "leer_inventario", "formatear_valor", "formatear_sub", "subs_texto",
           "filtrar", "distribucion_por_set", "libres_por_slot", "alternativas"]


@dataclass(frozen=True)
class FilaDisco:
    id: int
    set: str | None
    set_id: int | None
    set_en: str | None
    slot: int
    main: str | None
    main_valor: float | None
    main_unidad: str | None
    #: (nombre, valor, unidad, rolls) — sólo los que existen: 3 o 4
    subs: tuple[tuple[str, float | None, str | None, int], ...]
    rolls_total: int
    nivel: int
    equipado: bool
    dueno: str | None
    dueno_id: int | None

    @property
    def libre(self) -> bool:
        return not self.equipado


def leer_inventario(con: sqlite3.Connection, disco_id: int | None = None) -> list[FilaDisco]:
    """Todos los discos activos (o sólo `disco_id`). Tolera `row_factory` Row o tupla."""
    sql = """
        SELECT d.id, s.nombre, d.set_id, s.nombre_en, d.slot, d.main_stat, d.main_valor, d.unidad_main,
               d.sub1, d.val1, d.rolls1, d.unidad1, d.sub2, d.val2, d.rolls2, d.unidad2,
               d.sub3, d.val3, d.rolls3, d.unidad3, d.sub4, d.val4, d.rolls4, d.unidad4,
               d.nivel, d.equipado, a.nombre, a.id
        FROM inventory_discs d
        LEFT JOIN disc_sets s ON s.id = d.set_id
        LEFT JOIN agents a ON a.id = d.agente_asignado AND d.equipado = 1
        WHERE d.descartado = 0 {extra}
        ORDER BY d.id
    """
    params: tuple = ()
    extra = ""
    if disco_id is not None:
        extra, params = "AND d.id = ?", (disco_id,)
    salida = []
    for r in con.execute(sql.format(extra=extra), params):
        r = tuple(r)
        subs = []
        for base in (8, 12, 16, 20):
            nombre, valor, rolls, unidad = r[base:base + 4]
            if nombre:
                subs.append((nombre, valor, unidad, int(rolls or 0)))
        equipado = bool(r[25])
        salida.append(FilaDisco(
            id=r[0], set=r[1], set_id=r[2], set_en=r[3], slot=r[4], main=r[5], main_valor=r[6],
            main_unidad=r[7], subs=tuple(subs), rolls_total=sum(s[3] for s in subs),
            nivel=int(r[24] or 0), equipado=equipado,
            dueno=r[26] if equipado else None, dueno_id=r[27] if equipado else None,
        ))
    return salida


def subs_texto(fila: FilaDisco, sep: str = " · ") -> str:
    return sep.join(formatear_sub(n, v, u, k) for n, v, u, k in fila.subs)


def _valor_eje(f: FilaDisco, eje: str):
    if eje == "estado":
        return "equipado" if f.equipado else "libre"
    return getattr(f, eje)


def filtrar(filas: Iterable[FilaDisco], filtros: Mapping[str, set]) -> list[FilaDisco]:
    """Mismo contrato que `roster.datos.filtrar`: dentro de un eje SUMAN, entre ejes RESTAN.
    Ejes: `set`, `slot`, `main`, `dueno`, `estado` (`equipado` | `libre`)."""
    activos = {e: v for e, v in filtros.items() if v}
    return [f for f in filas if all(_valor_eje(f, e) in v for e, v in activos.items())]


def distribucion_por_set(filas: Iterable[FilaDisco]) -> list[tuple[str, int]]:
    cuenta = Counter(f.set or "sin set" for f in filas)
    return sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))


def libres_por_slot(filas: Iterable[FilaDisco]) -> dict[int, int]:
    salida = {s: 0 for s in range(1, 7)}
    for f in filas:
        if f.libre and f.slot in salida:
            salida[f.slot] += 1
    return salida


def alternativas(filas: Iterable[FilaDisco], disco: FilaDisco) -> list[FilaDisco]:
    """Otros discos del mismo set y slot. Libres primero, después nivel, después id — NO por
    calidad: ordenar por "mejor" sería una recomendación, y el scoring no está calibrado."""
    otros = [f for f in filas if f.id != disco.id and f.set_id == disco.set_id and f.slot == disco.slot]
    return sorted(otros, key=lambda f: (not f.libre, -f.nivel, f.id))
