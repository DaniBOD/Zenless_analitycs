"""Las sugerencias del motor sobre TODO el inventario — sin Qt, sin escribir nada.

La autoridad de "qué hacer con cada disco" (SPEC 2026-09-27, sugerencias en Discos): la usan la
pantalla Discos (en un hilo aparte) y el reporte de `app/scripts/sugerir_movimientos.py`.

Qué sugiere, con las reglas de los casos de Daniel:
  - **equipar** un disco LIBRE a quien más le mejora el build (compara contra lo que ya lleva);
  - **mover** un disco de un PJ a otro sólo si el que lo tiene NO pierde, contando un disco libre
    como reemplazo;
  - **armar_2pc** (R24): dos discos libres que cambian el 2pc por el siguiente de la guía para que
    el PJ CUMPLA un stat fijo, sin tocar el 4pc;
  - **mejorar** un disco sin terminar que promete, **reserva** uno bueno que hoy no le gana a nadie,
    **guardar** (sin subir) uno sin terminar en la misma situación, **descartar** el resto.

Las sugerencias no se pisan: se toman de la de más ganancia para abajo, y una que pide un slot o un
disco ya comprometido por otra queda "en conflicto" en vez de desaparecer. Cada una está calculada
contra el estado de HOY. **Sólo lee la DB** (`mode=ro`).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.coherencia import ETIQUETA_STAT
from app.core.recommender import buscar_par_2pc, nivel_prioridad, recomendar
from app.core.score_normalizer import ScoringContext
from app.db.repositories import AgentRepo, ArchetypeRepo, Disc, DiscSetRepo, InventoryDiscRepo

#: Los tipos, en el orden en que se leen (el reporte, el filtro y la leyenda de Discos).
TIPOS = ("mover", "equipar", "armar_2pc", "mejorar", "reserva", "guardar", "descartar")


@dataclass
class Sugerencia:
    tipo: str                   # equipar | mover | armar_2pc | mejorar | reserva | guardar | descartar
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
    #: Sólo `armar_2pc` (R24): el segundo disco del par, su slot, y qué cambia y para qué.
    disc_id_2: int | None = None
    slot_2: int | None = None
    nota: str | None = None


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
    for s in sorted((x for x in crudas if x.tipo in ("equipar", "mover", "armar_2pc")),
                    key=lambda x: (nivel_prioridad(x.prioridad), x.delta or 0.0), reverse=True):
        # Un par (R24) toma DOS slots y DOS discos: o entran los dos, o queda en conflicto entero.
        claves = [(s.destino_id, s.slot)] + ([(s.destino_id, s.slot_2)] if s.slot_2 else [])
        usados = ([s.disc_id] + ([s.reemplazo_id] if s.reemplazo_id else [])
                  + ([s.disc_id_2] if s.disc_id_2 else []))
        if any(c in tomados_slot for c in claves):
            c = next(c for c in claves if c in tomados_slot)
            s.conflicto = f"ese slot ya lo toma el disco #{tomados_slot[c]}"
        elif any(u in tomados_disco for u in usados):
            u = next(u for u in usados if u in tomados_disco)
            s.conflicto = f"el disco #{u} ya está comprometido en otra sugerencia"
        else:
            for c in claves:
                tomados_slot[c] = s.disc_id
            for u in usados:
                tomados_disco[u] = s.disc_id


@dataclass
class ContextoMotor:
    """Lo que el motor necesita para sugerir sobre un disco, armado UNA vez por DB (o por disco en
    vivo): los repos, el inventario activo y los libres, y los builds de cada PJ (cacheados)."""
    agentes: AgentRepo
    arqs: ArchetypeRepo
    sets_repo: DiscSetRepo
    inv: InventoryDiscRepo
    nombres: dict[int, str]
    prioridades: dict[int, str]
    sets: dict[int, str]
    activos: list[Disc]
    libres: list[Disc]
    ctx: ScoringContext
    _builds: dict[int, dict[int, Disc]] = field(default_factory=dict)

    def builds(self, agente_id: int) -> dict[int, Disc]:
        if agente_id not in self._builds:
            self._builds[agente_id] = self.inv.find_equipped_by_agent(agente_id)
        return self._builds[agente_id]


def contexto_motor(con: sqlite3.Connection) -> ContextoMotor:
    """El contexto del motor para una conexión. Una sola autoridad: lo usan `generar` (la pantalla
    Discos y el reporte) y `sugerir_un_disco` (el vivo, paso 8)."""
    agentes, arqs, sets_repo = AgentRepo(con), ArchetypeRepo(con), DiscSetRepo(con)
    inv = InventoryDiscRepo(con)
    activos = inv.get_all_active()
    return ContextoMotor(
        agentes=agentes, arqs=arqs, sets_repo=sets_repo, inv=inv,
        nombres={a.id: a.nombre for a in agentes.get_all()},
        prioridades={a.id: a.prioridad for a in agentes.get_all()},
        sets={s.id: s.nombre for s in sets_repo.get_all()},
        activos=activos, libres=[d for d in activos if not d.equipado], ctx=ScoringContext())


def _clasificar(d: Disc, rec, c: ContextoMotor) -> tuple[str, Sugerencia | None]:
    """La recomendación de un disco → su sugerencia. `("sin_cambio", None)` si está equipado y bien
    donde está; `("sin_nivel", None)` si es libre y no se leyó el nivel."""
    desc = _describir(d, c.sets)
    m = rec.movimiento
    if d.equipado and d.agente_asignado:
        if m is None:
            return "sin_cambio", None
        return "sugerencia", Sugerencia("mover", d.id, desc, c.nombres.get(m.agente_id),
                                        m.agente_id, m.slot, c.nombres.get(m.origen_id),
                                        m.reemplazo_id, round(m.delta, 3), round(rec.score_norm, 3))
    if d.nivel is None:
        return "sin_nivel", None
    if rec.tipo == "equipar" and m is not None:
        return "sugerencia", Sugerencia("equipar", d.id, desc, c.nombres.get(m.agente_id),
                                        m.agente_id, m.slot, delta=round(m.delta, 3),
                                        score=round(rec.score_norm, 3))
    return "sugerencia", Sugerencia(rec.tipo, d.id, desc, rec.agente_nombre, rec.agente_id,
                                    d.slot, score=round(rec.score_norm, 3))


def generar(db_path: Path) -> dict:
    """Evalúa todo el inventario. Devuelve el reporte como dict (no escribe nada)."""
    con = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        c = contexto_motor(con)
        agentes, arqs, sets_repo = c.agentes, c.arqs, c.sets_repo
        sets, prioridades, activos, libres, ctx = c.sets, c.prioridades, c.activos, c.libres, c.ctx
        builds = c.builds
        crudas: list[Sugerencia] = []
        sin_cambio = sin_nivel = 0
        for d in activos:
            rec = recomendar(d, agentes, arqs, sets_repo, ctx, builds=builds, libres=libres)
            estado, s = _clasificar(d, rec, c)
            if estado == "sin_cambio":
                sin_cambio += 1
            elif estado == "sin_nivel":
                sin_nivel += 1
            else:
                crudas.append(s)
        # R24: un par de discos libres que arma el siguiente 2pc de la guía y hace cumplir un fijo.
        etiquetas = ETIQUETA_STAT
        for a in agentes.get_all():
            arch = arqs.get_by_id(a.arquetipo_primario_id)
            if arch is None:
                continue
            par = buscar_par_2pc(a, arch, builds(a.id), libres, ctx, sets_repo)
            if par is None:
                continue
            da, db = par.discos
            viejo = sets.get(par.set_2p_viejo, "sin 2pc") if par.set_2p_viejo else "sin 2pc"
            crudas.append(Sugerencia(
                "armar_2pc", da.id, f"{_describir(da, sets)} + {_describir(db, sets)}",
                a.nombre, a.id, par.slots[0], delta=round(par.delta, 3),
                disc_id_2=db.id, slot_2=par.slots[1],
                nota=(f"cambia tu 2pc de {viejo} por {sets.get(par.set_id, par.set_id)} para llegar a "
                      f"{etiquetas.get(par.stat, par.stat)} {par.objetivo:g} "
                      f"({par.antes:g} → al menos {par.despues_min:.1f})")))
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


# ---------------------------------------------------------------------------
# Por disco: lo que la pantalla Discos necesita de cada fila
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SugerenciaDisco:
    """Lo que el motor dice de UN disco: su sugerencia propia (o None) y las de otros discos que lo
    nombran — el que REPONE en un "mover" y el segundo disco de un PAR (R24)."""
    propia: dict | None = None
    lo_nombran: tuple[tuple[str, dict], ...] = ()     # (("repone" | "par", sugerencia), ...)


def por_disco(reporte: dict) -> dict[int, SugerenciaDisco]:
    """El reporte de `generar` indexado por disco. Un disco que no aparece no tiene nada que hacer
    (equipado y sin cambio)."""
    propias: dict[int, dict] = {}
    nombran: dict[int, list[tuple[str, dict]]] = {}
    for lista in reporte.get("sugerencias", {}).values():
        for s in lista:
            propias[s["disc_id"]] = s
            if s.get("reemplazo_id"):
                nombran.setdefault(s["reemplazo_id"], []).append(("repone", s))
            if s.get("disc_id_2"):
                nombran.setdefault(s["disc_id_2"], []).append(("par", s))
    ids = set(propias) | set(nombran)
    return {i: SugerenciaDisco(propias.get(i), tuple(nombran.get(i, ()))) for i in ids}


# ---------------------------------------------------------------------------
# Un disco solo: el vivo (SPEC 2026-10-01, paso 8)
# ---------------------------------------------------------------------------

def sugerir_un_disco(con: sqlite3.Connection, disco: Disc,
                     contexto: ContextoMotor | None = None) -> SugerenciaDisco:
    """La sugerencia de UN disco con las mismas reglas que `generar`. Sin `resolver_conflictos`: en
    vivo no se cruza con las otras sugerencias, así que dice la mejora frente a lo que el PJ lleva
    hoy. Un disco que no está en la DB (un drop en sólo lectura, id −1) se evalúa igual: no hace
    falta sumarlo a los libres, porque R22 (`unico_en_la_cuenta`) excluye al propio disco y los
    libres sólo cuentan como reemplazo de un disco equipado que se mueve."""
    c = contexto or contexto_motor(con)
    rec = recomendar(disco, c.agentes, c.arqs, c.sets_repo, c.ctx, builds=c.builds, libres=c.libres)
    _estado, s = _clasificar(disco, rec, c)
    if s is None:
        return SugerenciaDisco()
    s.prioridad = c.prioridades.get(s.destino_id, "normal")
    return SugerenciaDisco(s.__dict__)
