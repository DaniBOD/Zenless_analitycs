"""
Hito 2.2.3 — Recomendador RF-04 §7.3.
Itera sobre todos los agentes, calcula score, emite decisión 4-vías.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.scoring import ScoreBreakdown
    from app.core.score_normalizer import ScoringContext
    from app.db.repositories import Agent, AgentRepo, ArchetypeRepo, Disc, DiscSetRepo

from app.core.scoring import score_disco


RECOMENDACIONES = ("equipar", "mejorar", "reserva", "descartar")


@dataclass
class Recommendation:
    tipo: str                   # equipar | mejorar | reserva | descartar
    agente_id: int | None
    agente_nombre: str | None
    score_norm: float
    top_candidatos: list[tuple["Agent", "ScoreBreakdown"]] = field(default_factory=list)
    desglose_top: "ScoreBreakdown | None" = None


def recomendar(
    disc: "Disc",
    agent_repo: "AgentRepo",
    archetype_repo: "ArchetypeRepo",
    disc_set_repo: "DiscSetRepo",
    ctx: "ScoringContext",
) -> Recommendation:
    """
    Evalúa el disco contra los 46 agentes del roster.
    Devuelve la mejor recomendación.
    """
    disc_archetypes = disc_set_repo.get_archetypes_for_set(disc.set_id)

    candidatos: list[tuple[Agent, ScoreBreakdown]] = []
    for agent in agent_repo.get_all():
        archetype = archetype_repo.get_by_id(agent.arquetipo_primario_id)
        if archetype is None:
            continue
        sb = score_disco(
            disc=disc,
            agent=agent,
            archetype=archetype,
            ctx=ctx,
            disc_set_archetypes=disc_archetypes,
        )
        candidatos.append((agent, sb))

    candidatos.sort(key=lambda x: x[1].score_norm, reverse=True)

    if not candidatos:
        return Recommendation("descartar", None, None, 0.0)

    top_agent, top_sb = candidatos[0]

    if top_sb.score_norm >= top_agent.threshold_equip:
        return Recommendation(
            tipo="equipar",
            agente_id=top_agent.id,
            agente_nombre=top_agent.nombre,
            score_norm=top_sb.score_norm,
            top_candidatos=candidatos[:5],
            desglose_top=top_sb,
        )
    if top_sb.score_norm >= top_agent.threshold_upgrade:
        return Recommendation(
            tipo="mejorar",
            agente_id=top_agent.id,
            agente_nombre=top_agent.nombre,
            score_norm=top_sb.score_norm,
            top_candidatos=candidatos[:5],
            desglose_top=top_sb,
        )

    # Fallback por arquetipo (sin agente específico)
    top_arch_score = top_sb.score_norm
    stock_threshold = 0.50
    for arch in archetype_repo.get_all():
        if top_arch_score >= arch.threshold_stock:
            stock_threshold = arch.threshold_stock
            break

    if top_sb.score_norm >= stock_threshold:
        return Recommendation(
            tipo="reserva",
            agente_id=None,
            agente_nombre=None,
            score_norm=top_sb.score_norm,
            top_candidatos=candidatos[:5],
            desglose_top=top_sb,
        )

    return Recommendation(
        tipo="descartar",
        agente_id=None,
        agente_nombre=None,
        score_norm=top_sb.score_norm,
        top_candidatos=candidatos[:5],
        desglose_top=top_sb,
    )


def recommendation_to_json(rec: Recommendation) -> str:
    return json.dumps({
        "tipo": rec.tipo,
        "agente_id": rec.agente_id,
        "agente_nombre": rec.agente_nombre,
        "score_norm": round(rec.score_norm, 4),
        "top_candidatos": [
            {"nombre": a.nombre, "score": round(sb.score_norm, 4)}
            for a, sb in rec.top_candidatos
        ],
    }, ensure_ascii=False)
