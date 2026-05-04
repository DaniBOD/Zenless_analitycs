"""
Hito 2.2.1 — Scoring engine puro (RF-04 §7.2.3 + RF-06 §5.1).
Función pura: (disco, agente) → ScoreBreakdown. Determinista.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.repositories import Agent, Archetype, Disc
    from app.core.score_normalizer import ScoringContext


@dataclass
class SubstatContrib:
    stat: str
    valor: float | None
    rolls: int
    peso: float
    contribucion: float


@dataclass
class ScoreBreakdown:
    score_raw: float
    score_norm: float
    set_match: str           # 'primario' | 'secundario' | 'no_match'
    set_match_score: float
    main_match: str          # 'exacta' | 'no_aplica' | 'no_match'
    main_match_score: float
    subs_positivos: list[SubstatContrib] = field(default_factory=list)
    subs_perjudiciales: list[SubstatContrib] = field(default_factory=list)
    nivel_bonus: float = 0.0


def _set_match_score(
    disc_set_id: int,
    agent_set4p: int | None,
    agent_set2p: int | None,
    peso_4pc_prim: float,
    peso_4pc_sec: float,
    peso_2pc_prim: float,
    peso_2pc_sec: float,
    disc_set_archetypes: list,
    agent_arch_id: int,
) -> tuple[str, float]:
    """Calcula el match del set del disco con el agente."""
    # Match exacto build del agente
    if agent_set4p and disc_set_id == agent_set4p:
        return "primario", peso_4pc_prim
    if agent_set2p and disc_set_id == agent_set2p:
        return "secundario", peso_2pc_prim

    # Fallback: match por arquetipo del set
    for dsa in disc_set_archetypes:
        if dsa.archetype_id == agent_arch_id:
            if dsa.prioridad == 1:
                return "primario", peso_4pc_sec
            if dsa.prioridad == 2:
                return "secundario", peso_2pc_sec

    return "no_match", 0.0


def score_disco(
    disc: "Disc",
    agent: "Agent",
    archetype: "Archetype",
    ctx: "ScoringContext",
    disc_set_archetypes: list | None = None,
    agent_set4p_id: int | None = None,
    agent_set2p_id: int | None = None,
) -> ScoreBreakdown:
    """
    Calcula el score del disco para el agente dado.
    Todos los nombres de stats en disc deben estar ya normalizados (Fase 2.0.4).
    """
    peso_4pc_prim = 1.5
    peso_4pc_sec = 0.7
    peso_2pc_prim = 0.4
    peso_2pc_sec = 0.2

    # 1. Set match
    set_label, set_score = _set_match_score(
        disc.set_id,
        agent_set4p_id,
        agent_set2p_id,
        peso_4pc_prim, peso_4pc_sec,
        peso_2pc_prim, peso_2pc_sec,
        disc_set_archetypes or [],
        archetype.id,
    )

    score = set_score

    # 2. Main stat (solo slots 4-6 tienen main variable)
    main_label = "no_aplica"
    main_score = 0.0
    if disc.slot >= 4 and disc.main_stat:
        slot_mains_key = f"mains_{disc.slot}"
        valid_mains = getattr(archetype, slot_mains_key, [])
        if disc.main_stat in valid_mains:
            main_label = "exacta"
            main_score = ctx.peso_main
        else:
            main_label = "no_match"
        score += main_score

    # 3. Substats — usar preferencias del agente o fallback al arquetipo
    pesos_pos = agent.substat_preferences if agent.substat_preferences else archetype.substats_positivos
    pesos_neg = archetype.substats_perjudiciales

    subs_pos: list[SubstatContrib] = []
    subs_neg: list[SubstatContrib] = []

    for (stat, val, unidad, rolls) in disc.subs:
        if stat in pesos_pos:
            peso = pesos_pos[stat]
            contrib = peso * (1.0 + rolls * ctx.roll_mult_pos)
            subs_pos.append(SubstatContrib(stat, val, rolls, peso, contrib))
            score += contrib
        if stat in pesos_neg:
            peso = abs(pesos_neg[stat])
            contrib = -peso * (1.0 + rolls * ctx.roll_mult_neg)
            subs_neg.append(SubstatContrib(stat, val, rolls, peso, contrib))
            score += contrib

    # 4. Nivel bonus
    nivel_bonus = min(ctx.nivel_bonus_max, disc.nivel / 30.0)
    score += nivel_bonus

    # 5. Normalizar
    score_max = ctx.score_maximo_teorico(archetype)
    score_norm = max(0.0, min(1.0, score / score_max))

    return ScoreBreakdown(
        score_raw=score,
        score_norm=score_norm,
        set_match=set_label,
        set_match_score=set_score,
        main_match=main_label,
        main_match_score=main_score,
        subs_positivos=subs_pos,
        subs_perjudiciales=subs_neg,
        nivel_bonus=nivel_bonus,
    )
