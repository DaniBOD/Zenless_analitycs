"""
Hito 2.6.2-3 — Optimizador de build RF-06.
Greedy por slot (K=10) + bonus pass (combos 4pc/2+2+2/3+3) + swap chains longitud 1.
Respeta agents.protected_build; devuelve top-3 builds con desglose.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Callable

from app.core.scoring import score_disco
from app.core.score_normalizer import ScoringContext
from app.db.repositories import (
    Agent, AgentDiscRepo, AgentRepo, Archetype, ArchetypeRepo,
    Disc, DiscSetRepo, InventoryDiscRepo, OptimizerRepo,
)

log = logging.getLogger(__name__)

DB_PATH = Path("db/danibod_zzz_v2.db")

K_PER_SLOT   = 10
TOP_N_BUILDS = 3

# Set bonus weights applied at build level (RF-06 §4.2)
BONUS_4PC_PRIM = 1.5
BONUS_4PC_SEC  = 0.7
BONUS_2PC_PRIM = 0.4
BONUS_2PC_SEC  = 0.2


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DiscInBuild:
    disc_id: int
    slot: int
    set_id: int
    set_name: str
    main_stat: str | None
    score_disc: float
    swap_origen: dict | None = None   # None = free; {pj_id, pj_nombre, delta_origen} if swap


@dataclass
class Build:
    rank: int
    build_id: str
    score_total: float        # Σ disc scores + set bonus
    score_norm: float         # / theoretical max
    set_bonus: float
    set_bonus_desc: str       # "4pc Balada + 2pc Tecno"
    discos: list[DiscInBuild]
    swaps_requeridos: list[dict]
    delta_vs_actual: float | None


@dataclass
class OptimizerResult:
    agente_id: int
    agente_nombre: str
    fecha: str
    score_actual: float
    builds: list[Build]
    latency_ms: float


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _disc_base_score(
    disc: Disc,
    agent: Agent,
    arch: Archetype,
    ctx: ScoringContext,
) -> float:
    """Score sin set bonus (substats + main + nivel). Usado para rankeo interno del optimizer."""
    bd = score_disco(
        disc, agent, arch, ctx,
        disc_set_archetypes=[],
        agent_set4p_id=None,
        agent_set2p_id=None,
    )
    return bd.score_raw


def _set_bonus_for_counts(
    set_counts: dict[int, int],
    arch: Archetype,
    set_repo: DiscSetRepo,
    agent_set4p_id: int | None,
    agent_set2p_id: int | None,
) -> tuple[float, str]:
    """Calcula bonus total del set combo y una descripción legible."""
    bonus = 0.0
    parts: list[str] = []

    set_names: dict[int, str] = {}
    try:
        for r in set_repo._con.execute("SELECT id, nombre FROM disc_sets"):
            set_names[r["id"]] = r["nombre"]
    except Exception:
        pass

    for set_id, count in sorted(set_counts.items()):
        if count < 2:
            continue
        dsas = set_repo.get_archetypes_for_set(set_id)
        is_prim = (
            set_id == agent_set4p_id
            or any(d.archetype_id == arch.id and d.prioridad == 1 for d in dsas)
        )
        is_sec = (
            set_id == agent_set2p_id
            or any(d.archetype_id == arch.id and d.prioridad == 2 for d in dsas)
        )

        pc4_done = False
        if count >= 4:
            b = BONUS_4PC_PRIM if is_prim else (BONUS_4PC_SEC if is_sec else 0.0)
            bonus += b
            if b:
                parts.append(f"4pc {set_names.get(set_id, str(set_id))}")
            pc4_done = True

        # 2pc bonus (always applies if count >= 2; additive with 4pc)
        b2 = BONUS_2PC_PRIM if is_prim else (BONUS_2PC_SEC if is_sec else 0.0)
        bonus += b2
        if b2 and not pc4_done:
            parts.append(f"2pc {set_names.get(set_id, str(set_id))}")

    desc = " + ".join(parts) if parts else "sin bonus de set"
    return bonus, desc


def _build_score_total(
    chosen: dict[int, Disc],      # slot → Disc
    base_scores: dict[int, float], # disc_id → base_score
    arch: Archetype,
    set_repo: DiscSetRepo,
    agent: Agent,
    ctx: ScoringContext,
) -> tuple[float, float, dict[int, int]]:
    """Suma base scores de los discos + set bonus. Devuelve (score_total, set_bonus, set_counts)."""
    set_counts: dict[int, int] = {}
    disc_sum = 0.0
    for slot, disc in chosen.items():
        disc_sum += base_scores[disc.id]
        set_counts[disc.set_id] = set_counts.get(disc.set_id, 0) + 1

    set_b, _ = _set_bonus_for_counts(
        set_counts, arch, set_repo, agent.set_4p_id, agent.set_2p_id
    )
    return disc_sum + set_b, set_b, set_counts


def _pick_best_for_assignment(
    candidates: dict[int, list[Disc]],   # slot → sorted desc
    slot_to_set: dict[int, int | None],   # slot → required set_id (None = free)
    base_scores: dict[int, float],
) -> dict[int, Disc] | None:
    """Para una asignación de set por slot, elige el mejor disco disponible. None si no hay disco para algún slot."""
    chosen: dict[int, Disc] = {}
    for slot, req_set in slot_to_set.items():
        best = None
        for disc in candidates.get(slot, []):
            if req_set is None or disc.set_id == req_set:
                best = disc
                break
        if best is None:
            return None
        chosen[slot] = best
    return chosen


def _all_slot_partitions_4_2(n_slots: int = 6) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """Devuelve todas las particiones (4 slots para 4pc, 2 slots para 2pc)."""
    slots = list(range(1, n_slots + 1))
    result = []
    for combo4 in combinations(slots, 4):
        combo2 = tuple(s for s in slots if s not in combo4)
        result.append((combo4, combo2))
    return result


def _all_slot_partitions_2_2_2(n_slots: int = 6) -> list[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]]:
    """Devuelve todas las particiones (2 slots por set, 3 sets)."""
    slots = list(range(1, n_slots + 1))
    result = []
    for p1 in combinations(slots, 2):
        remaining = [s for s in slots if s not in p1]
        for p2 in combinations(remaining, 2):
            p3 = tuple(s for s in remaining if s not in p2)
            if p1 < p2 < p3:  # avoid duplicates (canonical order)
                result.append((p1, p2, p3))
    return result


# ---------------------------------------------------------------------------
# Fase 1 — Greedy por slot
# ---------------------------------------------------------------------------

def _greedy_candidates(
    inv_discs: list[Disc],
    agent: Agent,
    arch: Archetype,
    ctx: ScoringContext,
) -> tuple[dict[int, list[Disc]], dict[int, float]]:
    """
    Por cada slot: filtra por main compatible con el arquetipo y ordena por score base.
    Devuelve (candidates_per_slot, base_scores_by_disc_id).
    """
    valid_mains: dict[int, list[str]] = {
        4: arch.mains_4,
        5: arch.mains_5,
        6: arch.mains_6,
    }
    # Slots 1-3 tienen main fijo, cualquier disco de ese slot es compatible
    eligible: dict[int, list[tuple[float, Disc]]] = {s: [] for s in range(1, 7)}
    base_scores: dict[int, float] = {}

    for disc in inv_discs:
        if disc.slot < 1 or disc.slot > 6:
            continue
        if disc.slot >= 4:
            allowed = valid_mains.get(disc.slot, [])
            if allowed and disc.main_stat and disc.main_stat not in allowed:
                continue  # main incompatible → excluir
        bs = _disc_base_score(disc, agent, arch, ctx)
        base_scores[disc.id] = bs
        eligible[disc.slot].append((bs, disc))

    candidates: dict[int, list[Disc]] = {}
    for slot, scored in eligible.items():
        scored.sort(key=lambda x: x[0], reverse=True)
        candidates[slot] = [d for _, d in scored[:K_PER_SLOT]]

    return candidates, base_scores


# ---------------------------------------------------------------------------
# Fase 2 — Bonus pass
# ---------------------------------------------------------------------------

def _bonus_pass(
    candidates: dict[int, list[Disc]],
    base_scores: dict[int, float],
    agent: Agent,
    arch: Archetype,
    set_repo: DiscSetRepo,
    ctx: ScoringContext,
) -> list[tuple[float, float, dict[int, Disc], dict[int, int]]]:
    """
    Enumera combos de set y devuelve lista de (score_total, set_bonus, chosen_discs, set_counts),
    ordenada descendente. Incluye combos 4pc+2pc, 2+2+2 y 3+3.
    """
    # Conjuntos disponibles por slot
    sets_per_slot: dict[int, set[int]] = {
        slot: {d.set_id for d in discs}
        for slot, discs in candidates.items()
    }
    all_sets = set().union(*sets_per_slot.values()) if sets_per_slot else set()

    # Slots con al menos 1 candidato
    active_slots = [s for s in range(1, 7) if candidates.get(s)]

    results: list[tuple[float, float, dict[int, Disc], dict[int, int]]] = []
    seen_disc_keys: set[tuple[int, ...]] = set()

    def _try_assignment(slot_to_set: dict[int, int | None]) -> None:
        chosen = _pick_best_for_assignment(candidates, slot_to_set, base_scores)
        if chosen is None or len(chosen) < len(active_slots):
            return
        key = tuple(chosen[s].id for s in sorted(chosen))
        if key in seen_disc_keys:
            return
        seen_disc_keys.add(key)
        total, sb, sc = _build_score_total(chosen, base_scores, arch, set_repo, agent, ctx)
        results.append((total, sb, chosen, sc))

    # A) 4pc + 2pc
    sets_4pc = {
        s for s in all_sets
        if sum(1 for sl in active_slots if s in sets_per_slot.get(sl, set())) >= 4
    }
    sets_2pc = {
        s for s in all_sets
        if sum(1 for sl in active_slots if s in sets_per_slot.get(sl, set())) >= 2
    }

    for s4 in sets_4pc:
        for s2 in sets_2pc:
            if s2 == s4:
                continue
            for slots4, slots2 in _all_slot_partitions_4_2(len(active_slots)):
                # remap partition indices to actual slot numbers
                sorted_slots = sorted(active_slots)
                if max(max(slots4), max(slots2)) > len(sorted_slots):
                    continue
                real4 = tuple(sorted_slots[i - 1] for i in slots4)
                real2 = tuple(sorted_slots[i - 1] for i in slots2)
                slot_to_set: dict[int, int | None] = {s: s4 for s in real4}
                slot_to_set.update({s: s2 for s in real2})
                _try_assignment(slot_to_set)

    # B) 2+2+2
    sets_list = sorted(sets_2pc)
    for s1, s2, s3 in combinations(sets_list, 3):
        for p1, p2, p3 in _all_slot_partitions_2_2_2(len(active_slots)):
            sorted_slots = sorted(active_slots)
            max_idx = max(max(p1), max(p2), max(p3))
            if max_idx > len(sorted_slots):
                continue
            real1 = tuple(sorted_slots[i - 1] for i in p1)
            real2 = tuple(sorted_slots[i - 1] for i in p2)
            real3 = tuple(sorted_slots[i - 1] for i in p3)
            slot_to_set = {s: s1 for s in real1}
            slot_to_set.update({s: s2 for s in real2})
            slot_to_set.update({s: s3 for s in real3})
            _try_assignment(slot_to_set)

    # C) Greedy puro sin restricción de set (fallback / baseline)
    _try_assignment({s: None for s in active_slots})

    results.sort(key=lambda x: x[0], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Fase 3 — Swap chains longitud 1
# ---------------------------------------------------------------------------

def _compute_swaps(
    build_discs: dict[int, Disc],
    target_agent: Agent,
    agent_repo: AgentRepo,
    arch_repo: ArchetypeRepo,
    agent_disc_repo: AgentDiscRepo,
    set_repo: DiscSetRepo,
    base_scores: dict[int, float],
    ctx: ScoringContext,
) -> list[dict]:
    """
    Para cada disco del build propuesto que esté equipado en otro PJ,
    calcula swap_neto = ganancia_destino - perdida_origen.
    Solo retorna swaps con neto > 0. Respeta protected_build del PJ origen.
    """
    swaps: list[dict] = []
    for disc in build_discs.values():
        if not disc.equipado or disc.agente_asignado is None:
            continue
        if disc.agente_asignado == target_agent.id:
            continue

        origen = agent_repo.get_by_id(disc.agente_asignado)
        if origen is None or origen.protected_build:
            continue

        origen_arch = arch_repo.get_by_id(origen.arquetipo_primario_id)
        if origen_arch is None:
            continue

        # Score del disco para el PJ origen (pérdida si se lo quitamos)
        score_for_origen = _disc_base_score(disc, origen, origen_arch, ctx)

        # Ganancia para el PJ destino (ya tenemos el score en base_scores)
        score_for_destino = base_scores.get(disc.id, 0.0)

        neto = score_for_destino - score_for_origen
        if neto > 0:
            swaps.append({
                "pj_origen_id":   origen.id,
                "pj_origen":      origen.nombre,
                "disc_id":        disc.id,
                "delta_origen":   round(-score_for_origen, 4),
                "delta_destino":  round(score_for_destino, 4),
                "neto":           round(neto, 4),
            })

    return swaps


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

class BuildOptimizer:
    """
    Optimizador de build para un PJ dado.
    Instanciar una vez por sesión de app (cachea repos y ctx).
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._ctx = ScoringContext()
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        self._con = con
        self._agent_repo     = AgentRepo(con)
        self._arch_repo      = ArchetypeRepo(con)
        self._set_repo       = DiscSetRepo(con)
        self._inv_disc_repo  = InventoryDiscRepo(con)
        self._agent_disc_repo = AgentDiscRepo(con)

    def close(self) -> None:
        self._con.close()

    def best_builds(
        self,
        agente_id: int,
        top_n: int = TOP_N_BUILDS,
        persist: bool = True,
    ) -> OptimizerResult:
        """
        Calcula las top_n mejores builds para el agente dado.
        Si persist=True, escribe el resultado en optimizer_pending_actions.
        """
        from datetime import datetime
        t0 = time.perf_counter()

        agent = self._agent_repo.get_by_id(agente_id)
        if agent is None:
            raise ValueError(f"Agente id={agente_id} no encontrado.")

        arch = self._arch_repo.get_by_id(agent.arquetipo_primario_id)
        if arch is None:
            raise ValueError(f"Arquetipo id={agent.arquetipo_primario_id} no encontrado.")

        # Score actual del PJ (baseline)
        current_discs = self._agent_disc_repo.get_by_agent(agente_id)
        score_actual = self._build_total_score(current_discs, agent, arch)

        # Inventario activo (todos los discos disponibles)
        inv_discs = self._inv_disc_repo.get_all_active()

        # Fase 1: greedy por slot
        candidates, base_scores = _greedy_candidates(inv_discs, agent, arch, self._ctx)

        # Para swaps: también considerar discos equipados en otros PJs
        equipped_others = [
            d for d in self._inv_disc_repo.get_all_active()
            if d.equipado and d.agente_asignado and d.agente_asignado != agente_id
        ]
        # Agregar a candidates y base_scores (si no están ya)
        for disc in equipped_others:
            if disc.id not in base_scores:
                if disc.slot < 1 or disc.slot > 6:
                    continue
                if disc.slot >= 4 and arch.mains_4:
                    allowed = getattr(arch, f"mains_{disc.slot}", [])
                    if allowed and disc.main_stat and disc.main_stat not in allowed:
                        continue
                bs = _disc_base_score(disc, agent, arch, self._ctx)
                base_scores[disc.id] = bs
                # Append al final de la lista del slot (baja prioridad salvo que sea muy bueno)
                candidates.setdefault(disc.slot, []).append(disc)
                # Re-ordenar y truncar
                slot_scored = [(base_scores[d.id], d) for d in candidates[disc.slot]]
                slot_scored.sort(key=lambda x: x[0], reverse=True)
                candidates[disc.slot] = [d for _, d in slot_scored[:K_PER_SLOT]]

        # Fase 2: bonus pass
        raw_results = _bonus_pass(candidates, base_scores, agent, arch, self._set_repo, self._ctx)

        # Normalizar scores
        score_max_teorico = self._ctx.score_maximo_teorico(arch)
        norm_factor = score_max_teorico * 6  # 6 discos

        builds: list[Build] = []
        seen_builds: set[tuple[int, ...]] = set()

        for rank_idx, (score_total, set_bonus, chosen_discs, set_counts) in enumerate(raw_results):
            if len(builds) >= top_n:
                break

            disc_key = tuple(sorted(chosen_discs[s].id for s in sorted(chosen_discs)))
            if disc_key in seen_builds:
                continue
            seen_builds.add(disc_key)

            _, set_bonus_desc = _set_bonus_for_counts(
                set_counts, arch, self._set_repo, agent.set_4p_id, agent.set_2p_id
            )

            swaps = _compute_swaps(
                chosen_discs, agent,
                self._agent_repo, self._arch_repo, self._agent_disc_repo,
                self._set_repo, base_scores, self._ctx,
            )
            swaps_disc_ids = {sw["disc_id"] for sw in swaps}

            discos_in_build: list[DiscInBuild] = []
            set_names: dict[int, str] = {}
            for r in self._con.execute("SELECT id, nombre FROM disc_sets"):
                set_names[r["id"]] = r["nombre"]

            for slot in sorted(chosen_discs):
                disc = chosen_discs[slot]
                swap_info = None
                if disc.id in swaps_disc_ids:
                    sw = next(s for s in swaps if s["disc_id"] == disc.id)
                    swap_info = {
                        "pj_id":     sw["pj_origen_id"],
                        "pj_nombre": sw["pj_origen"],
                        "delta_origen": sw["delta_origen"],
                    }
                discos_in_build.append(DiscInBuild(
                    disc_id=disc.id,
                    slot=slot,
                    set_id=disc.set_id,
                    set_name=set_names.get(disc.set_id, str(disc.set_id)),
                    main_stat=disc.main_stat,
                    score_disc=round(base_scores.get(disc.id, 0.0), 4),
                    swap_origen=swap_info,
                ))

            build = Build(
                rank=len(builds) + 1,
                build_id=str(uuid.uuid4()),
                score_total=round(score_total, 4),
                score_norm=round(min(1.0, score_total / max(norm_factor, 0.0001)), 4),
                set_bonus=round(set_bonus, 4),
                set_bonus_desc=set_bonus_desc,
                discos=discos_in_build,
                swaps_requeridos=[sw for sw in swaps if sw["disc_id"] in {d.disc_id for d in discos_in_build}],
                delta_vs_actual=round(score_total - score_actual, 4),
            )
            builds.append(build)

        latency_ms = (time.perf_counter() - t0) * 1000

        if persist and builds:
            self._persist_builds(agente_id, builds, score_actual)

        return OptimizerResult(
            agente_id=agente_id,
            agente_nombre=agent.nombre,
            fecha=datetime.now().isoformat(),
            score_actual=round(score_actual, 4),
            builds=builds,
            latency_ms=round(latency_ms, 1),
        )

    def _build_total_score(self, discs: list[Disc], agent: Agent, arch: Archetype) -> float:
        """Calcula score total de un conjunto de discos (build actual del PJ)."""
        base_scores = {d.id: _disc_base_score(d, agent, arch, self._ctx) for d in discs}
        set_counts: dict[int, int] = {}
        total = 0.0
        for disc in discs:
            total += base_scores[disc.id]
            set_counts[disc.set_id] = set_counts.get(disc.set_id, 0) + 1
        sb, _ = _set_bonus_for_counts(
            set_counts, arch, self._set_repo, agent.set_4p_id, agent.set_2p_id
        )
        return total + sb

    def _persist_builds(self, agente_id: int, builds: list[Build], score_actual: float) -> None:
        con_w = sqlite3.connect(str(self._db_path))
        con_w.row_factory = sqlite3.Row
        try:
            with con_w:
                repo = OptimizerRepo(con_w)
                for build in builds:
                    build_json = json.dumps({
                        "build_id":    build.build_id,
                        "set_bonus":   build.set_bonus_desc,
                        "score_total": build.score_total,
                        "discos": [
                            {
                                "slot":       d.slot,
                                "disc_id":    d.disc_id,
                                "set":        d.set_name,
                                "main":       d.main_stat,
                                "score":      d.score_disc,
                                "swap_origen": d.swap_origen,
                            }
                            for d in build.discos
                        ],
                    }, ensure_ascii=False)

                    swaps_json = json.dumps(build.swaps_requeridos, ensure_ascii=False)
                    repo.upsert_build(
                        agente_id=agente_id,
                        rank=build.rank,
                        score_estimado=build.score_total,
                        score_actual=score_actual,
                        delta=build.delta_vs_actual or 0.0,
                        build_json=build_json,
                        set_bonus=build.set_bonus_desc,
                        requiere_swaps=swaps_json,
                    )
        except Exception as exc:
            log.exception("Error persistiendo builds: %s", exc)
        finally:
            con_w.close()


# Función de conveniencia para llamadas one-shot (e.g., desde sync_equip)
def recompute_best_build(agente_id: int, db_path: Path = DB_PATH) -> OptimizerResult:
    opt = BuildOptimizer(db_path)
    try:
        return opt.best_builds(agente_id, persist=True)
    finally:
        opt.close()
