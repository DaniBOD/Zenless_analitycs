"""
Hito 2.4.7 / 2.5 — Monitor principal con polling adaptativo · RF-04 §5.
Loop en thread secundario: captura → clasifica → parsea → emite callback.
Integra UpgradeSyncer (S10 PRE/POST) y HotkeyManager (F8/F10).
Hook win32 para EVENT_SYSTEM_FOREGROUND (forzar scan al volver al juego).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.core.capturer import WindowBounds, capture_window, find_zzz_window
from app.core.detector import ScreenDetector, ScreenState, polling_cadence_ms
from app.core.parser_disc import DiscParsed, parse_modal_detalle
from app.core.ocr_backend import OcrBackend

log = logging.getLogger(__name__)

# Estado que requiere captura de disco
_DISC_DETAIL_STATES = {"S3", "S6", "S7"}
# Intervalo mínimo entre dos capturas del mismo estado (evitar parsear el mismo disco dos veces)
_SAME_STATE_COOLDOWN_S = 2.0


@dataclass
class MonitorEvent:
    kind: str            # "disc_detected" | "state_change" | "error"
    state: ScreenState
    disc: DiscParsed | None = None
    error: str | None = None


class Monitor:
    """
    Loop de monitoreo en thread separado.
    Al detectar un disco en pantalla llama a `on_disc` con el DiscParsed.
    Integra UpgradeSyncer para S10 y HotkeyManager para F8/F10.
    """

    def __init__(
        self,
        ocr: OcrBackend,
        detector: ScreenDetector,
        on_disc: Callable[[DiscParsed, ScreenState], None] | None = None,
        on_state_change: Callable[[ScreenState], None] | None = None,
        on_toggle_panel: Callable[[], None] | None = None,
        set_repo=None,
        upgrade_syncer=None,                                   # UpgradeSyncer opcional
        on_disc_rejected: Callable[[DiscParsed, ScreenState, str], None] | None = None,
    ):
        self._ocr = ocr
        self._detector = detector
        self._on_disc = on_disc
        self._on_state_change = on_state_change
        self._on_toggle_panel = on_toggle_panel
        self._set_repo = set_repo
        self._upgrade_syncer = upgrade_syncer
        # Callback opcional: se llama cuando un disco se parsea pero se descarta
        # (ej. confianza OCR baja). Útil para que la UI muestre por qué no salió el toast.
        self._on_disc_rejected = on_disc_rejected

        self._stop = threading.Event()
        self._paused = threading.Event()
        self._paused.set()          # no paused by default (set = can run)
        self._thread: threading.Thread | None = None
        self._last_state: ScreenState | None = None
        self._last_disc_state_time: float = 0.0
        self._window: WindowBounds | None = None

    # ---- Control ----------------------------------------------------------------

    def start(self) -> None:
        """Arranca el loop en thread secundario y registra hotkeys."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="zzz-monitor", daemon=True)
        self._thread.start()
        self._hook_foreground()
        self._register_hotkeys()
        log.info("Monitor arrancado.")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Monitor detenido.")

    def toggle_pause(self) -> bool:
        """Alterna pausa/reanuda. Devuelve True si ahora está pausado."""
        if self._paused.is_set():
            self._paused.clear()
            log.info("Monitor pausado (F10).")
            return True
        else:
            self._paused.set()
            log.info("Monitor reanudado (F10).")
            return False

    def force_scan(self) -> None:
        """Fuerza un scan inmediato (F8 o evento de foreground)."""
        self._stop.wait(0)          # no-op si no está parado
        if self._thread and self._thread.is_alive():
            # Señalamos con un evento interno; el loop lo consume en el siguiente tick
            self._force_event.set()

    # ---- Internals --------------------------------------------------------------

    def _run(self) -> None:
        self._force_event = threading.Event()
        while not self._stop.is_set():
            if not self._paused.is_set():
                time.sleep(0.5)
                continue
            frame = self._get_frame()
            if frame is None:
                continue
            state = self._detector.classify(frame)
            self._notify_state_change(state)
            self._dispatch_state(frame, state)
            self._wait_cadence(state)

    def _get_frame(self):
        """Captura el frame actual. Gestiona búsqueda y pérdida de ventana."""
        if self._window is None:
            self._window = find_zzz_window()
            if self._window is None:
                time.sleep(4.0)
                return None
        frame = capture_window(self._window)
        if frame is None:
            self._window = None
            time.sleep(2.0)
        return frame

    def _notify_state_change(self, state: ScreenState) -> None:
        if self._last_state is not None and state.code == self._last_state.code:
            return
        log.debug("Estado: %s (conf=%.2f)", state.code, state.confidence)
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception as exc:
                log.exception("Error en on_state_change: %s", exc)
        self._last_state = state

    def _dispatch_state(self, frame, state: ScreenState) -> None:
        """Enruta el frame al handler correspondiente según el estado."""
        self._handle_upgrade(frame, state)
        if state.code in _DISC_DETAIL_STATES:
            self._maybe_process_disc(frame, state)

    def _handle_upgrade(self, frame, state: ScreenState) -> None:
        if self._upgrade_syncer is None:
            return
        prev_code = self._last_state.code if self._last_state else ""
        if state.code == "S10":
            if prev_code != "S10":
                self._upgrade_syncer.on_s10_enter(frame)
            else:
                self._upgrade_syncer.on_s10_update(frame)
        elif prev_code == "S10":
            self._upgrade_syncer.on_s10_exit()

    def _maybe_process_disc(self, frame, state: ScreenState) -> None:
        now = time.monotonic()
        if now - self._last_disc_state_time >= _SAME_STATE_COOLDOWN_S:
            self._last_disc_state_time = now
            self._process_disc(frame, state)

    def _wait_cadence(self, state: ScreenState) -> None:
        cadence_ms = polling_cadence_ms(state)
        if self._force_event.wait(timeout=cadence_ms / 1000.0):
            self._force_event.clear()

    def _process_disc(self, frame, state: ScreenState) -> None:
        try:
            disc = parse_modal_detalle(frame, self._ocr, self._set_repo, state_code=state.code)
            if disc.confianza_global < 0.7:
                reason = f"confianza OCR {disc.confianza_global:.2f} < 0.70"
                log.info(
                    "Disco descartado: %s (set_raw=%r slot=%d main_raw=%r notas=%s)",
                    reason, disc.set_name_raw, disc.slot, disc.main_stat_raw, disc.notas,
                )
                if self._on_disc_rejected:
                    try:
                        self._on_disc_rejected(disc, state, reason)
                    except Exception:
                        log.exception("Error en on_disc_rejected")
                return
            log.info(
                "Disco detectado: set=%s slot=%d main=%s nivel=%d conf=%.2f",
                disc.set_name_canon or disc.set_name_raw,
                disc.slot,
                disc.main_stat_canon or disc.main_stat_raw,
                disc.nivel,
                disc.confianza_global,
            )
            if self._on_disc:
                self._on_disc(disc, state)
        except Exception as exc:
            log.exception("Error parseando disco en estado %s: %s", state.code, exc)

    def _register_hotkeys(self) -> None:
        from app.core.hotkeys import HotkeyManager
        hk = HotkeyManager()
        hk.on("f8",  self.force_scan)
        hk.on("f10", self.toggle_pause)
        if self._on_toggle_panel:
            hk.on("f9", self._on_toggle_panel)
        hk.start()
        self._hotkey_manager = hk

    def _hook_foreground(self) -> None:
        """
        Registra EVENT_SYSTEM_FOREGROUND via win32 para forzar scan
        cuando el usuario vuelve a la ventana del juego.
        """
        try:
            import win32con
            import win32event
            import win32api
            import win32gui

            def _cb(hWinEventHook, event, hwnd, *args):
                try:
                    title = win32gui.GetWindowText(hwnd)
                    if "ZenlessZoneZero" in title:
                        log.debug("ZZZ al frente — scan forzado.")
                        self.force_scan()
                except Exception:
                    pass

            self._win32_hook = win32api.SetWinEventHook(
                win32con.EVENT_SYSTEM_FOREGROUND,
                win32con.EVENT_SYSTEM_FOREGROUND,
                0, _cb, 0, 0,
                win32con.WINEVENT_OUTOFCONTEXT | win32con.WINEVENT_SKIPOWNPROCESS,
            )
        except Exception:
            log.debug("win32 foreground hook no disponible (no-Windows o pywin32 no instalado).")
