"""Corre el motor de discos sobre TODO el inventario y deja las sugerencias en `audit/sugerencias/`.

Pedido de Daniel (2026-09-22): "la DB tiene más de 300 discos y si cargo mi roster ya podrías
sugerir de un comienzo qué disco puede ser bueno para mis personajes". Es la etapa 1, paso 7.

Qué sugiere, con las reglas de sus casos:
  - **equipar** un disco LIBRE a quien más le mejora el build (compara contra lo que ya lleva);
  - **mover** un disco de un PJ a otro sólo si el que lo tiene NO pierde, contando un disco libre
    como reemplazo;
  - **mejorar** un disco sin terminar que promete, **reserva** uno bueno que hoy no le gana a nadie,
    **descartar** el resto de los libres.

Las sugerencias no se pisan: se toman de la de más ganancia para abajo, y una que pide un slot o
un disco ya comprometido por otra queda como "en conflicto" en vez de desaparecer. Cada una está
calculada contra el estado de HOY, no contra el que dejarían las anteriores.

**Sólo lee la DB de dominio** (se abre `mode=ro` y se verifica el sha256 antes y después: B3). Lo
único que escribe es el reporte.

Uso (desde la raíz del repo):

    python app/scripts/sugerir_movimientos.py
    python app/scripts/sugerir_movimientos.py --db otra.db
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.audit_paths import reservar_rutas, resolve_audit_dir  # noqa: E402
from app.core.recommender import nivel_prioridad, recomendar  # noqa: E402
from app.core.score_normalizer import ScoringContext  # noqa: E402
from app.db.repositories import (AgentRepo, ArchetypeRepo, Disc, DiscSetRepo,  # noqa: E402
                                 InventoryDiscRepo)

DB_DEFAULT = Path("db/danibod_zzz_v2.db")


@dataclass
class Sugerencia:
    tipo: str                   # equipar | mover | mejorar | reserva | descartar
    disc_id: int
    disco: str                  # descripción legible
    destino: str | None = None
    destino_id: int | None = None
    slot: int | None = None
    origen: str | None = None
    reemplazo_id: int | None = None
    delta: float | None = None
    score: float | None = None
    conflicto: str | None = None
    prioridad: str = "normal"     # la del PJ destino (mig 42)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _describir(d: Disc, sets: dict[int, str]) -> str:
    subs = ", ".join(f"{s}{f' +{m}' if m else ''}" for s, _v, _u, m in d.subs)
    return (f"#{d.id} {sets.get(d.set_id, f'set {d.set_id}')} · slot {d.slot} · "
            f"{d.main_stat or '?'} · Nv {d.nivel if d.nivel is not None else '?'} · {subs}")


def resolver_conflictos(crudas: list[Sugerencia]) -> None:
    """Las que mueven discos no se pueden pisar: dos no pueden llenar el mismo slot del mismo PJ ni
    usar el mismo disco (como el que se mueve o como el que repone). Se toman primero las de los PJs
    de mayor prioridad (mig 42: "recibe discos primero") y, entre iguales, de la de más ganancia
    para abajo. La que pierde queda marcada `conflicto`, no desaparece."""
    tomados_slot: dict[tuple[int, int], int] = {}
    tomados_disco: dict[int, int] = {}
    for s in sorted((x for x in crudas if x.tipo in ("equipar", "mover")),
                    key=lambda x: (nivel_prioridad(x.prioridad), x.delta or 0.0), reverse=True):
        clave = (s.destino_id, s.slot)
        usados = [s.disc_id] + ([s.reemplazo_id] if s.reemplazo_id else [])
        if clave in tomados_slot:
            s.conflicto = f"ese slot ya lo toma el disco #{tomados_slot[clave]}"
        elif any(u in tomados_disco for u in usados):
            u = next(u for u in usados if u in tomados_disco)
            s.conflicto = f"el disco #{u} ya está comprometido en otra sugerencia"
        else:
            tomados_slot[clave] = s.disc_id
            for u in usados:
                tomados_disco[u] = s.disc_id


def generar(db_path: Path) -> dict:
    """Evalúa todo el inventario. Devuelve el reporte como dict (no escribe nada)."""
    con = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        agentes, arqs, sets_repo = AgentRepo(con), ArchetypeRepo(con), DiscSetRepo(con)
        inv = InventoryDiscRepo(con)
        nombres = {a.id: a.nombre for a in agentes.get_all()}
        prioridades = {a.id: a.prioridad for a in agentes.get_all()}
        sets = {s.id: s.nombre for s in sets_repo.get_all()}
        activos = inv.get_all_active()
        libres = [d for d in activos if not d.equipado]
        cache: dict[int, dict[int, Disc]] = {}

        def builds(agente_id: int) -> dict[int, Disc]:
            if agente_id not in cache:
                cache[agente_id] = inv.find_equipped_by_agent(agente_id)
            return cache[agente_id]

        ctx = ScoringContext()
        crudas: list[Sugerencia] = []
        sin_cambio = sin_nivel = 0
        for d in activos:
            rec = recomendar(d, agentes, arqs, sets_repo, ctx, builds=builds, libres=libres)
            desc = _describir(d, sets)
            m = rec.movimiento
            if d.equipado and d.agente_asignado:
                if m is None:
                    sin_cambio += 1
                    continue
                crudas.append(Sugerencia("mover", d.id, desc, nombres.get(m.agente_id),
                                         m.agente_id, m.slot, nombres.get(m.origen_id),
                                         m.reemplazo_id, round(m.delta, 3), round(rec.score_norm, 3)))
                continue
            if d.nivel is None:
                sin_nivel += 1
                continue
            if rec.tipo == "equipar" and m is not None:
                crudas.append(Sugerencia("equipar", d.id, desc, nombres.get(m.agente_id),
                                         m.agente_id, m.slot, delta=round(m.delta, 3),
                                         score=round(rec.score_norm, 3)))
            else:
                crudas.append(Sugerencia(rec.tipo, d.id, desc, rec.agente_nombre, rec.agente_id,
                                         d.slot, score=round(rec.score_norm, 3)))
        for s in crudas:
            s.prioridad = prioridades.get(s.destino_id, "normal")
    finally:
        con.close()

    resolver_conflictos(crudas)

    por_tipo: dict[str, list[dict]] = {}
    for s in crudas:
        por_tipo.setdefault(s.tipo, []).append(s.__dict__)
    for lista in por_tipo.values():
        lista.sort(key=lambda x: (x["conflicto"] is not None, -(x["delta"] or x["score"] or 0)))
    return {
        "schema": "sugerencias_discos/1",
        "totales": {"inventario_activo": len(activos), "libres": len(libres),
                    "equipados_sin_cambio": sin_cambio, "sin_nivel_leido": sin_nivel,
                    **{t: len(v) for t, v in por_tipo.items()}},
        "sugerencias": por_tipo,
    }


def _markdown(rep: dict) -> str:
    t = rep["totales"]
    out = ["# Sugerencias del motor de discos", "",
           f"Inventario activo: **{t['inventario_activo']}** discos ({t['libres']} libres). "
           f"Equipados sin cambio: {t['equipados_sin_cambio']}. Sin nivel leído: {t['sin_nivel_leido']}.",
           "", "Cada sugerencia está calculada contra el estado de HOY. Las que se pisarían entre sí",
           "quedan marcadas **en conflicto**: se toma la de más ganancia.", ""]
    titulos = [("mover", "Mover de un PJ a otro (el que lo tiene NO pierde)"),
               ("equipar", "Equipar un disco libre"), ("mejorar", "Vale la pena subir"),
               ("reserva", "Guardar para un PJ futuro"),
               ("guardar", "Guardar sin subir (sirve, pero subido no le ganaría a nadie de hoy)"),
               ("descartar", "Descartar")]
    for tipo, titulo in titulos:
        lista = rep["sugerencias"].get(tipo, [])
        out += [f"## {titulo} — {len(lista)}", ""]
        if not lista:
            out += ["(ninguna)", ""]
            continue
        for s in lista:
            linea = f"- {s['disco']}"
            if s["destino"]:
                linea += f" → **{s['destino']}**"
                if s.get("prioridad", "normal") != "normal":
                    linea += f" (prioridad {s['prioridad']})"
            if s["origen"]:
                linea += f" (sale de {s['origen']}"
                linea += f"; lo repone el #{s['reemplazo_id']})" if s["reemplazo_id"] else "; queda vacío y no pierde)"
            if s["delta"] is not None:
                linea += f" · mejora {s['delta']:+.2f}"
            if s["conflicto"]:
                linea += f" · ⚠️ en conflicto: {s['conflicto']}"
            out.append(linea)
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sugerencias del motor de discos sobre todo el inventario.")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = ap.parse_args(argv)
    antes = _sha256(args.db)
    rep = generar(args.db)
    if _sha256(args.db) != antes:
        print("ERROR: la DB de dominio cambió durante un proceso de sólo lectura (B3)", file=sys.stderr)
        return 3
    rutas = reservar_rutas(resolve_audit_dir() / "sugerencias", "sugerencias_discos", ("json", "md"))
    rutas[0].write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    rutas[1].write_text(_markdown(rep), encoding="utf-8")
    t = rep["totales"]
    print(f"{t['inventario_activo']} discos · " + " · ".join(
        f"{k} {t.get(k, 0)}" for k in ("mover", "equipar", "mejorar", "reserva", "guardar", "descartar")))
    print(f"→ {rutas[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
