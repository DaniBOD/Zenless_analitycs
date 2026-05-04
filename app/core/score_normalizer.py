"""
Hito 2.2.2 — Normalizador de scores.
Cachea el score máximo teórico por arquetipo para que score_norm sea consistente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.repositories import Archetype


ROLL_MULTIPLIER_POS = 0.25
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
        score_subs = sum(p * (1 + 5 * self.roll_mult_pos) for p in top4)
        score_main = self.peso_main
        score_nivel = self.nivel_bonus_max
        total = score_subs + score_main + score_nivel
        total = max(total, 0.0001)
        self._maxima[arch.code] = total
        return total
