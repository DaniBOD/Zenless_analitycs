"""R21 — stats fijos: un cambio no puede dejar a un PJ por debajo del stat que su kit necesita.

Caso 14 (SPEC, 2026-09-25): el motor sugirió #151 a Gatillo (+1,06 por Daño Crítico) y le bajaba
7,2 puntos de Prob. Crítica, que su habilidad adicional convierte en aturdimiento hasta 90 %.
Daniel: "algunos PJ requieren un stat fijo para aprovechar todo su potencial". Los objetivos, con su
cuenta y su fuente, están en `pj_stats_fijos` (mig 45).

La pantalla de atributos (S18) da el TOTAL de cada stat, no la base. Para las líneas que suman
directo (Prob. Crítica, Tasa de Perforación, Competencia de Anomalía) el cambio es exacto. Para las
que son un % de la base (ATK%, PV%, Impacto, Maestría de Anomalía, Recarga de Energía) se usa una
COTA SUPERIOR de la base, `(total − lo plano de los discos) / (1 + lo % de los discos)`: los bonos
que no se ven (arma, pasivas, sets) sólo pueden achicarla. Con esa cota la pérdida se sobreestima y
una ganancia porcentual no se cuenta: el motor puede frenar de más, pero nunca deja a un PJ por
debajo de su fijo creyendo que no.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from app.db.repositories import Agent, Disc

#: stat (vocabulario de `agents`) → líneas de disco que lo suman tal cual (en sus unidades).
DIRECTOS: dict[str, tuple[str, ...]] = {
    "prob_critico": ("Prob. Crítica",),
    "tasa_perforacion": ("Tasa de Perforación",),
    "maestria_anomalia": ("Maestría de Anomalía",),
}
#: stat → (líneas planas, líneas que son un % de la base).
DE_BASE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "ataque": (("ATK",), ("ATK%",)),
    "pv": (("HP",), ("HP%",)),
    "defensa": (("DEF",), ("DEF%",)),
    "impacto": ((), ("Impacto",)),
    "tasa_anomalia": ((), ("Tasa de Anomalía",)),
    "rec_energia": ((), ("Recarga de Energía",)),
}


def _lineas(disc: "Disc") -> Iterable[tuple[str, float]]:
    if disc.main_stat and disc.main_valor is not None:
        yield disc.main_stat, float(disc.main_valor)
    for nombre, valor, _unidad, _mejoras in disc.subs:
        if valor is not None:
            yield nombre, float(valor)


def _suma(discos: Iterable["Disc"], nombres: tuple[str, ...]) -> float:
    return sum(v for d in discos for n, v in _lineas(d) if n in nombres)


def delta_conservador(stat: str, total: float, antes: Iterable["Disc"], despues: Iterable["Disc"]) -> float:
    """Cuánto cambia el TOTAL del stat al pasar del build `antes` al `despues`, del lado prudente."""
    antes, despues = list(antes), list(despues)
    if stat in DIRECTOS:
        return _suma(despues, DIRECTOS[stat]) - _suma(antes, DIRECTOS[stat])
    planas, pct = DE_BASE[stat]
    f_a, p_a = _suma(antes, planas), _suma(antes, pct) / 100
    f_d, p_d = _suma(despues, planas), _suma(despues, pct) / 100
    base_max = max(total - f_a, 0.0) / (1 + p_a)
    d_pct = p_d - p_a
    return (f_d - f_a) + (base_max * d_pct if d_pct < 0 else 0.0)


def rompe_stat_fijo(agent: "Agent", antes: dict[int, "Disc"], despues: dict[int, "Disc"]) -> str | None:
    """El primer stat fijo del PJ que el cambio le BAJA dejándolo por debajo del objetivo, o None.
    Sin el total del stat (S18 no lo leyó) no se juzga: abstenerse no es aprobar ni frenar (B2)."""
    fijos = getattr(agent, "stats_fijos", None) or {}
    stats = getattr(agent, "stats", None) or {}
    for stat, objetivo in fijos.items():
        total = stats.get(stat)
        if total is None or (stat not in DIRECTOS and stat not in DE_BASE):
            continue
        d = delta_conservador(stat, total, antes.values(), despues.values())
        if d < 0 and total + d < objetivo:
            return stat
    return None
