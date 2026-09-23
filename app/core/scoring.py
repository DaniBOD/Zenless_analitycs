"""
Hito 2.2.1 — Scoring engine puro (RF-04 §7.2.3 + RF-06 §5.1).
Función pura: (disco, agente) → ScoreBreakdown. Determinista.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean
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
    #: False = el principal no le sirve a este arquetipo (R9): el PJ NO es candidato para el disco,
    #: por buenos que sean los secundarios. El puntaje se calcula igual, para poder mostrarlo.
    principal_valido: bool = True


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


# La fórmula de UNA línea. La usan `score_disco` y `potencial`: si cada uno tuviera la suya, el
# valor esperado dejaría de ser el promedio de los puntajes que el motor realmente da (B1).
def _aporte_pos(peso: float, mejoras: int, ctx: "ScoringContext") -> float:
    return peso * (1.0 + mejoras * ctx.roll_mult_pos)


def _aporte_neg(peso: float, mejoras: int, ctx: "ScoringContext") -> float:
    return -abs(peso) * (1.0 + mejoras * ctx.roll_mult_neg)


#: Stat de un rango (vocabulario de `agents` y `agent_thresholds`) → las líneas de disco que lo mueven.
RANGO_A_LINEAS: dict[str, tuple[str, ...]] = {
    "ataque": ("ATK%", "ATK"),
    "pv": ("HP%", "HP"),
    "defensa": ("DEF%", "DEF"),
    "prob_critico": ("Prob. Crítica",),
    "dano_critico": ("Daño Crítico",),
    "maestria_anomalia": ("Maestría de Anomalía",),
}


def factor_rango(actual: float, techo: float | None) -> float:
    """Cuánto vale sumar a un stat según dónde está respecto de su techo.

    R16 (caso 8): pasado el tope "rinde menos pero sigue sumando" → `techo / actual`, que baja
    cuanto más se pasa y nunca llega a 0. Dentro del rango o por debajo, 1: los bordes son blandos
    (caso 1: 58 % contra un piso de 60 "es similar"). La curva es TENTATIVA: ningún caso fija
    todavía cuánto rinde menos, sólo que rinde menos.
    """
    if techo is None or actual <= techo:
        return 1.0
    return techo / actual


def ajustar_por_estado(pos: dict[str, float], agent: "Agent") -> dict[str, float]:
    """Los pesos positivos corregidos por DÓNDE ESTÁ el PJ: balance del crítico y rangos.

    Balance (caso 3, R4): el multiplicador medio del crítico es 1 + CR·DC; una mejora de CR vale
    `2,4 % · DC` y una de DC `4,8 % · CR`. Se reparte el MISMO peso total de los dos según esa
    proporción: con DC de sobra la CR pesa más, y con CR casi al 100 % pesa el DC. Arriba del 100 %
    la CR ya no suma nada. Sin CR y DC del PJ, no se toca (y el repositorio lo avisa).
    """
    from app.core.stats_vocab import VALOR_POR_MEJORA

    stats = getattr(agent, "stats", None) or {}
    rangos = getattr(agent, "rangos", None) or {}
    out = dict(pos)
    cr, dc = stats.get("prob_critico"), stats.get("dano_critico")
    if cr and dc and out.get("Prob. Crítica", 0) > 0 and out.get("Daño Crítico", 0) > 0:
        medio = (out["Prob. Crítica"] + out["Daño Crítico"]) / 2
        m_cr = 0.0 if cr >= 100 else VALOR_POR_MEJORA["Prob. Crítica"] * dc
        m_dc = VALOR_POR_MEJORA["Daño Crítico"] * cr
        out["Prob. Crítica"] = medio * 2 * m_cr / (m_cr + m_dc)
        out["Daño Crítico"] = medio * 2 * m_dc / (m_cr + m_dc)
    for stat, (_piso, techo) in rangos.items():
        actual = stats.get(stat)
        if actual is None:
            continue
        f = factor_rango(actual, techo)
        for linea in RANGO_A_LINEAS.get(stat, ()):
            if out.get(linea, 0) > 0:
                out[linea] *= f
    return out


def _pesos(agent: "Agent", archetype: "Archetype") -> tuple[dict[str, float], dict[str, float]]:
    """Los pesos de TODO el motor: los del PJ (o los de su arquetipo), corregidos por el estado del
    PJ, y los perjudiciales. La usan `score_disco`, `potencial` y los bonos de set del recomendador:
    una sola autoridad (B1)."""
    pos = agent.substat_preferences if agent.substat_preferences else archetype.substats_positivos
    return ajustar_por_estado(pos, agent), archetype.substats_perjudiciales


def aporte_linea(stat: str, mejoras: int, pesos_pos: dict[str, float],
                 pesos_neg: dict[str, float], ctx: "ScoringContext") -> float:
    """Lo que suma UNA línea al puntaje, igual que dentro de `score_disco`."""
    total = 0.0
    if stat in pesos_pos:
        total += _aporte_pos(pesos_pos[stat], mejoras, ctx)
    if stat in pesos_neg:
        total += _aporte_neg(pesos_neg[stat], mejoras, ctx)
    return total


def principal_valido(disc: "Disc", archetype: "Archetype") -> bool:
    """¿El principal de este disco le sirve a este arquetipo? Sólo pregunta en los slots 4-6.

    Regla de Daniel (caso 6, R9): un principal equivocado mata al disco para ese rol, con
    secundarios perfectos y todo. El scoring viejo le daba al principal el peso de UNA línea, así
    que un PV % en slot 4 con cuatro buenas líneas empataba EXACTO (0,448) con un Daño Crítico
    de tres. Es la única autoridad sobre esta pregunta: la usan el recomendador y el optimizador,
    que antes la contestaba por su cuenta con un `if` propio (B1).

    Una lista vacía de principales permitidos no restringe nada, igual que antes en el optimizador.
    """
    if disc.slot < 4 or not disc.main_stat:
        return True
    permitidos = getattr(archetype, f"mains_{disc.slot}", None) or []
    return not permitidos or disc.main_stat in permitidos


#: Niveles en los que un disco S recibe una mejora. MEDIDO sobre el inventario (2026-09-22): los
#: Nivel 15 tienen 4 o 5 mejoras (283 y 74 discos), los Nivel 6 una y los Nivel 12 tres — o sea
#: mejoras en +3/+6/+9/+12/+15, y la primera agrega la 4ª línea si el disco arrancó con 3.
NIVELES_DE_MEJORA: tuple[int, ...] = (3, 6, 9, 12, 15)


def mejoras_pendientes(nivel: int) -> int:
    return sum(1 for n in NIVELES_DE_MEJORA if n > nivel)


@dataclass
class Potencial:
    """Lo que un disco sin terminar puede llegar a ser para UN PJ, en promedio."""
    score_raw: float                    # esperado en Nivel 15
    score_norm: float
    lineas_muertas: list[str]           # líneas YA conocidas que a este PJ no le sirven (peso ≤ 0)
    cuarta_linea_supuesta: bool         # la 4ª se promedió con probabilidad uniforme (tentativo)
    #: Ya se GASTÓ una mejora en una línea muerta: la subió, o la creó (la 4ª de un disco que
    #: arrancó con 3). Caso 9 de Daniel: una muerta se tolera "siempre y cuando las mejoras no
    #: apliquen a él"; cuando aplican, se frena (caso 7).
    mejora_en_linea_muerta: bool = False


def potencial(
    disc: "Disc", agent: "Agent", archetype: "Archetype", ctx: "ScoringContext",
    disc_set_archetypes: list | None = None,
) -> Potencial:
    """El puntaje ESPERADO del disco en Nivel 15, y sus líneas muertas.

    Exacto por linealidad: cada mejora pendiente sube una de las 4 líneas con la misma
    probabilidad, y el puntaje es lineal en las mejoras, así que el promedio de los 4ⁿ finales
    posibles es el puntaje de hoy más `n ×` el promedio de lo que suma una mejora en cada línea.
    Un test lo verifica contra la enumeración completa.

    La 4ª línea de un disco que arrancó con 3 sale entre los secundarios que no están ni son el
    principal, con probabilidad UNIFORME. No hay una fuente autorizada con la probabilidad real
    (RNF-02): queda marcado en `cuarta_linea_supuesta`.
    """
    from app.core.stats_vocab import CANONICAL_SUBSTATS

    base = score_disco(disc, agent, archetype, ctx, disc_set_archetypes=disc_set_archetypes)
    pos, neg = _pesos(agent, archetype)
    lineas = [(stat, mejoras or 0) for stat, _v, _u, mejoras in disc.subs]
    pendientes = mejoras_pendientes(disc.nivel or 0)

    raw = base.score_raw - base.nivel_bonus + min(ctx.nivel_bonus_max, 15 / 30.0)
    por_mejora = [aporte_linea(s, 1, pos, neg, ctx) - aporte_linea(s, 0, pos, neg, ctx)
                  for s, _ in lineas]
    supuesta = False
    if len(lineas) == 3 and pendientes > 0:
        presentes = {s for s, _ in lineas} | {disc.main_stat}
        posibles = sorted(s for s in CANONICAL_SUBSTATS if s not in presentes)
        raw += fmean(aporte_linea(s, 0, pos, neg, ctx) for s in posibles)
        por_mejora.append(fmean(aporte_linea(s, 1, pos, neg, ctx) - aporte_linea(s, 0, pos, neg, ctx)
                                for s in posibles))
        pendientes -= 1                 # la primera mejora agrega la línea, no la sube
        supuesta = True
    if por_mejora:
        raw += pendientes * fmean(por_mejora)

    muertas = [s for s, _ in lineas if aporte_linea(s, 0, pos, neg, ctx) <= 0]
    # ¿Arrancó con 3 líneas? Entonces una de las mejoras ya hechas CREÓ la 4ª, y se nota en la
    # cuenta: tiene una mejora menos repartida que las hechas. PREMISA (no medida): la línea
    # agregada es la ÚLTIMA en pantalla, que es el orden en que la lee el parser.
    hechas = len(NIVELES_DE_MEJORA) - mejoras_pendientes(disc.nivel or 0)
    agregada = (lineas[3][0] if len(lineas) == 4 and hechas >= 1
                and sum(m for _, m in lineas) == hechas - 1 else None)
    gastada = any(m > 0 for s, m in lineas if s in muertas) or agregada in muertas

    return Potencial(
        score_raw=raw,
        score_norm=max(0.0, min(1.0, raw / ctx.score_maximo_teorico(archetype))),
        lineas_muertas=muertas,
        cuarta_linea_supuesta=supuesta,
        mejora_en_linea_muerta=gastada,
    )


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
    pesos_pos, pesos_neg = _pesos(agent, archetype)

    subs_pos: list[SubstatContrib] = []
    subs_neg: list[SubstatContrib] = []

    for (stat, val, unidad, rolls) in disc.subs:
        if stat in pesos_pos:
            peso = pesos_pos[stat]
            contrib = _aporte_pos(peso, rolls, ctx)
            subs_pos.append(SubstatContrib(stat, val, rolls, peso, contrib))
            score += contrib
        if stat in pesos_neg:
            peso = abs(pesos_neg[stat])
            contrib = _aporte_neg(peso, rolls, ctx)
            subs_neg.append(SubstatContrib(stat, val, rolls, peso, contrib))
            score += contrib

    # 4. Nivel bonus. Un nivel SIN LEER (None desde la Fase 3) no suma: premiar un nivel que no
    #    se vio sería puntuar una suposición, y castigarlo tampoco corresponde — vale 0, igual que
    #    un disco en Nivel 0 de verdad, y el disco se distingue igual por sus substats.
    nivel_bonus = 0.0 if disc.nivel is None else min(ctx.nivel_bonus_max, disc.nivel / 30.0)
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
        principal_valido=principal_valido(disc, archetype),
    )
