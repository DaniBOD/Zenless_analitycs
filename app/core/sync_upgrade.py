"""
Hito 2.5.2 — Sync RF-05: captura PRE/POST del modal de upgrade (S10).
Detecta cambio de nivel entre snapshots, calcula diff de rolls,
re-evalúa el disco y persiste con trigger="re_eval_upgrade".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from app.core.parser_disc import DiscParsed, parse_modal_detalle
from app.core.ocr_backend import OcrBackend
from app.core.capturer import capture_window, crop_named_roi, WindowBounds

log = logging.getLogger(__name__)

# Diferencia mínima de nivel para considerar que hubo un upgrade real
_MIN_LEVEL_DELTA = 3


@dataclass
class UpgradeSnapshot:
    nivel: int
    parsed: DiscParsed
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class UpgradeDiff:
    disc_id: int | None
    nivel_pre: int
    nivel_post: int
    rolls_diff: dict[str, int]      # {substat_canon: delta_rolls}
    recomendacion_post: str
    score_post: float


class UpgradeSyncer:
    """
    Gestiona el ciclo PRE → POST del modal de upgrade (S10).
    Uso:
        syncer.on_s10_enter(frame)    # al detectar S10
        syncer.on_s10_update(frame)   # en cada tick mientras S10 activo
        syncer.on_s10_exit()          # al salir de S10
    """

    def __init__(self, ocr: OcrBackend, disc_syncer=None):
        self._ocr = ocr
        self._disc_syncer = disc_syncer   # DiscSyncer de sync_equip para re-eval
        self._pre: UpgradeSnapshot | None = None
        self._last_nivel: int = -1

    def on_s10_enter(self, frame: np.ndarray) -> None:
        """Captura el estado PRE al entrar al modal de upgrade."""
        try:
            parsed = parse_modal_detalle(frame, self._ocr)
            self._pre = UpgradeSnapshot(nivel=parsed.nivel, parsed=parsed)
            self._last_nivel = parsed.nivel
            log.info("PRE upgrade capturado: nivel=%d  set=%s slot=%d",
                     parsed.nivel, parsed.set_name_raw, parsed.slot)
        except Exception as exc:
            log.exception("Error capturando PRE upgrade: %s", exc)

    def on_s10_update(self, frame: np.ndarray) -> UpgradeDiff | None:
        """
        Llamar en cada tick mientras S10 sigue activo.
        Si detecta cambio de nivel (nivel_post > nivel_pre + MIN_DELTA),
        parsea el POST, calcula diff de rolls y dispara re-eval.
        Devuelve UpgradeDiff si hubo upgrade, None si no cambió nada.
        """
        if self._pre is None:
            return None

        try:
            # OCR rápido solo del nivel para minimizar latencia
            roi_nivel = crop_named_roi(frame, "modal_upgrade", "nivel_actual")
            nivel_raw, conf = self._ocr.text(roi_nivel, psm=7)
        except Exception:
            return None

        import re
        m = re.search(r"(\d{1,2})", nivel_raw)
        if not m:
            return None
        nivel_now = int(m.group(1))

        # Ignorar si el nivel no subió lo suficiente o retrocedió (lectura errónea)
        if nivel_now <= self._last_nivel or (nivel_now - self._pre.nivel) < _MIN_LEVEL_DELTA:
            return None

        self._last_nivel = nivel_now
        log.debug("Nivel cambió de %d a %d — parseando POST.", self._pre.nivel, nivel_now)

        try:
            post_parsed = parse_modal_detalle(frame, self._ocr)
        except Exception as exc:
            log.exception("Error parseando POST upgrade: %s", exc)
            return None

        diff = self._compute_diff(self._pre.parsed, post_parsed)
        log.info(
            "Upgrade diff nivel %d→%d  rolls_diff=%s",
            self._pre.nivel, post_parsed.nivel, diff,
        )

        # Re-eval via DiscSyncer (trigger distinto para histórico)
        disc_id = None
        score_post = 0.0
        rec_post = "descartar"
        if self._disc_syncer is not None:
            result = self._disc_syncer.on_disc_detected(post_parsed)
            if result:
                disc_id = result.disc_id
                score_post = result.score_norm
                rec_post = result.recomendacion

        return UpgradeDiff(
            disc_id=disc_id,
            nivel_pre=self._pre.nivel,
            nivel_post=post_parsed.nivel,
            rolls_diff=diff,
            recomendacion_post=rec_post,
            score_post=score_post,
        )

    def on_s10_exit(self) -> None:
        """Limpia el estado PRE al salir del modal."""
        self._pre = None
        self._last_nivel = -1
        log.debug("Modal upgrade cerrado — estado PRE limpiado.")

    @staticmethod
    def _compute_diff(pre: DiscParsed, post: DiscParsed) -> dict[str, int]:
        """
        Calcula qué substats aumentaron de rolls entre PRE y POST.
        Devuelve {substat_canon: delta} solo para los que cambiaron.
        """
        pre_rolls  = {s.nombre_canon or s.nombre_raw: s.rolls for s in pre.subs}
        post_rolls = {s.nombre_canon or s.nombre_raw: s.rolls for s in post.subs}

        diff: dict[str, int] = {}
        for name, rolls_post in post_rolls.items():
            rolls_pre = pre_rolls.get(name, 0)
            if rolls_post > rolls_pre:
                diff[name] = rolls_post - rolls_pre
        return diff
