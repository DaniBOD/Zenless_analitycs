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

from collections import Counter
from typing import Callable

from app.core.scoring import Potencial, potencial, principal_valido, score_disco
from app.core.stats_vocab import VALOR_POR_MEJORA, bono_2pc_como_substat


RECOMENDACIONES = ("equipar", "mejorar", "reserva", "descartar")


@dataclass
class Recommendation:
    tipo: str                   # equipar | mejorar | reserva | descartar
    agente_id: int | None
    agente_nombre: str | None
    score_norm: float
    top_candidatos: list[tuple["Agent", "ScoreBreakdown"]] = field(default_factory=list)
    desglose_top: "ScoreBreakdown | None" = None
    #: Sólo en la decisión comparativa: a quién mejora el disco, y cuánto.
    movimiento: "Cambio | None" = None
    #: Sólo para un disco sin terminar: lo que puede llegar a ser para el PJ elegido.
    potencial: "Potencial | None" = None


# ---------------------------------------------------------------------------
# Decisión COMPARATIVA (etapa 1, paso 3 — 2026-09-22)
# ---------------------------------------------------------------------------
# Las 8 respuestas de Daniel fueron comparativas ("¿cuál le equipás?", "¿le gana al que tiene?"),
# y el recomendador decidía por un umbral absoluto sin mirar el slot del PJ. Acá el disco se mide
# contra el que el PJ YA lleva en ese slot, y el set se mide en el BUILD, no en el disco: un set
# sólo vale algo cuando junta 2 o 4 piezas.

#: Cuánto vale TENER el 4pc activo, como fracción del mejor disco posible para ese PJ. R5: "el 4pc
#: no se rompe salvo que sean secundarios excelentes, y sería muy puntual". Calibrado con el caso 4
#: (secundarios +3,5 mejores y Daniel NO rompe: hace falta > 0,42). Con UN solo caso esto es
#: tentativo: cada caso nuevo de 4pc lo ajusta.
VALOR_4PC_FRACCION = 0.5


@dataclass
class Cambio:
    """Qué pasa con el build de un PJ si en `slot` se pone el disco nuevo."""
    agente_id: int
    agente_nombre: str
    slot: int
    delta: float                    # > 0: el PJ mejora
    delta_disco: float              # sólo el disco contra el disco
    delta_sets: float               # lo que se gana o pierde en bonos de set
    rompe_4pc: bool = False
    completa_4pc: bool = False
    notas: list[str] = field(default_factory=list)


def _pesos_pj(agent: "Agent", arch) -> dict[str, float]:
    """Los mismos pesos que usa `score_disco`: los del PJ, o los de su arquetipo."""
    return agent.substat_preferences if agent.substat_preferences else arch.substats_positivos


def valor_disco(disc: "Disc", agent: "Agent", arch, ctx: "ScoringContext") -> float:
    """Lo que el disco aporta POR SÍ MISMO al PJ: líneas, principal y nivel. Sin el set, que es
    del build (si el set entrara acá también, se contaría dos veces)."""
    return score_disco(disc, agent, arch, ctx, disc_set_archetypes=[]).score_raw


def _mejor_disco_posible(pesos: dict[str, float]) -> float:
    positivos = sorted((p for p in pesos.values() if p > 0), reverse=True)[:4]
    return sum(positivos) + 5 * (positivos[0] if positivos else 0.0)


def valor_sets(
    conteo: Counter, agent: "Agent", arch, bonos_2pc: Callable[[int], tuple[str, float] | None],
) -> tuple[float, list[str]]:
    """Lo que valen los bonos de set de un build: cada 2pc como sus stats (R7), y el 4pc como una
    fracción del mejor disco posible (R5). Un 2pc que no es un secundario no suma y se ANOTA."""
    pesos = _pesos_pj(agent, arch)
    total, notas = 0.0, []
    for set_id, piezas in conteo.items():
        if set_id is None or piezas < 2:
            continue
        bono = bonos_2pc(set_id)
        if bono is None:
            notas.append(f"2pc del set {set_id} sin modelar (no es un secundario)")
        else:
            stat, valor = bono
            total += valor / VALOR_POR_MEJORA[stat] * max(pesos.get(stat, 0.0), 0.0)
        if piezas >= 4:
            total += VALOR_4PC_FRACCION * _mejor_disco_posible(pesos)
    return total, notas


def evaluar_cambio(
    agent: "Agent", arch, build: dict[int, "Disc"], nuevo: "Disc", ctx: "ScoringContext",
    bonos_2pc: Callable[[int], tuple[str, float] | None],
) -> Cambio:
    """¿Cuánto mejora el build del PJ si en el slot del disco nuevo se pone el disco nuevo?"""
    actual = build.get(nuevo.slot)
    v_nuevo = valor_disco(nuevo, agent, arch, ctx)
    v_actual = valor_disco(actual, agent, arch, ctx) if actual is not None else 0.0

    antes = Counter(d.set_id for d in build.values())
    despues = Counter(d.set_id for s, d in build.items() if s != nuevo.slot)
    despues[nuevo.set_id] += 1
    s_antes, notas = valor_sets(antes, agent, arch, bonos_2pc)
    s_despues, _ = valor_sets(despues, agent, arch, bonos_2pc)

    d_disco, d_sets = v_nuevo - v_actual, s_despues - s_antes
    return Cambio(
        agente_id=agent.id, agente_nombre=agent.nombre, slot=nuevo.slot,
        delta=d_disco + d_sets, delta_disco=d_disco, delta_sets=d_sets,
        rompe_4pc=any(n >= 4 and despues[s] < 4 for s, n in antes.items()),
        completa_4pc=any(n >= 4 and antes[s] < 4 for s, n in despues.items()),
        notas=notas,
    )


def recomendar(
    disc: "Disc",
    agent_repo: "AgentRepo",
    archetype_repo: "ArchetypeRepo",
    disc_set_repo: "DiscSetRepo",
    ctx: "ScoringContext",
    builds: "Callable[[int], dict[int, Disc]] | None" = None,
) -> Recommendation:
    """
    Evalúa el disco contra los agentes del roster y devuelve la mejor recomendación.

    Con `builds` (agente_id → {slot: disco equipado}) y un disco LIBRE en Nivel 15 la decisión es
    COMPARATIVA: EQUIPAR a quien más mejora el build, RESERVA si es bueno para su rol pero no le
    gana a nadie, DESCARTAR si no. Sin `builds`, o para un disco que otro PJ lleva puesto (mover
    uno ajeno es el paso 7: "sólo si el que lo tiene no pierde"), sigue el umbral absoluto de antes.
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
        if not sb.principal_valido:
            continue        # R9: para este rol el disco no sirve, por buenos que sean los subs
        candidatos.append((agent, sb))

    candidatos.sort(key=lambda x: x[1].score_norm, reverse=True)

    if not candidatos:
        return Recommendation("descartar", None, None, 0.0)

    libre = not (disc.equipado and disc.agente_asignado)
    if builds is not None and disc.nivel == 15 and libre:
        return _recomendar_comparando(disc, candidatos, archetype_repo, disc_set_repo, ctx, builds)
    if disc.nivel is not None and disc.nivel < 15:
        return _recomendar_por_potencial(disc, candidatos, archetype_repo, ctx, disc_archetypes)

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


def _bonos_2pc_desde(disc_set_repo) -> Callable[[int], tuple[str, float] | None]:
    get_bonus = getattr(disc_set_repo, "get_bonus", None)
    if get_bonus is None:
        return lambda set_id: None
    cache: dict[int, tuple[str, float] | None] = {}

    def bono(set_id: int) -> tuple[str, float] | None:
        if set_id not in cache:
            stat, valor, _ = get_bonus(set_id)
            cache[set_id] = bono_2pc_como_substat(stat, valor)
        return cache[set_id]
    return bono


def _recomendar_por_potencial(disc, candidatos, archetype_repo, ctx, disc_archetypes):
    """Un disco sin terminar: ¿vale la pena invertirle? (casos 6 y 7 de Daniel)

    Se evalúa para todos los roles y vale el mejor que sirva (R11). No sirve si tiene DOS líneas
    muertas (R13) o si ya se gastó una mejora en una muerta (caso 7; caso 9: "se puede permitir uno
    muerto siempre y cuando las mejoras no apliquen a él"). Daniel igual sube todo "para ver el
    valor final" (R14), pero la RECOMENDACIÓN es frenar. Si sirve, MEJORAR cuando lo esperable
    llega al umbral de mejora del PJ. Un disco sin terminar no se equipa ni se reserva.
    """
    evaluados = []
    for agent, sb in candidatos:
        arch = archetype_repo.get_by_id(agent.arquetipo_primario_id)
        evaluados.append((agent, sb, potencial(disc, agent, arch, ctx, disc_archetypes)))
    evaluados.sort(key=lambda t: t[2].score_norm, reverse=True)
    top = [(a, sb) for a, sb, _ in evaluados][:5]

    sanos = [t for t in evaluados
             if len(t[2].lineas_muertas) <= 1 and not t[2].mejora_en_linea_muerta]
    if sanos:
        agent, sb, pot = sanos[0]
        if pot.score_norm >= agent.threshold_upgrade:
            return Recommendation("mejorar", agent.id, agent.nombre, pot.score_norm,
                                  top_candidatos=top, desglose_top=sb, potencial=pot)
    _, sb, pot = evaluados[0]
    return Recommendation("descartar", None, None, pot.score_norm,
                          top_candidatos=top, desglose_top=sb, potencial=pot)


def _recomendar_comparando(disc, candidatos, archetype_repo, disc_set_repo, ctx, builds):
    bonos = _bonos_2pc_desde(disc_set_repo)
    mejor: tuple["Agent", "ScoreBreakdown", Cambio] | None = None
    for agent, sb in candidatos:
        arch = archetype_repo.get_by_id(agent.arquetipo_primario_id)
        cambio = evaluar_cambio(agent, arch, builds(agent.id), disc, ctx, bonos)
        if cambio.delta > 0 and (mejor is None or cambio.delta > mejor[2].delta):
            mejor = (agent, sb, cambio)
    if mejor is not None:
        agent, sb, cambio = mejor
        return Recommendation("equipar", agent.id, agent.nombre, sb.score_norm,
                              top_candidatos=candidatos[:5], desglose_top=sb, movimiento=cambio)

    # No le gana a nadie hoy. ¿Es bueno para su rol? Entonces se guarda para un PJ futuro (Daniel:
    # "un disco perfecto, pero no para la actualidad sino para el futuro").
    top_agent, top_sb = candidatos[0]
    arch = archetype_repo.get_by_id(top_agent.arquetipo_primario_id)
    tipo = "reserva" if top_sb.score_norm >= arch.threshold_stock else "descartar"
    return Recommendation(tipo, None, None, top_sb.score_norm,
                          top_candidatos=candidatos[:5], desglose_top=top_sb)


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
        "movimiento": None if rec.movimiento is None else {
            "agente_id": rec.movimiento.agente_id,
            "slot": rec.movimiento.slot,
            "delta": round(rec.movimiento.delta, 4),
            "delta_disco": round(rec.movimiento.delta_disco, 4),
            "delta_sets": round(rec.movimiento.delta_sets, 4),
            "rompe_4pc": rec.movimiento.rompe_4pc,
            "completa_4pc": rec.movimiento.completa_4pc,
            "notas": rec.movimiento.notas,
        },
        "potencial": None if rec.potencial is None else {
            "score_norm": round(rec.potencial.score_norm, 4),
            "lineas_muertas": rec.potencial.lineas_muertas,
            "cuarta_linea_supuesta": rec.potencial.cuarta_linea_supuesta,
            "mejora_en_linea_muerta": rec.potencial.mejora_en_linea_muerta,
        },
    }, ensure_ascii=False)
