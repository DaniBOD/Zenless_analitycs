"""La ficha de un PJ para el modal — sólo lecturas, sin Qt.

Todo sale de fuentes que ya existen, sin una segunda definición:

- los 6 slots: `BuildProvider.build_de` (la misma que dibuja el hexágono de la vista en vivo);
- el arma: `InventoryWeaponRepo.find_equipped_by_agent` + `WeaponRepo.get_by_id`;
- los íconos: `asset_resolver`.

Lo que NO está en la ficha es tan deliberado como lo que sí: ni "build completion" ni ninguna
recomendación. Salen de un scoring que no está calibrado (decisión de Daniel, 2026-09-13).

Un dato ausente queda en `None` y la vista dice "sin leer" / "sin registro". Desde la
reconstrucción de la DB (17/08) las stats están vacías para todos: se llenan solas al abrir los
atributos del PJ en el juego (`sync_agent_stats`), no inventándolas acá.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from app.core.asset_resolver import agent_avatar_path, engine_icon_path, faction_logo_path

log = logging.getLogger(__name__)

#: (etiqueta, columna de `agents`). El orden y la selección son los del mockup.
STATS: tuple[tuple[str, str], ...] = (
    ("PV", "pv"),
    ("Ataque", "ataque"),
    ("Defensa", "defensa"),
    ("Impacto", "impacto"),
    ("Prob. Crítico", "prob_critico"),
    ("Daño Crítico", "dano_critico"),
    ("Maestría Anom.", "maestria_anomalia"),
    ("Recup. Energía", "rec_energia"),
)
#: El Armero (v3.2) no tiene ATK ni Recup. Energía en su ficha: en esas dos celdas muestra
#: Daño de laceración y Acumulación Automática de afiladura. Mismo lugar, mismo orden.
STATS_ARMERO: tuple[tuple[str, str], ...] = tuple(
    {"ataque": ("Laceración", "dano_laceracion"),
     "rec_energia": ("Afiladura", "acumulacion_afiladura")}.get(col, (etq, col))
    for etq, col in STATS
)
_PORCENTAJE = {"prob_critico", "dano_critico", "dano_laceracion"}
_MULTIPLICADOR = {"rec_energia", "acumulacion_afiladura"}


def stats_de_rol(rol: str | None) -> tuple[tuple[str, str], ...]:
    """Las filas de stats que corresponden al rol. Una sola respuesta para la ficha y el widget."""
    return STATS_ARMERO if (rol or "").strip() == "Armero" else STATS


@dataclass(frozen=True)
class ArmaFicha:
    nombre: str
    nivel: int | None
    refinamiento: int | None
    icono: str | None


@dataclass(frozen=True)
class FichaPJ:
    id: int
    nombre: str
    rango: str | None
    elemento: str | None
    rol: str | None
    faccion: str | None
    mindscape: int | None
    nivel: int | None
    #: (etiqueta, texto ya formateado | None)
    stats: list[tuple[str, str | None]]
    #: stat → valor crudo, para dibujar la barra (None = sin barra)
    stats_crudos: dict[str, float | None]
    bono: str | None
    slots: dict[int, dict]
    sets: list[tuple[str, int]]
    set_logos: dict[str, str | None]
    arma: ArmaFicha | None
    #: Nivel de despertar 0–6, o None si el PJ no tiene fila (≠ nivel 0).
    despertar: int | None
    despertar_nombre: str | None
    avatar: str | None = None
    arte: str | None = None
    faccion_logo: str | None = None
    extra: dict = field(default_factory=dict)
    #: Prioridad de buildeo (mig 42): 'alta' | 'normal' | 'baja', de `PrioridadRepo`.
    prioridad: str = "normal"


def formatear_stat(columna: str, valor) -> str | None:
    """`None` se queda en `None`: la vista decide cómo decir "sin leer"."""
    if valor is None:
        return None
    if columna in _PORCENTAJE:
        return f"{float(valor):.1f}%"
    if columna in _MULTIPLICADOR:
        return f"{float(valor):.2f}"
    return f"{int(round(float(valor))):,}".replace(",", ".")


def sets_de_build(slots: dict[int, dict]) -> list[tuple[str, int]]:
    """Sets con al menos 2 piezas, de más a menos piezas. No fuerza un 4+2 que no existe: con 6
    sueltos devuelve [], y la pieza suelta de un 4+1 no aparece."""
    cuenta = Counter(d.get("set") for d in slots.values() if d.get("set"))
    return sorted(((n, k) for n, k in cuenta.items() if k >= 2), key=lambda x: (-x[1], x[0]))


def ficha_pj(con: sqlite3.Connection, agente_id: int) -> FichaPJ | None:
    """Arma la ficha. `None` si el PJ no existe. Espera `row_factory = sqlite3.Row`."""
    from app.db.repositories import InventoryWeaponRepo, WeaponRepo
    from app.ui.live.build_provider import BuildProvider

    fila = con.execute("SELECT * FROM agents WHERE id = ?", (agente_id,)).fetchone()
    if fila is None:
        return None
    a = dict(fila)

    slots = BuildProvider(con).build_de(a["nombre"])
    sets = sets_de_build(slots)
    set_logos = {}
    for d in slots.values():
        if d.get("set") and d.get("set") not in set_logos:
            set_logos[d["set"]] = d.get("logo")

    arma = None
    try:
        inv = InventoryWeaponRepo(con).find_equipped_by_agent(agente_id)
        if inv is not None:
            cat = WeaponRepo(con).get_by_id(inv.weapon_id)
            if cat is not None:
                icono = engine_icon_path(cat.nombre, cat.nombre_en)
                arma = ArmaFicha(nombre=cat.nombre, nivel=inv.nivel, refinamiento=inv.refinamiento,
                                 icono=str(icono) if icono else None)
    except sqlite3.Error:
        log.exception("[modal] no se pudo leer el arma de %s", a["nombre"])

    despertar = despertar_nombre = None
    try:
        d = con.execute("SELECT nivel, nombre FROM agent_awakenings WHERE agente_id = ? "
                        "ORDER BY nivel DESC LIMIT 1", (agente_id,)).fetchone()
        if d is not None:
            despertar = d[0]
            # Los textos "[Despertar nv6 — pendiente captura textual]" son marcadores, no nombres.
            despertar_nombre = d[1] if d[1] and not str(d[1]).startswith("[") else None
    except sqlite3.Error:
        log.exception("[modal] no se pudo leer el despertar de %s", a["nombre"])

    bono_v = a.get("bono_dano_elemento")
    bono = f"Bono {a.get('elemento')} {float(bono_v):g}%" if bono_v is not None else None

    from app.db.repositories import PrioridadRepo
    prioridad = "normal"
    try:
        prioridad = PrioridadRepo(con).get(agente_id)
    except sqlite3.Error:
        log.exception("[modal] no se pudo leer la prioridad de %s", a["nombre"])

    avatar = agent_avatar_path(a["nombre"], "ico")
    arte = agent_avatar_path(a["nombre"], "extend")
    logo_fac = faction_logo_path(a.get("faccion"))
    return FichaPJ(
        prioridad=prioridad,
        id=a["id"], nombre=a["nombre"], rango=a.get("rango"), elemento=a.get("elemento"),
        rol=a.get("rol"), faccion=a.get("faccion"), mindscape=a.get("mindscape"),
        nivel=a.get("nivel"),
        stats=[(etq, formatear_stat(col, a.get(col))) for etq, col in stats_de_rol(a.get("rol"))],
        stats_crudos={col: a.get(col) for _e, col in stats_de_rol(a.get("rol"))},
        bono=bono, slots=slots, sets=sets, set_logos=set_logos, arma=arma,
        despertar=despertar, despertar_nombre=despertar_nombre,
        avatar=str(avatar) if avatar else None, arte=str(arte) if arte else None,
        faccion_logo=str(logo_fac) if logo_fac else None,
    )
