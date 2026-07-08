"""Matcher de sets por badge/render del disco (Fase B del plan de predicción de sets).

En S2 cada tile muestra el render del disco (el arte del set). Este matcher reconoce el SET
—no la rareza— a partir de ese render, restringido a las 2 clases predichas por S13 (enfoque C:
el flujo da contexto, el contenido confirma). Es un wrapper fino sobre el descriptor robusto
de `avatar_descriptor.AvatarMatcher` (su docstring ya lo habilita para íconos de discos).

Piezas:
- `crop_package_disc`: aísla el disco central del package render 256×256 (descarta el badge
  "RARITY S/A/B" abajo-der., la marca de agua a la izq. y el marco). Los 3 tiers de un set
  quedan casi idénticos tras el crop → se agregan como multi-ref de la MISMA clase (nombre_en),
  volviendo el descriptor invariante a la rareza.
- `SetBadgeMatcher.identify`: restringe el match a las clases candidatas + abstención (conf/
  margen) del `AvatarMatcher`. No hay reject-set (no tenemos negativos de disco); la guarda es
  conf+margen y la restricción a 2 candidatos.

Riesgo aceptado (§8.1 del doc canónico): el render-package puede diferir del tile in-game
(resolución/compresión/composición). v1 construye refs en memoria desde los package badges; si
falla en vivo, se cosechan tiles reales de S2 como refs (patrón `.npz` de AvatarMatcher).
"""
from __future__ import annotations

import glob
import logging
import urllib.parse
from pathlib import Path

import cv2
import numpy as np

from app.core.asset_resolver import SET_BADGES_DIR
from app.core.avatar_descriptor import (
    AvatarMatcher,
    MatchResult,
    build_descriptor,
    descriptor_distance,
)

log = logging.getLogger(__name__)

# Caja normalizada (x0, y0, x1, y1) del disco dentro del package render 256×256. El disco cae
# arriba-izquierda; esta caja lo aísla dejando fuera el badge de rareza (abajo-der.) y la marca
# de agua (borde izq.). AJUSTADA en vivo 2026-07-08 (validada con 3 tiles etiquetados): recortar
# fino es CLAVE — el badge dorado "RARITY S" contaminaba el histograma de color y borraba la
# diferencia real del disco (azul Wuthering vs dorado Sky Ablaze).
_PKG_DISC_BOX = (0.06, 0.06, 0.55, 0.55)

# Pesos del descriptor para SETS (hist, ncc, regiones), sesgados al HISTOGRAMA: entre sets el
# COLOR del disco es el discriminador robusto (el NCC espacial no transfiere package↔tile).
# Validado 2026-07-08: 3/3 sobre tiles reales (Wuthering azul vs Sky Ablaze dorado).
_SET_WEIGHTS = (0.75, 0.15, 0.10)


def crop_package_disc(bgr: np.ndarray) -> np.ndarray:
    """Recorta el disco central de un package render (descarta rareza/marca de agua/marco)."""
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return bgr
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = _PKG_DISC_BOX
    crop = bgr[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    return crop if crop.size > 0 else bgr


def en_from_badge_filename(stem: str) -> str:
    """'Drive_Disc_Dawn%27s_Bloom_S' → \"Dawn's Bloom\" (quita prefijo/tier, url-decode)."""
    s = stem
    if s.startswith("Drive_Disc_"):
        s = s[len("Drive_Disc_"):]
    if len(s) >= 2 and s[-2] == "_" and s[-1] in ("S", "A", "B"):
        s = s[:-2]
    s = s.replace("_", " ")
    return urllib.parse.unquote(s)


class SetBadgeMatcher:
    """Reconoce el set del disco de un tile, restringido a las clases candidatas de S13."""

    def __init__(self, avatar_matcher: AvatarMatcher):
        self._m = avatar_matcher

    @classmethod
    def from_package_badges(
        cls, only_en: set[str] | None = None,
        min_conf: float | None = None, min_margin: float | None = None,
        weights: tuple[float, float, float] | None = None,
    ) -> "SetBadgeMatcher":
        """Construye el matcher en memoria desde los package badges (S/A/B por set → multi-ref).

        `only_en`: restringe a un subconjunto de sets (por defecto, todos los presentes en
        disco). Kwargs de abstención se pasan al `AvatarMatcher`; los pesos por defecto son
        `_SET_WEIGHTS` (sesgo histograma/color)."""
        kw: dict = {"weights": weights if weights is not None else _SET_WEIGHTS}
        if min_conf is not None:
            kw["min_conf"] = min_conf
        if min_margin is not None:
            kw["min_margin"] = min_margin
        m = AvatarMatcher(**kw)
        n_refs = 0
        for p in sorted(glob.glob(str(SET_BADGES_DIR / "*.webp"))):
            en = en_from_badge_filename(Path(p).stem)
            if only_en is not None and en not in only_en:
                continue
            img = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                log.warning("SetBadgeMatcher: no se pudo leer %s", p)
                continue
            if m.add_reference(en, crop_package_disc(img), max_per_name=8):
                n_refs += 1
        log.info("SetBadgeMatcher: %d refs de %d sets", n_refs, len(m.names))
        return cls(m)

    @property
    def names(self) -> list[str]:
        return self._m.names

    def identify(self, bgr_or_desc, candidate_en: list[str]) -> MatchResult:
        """Reconoce el set del disco entre `candidate_en` (los 2 predichos por S13).

        Se abstiene (name=None) si no hay candidatos con refs, si la confianza es baja, o si el
        margen entre los 2 candidatos es chico (RNF-02: preferir incierto a set equivocado)."""
        q = bgr_or_desc if not isinstance(bgr_or_desc, np.ndarray) else build_descriptor(bgr_or_desc)
        if q is None or not candidate_en:
            return MatchResult(None, 0.0, 0.0, False, [])
        scored: list[tuple[str, float]] = []
        for en in candidate_en:
            refs = self._m._refs.get(en)
            if not refs:
                continue
            # SIEMPRE por color (gray_only=False): el disco tiene mucho metálico gris y el
            # descriptor lo tomaría como "avatar desaturado" → ruta luminancia que IGNORA el
            # color, que es justo el discriminador entre sets. (Bug encontrado en QA 2026-07-08.)
            dist = min(descriptor_distance(q, r, self._m.weights, gray_only=False) for r in refs)
            scored.append((en, dist))
        if not scored:
            return MatchResult(None, 0.0, 0.0, False, [])
        scored.sort(key=lambda t: t[1])
        best_en, d1 = scored[0]
        d2 = scored[1][1] if len(scored) > 1 else 1.0
        conf = max(0.0, 1.0 - d1)
        margin = d2 - d1
        name: str | None = best_en
        if conf < self._m.min_conf:
            name = None
        elif len(scored) > 1 and margin < self._m.min_margin:
            name = None   # dos candidatos empatados → no adivinar
        return MatchResult(name, round(conf, 3), round(margin, 3), False, scored[:5])
