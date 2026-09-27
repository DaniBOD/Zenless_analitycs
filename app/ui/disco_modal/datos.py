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


# ---------------------------------------------------------------------------
# La sugerencia del motor para este disco (SPEC 2026-09-27, sugerencias en Discos)
# ---------------------------------------------------------------------------

#: El porqué de los tipos que no tienen destino. Honesto con lo que el motor decide: "reserva" y
#: "guardar" también salen de R22 (el único de su tipo en la cuenta), no sólo de la calidad.
PORQUE = {
    "reserva": "Hoy no le gana a nadie, pero vale guardarlo: es bueno para su rol o es el único de su "
               "tipo (set, slot y principal) en tu cuenta.",
    "guardar": "Está sin terminar: sirve, pero subido no le ganaría a nadie de hoy. Guardalo sin "
               "gastarle materiales.",
    "descartar": "No le sirve a ningún PJ de tu cuenta y no es el único de su tipo.",
}


def _describir(f: FilaDisco) -> str:
    from app.ui.discos.datos import subs_texto
    from app.ui.formato import formatear_valor
    return (f"#{f.id:05d} {f.set or 'sin set'} · {f.main or '—'} "
            f"{formatear_valor(f.main_valor, f.main_unidad)} · Nv {f.nivel if f.nivel is not None else '?'}"
            f" · {subs_texto(f)}")


def _lleva(todos: list[FilaDisco], agente_id: int | None, slot: int | None) -> FilaDisco | None:
    return next((x for x in todos if x.equipado and x.dueno_id == agente_id and x.slot == slot), None)


def detalle_sugerencia(con: sqlite3.Connection, sd) -> list[str]:
    """Las líneas del recuadro, según el tipo. `sd` es un `SugerenciaDisco` (o None: nada)."""
    if sd is None:
        return []
    todos = leer_inventario(con)
    por_id = {x.id: x for x in todos}
    lineas: list[str] = []
    s = sd.propia
    if s is not None:
        tipo = s["tipo"]
        if tipo in ("equipar", "mejorar"):
            hoy = _lleva(todos, s.get("destino_id"), s.get("slot"))
            lineas.append(f"Hoy {s.get('destino')} lleva en el slot {s.get('slot')}: "
                          + (_describir(hoy) if hoy else "nada"))
            if tipo == "mejorar":
                lineas.append("Subido, se espera que le gane a lo que lleva.")
        elif tipo == "mover":
            rep = por_id.get(s.get("reemplazo_id")) if s.get("reemplazo_id") else None
            lineas.append(f"Sale de {s.get('origen')}; " + (f"lo repone {_describir(rep)}" if rep
                          else "el slot queda vacío y no pierde"))
            hoy = _lleva(todos, s.get("destino_id"), s.get("slot"))
            lineas.append(f"Va a {s.get('destino')}, que hoy lleva: " + (_describir(hoy) if hoy else "nada"))
        elif tipo == "armar_2pc":
            if s.get("nota"):
                lineas.append(s["nota"][:1].upper() + s["nota"][1:])
            for i in (s.get("disc_id"), s.get("disc_id_2")):
                if i in por_id:
                    lineas.append(f"Pieza: {_describir(por_id[i])}")
        elif tipo in PORQUE:
            lineas.append(PORQUE[tipo])
        if s.get("conflicto"):
            lineas.append(f"En conflicto: {s['conflicto']}.")
    for rol, otra in sd.lo_nombran:
        if rol == "repone":
            lineas.append(f"Parte de otra sugerencia: si #{otra['disc_id']} se mueve a {otra.get('destino')}, "
                          f"este disco ocupa su lugar en {otra.get('origen')}.")
        else:
            lineas.append(f"Parte de otra sugerencia: forma el par con #{otra['disc_id']} para "
                          f"{otra.get('destino')}.")
    return lineas
