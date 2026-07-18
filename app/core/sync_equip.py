"""
Hito 2.5.1 — Sync RF-04: disco capturado en pantalla → DB → score → notify.
Recibe un DiscParsed del parser, hace UPSERT en inventory_discs,
inserta en inventory_disc_evaluations y actualiza score_evaluacion.
Thread-safe: cada llamada abre su propia transacción (con RNF-01 cumplido).
"""
from __future__ import annotations

import difflib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.core.parser_disc import DiscParsed
from app.core.score_normalizer import ScoringContext
from app.core.stats_vocab import _norm_key
from app.db.connection import is_readonly
from app.core.recommender import Recommendation, recomendar, recommendation_to_json
from app.db.repositories import (
    AgentRepo,
    ArchetypeRepo,
    Disc,
    DiscSetRepo,
    EvaluationRepo,
    InventoryDiscRepo,
)

log = logging.getLogger(__name__)

# Fuzzy de nombre de set (difflib) en _resolve_set_id: umbral alto + margen de
# ambigüedad (RNF-02). Cutoff 0.86 acepta drops de 1 char ('Fábula'→'Fäbua'≈0.96)
# y rechaza nombres genuinamente distintos/ambiguos (p.ej. la forma larga de
# 'Balada …' vs el alias corto del catálogo ≈0.72).
_SET_FUZZY_CUTOFF = 0.86
_SET_FUZZY_MARGIN = 0.06

DB_PATH = Path("db/danibod_zzz_v2.db")


@dataclass
class SyncResult:
    disc_id: int
    trigger: str        # "captura_inicial" | "re_eval_threshold"
    recomendacion: str
    score_norm: float
    agente_nombre: str | None          # PJ recomendado por el scoring
    latency_ms: float
    # Asignación real capturada en S17 (PJ donde está equipado) — distinto del
    # recomendado. None si no hubo asignación confiable (no se tocó la DB).
    agente_asignado_nombre: str | None = None
    # Bono de conjunto curado del set (item #3, desde disc_sets — no OCR).
    set_bonus_2p: str | None = None
    set_bonus_4p: str | None = None
    # Composición de set del PJ asignado (derivada de los discos equipados en
    # inventory_discs): resumen legible "4pc X + 2pc Y · 6/6 · estándar 4+2".
    set_composition: str | None = None


# Callback opcional que recibe el resultado (para el toast de Fase 3)
NotifyFn = Callable[[SyncResult, DiscParsed], None]

# Callback opcional para cuando el optimizador termina (recibe OptimizerResult)
OptimizerNotifyFn = Callable[["OptimizerResult"], None]  # type: ignore[type-arg]

_OPTIMIZER_DEBOUNCE_S = 2.0


def compute_set_composition(con: sqlite3.Connection, agente_id: int) -> dict:
    """
    Composición de set de un PJ derivada de sus discos equipados (inventory_discs).
    Reusa el set leído por OCR del título en cada captura S17 (fiable). Devuelve:

        {
          "sets": [{"nombre", "count", "slots": [..], "tier": "4pc"|"2pc"|"suelto"}],
          "slots_llenos": [..], "faltantes": [..],
          "clasificacion": "estándar 4+2"|"exótica"|"incompleta",
        }

    `tier`: ≥4→"4pc" (que también activa el 2pc), ≥2→"2pc", ==1→"suelto".
    `clasificacion`: incompleta si hay slots faltantes (nulo o no capturado aún);
    estándar 4+2 si exactamente un set con 4 y uno con 2 sin faltantes; si no, exótica.
    """
    rows = con.execute(
        """SELECT iv.slot AS slot, iv.set_id AS set_id, ds.nombre AS nombre
           FROM inventory_discs iv LEFT JOIN disc_sets ds ON ds.id = iv.set_id
           WHERE iv.agente_asignado = ? AND iv.equipado = 1
             AND (iv.descartado = 0 OR iv.descartado IS NULL)
           ORDER BY iv.slot""",
        (agente_id,),
    ).fetchall()

    by_set: dict[int, dict] = {}
    slots_llenos: list[int] = []
    for r in rows:
        slot = r["slot"]
        sid = r["set_id"]
        if slot is not None:
            slots_llenos.append(slot)
        entry = by_set.setdefault(sid, {"nombre": r["nombre"] or f"set#{sid}", "slots": []})
        if slot is not None:
            entry["slots"].append(slot)

    def _tier(n: int) -> str:
        return "4pc" if n >= 4 else ("2pc" if n >= 2 else "suelto")

    sets = [
        {"nombre": e["nombre"], "count": len(e["slots"]),
         "slots": sorted(e["slots"]), "tier": _tier(len(e["slots"]))}
        for e in by_set.values()
    ]
    # Orden: por count desc (4pc primero), luego nombre.
    sets.sort(key=lambda s: (-s["count"], s["nombre"]))

    llenos = sorted(set(slots_llenos))
    faltantes = sorted(set(range(1, 7)) - set(llenos))

    counts = sorted((s["count"] for s in sets), reverse=True)
    if faltantes:
        clasificacion = "incompleta"
    elif counts == [4, 2]:
        clasificacion = "estándar 4+2"
    else:
        clasificacion = "exótica"

    return {
        "sets": sets,
        "slots_llenos": llenos,
        "faltantes": faltantes,
        "clasificacion": clasificacion,
    }


def format_composition(comp: dict) -> str:
    """Resumen legible de `compute_set_composition` para el log/UI."""
    if not comp.get("sets"):
        return "sin discos equipados capturados"
    partes = [f"{s['tier']} {s['nombre']}" for s in comp["sets"]]
    cuerpo = " + ".join(partes)
    n = len(comp["slots_llenos"])
    cob = f"{n}/6"
    extra = ""
    if comp["faltantes"]:
        fl = ",".join(str(s) for s in comp["faltantes"])
        extra = f" · slots {fl} faltantes (nulo/no capturado)"
    return f"{cuerpo} · {cob} · {comp['clasificacion']}{extra}"


def _parsed_to_disc(p: DiscParsed, disc_id: int, set_id: int) -> Disc:
    """Convierte DiscParsed → Disc para pasarlo al scoring engine."""
    subs = []
    for s in p.subs:
        name = s.nombre_canon or s.nombre_raw
        if name:
            subs.append((name, s.valor, s.unidad, s.rolls))
    return Disc(
        id=disc_id,
        set_id=set_id,
        slot=p.slot,
        main_stat=p.main_stat_canon or p.main_stat_raw,
        main_valor=p.main_valor,
        main_unidad=p.main_unidad,
        subs=subs,
        nivel=p.nivel,
        equipado=0,
        agente_asignado=None,
    )


class DiscSyncer:
    """
    Procesa un DiscParsed completo: persistencia + scoring + notificación.
    Usar una instancia por sesión de app (cachea repos).
    """

    def __init__(
        self,
        db_path: Path = DB_PATH,
        notify: NotifyFn | None = None,
        on_optimizer_result: "OptimizerNotifyFn | None" = None,
    ):
        self._db_path = db_path
        self._notify = notify
        self._on_optimizer_result = on_optimizer_result
        self._ctx = ScoringContext()

        # Repos de lectura (reutilizados entre llamadas). `check_same_thread=False`:
        # el DiscSyncer se construye en el thread de la UI pero `persist_s17_disc`
        # corre en el thread del monitor (daemon). El uso es single-thread real (no
        # hay accesos concurrentes a esta conexión), así que es seguro; sin esto
        # SQLite lanza "objects created in a thread can only be used in that thread".
        self._con_r = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con_r.row_factory = sqlite3.Row
        self._agent_repo  = AgentRepo(self._con_r)
        self._arch_repo   = ArchetypeRepo(self._con_r)
        self._set_repo    = DiscSetRepo(self._con_r)
        self._disc_repo_r = InventoryDiscRepo(self._con_r)

        # Debounce timers para auto-trigger optimizer (agente_id → Timer)
        self._opt_timers: dict[int, threading.Timer] = {}
        self._opt_lock   = threading.Lock()

    def close(self) -> None:
        with self._opt_lock:
            for t in self._opt_timers.values():
                t.cancel()
            self._opt_timers.clear()
        self._con_r.close()

    def on_disc_detected(self, parsed: DiscParsed) -> SyncResult | None:
        """
        Punto de entrada principal. Llamar desde monitor.py on_disc callback.
        Abre su propia conexión de escritura con transacción.
        Devuelve None si el disco tiene baja confianza o set desconocido.
        """
        t0 = time.perf_counter()

        # Resolver set_id desde el nombre capturado por OCR
        set_id = self._resolve_set_id(parsed)
        if set_id is None:
            log.warning("Set desconocido '%s' — disco descartado.", parsed.set_name_raw)
            return None

        if parsed.confianza_global < 0.7:
            log.debug("Confianza baja (%.2f) — disco ignorado.", parsed.confianza_global)
            return None

        # PJ asignado (S17): solo si el monitor lo marcó como confiable (latch +
        # avatar). None ⇒ no se toca agente_asignado/equipado (preserva lo curado).
        agente_id = self._resolve_agent_id(parsed)

        if is_readonly():
            log.info(
                "[readonly] disco NO persiste — set=%s slot=%s asignado=%s",
                parsed.set_name_raw, parsed.slot, parsed.agente_asignado_nombre or "-",
            )
            return None

        # Abrir conexión de escritura para esta transacción
        con_w = sqlite3.connect(str(self._db_path))
        con_w.row_factory = sqlite3.Row
        disc_repo_w  = InventoryDiscRepo(con_w)
        eval_repo_w  = EvaluationRepo(con_w)

        try:
            with con_w:
                # UPSERT por hash (set_id, slot, main_stat, main_valor)
                existing = disc_repo_w.find_by_hash(
                    set_id, parsed.slot,
                    parsed.main_stat_canon or parsed.main_stat_raw,
                    parsed.main_valor,
                )

                if existing:
                    disc_id = existing.id
                    trigger = "re_eval_threshold"
                    disc_repo_w.update_from_parsed(disc_id, parsed)
                    if agente_id is not None:
                        disc_repo_w.update_assignment(disc_id, agente_id)
                        log.info("Disco id=%d → asignado a '%s' (equipado).",
                                 disc_id, parsed.agente_asignado_nombre)
                    log.debug("Disco existente id=%d — actualizado.", disc_id)
                else:
                    disc_id = disc_repo_w.insert_from_parsed(
                        parsed, set_id,
                        agente_asignado=agente_id,
                        equipado=1 if agente_id is not None else 0,
                    )
                    trigger = "captura_inicial"
                    log.info(
                        "Disco nuevo insertado id=%d  set=%s slot=%d%s.",
                        disc_id, parsed.set_name_raw, parsed.slot,
                        f"  asignado='{parsed.agente_asignado_nombre}'" if agente_id is not None else "",
                    )

                # Scoring
                disc_obj = _parsed_to_disc(parsed, disc_id, set_id)
                rec = recomendar(disc_obj, self._agent_repo, self._arch_repo, self._set_repo, self._ctx)

                # Persistir evaluación y score
                eval_repo_w.insert(disc_id, trigger, rec.tipo, rec.score_norm, recommendation_to_json(rec))
                disc_repo_w.update_score(
                    disc_id,
                    rec.score_norm,
                    json.dumps({"top": [a.nombre for a, _ in rec.top_candidatos[:3]]}, ensure_ascii=False),
                    "; ".join(parsed.notas) if parsed.notas else None,
                )

            # Bono de conjunto curado (item #3) — desde disc_sets, no OCR.
            bonus_2p_stat, bonus_2p_valor, bonus_4p = self._set_repo.get_bonus(set_id)
            bonus_2p = (
                f"{bonus_2p_stat} {bonus_2p_valor}".strip()
                if (bonus_2p_stat or bonus_2p_valor) else None
            )

            latency_ms = (time.perf_counter() - t0) * 1000
            log.info(
                "Sync OK  id=%d  %s  score=%.3f  rec_agente=%s  asignado=%s  2pc=%s  %.0fms",
                disc_id, rec.tipo, rec.score_norm, rec.agente_nombre or "-",
                parsed.agente_asignado_nombre or "-", bonus_2p or "-", latency_ms,
            )

            result = SyncResult(
                disc_id=disc_id,
                trigger=trigger,
                recomendacion=rec.tipo,
                score_norm=rec.score_norm,
                agente_nombre=rec.agente_nombre,
                latency_ms=round(latency_ms, 1),
                agente_asignado_nombre=parsed.agente_asignado_nombre,
                set_bonus_2p=bonus_2p,
                set_bonus_4p=bonus_4p,
            )
            if self._notify:
                try:
                    self._notify(result, parsed)
                except Exception as exc:
                    log.exception("Error en notify callback: %s", exc)

            # Hito 2.6.4 — auto-trigger del optimizador con debounce 2s
            if rec.tipo == "equipar" and rec.agente_id is not None:
                self._schedule_optimizer(rec.agente_id)

            return result

        except Exception as exc:
            log.exception("Error en on_disc_detected: %s", exc)
            return None
        finally:
            con_w.close()

    def persist_s17_disc(self, parsed: DiscParsed) -> SyncResult | None:
        """
        Persistencia ENFOCADA de un disco equipado S17 (decisión 2026-06-06):
        upsert disco + asignación con salvaguarda + bono, SIN scoring/optimizer
        (consistente con 'S17 = extracción, scoring fase posterior'). Devuelve un
        SyncResult informativo (recomendacion='(s17)', score 0) o None si no se
        pudo resolver el set / baja confianza.
        """
        t0 = time.perf_counter()
        set_id = self._resolve_set_id(parsed)
        if set_id is None:
            log.warning("S17: set desconocido '%s' — no se persiste.", parsed.set_name_raw)
            return None
        if parsed.confianza_global < 0.7:
            log.debug("S17: confianza baja (%.2f) — no se persiste.", parsed.confianza_global)
            return None

        agente_id = self._resolve_agent_id(parsed)
        # Sin PJ confiable NO se persiste: el disco S17 está equipado en ALGÚN PJ y
        # la clave correcta es (PJ, slot). Sin saber el PJ, cualquier match por firma
        # (set+slot+main+substats) colisiona con discos de otros PJs (en este roster,
        # 72% de los discos comparten firma con otro PJ) → corromper/robar datos.
        # Mejor no escribir y dejar que el usuario identifique el PJ (Atributos base).
        if agente_id is None:
            log.info(
                "S17: PJ no confiable para '%s' slot=%d — no se persiste (evita colisión entre PJs).",
                parsed.set_name_raw, parsed.slot,
            )
            return None

        if is_readonly():
            # Modo offline: NO se escribe. Se computa lo legible (set/composición) y
            # se loguea lo que SE HARÍA, para testear hipótesis sin tocar la DB. La
            # identificación del PJ (que puede ser errónea) ya la logueó el monitor.
            comp = None
            try:
                comp = format_composition(compute_set_composition(self._con_r, agente_id))
            except Exception:
                log.exception("Error computando composición (readonly)")
            bonus_2p_stat, bonus_2p_valor, bonus_4p = self._set_repo.get_bonus(set_id)
            bonus_2p = (
                f"{bonus_2p_stat} {bonus_2p_valor}".strip()
                if (bonus_2p_stat or bonus_2p_valor) else None
            )
            log.info(
                "[readonly] S17 NO persiste — set=%s slot=%d asignado=%s comp=%s",
                parsed.set_name_raw, parsed.slot,
                parsed.agente_asignado_nombre or "-", comp or "-",
            )
            return SyncResult(
                disc_id=-1, trigger="readonly", recomendacion="(s17)", score_norm=0.0,
                agente_nombre=None, latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                agente_asignado_nombre=parsed.agente_asignado_nombre,
                set_bonus_2p=bonus_2p, set_bonus_4p=bonus_4p, set_composition=comp,
            )

        con_w = sqlite3.connect(str(self._db_path))
        con_w.row_factory = sqlite3.Row
        disc_repo_w = InventoryDiscRepo(con_w)
        try:
            with con_w:
                # Clave NATURAL del equipamiento: un PJ tiene un disco por slot.
                # Nunca matchea el disco de otro PJ (a diferencia de find_by_hash).
                slot_disc = disc_repo_w.find_equipped_by_agent_slot(agente_id, parsed.slot)
                if slot_disc is not None and slot_disc.set_id == set_id:
                    # Mismo disco (refresco de nivel/substats tras upgrade).
                    disc_id = slot_disc.id
                    trigger = "s17_update"
                    disc_repo_w.update_from_parsed(disc_id, parsed)
                elif slot_disc is not None:
                    # El PJ cambió el disco de este slot (set distinto): swap-out el
                    # viejo (queda en inventario) e inserta el nuevo equipado.
                    disc_repo_w.set_unequipped(slot_disc.id)
                    disc_id = disc_repo_w.insert_from_parsed(
                        parsed, set_id, agente_asignado=agente_id, equipado=1,
                    )
                    trigger = "s17_swap"
                else:
                    # PJ sin disco previo en ese slot → alta.
                    disc_id = disc_repo_w.insert_from_parsed(
                        parsed, set_id, agente_asignado=agente_id, equipado=1,
                    )
                    trigger = "s17_insert"

            bonus_2p_stat, bonus_2p_valor, bonus_4p = self._set_repo.get_bonus(set_id)
            bonus_2p = (
                f"{bonus_2p_stat} {bonus_2p_valor}".strip()
                if (bonus_2p_stat or bonus_2p_valor) else None
            )
            # Composición de set del PJ (derivada de los discos equipados). Solo si
            # hay PJ asignado confiable. Usa _con_r (check_same_thread=False).
            composition = None
            if agente_id is not None:
                try:
                    composition = format_composition(
                        compute_set_composition(self._con_r, agente_id)
                    )
                except Exception:
                    log.exception("Error computando composición de set")
            latency_ms = (time.perf_counter() - t0) * 1000
            log.info(
                "S17 persistido id=%d %s set=%s slot=%d asignado=%s 2pc=%s comp=%s %.0fms",
                disc_id, trigger, parsed.set_name_raw, parsed.slot,
                parsed.agente_asignado_nombre or "-", bonus_2p or "-",
                composition or "-", latency_ms,
            )
            return SyncResult(
                disc_id=disc_id,
                trigger=trigger,
                recomendacion="(s17)",
                score_norm=0.0,
                agente_nombre=None,
                latency_ms=round(latency_ms, 1),
                agente_asignado_nombre=parsed.agente_asignado_nombre,
                set_bonus_2p=bonus_2p,
                set_bonus_4p=bonus_4p,
                set_composition=composition,
            )
        except Exception as exc:
            log.exception("Error en persist_s17_disc: %s", exc)
            return None
        finally:
            con_w.close()

    def move_disc_between_agents(
        self, origin_name: str | None, dest_name: str | None, slot: int,
        set_id: int | None = None,
    ) -> bool:
        """Mueve el disco equipado del PJ ORIGEN en `slot` al PJ DESTINO (swap detectado en S23).

        Actualiza la fila EXISTENTE del disco del origen (`update_assignment` → destino), en vez de
        dejar que la persistencia S17 inserte una fila nueva (que duplicaría el disco y dejaría al
        origen reclamándolo). Desequipa primero el disco desplazado del destino en ese slot. Corre
        ANTES de la persistencia S17 del mismo disco: al persistir, `find_equipped_by_agent_slot`
        del destino ya encuentra este disco (set correcto) → va por el path de update, sin duplicar.

        Devuelve True si movió una fila. No-op (False) si readonly, si falta un PJ, o si el disco
        del origen no está en la DB (en ese caso la persistencia S17 normal lo dará de alta en el
        destino — sin la fila del origen no hay nada que mover). RNF-01: el backup de sesión lo hace
        el controller al arrancar; escribe en su propia transacción."""
        if is_readonly():
            log.info("[readonly] swap NO persiste — %s → %s slot=%s", origin_name, dest_name, slot)
            return False
        if not origin_name or not dest_name:
            log.info("Swap sin PJ resoluble (origen=%s destino=%s) — no se mueve.", origin_name, dest_name)
            return False
        origin = self._agent_repo.get_by_nombre(origin_name)
        dest = self._agent_repo.get_by_nombre(dest_name)
        if origin is None or dest is None:
            log.info("Swap: PJ no resuelto (origen=%s destino=%s) — no se mueve.", origin_name, dest_name)
            return False
        if origin.id == dest.id:
            return False

        con_w = sqlite3.connect(str(self._db_path))
        con_w.row_factory = sqlite3.Row
        disc_repo_w = InventoryDiscRepo(con_w)
        try:
            with con_w:
                moved = disc_repo_w.find_equipped_by_agent_slot(origin.id, slot)
                if moved is None:
                    log.info(
                        "Swap: el disco del origen %s slot=%d no está en la DB → lo dará de alta "
                        "la persistencia S17 en %s (sin fila de origen que mover).",
                        origin_name, slot, dest_name,
                    )
                    return False
                if set_id is not None and moved.set_id != set_id:
                    log.warning(
                        "Swap: el disco equipado de %s slot=%d es set=%s pero el diálogo decía "
                        "set_id=%s — no se mueve (RNF-02).", origin_name, slot, moved.set_id, set_id,
                    )
                    return False
                # Desequipar el disco desplazado del destino en ese slot (si tenía otro distinto).
                displaced = disc_repo_w.find_equipped_by_agent_slot(dest.id, slot)
                if displaced is not None and displaced.id != moved.id:
                    disc_repo_w.set_unequipped(displaced.id)
                # Mover la fila EXISTENTE del disco al destino (sin duplicar).
                disc_repo_w.update_assignment(moved.id, dest.id, equipado=1)
            log.info(
                "Swap persistido: disco id=%d slot=%d movido %s → %s%s",
                moved.id, slot, origin_name, dest_name,
                f" (desplazó id={displaced.id})" if displaced and displaced.id != moved.id else "",
            )
            return True
        except Exception as exc:
            log.exception("Error en move_disc_between_agents: %s", exc)
            return False
        finally:
            con_w.close()

    def _schedule_optimizer(self, agente_id: int) -> None:
        """Dispara recompute_best_build con debounce de 2 s por PJ."""
        def _run() -> None:
            try:
                from app.core.optimizer import recompute_best_build
                result = recompute_best_build(agente_id, self._db_path)
                log.info(
                    "Optimizer PJ=%d  score_actual=%.3f  best=%.3f  latency=%.0fms",
                    agente_id,
                    result.score_actual,
                    result.builds[0].score_total if result.builds else 0.0,
                    result.latency_ms,
                )
                if self._on_optimizer_result:
                    try:
                        self._on_optimizer_result(result)
                    except Exception as exc:
                        log.exception("Error en on_optimizer_result: %s", exc)
            except Exception as exc:
                log.exception("Error en optimizer para PJ=%d: %s", agente_id, exc)
            finally:
                with self._opt_lock:
                    self._opt_timers.pop(agente_id, None)

        with self._opt_lock:
            existing = self._opt_timers.pop(agente_id, None)
            if existing:
                existing.cancel()
            t = threading.Timer(_OPTIMIZER_DEBOUNCE_S, _run)
            t.daemon = True
            self._opt_timers[agente_id] = t
            t.start()
        log.debug("Optimizer debounce iniciado para PJ=%d.", agente_id)

    def _resolve_agent_id(self, parsed: DiscParsed) -> int | None:
        """
        Resuelve el agent_id del PJ asignado (S17), SOLO si el monitor lo marcó
        confiable (nombre presente y conf > 0). None ⇒ no se escribe la asignación
        (preserva agente_asignado/equipado curados, RNF-02).
        """
        name = parsed.agente_asignado_nombre
        if not name or parsed.agente_asignado_conf <= 0:
            return None
        a = self._agent_repo.get_by_nombre(name)
        if a is None:
            log.warning("S17: PJ asignado '%s' no existe en agents — sin asignar.", name)
            return None
        return a.id

    def _resolve_set_id(self, parsed: DiscParsed) -> int | None:
        """Resuelve set_id desde el nombre del set (posible ruido OCR): exact → fuzzy sin
        acentos → difflib con guarda de ambigüedad. Delega en `DiscSetRepo.resolve_id`
        (fuente única, compartida con el selector de tienda de música S4)."""
        name = parsed.set_name_canon or parsed.set_name_raw
        return self._set_repo.resolve_id(name, cutoff=_SET_FUZZY_CUTOFF, margin=_SET_FUZZY_MARGIN)
