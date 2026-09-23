"""
Hito 2.2.2 — Normalizador de scores.
Cachea el score máximo teórico por arquetipo para que score_norm sea consistente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.repositories import Archetype


# Cuánto suma cada MEJORA de una línea positiva, en unidades de la línea base. Era 0,25: una línea
# +4 (cinco veces el stat de una +0) contaba el doble. Daniel juzga por el stat ("DC 175 → 189"),
# no por la presencia: 1,0 hace el puntaje proporcional a lo que el disco da (etapa 1, 2026-09-22).
ROLL_MULTIPLIER_POS = 1.0
NIVEL_BONUS_MAX = 0.5
PESO_MAIN = 1.0


@dataclass
class ScoringContext:
    roll_mult_pos: float = ROLL_MULTIPLIER_POS
    roll_mult_neg: float = 0.5
    peso_main: float = PESO_MAIN
    nivel_bonus_max: float = NIVEL_BONUS_MAX
    _maxima: dict[str, float] = field(default_factory=dict, init=False)

    def score_maximo_teorico(self, arch: "Archetype") -> float:
        if arch.code in self._maxima:
            return self._maxima[arch.code]

        pesos = list(arch.substats_positivos.values())
        top4 = sorted(pesos, reverse=True)[:4]
        # El mejor disco posible: las 4 mejores líneas, y las 5 mejoras de un Nivel 15 en la mejor
        # de ellas. Antes sumaba 5 mejoras en CADA línea (20 en total), un disco que no existe: con
        # mejoras proporcionales eso dejaba todo puntaje real muy por debajo de 1.
        score_subs = sum(top4) + 5 * self.roll_mult_pos * (top4[0] if top4 else 0.0)
        score_main = self.peso_main
        score_nivel = self.nivel_bonus_max
        total = score_subs + score_main + score_nivel
        total = max(total, 0.0001)
        self._maxima[arch.code] = total
        return total
