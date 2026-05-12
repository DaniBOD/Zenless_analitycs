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
from app.core.detector import ScreenDetector, ScreenState, extract_s17_slot, extract_s9_slot, polling_cadence_ms
from app.core.parser_disc import DiscParsed, parse_modal_detalle
from app.core.ocr_backend import OcrBackend

log = logging.getLogger(__name__)

# Estado que requiere captura de disco
_DISC_DETAIL_STATES = {"S3", "S6", "S7"}


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
        on_diagnostic: Callable[[str], None] | None = None,
    ):
        self._ocr = ocr
        self._detector = detector
        self._on_disc = on_disc
        self._on_state_change = on_state_change
        self._on_toggle_panel = on_toggle_panel
        self._set_repo = set_repo
        self._upgrade_syncer = upgrade_syncer
        self._on_disc_rejected = on_disc_rejected
        # Callback para mensajes de diagnóstico (heartbeat, fallos de captura, etc).
        # Permite que la UI muestre por qué el monitor "está silencioso".
        self._on_diagnostic = on_diagnostic
        # Tracking interno para el heartbeat
        self._last_diagnostic_msg: str | None = None
        self._loop_ticks: int = 0

        self._stop = threading.Event()
        self._paused = threading.Event()
        self._paused.set()          # no paused by default (set = can run)
        self._thread: threading.Thread | None = None
        self._last_state: ScreenState | None = None
        # Código del estado en el que ya emitimos un evento de captura. Sólo
        # disparamos `_process_disc` al ENTRAR a un disc-state (transición),
        # no en cada tick. Se resetea cuando salimos del estado.
        self._processed_disc_state_code: str | None = None
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
        last_heartbeat = time.monotonic()
        while not self._stop.is_set():
            if not self._paused.is_set():
                time.sleep(0.5)
                continue
            frame = self._get_frame()
            if frame is None:
                continue
            self._loop_ticks += 1
            state = self._detector.classify(frame)
            # Slot detection via OCR del titulo "Set Name (N)":
            # - S17 (vista detalle disco en PJ): panel central
            # - S9 (inventario con disco seleccionado): panel derecho
            #   En S9-sin-seleccion el OCR retorna None y state.slot
            #   queda None (eso es el indicador de "no hay disco activo").
            if state.code == "S17":
                state.slot = extract_s17_slot(frame, self._ocr)
            elif state.code == "S9":
                state.slot = extract_s9_slot(frame, self._ocr)
            self._notify_state_change(state)
            self._dispatch_state(frame, state)

            # Heartbeat cada 5s para confirmar que el loop está vivo.
            # QA 2026-05-12: bajado de 15s porque el usuario pasaba por estados
            # clave (S13/S15/S18) sin tiempo a ver feedback de actividad.
            now = time.monotonic()
            if now - last_heartbeat >= 5.0:
                last_heartbeat = now
                self._emit_diagnostic(
                    f"heartbeat: {self._loop_ticks} ticks, "
                    f"último estado={state.code} slot={state.slot} "
                    f"(conf {state.confidence:.2f})"
                )

            self._wait_cadence(state)

    def _emit_diagnostic(self, msg: str) -> None:
        """Emite mensaje de diagnóstico solo si cambió respecto al anterior (evita spam)."""
        if msg == self._last_diagnostic_msg:
            return
        self._last_diagnostic_msg = msg
        log.info("[diag] %s", msg)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.exception("Error en on_diagnostic")

    def _get_frame(self):
        """Captura el frame actual. Gestiona búsqueda y pérdida de ventana."""
        if self._window is None:
            self._window = find_zzz_window()
            if self._window is None:
                self._emit_diagnostic("ventana ZZZ no encontrada — esperando...")
                time.sleep(4.0)
                return None
            self._emit_diagnostic(
                f"ventana ZZZ encontrada: '{self._window.title}' "
                f"({self._window.width}x{self._window.height})"
            )

        try:
            frame = capture_window(self._window)
        except Exception as exc:
            log.exception("capture_window falló")
            self._emit_diagnostic(f"error al capturar frame: {exc}")
            self._window = None
            time.sleep(2.0)
            return None

        if frame is None:
            self._emit_diagnostic("capture_window devolvió None — re-buscando ventana")
            self._window = None
            time.sleep(2.0)
        return frame

    def _notify_state_change(self, state: ScreenState) -> None:
        # Detectar cambio: code distinto, O mismo code S17 pero distinto slot
        # (el usuario clickea otro disco equipado en el mismo PJ).
        if self._last_state is not None:
            same_code = state.code == self._last_state.code
            same_slot = state.slot == self._last_state.slot
            if same_code and same_slot:
                return
        log.debug("Estado: %s slot=%s (conf=%.2f)",
                  state.code, state.slot, state.confidence)
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
        else:
            # Salimos del disc-state — limpiar flag para permitir captura al volver
            self._processed_disc_state_code = None

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
        """
        Dispara `_process_disc` UNA SOLA VEZ por entrada al estado.
        Si seguimos en el mismo disc-state que ya procesamos, no re-emitimos.
        Para re-capturar el mismo disco el usuario debe cerrar y volver a abrir
        el modal (eso genera una transición S3→otro→S3 que resetea el flag).
        """
        if self._processed_disc_state_code == state.code:
            return
        self._processed_disc_state_code = state.code
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
