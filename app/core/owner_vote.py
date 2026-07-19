"""
Fase 5R.L.8 — Acumulador de votos/presencia del DUEÑO de un ítem por badges.

Extraído de `monitor.py` (donde vivía como ~10 variables `_s17_*`) para que futuras
pantallas lo reúsen sin re-implementar la política: S17 (detalle de disco) hoy;
S9 (inventario global, dueño por badge) y S23 (reemplazo) mañana. Cada pantalla
instancia su acumulador, le reporta lo que sus superficies de badge ven frame a
frame (voto de nombre + presencia estructural) y le pregunta el veredicto.

Dos preguntas SEPARADAS (la lección del falso-LIBRE, QA 2026-07-18):
  - ¿QUIÉN es el dueño?  → `decide()` (naming: votos con guard + política primario/
    corrobora + anti-imán). Puede abstenerse (RNF-02).
  - ¿HAY un dueño?       → `is_libre()` (presencia ESTRUCTURAL: si alguna superficie
    fiable vio una CARA — nombrable o no — el ítem NO está libre).

Política de naming (5R.L.3, medida en QA):
  - Superficie PRIMARIA (grid): si votó, manda; la secundaria solo corrobora — no
    puede introducir otro PJ (el viejo imán no mete wrongs).
  - Secundaria SOLA (detail): propone dueño únicamente con score acumulado ≥
    `solo_min_score` y dominancia ≥ `solo_dominance` sobre el 2º; y NUNCA si propone
    al latch sin corroboración (guard anti-imán 5R.L.6b).
"""
from __future__ import annotations

import logging

from app.core.stats_vocab import _norm_key

log = logging.getLogger(__name__)

# 5R.L.3/L.4 — guard del detail-SOLO (calibrado en vivo 2026-06-18: 1 frame confiable
# basta; el detail ya vota con conf≥0.80 + margen + reject).
_DET_SOLO_MIN_SCORE = 0.80   # suma de conf del detail ganador (≈ 1 frame confiable)
_DET_SOLO_DOMINANCE = 1.50   # ganador ≥ 1.5× el 2º acumulado (sin empate cerrado)

# Ids de superficie por defecto (S17). Otras pantallas pueden usar los suyos.
GRID = "grid"
DETAIL = "detail"


def vote_winner(votes: dict[str, float]) -> tuple[str | None, float, float]:
    """(nombre, score_1º, score_2º) del dict de votos acumulados, o (None, 0, 0)."""
    if not votes:
        return None, 0.0, 0.0
    ordered = sorted(votes.items(), key=lambda kv: -kv[1])
    name, score = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    return name, score, second


def decide_owner(grid_votes: dict[str, float],
                 det_votes: dict[str, float],
                 latch: str | None = None,
                 solo_min_score: float = _DET_SOLO_MIN_SCORE,
                 solo_dominance: float = _DET_SOLO_DOMINANCE) -> tuple[str | None, str | None]:
    """Decide el dueño votado combinando primaria (grid) + secundaria (detail) con
    garantía RNF-02. Devuelve (owner|None, source):
      - grid-PRIMARIO: si el grid votó, manda el grid; el detail solo corrobora (no puede
        introducir otro PJ). source='grid+det' si coinciden, 'grid' si no.
      - detail-SOLO: si el grid no votó (NOLOC), el detail propone dueño SOLO con score
        acumulado ≥ solo_min_score y dominancia ≥ solo_dominance. source='det'.
      - si nada alcanza, (None, None) → incierto (abstención antes que error).
    `latch` (opcional) = agente cuya página se está viendo; activa el guard anti-imán.
    """
    g_name, _gs, _g2 = vote_winner(grid_votes)
    d_name, d_score, d2 = vote_winner(det_votes)
    if g_name:
        return g_name, ("grid+det" if d_name == g_name else "grid")
    if d_name and d_score >= solo_min_score and d_score >= solo_dominance * max(d2, 1e-9):
        # ANTI-IMÁN (5R.L.6b): un CANDIDATO cuyo detalle solo-propone al MISMO agente cuya
        # página estamos viendo (latch) es la firma del imán — refs del latch sobre-representadas
        # + correlación de fondo tiran del descriptor hacia el dueño de la página. El disco
        # realmente equipado lo asigna el ANCLA (no este path); un candidato que "casualmente"
        # matchea al latch sin que la grilla corrobore es sospechoso → abstenerse (RNF-02:
        # incierto > wrong). Se libera solo cuando el PJ correcto entra a la librería (cosecha).
        if latch is not None and _norm_key(d_name) == _norm_key(latch):
            return None, None
        return d_name, "det"
    return None, None


class OwnerVoteAccumulator:
    """Estado de votación/presencia del ítem ACTUAL (se resetea al cambiar de ítem).

    `presence_surface` es la superficie cuya presencia arbitra LIBRE (en S17 el
    detalle: localiza ~100% y su gate estructural no es leaky — el grid sí, L.7.2).
    """

    def __init__(self, primary: str = GRID, presence_surface: str = DETAIL,
                 solo_min_score: float = _DET_SOLO_MIN_SCORE,
                 solo_dominance: float = _DET_SOLO_DOMINANCE):
        self.primary = primary
        self.presence_surface = presence_surface
        self.solo_min_score = solo_min_score
        self.solo_dominance = solo_dominance
        self._votes: dict[str, dict[str, float]] = {}
        self._present: dict[str, int] = {}
        self._absent: dict[str, int] = {}
        self.passes: int = 0    # pasadas del loop rápido (warmup del dueño, 5R.L.6)

    # ---- acumulación por frame ----------------------------------------------
    def reset(self) -> None:
        """Ítem nuevo en pantalla → votación limpia."""
        self._votes.clear()
        self._present.clear()
        self._absent.clear()
        self.passes = 0

    def vote(self, surface: str, name: str, conf: float) -> None:
        v = self._votes.setdefault(surface, {})
        v[name] = v.get(name, 0.0) + float(conf)

    def mark_present(self, surface: str) -> None:
        self._present[surface] = self._present.get(surface, 0) + 1

    def mark_absent(self, surface: str) -> None:
        self._absent[surface] = self._absent.get(surface, 0) + 1

    # ---- lectura -------------------------------------------------------------
    def votes(self, surface: str) -> dict[str, float]:
        """Dict VIVO de votos de la superficie (mutable a propósito: compat)."""
        return self._votes.setdefault(surface, {})

    def set_votes(self, surface: str, votes: dict[str, float]) -> None:
        self._votes[surface] = dict(votes)

    def present(self, surface: str) -> int:
        return self._present.get(surface, 0)

    def absent(self, surface: str) -> int:
        return self._absent.get(surface, 0)

    def set_present(self, surface: str, n: int) -> None:
        self._present[surface] = int(n)

    def set_absent(self, surface: str, n: int) -> None:
        self._absent[surface] = int(n)

    @property
    def has_votes(self) -> bool:
        return any(self._votes.get(s) for s in self._votes)

    # ---- veredictos ----------------------------------------------------------
    def decide(self, latch: str | None = None) -> tuple[str | None, str | None]:
        """(owner|None, source) por la política primario/corrobora/solo (RNF-02)."""
        grid = self._votes.get(self.primary, {})
        det = {k: v for s, vs in self._votes.items() if s != self.primary
               for k, v in vs.items()}
        return decide_owner(grid, det, latch=latch,
                            solo_min_score=self.solo_min_score,
                            solo_dominance=self.solo_dominance)

    def is_libre(self) -> bool:
        """PRESENCIA GANA A LIBRE (5R.L.8): sin votos de ninguna superficie Y presencia
        CERO de la superficie fiable → LIBRE. Un solo frame con cara (nombrable o no)
        bloquea LIBRE hasta el reset. La presencia de las otras superficies (grid leaky
        en libres, L.7.2) no participa."""
        if self.has_votes:
            return False
        return self.present(self.presence_surface) == 0
