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

from app.core.scoring import Potencial, _pesos, potencial, principal_valido, score_disco, set_valido
from app.core.stats_fijos import rompe_stat_fijo
from app.core.stats_vocab import VALOR_POR_MEJORA, bono_2pc_como_substat
from app.db.repositories import PRIORIDADES


RECOMENDACIONES = ("equipar", "mejorar", "reserva", "guardar", "descartar")


@dataclass
class Recommendation:
    tipo: str                   # equipar | mejorar | reserva | guardar | descartar
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
    #: Deja por debajo de su cuenta (4 y 2) un set del build objetivo que estaba ACTIVO: R20
    #: "mejorar en base a los sets que ya tiene", no desarmar el build (`_elegir` lo descarta).
    rompe_objetivo: bool = False
    #: R21 (mig 45): el stat fijo que el cambio le baja al PJ dejándolo por debajo de su objetivo
    #: (`app.core.stats_fijos`); None si no rompe ninguno. `_elegir` lo descarta.
    rompe_stat_fijo: str | None = None
    notas: list[str] = field(default_factory=list)
    #: Sólo cuando el disco lo lleva OTRO PJ: de quién sale, qué disco libre lo reemplaza allá
    #: (None = el slot queda vacío) y cómo queda el origen con ese reemplazo (≥ 0: no pierde).
    origen_id: int | None = None
    reemplazo_id: int | None = None
    delta_origen: float | None = None


@dataclass
class Salida:
    """Qué le pasa al PJ que LLEVA un disco si se lo sacan, con el mejor reemplazo libre."""
    mejor_delta: float              # ≥ 0: queda igual o mejor ("A no pierde")
    reemplazo_id: int | None        # el disco libre que lo reemplazaría; None = slot vacío


def _pesos_pj(agent: "Agent", arch) -> dict[str, float]:
    """Los MISMOS pesos que usa `score_disco` — con el estado del PJ adentro. Tenía su propia copia
    y un bono de set se valuaba sin el balance del crítico que sí veía el disco (B1)."""
    return _pesos(agent, arch)[0]


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
    valor_nuevo: float | None = None,
) -> Cambio:
    """¿Cuánto mejora el build del PJ si en el slot del disco nuevo se pone el disco nuevo?

    `valor_nuevo` reemplaza el valor del disco nuevo: para uno sin terminar se pasa lo que se
    espera que valga en Nivel 15 (`potencial`), y la comparación es la misma que para uno terminado.
    """
    actual = build.get(nuevo.slot)
    v_nuevo = valor_disco(nuevo, agent, arch, ctx) if valor_nuevo is None else valor_nuevo
    v_actual = valor_disco(actual, agent, arch, ctx) if actual is not None else 0.0

    antes = Counter(d.set_id for d in build.values())
    despues = Counter(d.set_id for s, d in build.items() if s != nuevo.slot)
    despues[nuevo.set_id] += 1
    build_despues = {**build, nuevo.slot: nuevo}
    s_antes, notas = valor_sets(antes, agent, arch, bonos_2pc)
    s_despues, _ = valor_sets(despues, agent, arch, bonos_2pc)

    d_disco, d_sets = v_nuevo - v_actual, s_despues - s_antes
    objetivo = [(s, n) for s, n in ((getattr(agent, "set_4p_id", None), 4),
                                    (getattr(agent, "set_2p_id", None), 2)) if s is not None]
    return Cambio(
        agente_id=agent.id, agente_nombre=agent.nombre, slot=nuevo.slot,
        delta=d_disco + d_sets, delta_disco=d_disco, delta_sets=d_sets,
        rompe_4pc=any(n >= 4 and despues[s] < 4 for s, n in antes.items()),
        completa_4pc=any(n >= 4 and antes[s] < 4 for s, n in despues.items()),
        rompe_objetivo=any(antes[s] >= n > despues[s] for s, n in objetivo),
        rompe_stat_fijo=rompe_stat_fijo(agent, build, build_despues),
        notas=notas,
    )


def evaluar_salida(
    disc: "Disc", origen: "Agent", arch, build: dict[int, "Disc"], libres: list["Disc"],
    ctx: "ScoringContext", bonos_2pc: Callable[[int], tuple[str, float] | None],
) -> Salida:
    """Si a `origen` le sacan `disc`, ¿cómo queda con el mejor disco LIBRE para ese slot?

    Regla de Daniel para mover un disco de un PJ a otro: "sin perjudicar al PJ que lo tiene
    equipado". Se prueban todos los libres de ese slot que le sirvan (principal válido) y también
    dejar el slot vacío — que puede ser MEJOR que un disco que le resta. Vale el mejor.
    """
    slot = disc.slot
    sin_el = {s: d for s, d in build.items() if s != slot}
    antes = Counter(d.set_id for d in build.values())
    despues_vacio = Counter(d.set_id for d in sin_el.values())
    s_con, _ = valor_sets(antes, origen, arch, bonos_2pc)
    s_sin, _ = valor_sets(despues_vacio, origen, arch, bonos_2pc)
    # R20: dejar el slot vacío o reponerlo con otro disco NO puede desarmarle al origen un set de su
    # build objetivo que estaba activo (un 2pc que el motor no sabe valorar se perdería "gratis").
    objetivo = [(s, n) for s, n in ((getattr(origen, "set_4p_id", None), 4),
                                    (getattr(origen, "set_2p_id", None), 2)) if s is not None]
    # R21: tampoco puede dejarlo por debajo de un stat fijo que el disco le sostenía.
    vacio_rompe = (any(antes[s] >= n > despues_vacio[s] for s, n in objetivo)
                   or rompe_stat_fijo(origen, build, sin_el) is not None)
    mejor = (float("-inf") if vacio_rompe else -valor_disco(disc, origen, arch, ctx) + (s_sin - s_con),
             None)
    for libre in libres:
        if (libre.slot != slot or libre.id == disc.id or not principal_valido(libre, arch, origen)
                or not set_valido(libre, origen)):
            continue
        cambio = evaluar_cambio(origen, arch, build, libre, ctx, bonos_2pc)
        if cambio.rompe_objetivo or cambio.rompe_stat_fijo:
            continue
        if cambio.delta > mejor[0]:
            mejor = (cambio.delta, libre.id)
    # Redondeado: dos discos que valen lo mismo no pueden volverse "pérdida" por coma flotante.
    return Salida(mejor_delta=round(mejor[0], 6), reemplazo_id=mejor[1])


# ---------------------------------------------------------------------------
# Prioridad de buildeo (migración 42)
# ---------------------------------------------------------------------------
# Daniel (2026-09-24): con los stats reales, 32 de 108 movimientos iban a Piper, "que no uso casi
# nada", sacándole discos a PJs que sí usa. Eligió tres niveles y que la prioridad BLOQUEE:
#   - nunca se sugiere sacarle un disco a un PJ para dárselo a otro de prioridad MÁS BAJA;
#   - entre iguales sigue "el que lo tiene no pierde" (`evaluar_salida`);
#   - los discos van primero a los de prioridad alta ("recibe discos primero").
# Estas funciones son la única regla (B1): las usan el recomendador, el optimizador y el orden de
# las sugerencias del reporte.

def nivel_prioridad(prioridad: str | None) -> int:
    """alta 2 · normal 1 · baja 0, tomado del orden de `PRIORIDADES`. Desconocido = normal."""
    if prioridad not in PRIORIDADES:
        prioridad = "normal"
    return len(PRIORIDADES) - 1 - PRIORIDADES.index(prioridad)


def puede_recibir_de(destino: "Agent", origen: "Agent") -> bool:
    """¿Se le puede sugerir a `destino` un disco que hoy lleva `origen`? No si es de menor
    prioridad: un PJ relegado no le saca discos a uno que el usuario quiere mejorar."""
    return nivel_prioridad(destino.prioridad) >= nivel_prioridad(origen.prioridad)


#: La mejora mínima para sugerir un cambio, en las unidades del puntaje (1,0 = una mejora de un
#: secundario de peso máximo). Daniel (2026-09-25) aceptó "una exigencia mínima" tras ver #93 →
#: Ju Fufu con +0,00: #93 y el #385 que ella lleva tienen los mismos stats en otro orden, y la coma
#: flotante lo hacía "mejor". El reporte de ese día tenía un hueco entre 0,027 (#251 → Sporos, mover
#: por 3 % de una mejora) y 0,156: un décimo de mejora cae en el hueco. Parámetro, no dato del juego.
MEJORA_MINIMA = 0.1


def _elegir(opciones: list[tuple["Agent", "ScoreBreakdown", Cambio]]):
    """De los cambios que MEJORAN (delta ≥ `MEJORA_MINIMA`), el del PJ de mayor prioridad; entre
    iguales, el que más gana. `None` si ninguno mejora."""
    utiles = [o for o in opciones
              if o[2].delta >= MEJORA_MINIMA and not o[2].rompe_objetivo and not o[2].rompe_stat_fijo]
    if not utiles:
        return None
    return max(utiles, key=lambda o: (nivel_prioridad(o[0].prioridad), o[2].delta))


def recomendar(
    disc: "Disc",
    agent_repo: "AgentRepo",
    archetype_repo: "ArchetypeRepo",
    disc_set_repo: "DiscSetRepo",
    ctx: "ScoringContext",
    builds: "Callable[[int], dict[int, Disc]] | None" = None,
    libres: "list[Disc] | None" = None,
) -> Recommendation:
    """
    Evalúa el disco contra los agentes del roster y devuelve la mejor recomendación.

    Con `builds` (agente_id → {slot: disco equipado}) y un disco LIBRE en Nivel 15 la decisión es
    COMPARATIVA: EQUIPAR a quien más mejora el build, RESERVA si es bueno para su rol pero no le
    gana a nadie, DESCARTAR si no. Un disco que ya lleva OTRO PJ se sugiere mover sólo si el que
    lo tiene no pierde, contando los discos `libres` como reemplazo (paso 7); si no hay un
    movimiento así, sigue el umbral absoluto de antes.
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
    # R20: a quién se le puede SUGERIR (equipar, mover, mejorar) lo decide también el set. Guardar
    # o descartar se sigue juzgando por rol con todos los candidatos: un disco excelente de un set
    # que hoy no usa nadie se guarda para el futuro, no se tira por eso.
    aptos = [(a, sb) for a, sb in candidatos if set_valido(disc, a)]

    libre = not (disc.equipado and disc.agente_asignado)
    if builds is not None and disc.nivel == 15 and libre:
        return _recomendar_comparando(disc, candidatos, aptos, archetype_repo, disc_set_repo, ctx,
                                      builds)
    if builds is not None and libres is not None and disc.nivel == 15 and not libre:
        mover = _recomendar_mover_ajeno(disc, candidatos, aptos, agent_repo, archetype_repo,
                                        disc_set_repo, ctx, builds, libres)
        if mover is not None:
            return mover
    if disc.nivel is not None and disc.nivel < 15:
        return _recomendar_por_potencial(disc, candidatos, archetype_repo, ctx, disc_archetypes,
                                         disc_set_repo, builds, aptos)

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


def _recomendar_por_potencial(disc, candidatos, archetype_repo, ctx, disc_archetypes,
                              disc_set_repo=None, builds=None, aptos=None):
    """Un disco sin terminar: ¿vale la pena invertirle? (casos 6 y 7 de Daniel)

    Se evalúa para todos los roles y vale el mejor que sirva (R11). No sirve si tiene DOS líneas
    muertas (R13) o si ya se gastó una mejora en una muerta (caso 7; caso 9: "se puede permitir uno
    muerto siempre y cuando las mejoras no apliquen a él"). Daniel igual sube todo "para ver el
    valor final" (R14), pero la RECOMENDACIÓN es frenar. Un disco sin terminar no se equipa ni se
    reserva.

    Si sirve pero subido no le ganaría a nadie de hoy, GUARDAR (sin subir) cuando lo esperable
    alcanza el umbral de reserva de su rol: es lo que se haría con un disco terminado de la misma
    calidad (reserva), sin gastarle materiales. Daniel (2026-09-25), por el #356 (potencial 1,00,
    cero líneas muertas) que se descartaba: "me gusta el guardar sin subir".

    Si sirve, MEJORAR cuando lo esperable LE GANA a lo que un PJ ya lleva en ese slot (R12), con
    la misma comparación que un disco terminado (`evaluar_cambio`, set incluido). Hallado con #369
    (2026-09-23): contra el umbral fijo daba 0,468 < 0,50 y se descartaba, pero subido le gana al
    slot 5 de Soukaku y al de Lycaon. Sin `builds` no hay contra qué comparar y sigue el umbral.
    """
    evaluados = []
    for agent, sb in candidatos:
        arch = archetype_repo.get_by_id(agent.arquetipo_primario_id)
        evaluados.append((agent, sb, potencial(disc, agent, arch, ctx, disc_archetypes)))
    evaluados.sort(key=lambda t: t[2].score_norm, reverse=True)
    top = [(a, sb) for a, sb, _ in evaluados][:5]

    sanos = [t for t in evaluados
             if len(t[2].lineas_muertas) <= 1 and not t[2].mejora_en_linea_muerta]
    if sanos and builds is not None:
        bonos = _bonos_2pc_desde(disc_set_repo)
        opciones, pots = [], {}
        ids_aptos = {a.id for a, _ in aptos} if aptos is not None else None
        for agent, sb, pot in sanos:
            if ids_aptos is not None and agent.id not in ids_aptos:
                continue                    # R20: no se le sube un disco de un set que no usa
            arch = archetype_repo.get_by_id(agent.arquetipo_primario_id)
            # El valor esperado SIN el set: el set lo pone `evaluar_cambio`, que lo mide en el build.
            esperado = potencial(disc, agent, arch, ctx, []).score_raw
            opciones.append((agent, sb, evaluar_cambio(agent, arch, builds(agent.id), disc, ctx,
                                                       bonos, valor_nuevo=esperado)))
            pots[agent.id] = pot
        mejor = _elegir(opciones)   # a quién subirlo: mismo orden que un libre
        if mejor is not None:
            agent, sb, _ = mejor
            pot = pots[agent.id]
            return Recommendation("mejorar", agent.id, agent.nombre, pot.score_norm,
                                  top_candidatos=top, desglose_top=sb, potencial=pot)
    elif sanos:
        agent, sb, pot = sanos[0]
        if pot.score_norm >= agent.threshold_upgrade:
            return Recommendation("mejorar", agent.id, agent.nombre, pot.score_norm,
                                  top_candidatos=top, desglose_top=sb, potencial=pot)
    if sanos:
        agent, sb, pot = sanos[0]
        arch = archetype_repo.get_by_id(agent.arquetipo_primario_id)
        if arch is not None and pot.score_norm >= arch.threshold_stock:
            return Recommendation("guardar", None, None, pot.score_norm,
                                  top_candidatos=top, desglose_top=sb, potencial=pot)
    _, sb, pot = evaluados[0]
    return Recommendation("descartar", None, None, pot.score_norm,
                          top_candidatos=top, desglose_top=sb, potencial=pot)


def _recomendar_mover_ajeno(disc, candidatos, aptos, agent_repo, archetype_repo, disc_set_repo,
                            ctx, builds, libres):
    """Un disco que lleva A, ¿le sirve más a B? Sólo si A no pierde (con su mejor reemplazo libre),
    B gana y B no es de menor prioridad que A (mig 42). Entre los B posibles, el de mayor
    prioridad. `None` si no hay un movimiento así: el disco se queda donde está."""
    origen = next((a for a in agent_repo.get_all() if a.id == disc.agente_asignado), None)
    if origen is None or origen.protected_build:
        return None
    arch_origen = archetype_repo.get_by_id(origen.arquetipo_primario_id)
    if arch_origen is None:
        return None
    bonos = _bonos_2pc_desde(disc_set_repo)
    salida = evaluar_salida(disc, origen, arch_origen, builds(origen.id), libres, ctx, bonos)
    if salida.mejor_delta < 0:
        return None                         # "sin perjudicar al PJ que lo tiene equipado"

    opciones = []
    for agent, sb in aptos:
        if agent.id == origen.id or not puede_recibir_de(agent, origen):
            continue
        arch = archetype_repo.get_by_id(agent.arquetipo_primario_id)
        opciones.append((agent, sb, evaluar_cambio(agent, arch, builds(agent.id), disc, ctx, bonos)))
    mejor = _elegir(opciones)
    if mejor is None:
        return None
    agent, sb, cambio = mejor
    cambio.origen_id, cambio.reemplazo_id = origen.id, salida.reemplazo_id
    cambio.delta_origen = salida.mejor_delta
    return Recommendation("equipar", agent.id, agent.nombre, sb.score_norm,
                          top_candidatos=candidatos[:5], desglose_top=sb, movimiento=cambio)


def _recomendar_comparando(disc, candidatos, aptos, archetype_repo, disc_set_repo, ctx, builds):
    bonos = _bonos_2pc_desde(disc_set_repo)
    opciones = []
    for agent, sb in aptos:
        arch = archetype_repo.get_by_id(agent.arquetipo_primario_id)
        opciones.append((agent, sb, evaluar_cambio(agent, arch, builds(agent.id), disc, ctx, bonos)))
    mejor = _elegir(opciones)       # un libre va primero a los de prioridad alta
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
            "origen_id": rec.movimiento.origen_id,
            "reemplazo_id": rec.movimiento.reemplazo_id,
            "delta_origen": rec.movimiento.delta_origen,
        },
        "potencial": None if rec.potencial is None else {
            "score_norm": round(rec.potencial.score_norm, 4),
            "lineas_muertas": rec.potencial.lineas_muertas,
            "cuarta_linea_supuesta": rec.potencial.cuarta_linea_supuesta,
            "mejora_en_linea_muerta": rec.potencial.mejora_en_linea_muerta,
        },
    }, ensure_ascii=False)
