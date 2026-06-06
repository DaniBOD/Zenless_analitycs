"""
Hito 2.5.1 — Sync RF-04: disco capturado en pantalla → DB → score → notify.
Recibe un DiscParsed del parser, hace UPSERT en inventory_discs,
inserta en inventory_disc_evaluations y actualiza score_evaluacion.
Thread-safe: cada llamada abre su propia transacción (con RNF-01 cumplido).
"""
from __future__ import annotations

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


# Callback opcional que recibe el resultado (para el toast de Fase 3)
NotifyFn = Callable[[SyncResult, DiscParsed], None]

# Callback opcional para cuando el optimizador termina (recibe OptimizerResult)
OptimizerNotifyFn = Callable[["OptimizerResult"], None]  # type: ignore[type-arg]

_OPTIMIZER_DEBOUNCE_S = 2.0


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

        # Repos de lectura (reutilizados entre llamadas)
        self._con_r = sqlite3.connect(str(db_path))
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

        con_w = sqlite3.connect(str(self._db_path))
        con_w.row_factory = sqlite3.Row
        disc_repo_w = InventoryDiscRepo(con_w)
        try:
            with con_w:
                existing = disc_repo_w.find_by_hash(
                    set_id, parsed.slot,
                    parsed.main_stat_canon or parsed.main_stat_raw,
                    parsed.main_valor,
                )
                if existing:
                    disc_id = existing.id
                    trigger = "s17_update"
                    disc_repo_w.update_from_parsed(disc_id, parsed)
                    if agente_id is not None:
                        disc_repo_w.update_assignment(disc_id, agente_id)
                else:
                    disc_id = disc_repo_w.insert_from_parsed(
                        parsed, set_id,
                        agente_asignado=agente_id,
                        equipado=1 if agente_id is not None else 0,
                    )
                    trigger = "s17_insert"

            bonus_2p_stat, bonus_2p_valor, bonus_4p = self._set_repo.get_bonus(set_id)
            bonus_2p = (
                f"{bonus_2p_stat} {bonus_2p_valor}".strip()
                if (bonus_2p_stat or bonus_2p_valor) else None
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            log.info(
                "S17 persistido id=%d %s set=%s slot=%d asignado=%s 2pc=%s %.0fms",
                disc_id, trigger, parsed.set_name_raw, parsed.slot,
                parsed.agente_asignado_nombre or "-", bonus_2p or "-", latency_ms,
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
            )
        except Exception as exc:
            log.exception("Error en persist_s17_disc: %s", exc)
            return None
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
        """Intenta resolver set_id desde set_name_raw usando exact + fuzzy matching."""
        name = parsed.set_name_canon or parsed.set_name_raw
        if not name:
            return None

        # 1. Exact match (case-insensitive)
        sid = self._set_repo.get_id_by_name(name)
        if sid:
            return sid

        # 2. Fuzzy: buscar set cuyo nombre sea substring del texto OCR o viceversa
        all_sets = self._set_repo.get_all_names()  # {nombre_lower: id}
        name_l = name.lower().strip()
        for sname, sid in all_sets.items():
            if sname in name_l or name_l in sname:
                log.debug("Set fuzzy match: '%s' → '%s' (id=%d)", name, sname, sid)
                return sid

        return None
