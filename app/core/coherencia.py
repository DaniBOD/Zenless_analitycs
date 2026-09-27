"""El asesor de coherencia de la ficha del PJ (SPEC 2026-09-27, parte 3) — sin DB ni Qt.

Daniel (2026-09-25): "si el usuario ajusta una substat de Ellen a DEF% como prioritario lo puede
hacer, pero que el sistema le diga 'Oye, esto no te beneficia en nada, te recomiendo Daño y
Probabilidad crítica'". Y que sus builds propias de Grace y Gatillo "tengan sentido".

Nunca bloquea: el motor usa lo que el usuario eligió igual. Dos severidades:

- `aviso` ⚠️ "no te beneficia": algo que el usuario eligió y que la guía o el set contradicen.
- `info` ℹ️: algo que conviene saber, sin tono de error (un set fuera de la guía, un fijo que el
  set agrega, un fijo que el motor está buscando).

Recibe todo armado (`GuiaPJ`, `EleccionPJ`, el estado del PJ); lo lee `app.db.repositories`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.db.repositories import CondicionSet, cumple_condiciones_4pc

AVISO, INFO = "aviso", "info"

#: El vocabulario de `agents` (el de los fijos) → cómo se lee en la ficha.
ETIQUETA_STAT = {
    "prob_critico": "Prob. Crítica", "ataque": "ATK", "pv": "PV", "defensa": "DEF",
    "impacto": "Impacto", "tasa_anomalia": "Tasa de Anomalía",
    "maestria_anomalia": "Maestría de Anomalía", "tasa_perforacion": "Tasa de Perforación",
    "rec_energia": "Recarga de Energía",
}


@dataclass(frozen=True)
class Aviso:
    severidad: str          # AVISO | INFO
    tipo: str
    texto: str


@dataclass
class GuiaPJ:
    """Lo que dice la guía del PJ (mig 43, primera variante). Vacía = PJ sin guía todavía."""
    niveles: dict[str, int] = field(default_factory=dict)            # substat → nivel (1 = arriba)
    principales: dict[int, set[str]] = field(default_factory=dict)   # slot 4-6 → principales
    sets_4pc: tuple[int, ...] = ()                                   # en el orden de la guía
    dos_por_4pc: dict[int, set[int]] = field(default_factory=dict)   # 4pc → 2pc que combina

    @property
    def vacia(self) -> bool:
        return not (self.niveles or self.principales or self.sets_4pc)


@dataclass
class EleccionPJ:
    """Lo que el USUARIO eligió en la ficha (sólo sus ajustes, no la mezcla)."""
    niveles: dict[str, int] = field(default_factory=dict)            # substat → 0..4
    principales: dict[int, tuple[str, ...]] = field(default_factory=dict)
    set_4p_id: int | None = None                                     # declarado (mig 43)
    set_2p_id: int | None = None


def _n(x: float) -> str:
    """Un número como lo lee la ficha: coma decimal ("48,2"), sin ceros de más."""
    return f"{x:g}".replace(".", ",")


def _y(nombres: Iterable[str]) -> str:
    nombres = list(nombres)
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def avisos(nombre: str, guia: GuiaPJ, eleccion: EleccionPJ, *, rol: str | None,
           elemento: str | None, set_4p_id: int | None, set_2p_id: int | None,
           condiciones: Iterable[CondicionSet], stats: dict[str, float],
           stats_fijos: dict[str, float], sets: dict[int, str]) -> list[Aviso]:
    """Los avisos de la ficha de un PJ. `set_4p_id`/`set_2p_id`/`stats_fijos` son los que USA el
    motor (la mezcla); `eleccion` es sólo lo que el usuario tocó."""
    out: list[Aviso] = []
    condiciones = list(condiciones)
    nombre_set = lambda s: sets.get(s, f"set {s}")  # noqa: E731

    if not guia.vacia:
        arriba = [s for s, n in sorted(guia.niveles.items(), key=lambda x: x[1]) if n <= 2]
        for sub, nivel in eleccion.niveles.items():
            if nivel > 0 and sub not in guia.niveles:
                out.append(Aviso(AVISO, "substat_no_te_beneficia",
                                 f"{sub} no le suma nada a {nombre}."
                                 + (f" La guía prioriza {_y(arriba)}." if arriba else "")))
            if nivel == 0 and guia.niveles.get(sub) == 1:
                out.append(Aviso(AVISO, "imprescindible_descartado",
                                 f"La guía pone {sub} como imprescindible para {nombre} y lo marcaste "
                                 "como que no sirve."))
        for slot, elegidos in eleccion.principales.items():
            de_la_guia = guia.principales.get(slot)
            if not de_la_guia:
                continue
            fuera = [p for p in elegidos if p not in de_la_guia]
            if fuera:
                out.append(Aviso(AVISO, "principal_fuera_de_guia",
                                 f"{_y(fuera)} en el slot {slot} no le sirve a {nombre} según su guía, "
                                 f"que pide {_y(sorted(de_la_guia))}."))
        if eleccion.set_4p_id is not None:
            s4, s2 = eleccion.set_4p_id, eleccion.set_2p_id
            if s4 not in guia.sets_4pc:
                out.append(Aviso(INFO, "set_fuera_de_guia",
                                 f"El 4pc de {nombre_set(s4)} está fuera de la guía de {nombre}: es un "
                                 "build tuyo."))
            elif s2 is not None and s2 not in guia.dos_por_4pc.get(s4, set()):
                out.append(Aviso(INFO, "set_fuera_de_guia",
                                 f"La guía no combina {nombre_set(s2)} con el 4pc de {nombre_set(s4)}: "
                                 "es un build tuyo."))

    # El 4pc que usa el motor: ¿se activa para este PJ? (Nana sólo en Soporte, …)
    for c in condiciones:
        if c.set_id != set_4p_id or c.tipo not in ("rol", "elemento"):
            continue
        suyo, pide = (rol, c.rol) if c.tipo == "rol" else (elemento, c.elemento)
        if suyo is None or suyo == pide:
            continue
        if c.alcance == "todo":
            out.append(Aviso(AVISO, "4pc_no_se_activa",
                             f"El 4pc de {nombre_set(c.set_id)} sólo se activa en {pide}, y {nombre} "
                             f"es {suyo}: no te beneficia."))
        else:
            out.append(Aviso(INFO, "4pc_a_medias",
                             f"Con el 4pc de {nombre_set(c.set_id)}, {nombre} pierde una parte "
                             f"(pide {pide}): {c.texto}"))

    # Condiciones de stat del 4pc que quedaron como fijos.
    if cumple_condiciones_4pc(condiciones, set_4p_id, rol, elemento):
        for c in condiciones:
            if c.set_id == set_4p_id and c.tipo == "stat" and c.stat in stats_fijos:
                out.append(Aviso(INFO, "condicion_como_fijo",
                                 f"El 4pc de {nombre_set(c.set_id)} pide {ETIQUETA_STAT.get(c.stat, c.stat)} "
                                 f"≥ {_n(c.umbral)}: queda como stat fijo."))

    # Fijos por debajo: el motor los busca (R23) y puede cambiar el 2pc para alcanzarlos (R24).
    for stat, objetivo in stats_fijos.items():
        actual = stats.get(stat)
        if actual is not None and actual < objetivo:
            out.append(Aviso(INFO, "fijo_se_busca",
                             f"{ETIQUETA_STAT.get(stat, stat)}: {_n(actual)} de {_n(objetivo)} (faltan "
                             f"{_n(round(objetivo - actual, 2))}). El motor lo busca."))
    return out
