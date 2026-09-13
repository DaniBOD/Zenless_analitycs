"""La ficha de un disco para el modal — sólo lecturas, sin Qt.

Todo sale de fuentes que ya existen:

- el disco y sus alternativas: `discos.datos` (la misma consulta que la tabla);
- el build del dueño: `BuildProvider.build_de` (la misma que el hexágono de la vista en vivo y el
  modal de PJ);
- los efectos del set: `disc_sets.bonus_2p_*` / `bonus_4p_desc` (30/30 cargados);
- el logo: `asset_resolver.set_logo_path`.

Nada sale de `inventory_disc_evaluations` ni de `disc_archetypes`: el mockup los usaba para
"PJs compatibles", arquetipo, score proyectado y recomendación, y el scoring no está calibrado.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from app.core.asset_resolver import agent_avatar_path, set_logo_path
from app.ui.discos.datos import FilaDisco, alternativas, leer_inventario


@dataclass(frozen=True)
class FichaDisco:
    disco: FilaDisco
    set_logo: str | None
    bono_2p: str | None
    bono_4p: str | None
    dueno_avatar: str | None
    #: build del dueño `{slot: {...}}`; vacío si el disco está libre
    build: dict[int, dict] = field(default_factory=dict)
    alternativas: list[FilaDisco] = field(default_factory=list)


def ficha_disco(con: sqlite3.Connection, disco_id: int) -> FichaDisco | None:
    """`None` si el disco no existe o está descartado."""
    from app.ui.live.build_provider import BuildProvider

    propio = leer_inventario(con, disco_id)
    if not propio:
        return None
    d = propio[0]

    bono_2p = bono_4p = None
    if d.set_id is not None:
        r = con.execute("SELECT bonus_2p_stat, bonus_2p_valor, bonus_4p_desc FROM disc_sets WHERE id = ?",
                        (d.set_id,)).fetchone()
        if r is not None:
            stat, valor, desc = tuple(r)
            bono_2p = " ".join(x for x in (stat, valor) if x) or None
            bono_4p = desc or None

    todos = leer_inventario(con)
    logo = set_logo_path(d.set_en)
    avatar = agent_avatar_path(d.dueno, "ico") if d.dueno else None
    return FichaDisco(
        disco=d,
        set_logo=str(logo) if logo else None,
        bono_2p=bono_2p, bono_4p=bono_4p,
        dueno_avatar=str(avatar) if avatar else None,
        build=BuildProvider(con).build_de(d.dueno) if d.dueno else {},
        alternativas=alternativas(todos, d),
    )
