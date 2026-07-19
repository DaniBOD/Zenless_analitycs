"""
Fase 5R.L.8 (B1) — Superficie de badge reusable.

Una "superficie" es un lugar de la pantalla donde aparece el avatar de un PJ:
la barra superior de S8/S19 (`row`), el tile de la grilla S17 (`grid`), el panel
de detalle S17 (`detail`) — y mañana el inventario global S9 o el diálogo de
reemplazo S23. Todas repiten el mismo boilerplate: recortar el crop, matchearlo
contra una librería PROPIA (like-with-like es lo que da robustez, medido
2026-06-10), cosechar refs con label canónico y decidir presencia estructural.

`BadgeSurface` empaqueta ese boilerplate. Una pantalla nueva declara:

    surf = BadgeSurface(
        name="s9_tile",
        crop_fn=crop_s9_owner_badge,          # frame -> crop | None
        matcher=AvatarMatcher(),               # librería propia (nuevo encuadre)
        library_path=base / "avatar_s9_v1.npz",
        canonicalize=identifier.canonical_name,  # lección 2026-06-18: SIEMPRE canonizar
        persist_gate=badge_harvest_or_writable,  # gating readonly/cosecha
        presence_fn=clasificador_estructural,    # opcional: presencia ≠ naming
    )

y consume `surf.sample(frame)` (crop+match+presencia) + `surf.learn(crop, label)`,
alimentando un `OwnerVoteAccumulator` (app/core/owner_vote.py) con el resultado.

Dos señales SEPARADAS por diseño (la lección del falso-LIBRE, QA 2026-07-18):
  - `BadgeOutcome.name`    = NAMING (guard de confianza, puede abstenerse — RNF-02).
  - `BadgeOutcome.present` = PRESENCIA estructural (¿hay una cara?), decidida por
    `presence_fn` si existe (p.ej. cara-vs-texto del detalle) o por la localización
    del crop. Nunca por la confianza del naming.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from app.core.avatar_descriptor import AvatarMatcher, MatchResult

log = logging.getLogger(__name__)

# Guard de naming por defecto (= _S17_GUARD_DEFAULT histórico, sub-fase B 2026-06-12).
_GUARD_DEFAULT = 0.80


@dataclass
class BadgeOutcome:
    """Lo que la superficie vio en UN frame."""
    crop: np.ndarray | None      # el recorte del badge (None = no localizó)
    present: bool                # presencia ESTRUCTURAL (hay una cara, nombrable o no)
    name: str | None             # naming bajo guard (None = abstención, RNF-02)
    conf: float
    margin: float
    rejected: bool               # el crop cayó en el reject-set del matcher


class BadgeSurface:
    """crop + matcher + librería + cosecha canónica de UNA superficie de badge."""

    def __init__(self, name: str,
                 crop_fn: Callable[[np.ndarray], np.ndarray | None],
                 matcher: AvatarMatcher,
                 library_path: Path | None = None,
                 canonicalize: Callable[[str], str | None] | None = None,
                 persist_gate: Callable[[], bool] | None = None,
                 presence_fn: Callable[[np.ndarray], bool] | None = None,
                 guard: float = _GUARD_DEFAULT):
        self.name = name
        self.crop_fn = crop_fn
        self.matcher = matcher
        self.library_path = Path(library_path) if library_path else None
        self._canonicalize = canonicalize
        self._persist_gate = persist_gate
        self._presence_fn = presence_fn
        self.guard = guard

    # ---- persistencia -------------------------------------------------------
    def load(self) -> int:
        """Fusiona la librería persistida (si existe). Devuelve refs cargadas."""
        if self.library_path is None:
            return 0
        n = self.matcher.load_merge(self.library_path)
        if n:
            log.info("BadgeSurface[%s]: %d refs cargadas de %s", self.name, n, self.library_path)
        return n

    def save(self) -> None:
        if self.library_path is not None:
            self.matcher.save(self.library_path)

    # ---- cosecha ------------------------------------------------------------
    def learn(self, crop, label: str) -> bool:
        """Aprende `crop` como referencia de `label`, canonicalizando el label al
        roster ANTES de guardar (lección 2026-06-18: una librería con claves no
        canónicas la vacía `prune_to_roster` al arrancar). Respeta el gate de
        persistencia (readonly/modo cosecha). Devuelve True si aprendió."""
        if crop is None or not label:
            return False
        if self._persist_gate is not None and not self._persist_gate():
            return False
        canon = self._canonicalize(label) if self._canonicalize else label
        if canon is None:
            log.debug("BadgeSurface[%s]: '%s' fuera del roster → no se aprende", self.name, label)
            return False
        if not self.matcher.add_reference(canon, crop):
            return False
        self.save()
        return True

    # ---- lectura ------------------------------------------------------------
    def match(self, crop) -> MatchResult | None:
        """Match CRUDO del crop contra la librería (None si el crop es inválido)."""
        if crop is None:
            return None
        return self.matcher.match(crop)

    def is_present(self, crop) -> bool:
        """Presencia ESTRUCTURAL del crop (independiente del naming): la decide el
        clasificador de la superficie si lo hay; si no, la localización misma."""
        if crop is None:
            return False
        if self._presence_fn is not None:
            return bool(self._presence_fn(crop))
        return True

    def sample(self, frame) -> BadgeOutcome:
        """Un frame → (crop, presencia, naming). El naming aplica el guard de la
        superficie (name=None bajo umbral — abstención, RNF-02)."""
        crop = self.crop_fn(frame) if frame is not None else None
        if crop is None or getattr(crop, "size", 0) == 0:
            return BadgeOutcome(None, False, None, 0.0, 0.0, False)
        present = self.is_present(crop)
        r = self.matcher.match(crop)
        name = r.name if (r.name is not None and r.conf >= self.guard) else None
        return BadgeOutcome(crop, present, name, r.conf, r.margin, r.rejected)
