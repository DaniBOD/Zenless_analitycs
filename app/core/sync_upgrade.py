"""Sync RF-05 — tracking PRE→POST del modal de MEJORA de disco (S10). DISPLAY-ONLY.

Reescrito 2026-07-10: usa el parser espacial `parse_disc_s10` (el path viejo per-ROI
`parse_modal_detalle` nunca se calibró para este layout) y **no escribe a DB** — solo emite
diagnósticos. Al entrar al modal captura el disco (PRE); cuando el nivel SUBE tras "Mejorar",
loguea qué substat ganó roll (diff incremental).

Estado final autoritativo = la S17 posterior (QA 2026-07-10): al MAXEAR, el juego auto-cierra
el modal S10 en <1 ciclo de poll, así que el frame MAX (con el último roll asentado) suele NO
poder leerse dentro de S10. Por eso el RESUMEN se difiere: al salir de S10 se guarda un
"pendiente" (PRE + último visto en S10), y la pantalla de inventario del PJ (S17) que sigue —
que muestra el disco maxeado con todos los rolls asentados — lo CONFIRMA vía
`on_post_upgrade_disc`. Cae a un resumen sólo-S10 si el próximo modal abre sin confirmación.

Gate RNF-06: re-parsea (OCR full-frame) solo cuando la BARRA DE NIVEL cambió en pantalla.

Uso (desde el monitor):
    syncer.on_s10_enter(frame)          # al ENTRAR a S10 (prev != S10)
    syncer.on_s10_update(frame)         # cada ciclo mientras S10 sigue activo
    syncer.on_s10_exit()                # al SALIR de S10
    syncer.on_post_upgrade_disc(disc)   # por cada disco S17 emitido (confirma el estado final)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

from app.core.parser_disc import DiscParsed
from app.core.parser_disc_s10 import parse_disc_s10
from app.core.stats_vocab import _norm_key

log = logging.getLogger(__name__)

# ROI (x, y, w, h) normalizado de la barra de nivel chevron → firma anti-re-OCR.
_LEVEL_BAR_ROI = (0.49, 0.495, 0.35, 0.045)
# Diff medio (0-255) de la firma 32×32 por debajo del cual se considera la MISMA barra.
_LEVEL_SIG_MAX = 6.0
# Ventana (s) para que la S17 posterior confirme el estado final de un upgrade. Generosa
# porque al MAXEAR se interpone el popup "Materiales recuperados" (vuelto de sobrantes), que
# exige un click manual de Confirmar → el salto S10→S17 puede tardar bastante (QA: ~47 s).
# Seguro pese a lo largo: la confirmación exige match set+slot (_same_disc) y el pendiente se
# limpia al abrir el próximo modal (_flush_pending).
_PENDING_TTL_S = 120.0


@dataclass
class _Snap:
    nivel: int
    parsed: DiscParsed


def _fmt_val(valor: float | None, unidad: str | None) -> str:
    if valor is None:
        return "?"
    num = f"{valor:g}"
    return f"{num}%" if unidad == "%" else num


def _sig_diff(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 1e9
    return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())


def _target_from_notas(notas) -> int | None:
    """Extrae el nivel PROYECTADO de la nota 's10_target:N' (pill derecha de la barra)."""
    for n in notas or ():
        if n.startswith("s10_target:"):
            try:
                return int(n.split(":", 1)[1])
            except (ValueError, IndexError):
                return None
    return None


def _same_disc(a: DiscParsed, b: DiscParsed) -> bool:
    """Mismo disco = mismo slot + mismo set (tolerante a tildes/canon vs raw)."""
    if a.slot != b.slot or not a.slot:
        return False
    ka = _norm_key(a.set_name_canon or a.set_name_raw or "")
    kb = _norm_key(b.set_name_canon or b.set_name_raw or "")
    return bool(ka) and ka == kb


def _roll_diff(pre: DiscParsed, post: DiscParsed) -> dict[str, int]:
    """{substat: delta_rolls} solo para los que ganaron roll (o aparecieron) PRE→POST."""
    def rolls_by_name(d: DiscParsed) -> dict[str, int]:
        return {(s.nombre_canon or s.nombre_raw): s.rolls for s in d.subs if (s.nombre_canon or s.nombre_raw)}
    pre_r = rolls_by_name(pre)
    out: dict[str, int] = {}
    for name, rp in rolls_by_name(post).items():
        delta = rp - pre_r.get(name, 0)
        if delta > 0:
            out[name] = delta
    return out


class UpgradeSyncer:
    """Trackea el ciclo PRE→POST del modal de upgrade (S10). Display-only (sin DB)."""

    def __init__(self, ocr, on_diagnostic=None, set_repo=None):
        self._ocr = ocr
        self._on_diagnostic = on_diagnostic
        self._set_repo = set_repo
        self._pre: _Snap | None = None
        self._last: _Snap | None = None
        self._ref_sig: np.ndarray | None = None   # firma de la barra del último estado aceptado
        self._changed = False
        self._maxed = False
        self._target: int | None = None           # nivel proyectado (pill der) si hay materiales cargados
        self._target_announced: int | None = None  # último target ya logueado (anti-spam)
        self._refund_seen = False                  # popup "Materiales recuperados" ya anunciado (edge)
        # Pendiente de confirmación por la S17 posterior: (pre, last, target, ts_salida).
        self._pending: tuple[_Snap, _Snap, int | None, float] | None = None

    # -- ciclo de vida ------------------------------------------------------
    def on_s10_enter(self, frame) -> None:
        # Si quedó un upgrade previo sin confirmar en inventario, cerrarlo con lo visto en S10.
        self._flush_pending(confirmado=False)
        parsed = self._safe_parse(frame)
        if parsed is None:
            return
        self._pre = self._last = _Snap(parsed.nivel, parsed)
        self._ref_sig = self._level_sig(frame)
        self._changed = False
        self._maxed = "s10_max" in parsed.notas
        self._target = _target_from_notas(parsed.notas)
        self._target_announced = self._target
        setn = self._set_name(parsed)
        if self._maxed:
            estado = "MÁXIMO (15)"
        elif self._target is not None:
            # Materiales ya cargados al entrar → mostramos el antes→después de una.
            estado = f"nivel {parsed.nivel} → proyectado {self._target}"
        else:
            estado = f"nivel {parsed.nivel}"
        self._emit(
            f"[mejora] {setn} slot {parsed.slot} · {estado} · "
            f"main {parsed.main_stat_canon or parsed.main_stat_raw} "
            f"{_fmt_val(parsed.main_valor, parsed.main_unidad)} · {self._fmt_subs(parsed)}"
        )

    def on_s10_update(self, frame) -> None:
        if self._last is None or self._maxed:
            return   # ya maxeado → nada más que trackear en esta sesión de modal
        sig = self._level_sig(frame)
        if sig is None:
            return
        # Sin cambios respecto al último estado aceptado → idle, no re-parsear (RNF-06).
        if self._ref_sig is not None and _sig_diff(sig, self._ref_sig) <= _LEVEL_SIG_MAX:
            return
        # La barra cambió → parsear YA (sin esperar 2 lecturas): al maxear, el juego
        # auto-cierra el modal casi al instante y el estado MAX se ve <1s (QA 2026-07-10).
        parsed = self._safe_parse(frame)
        if parsed is None:
            return
        nivel = parsed.nivel
        maxed = "s10_max" in parsed.notas or nivel >= 15
        # Materiales cargados: la barra cambió y aparece el nivel PROYECTADO (pill der) aunque
        # el nivel actual aún no subió (falta clickear "Mejorar"). Registramos el destino y lo
        # anunciamos una vez → si luego el maxeo auto-cierra el modal sin dejarnos ver el
        # level-up, igual conocemos el target para el resumen/fallback (RF-05).
        target = _target_from_notas(parsed.notas)
        if target is not None and target > nivel:
            self._target = target
            self._ref_sig = sig   # aceptamos esta firma → no re-OCR hasta el próximo cambio
            if self._target_announced != target:
                self._target_announced = target
                self._emit(f"[mejora] materiales cargados · nivel {nivel} → proyectado {target}")
        # Guarda anti-ruido: un frame intermedio de animación suele NO leer nivel limpio
        # (nivel 0 / no detectado). Solo aceptamos lecturas SANAS: subió, o es el MAX. Si
        # no, dejamos ref_sig como está → se re-parsea el próximo ciclo hasta que asiente.
        if nivel <= self._last.nivel and not maxed:
            return
        self._ref_sig = sig
        diff = _roll_diff(self._last.parsed, parsed)
        pretty = ", ".join(f"+{d} en {n}" for n, d in diff.items()) or "sin cambio de roll"
        remate = " · MÁXIMO (15) alcanzado" if maxed else ""
        self._emit(f"[mejora] nivel {self._last.nivel}→{nivel}{remate} · {pretty}")
        self._last = _Snap(nivel, parsed)
        self._changed = True
        if maxed:
            self._maxed = True

    def on_s10_exit(self) -> None:
        # Diferir el resumen: la S17 posterior tiene el estado final asentado (incluye el
        # último roll que S10 pierde al auto-cerrar en MAX). Guardar pendiente para confirmar.
        # Adjuntamos el target (nivel proyectado) para el fallback si la S17 nunca llega.
        if self._pre is not None and self._last is not None:
            self._pending = (self._pre, self._last, self._target, time.monotonic())
        self._pre = self._last = None
        self._ref_sig = None
        self._changed = False
        self._maxed = False
        self._target = None
        self._target_announced = None
        self._refund_seen = False

    def on_material_refund(self, now: float | None = None) -> None:
        """El popup 'Materiales recuperados' (S20) confirma que la mejora se ejecutó y exige un
        click manual → puede demorar la S17. Mientras se muestra, REFRESCAMOS el timer del
        pendiente para que no expire por la espera, y lo anunciamos una vez (edge)."""
        if self._pending is None:
            return
        pre, last, target, _ts = self._pending
        self._pending = (pre, last, target, now if now is not None else time.monotonic())
        if not self._refund_seen:
            self._refund_seen = True
            self._emit("[mejora] vuelto de materiales confirmado · esperando inventario para el resumen")

    def _same_disc_canon(self, a: DiscParsed, b: DiscParsed) -> bool:
        """`_same_disc` pero resolviendo ambos sets al canónico (difuso, `DiscSetRepo.resolve_id`)
        antes de comparar. El OCR del nombre del set es inestable ('Firmamento llameante' /
        'Ilameante' / 'Illameante': I mayúscula vs l minúscula) y en S5 hay UNA sola pasada de
        confirmación → comparar crudo perdía el resumen. Sin `set_repo` cae al comportamiento
        de `_same_disc` (nombre crudo normalizado)."""
        if a.slot != b.slot or not a.slot:
            return False
        ka = _norm_key(self._set_name(a))
        kb = _norm_key(self._set_name(b))
        return bool(ka) and ka == kb

    def on_post_upgrade_disc(self, disc: DiscParsed, now: float | None = None) -> None:
        """Confirma el estado FINAL de un upgrade desde la pantalla que SIGUE al modal y muestra
        el disco con TODOS los rolls asentados (incl. el último que S10 pierde por el auto-cierre
        al maxear). Dos flujos, misma función:
          - inventario del PJ (S17) — mejora desde el equipamiento;
          - resultado de afinación (S5) — mejora desde la tienda de música, que NUNCA pasa por
            S17 (QA 2026-07-16). La S5 posterior también trae nivel real y rolls asentados.
        Llamar por cada disco emitido; solo actúa si hay un pendiente que matchea (set+slot)."""
        if self._pending is None:
            return
        now = now if now is not None else time.monotonic()
        pre, last, _target, ts = self._pending
        if now - ts > _PENDING_TTL_S:
            self._pending = None
            return
        if not self._same_disc_canon(pre.parsed, disc):
            return
        self._pending = None
        # POST autoritativo = el de mayor nivel (S17 asentado gana si S10 se quedó atrás).
        if disc.nivel >= last.nivel:
            post_parsed, post_nivel = disc, disc.nivel
        else:
            post_parsed, post_nivel = last.parsed, last.nivel
        if post_nivel <= pre.nivel:
            return   # no subió → nada que resumir
        self._emit_resumen(pre, post_parsed, post_nivel)

    def _flush_pending(self, confirmado: bool) -> None:
        """Cierra un pendiente sin confirmación de S17 (fallback): usa lo último visto en S10.

        Si S10 nunca llegó a ver el level-up (el maxeo auto-cerró el modal) pero conocíamos el
        nivel PROYECTADO (pill der del preview), resumimos con ese destino, marcado como
        proyectado/sin confirmar — honesto: no pudimos observar los rolls finales."""
        if self._pending is None:
            return
        pre, last, target, _ts = self._pending
        self._pending = None
        if last.nivel > pre.nivel:
            self._emit_resumen(pre, last.parsed, last.nivel, sufijo=" (sin confirmar en inventario)")
        elif target is not None and target > pre.nivel:
            self._emit_resumen(pre, last.parsed, target,
                               sufijo=" (proyectado, sin confirmar en inventario)")

    def _emit_resumen(self, pre: _Snap, post_parsed: DiscParsed, post_nivel: int,
                      sufijo: str = "") -> None:
        total = _roll_diff(pre.parsed, post_parsed)
        pretty = ", ".join(f"{n}: +{d}" for n, d in total.items()) or "sin cambios de roll"
        remate = " · MÁXIMO" if post_nivel >= 15 else ""
        self._emit(f"[mejora] resumen: nivel {pre.nivel}→{post_nivel}{remate} · {pretty}{sufijo}")

    def _safe_parse(self, frame) -> DiscParsed | None:
        try:
            return parse_disc_s10(frame, self._ocr)
        except Exception:
            log.exception("parse_disc_s10 falló")
            return None

    def _level_sig(self, frame) -> np.ndarray | None:
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            h, w = frame.shape[:2]
            x, y, rw, rh = _LEVEL_BAR_ROI
            sub = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
            if sub.size == 0:
                return None
            return cv2.cvtColor(
                cv2.resize(sub, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return None

    def _set_name(self, parsed: DiscParsed) -> str:
        raw = parsed.set_name_raw or "?"
        if self._set_repo is not None and raw:
            try:
                sid = self._set_repo.resolve_id(raw)
                if sid is not None:
                    e = next((e for e in self._set_repo.get_all() if e.id == sid), None)
                    if e is not None:
                        return e.nombre
            except Exception:
                pass
        return raw

    def _fmt_subs(self, parsed: DiscParsed) -> str:
        parts = []
        for s in parsed.subs:
            name = s.nombre_canon or s.nombre_raw
            roll = f" +{s.rolls}" if s.rolls else ""
            parts.append(f"{name}{roll} {_fmt_val(s.valor, s.unidad)}".strip())
        return " · ".join(parts)

    def _emit(self, msg: str) -> None:
        log.info("Upgrade S10: %s", msg)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.debug("on_diagnostic upgrade falló", exc_info=True)
