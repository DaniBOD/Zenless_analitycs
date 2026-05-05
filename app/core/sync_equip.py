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
    agente_nombre: str | None
    latency_ms: float


# Callback opcional que recibe el resultado (para el toast de Fase 3)
NotifyFn = Callable[[SyncResult, DiscParsed], None]


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
    ):
        self._db_path = db_path
        self._notify = notify
        self._ctx = ScoringContext()

        # Repos de lectura (reutilizados entre llamadas)
        self._con_r = sqlite3.connect(str(db_path))
        self._con_r.row_factory = sqlite3.Row
        self._agent_repo  = AgentRepo(self._con_r)
        self._arch_repo   = ArchetypeRepo(self._con_r)
        self._set_repo    = DiscSetRepo(self._con_r)
        self._disc_repo_r = InventoryDiscRepo(self._con_r)

    def close(self) -> None:
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
                    log.debug("Disco existente id=%d — actualizado.", disc_id)
                else:
                    disc_id = disc_repo_w.insert_from_parsed(parsed, set_id)
                    trigger = "captura_inicial"
                    log.info("Disco nuevo insertado id=%d  set=%s slot=%d.", disc_id, parsed.set_name_raw, parsed.slot)

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

            latency_ms = (time.perf_counter() - t0) * 1000
            log.info(
                "Sync OK  id=%d  %s  score=%.3f  agente=%s  %.0fms",
                disc_id, rec.tipo, rec.score_norm, rec.agente_nombre or "-", latency_ms,
            )

            result = SyncResult(
                disc_id=disc_id,
                trigger=trigger,
                recomendacion=rec.tipo,
                score_norm=rec.score_norm,
                agente_nombre=rec.agente_nombre,
                latency_ms=round(latency_ms, 1),
            )
            if self._notify:
                try:
                    self._notify(result, parsed)
                except Exception as exc:
                    log.exception("Error en notify callback: %s", exc)

            return result

        except Exception as exc:
            log.exception("Error en on_disc_detected: %s", exc)
            return None
        finally:
            con_w.close()

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
