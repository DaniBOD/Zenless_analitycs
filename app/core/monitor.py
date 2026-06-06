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
from app.core.detector import (
    ScreenDetector, ScreenState, TemporalBuffer, AGENT_STATS_STATES,
    extract_s17_slot, extract_s9_slot, polling_cadence_ms,
    _deep_detect_s18, detect_active_tab, selected_avatar_x,
)
from app.core.parser_disc import DiscParsed, parse_modal_detalle
from app.core.parser_disc_s17 import parse_disc_s17
from app.core.parser_agent_stats import AgentStatsParsed, parse_agent_stats, AgentStatsAggregator
from app.core.agent_identifier import AgentIdentifier
from app.core.ocr_backend import OcrBackend

log = logging.getLogger(__name__)

# Estados donde hay un disco visible para parsear.
# S17 = vista detalle disco en Personalización de pistas (equipamiento PJ).
_NEW_DISC_STATES = {"S3", "S6", "S7"}       # discos nuevos (drop/tienda)
_EQUIPPED_DISC_STATES = {"S17"}              # discos equipados (vista PJ)
_DISC_DETAIL_STATES = _NEW_DISC_STATES | _EQUIPPED_DISC_STATES

# Pantallas de la familia "detalle de agente" SIN extracción de stats pero con
# logging persistente + identidad heredada de Atributos base (S18):
#   S8  = Equipamiento (hexágono de discos)
#   S19 = Habilidades
# No muestran el nombre del PJ en pantalla → identidad por carry-forward desde
# S18, con detección de cambio de PJ vía posición del avatar resaltado.
_AGENT_DETAIL_STATES = {"S8", "S19"}
# Estados re-procesados en CADA ciclo de cadencia (no one-shot por entrada):
_CONTINUOUS_STATES = AGENT_STATS_STATES | _AGENT_DETAIL_STATES
# Tolerancia de posición x del avatar para considerar "mismo PJ" (avatares
# adyacentes distan ~0.04-0.05 norm; media-ranura como margen anti-jitter).
_AVATAR_X_TOL = 0.025

# Confianza mínima de un estado NO-detalle para resetear el latch de identidad.
# Un fundido de transición entre pestañas (S12/dark_frame_filter, conf~0) NO debe
# olvidar al PJ — eso causaba el parpadeo "detecta→no reconoce" (Zhu Yuan,
# 2026-06-06). Solo una pantalla no-detalle CONFIRMADA (roster/ciudad) resetea.
_DETAIL_RESET_MIN_CONF = 0.50

# Intervalo de captura rápida (entre frames para buffer, sin procesar)
_FAST_CAPTURE_MS = 100  # 10 fps — MSS captura en ~20ms, template match en ~50ms

# Heartbeat intervalo (logging de diagnóstico)
_HEARTBEAT_S = 2.0


@dataclass
class MonitorEvent:
    kind: str            # "disc_detected" | "state_change" | "agent_stats" | "error"
    state: ScreenState
    disc: DiscParsed | None = None
    agent_stats: AgentStatsParsed | None = None
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
        on_agent_stats: Callable[[AgentStatsParsed, ScreenState], None] | None = None,
        on_diagnostic: Callable[[str], None] | None = None,
        on_agent_detail: Callable[[ScreenState, str | None, bool, str | None], None] | None = None,
        agent_identifier: AgentIdentifier | None = None,
    ):
        self._ocr = ocr
        self._detector = detector
        self._on_disc = on_disc
        self._on_state_change = on_state_change
        self._on_toggle_panel = on_toggle_panel
        self._set_repo = set_repo
        self._upgrade_syncer = upgrade_syncer
        self._on_disc_rejected = on_disc_rejected
        self._on_agent_stats = on_agent_stats
        # Callback para pantallas de detalle de agente sin stats (S8/S19): emite
        # (state, agent_name|None, identified) en cada ciclo continuo.
        self._on_agent_detail = on_agent_detail
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
        self._reported_agent_stats_state_code: str | None = None
        # Último estado confirmado por votación. Persiste aunque el buffer
        # dedupee (devuelva None por mismo estado), para permitir
        # re-extracción CONTINUA de S18 sin requerir cambio de estado ni F8.
        self._confirmed_state: ScreenState | None = None
        # Flag para loggear "[S18] perfil reconocido" una sola vez por entrada
        # (el log de stats sí se repite en cada ciclo de extracción).
        self._agent_stats_screen_logged: bool = False
        # Nombre del agente del último ciclo de extracción S18, para detectar
        # y loggear cambios de agente (navegación entre perfiles sin salir de S18).
        self._last_agent_name: str | None = None
        # Posición x del avatar resaltado cuando se confirmó la identidad en S18.
        # Se usa en S8/S19 (sin nombre en pantalla) para decidir si el PJ sigue
        # siendo el mismo (carry-forward) o cambió (→ matcher / "sin identificar").
        self._agent_anchor_x: float | None = None
        # Origen de la identidad latcheada para S8/S19: "heredado" (anchor desde
        # S18) | "avatar" (matcher) | None. La identidad (nombre+anchor+source) se
        # LATCHEA muestreando el avatar en el loop rápido (10 fps) y se SOSTIENE
        # mientras el avatar esté oculto (interfaz deslizante) — solo cambia al ver
        # positivamente otro avatar. Da robustez frente al auto-hide del row.
        self._detail_source: str | None = None
        self._window: WindowBounds | None = None
        # TemporalBuffer del loop _run(). Instance var para que force_scan()
        # pueda resetearlo y permitir re-emisión de [reconocido]/[stats].
        self._buffer: TemporalBuffer | None = None
        # Aggregator de stats S18: madura la extracción entre capturas
        # consecutivas. OCR es no-determinista frame-a-frame; tras 2-3 F8
        # los stats convergen a sus valores reales aunque cada captura sea
        # parcial. Se resetea automáticamente cuando cambia el agente.
        self._stats_aggregator = AgentStatsAggregator()
        # Identificador de agente por avatar (Etapa 2): aprende en S18, matchea
        # en S8/S19. Permite nombrar al PJ tras un switch directo (sin pasar por
        # Atributos base), siempre que ese PJ ya se haya visto en S18 antes.
        self._identifier = agent_identifier if agent_identifier is not None else AgentIdentifier()

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
        """
        Fuerza un scan inmediato (F8 o evento de foreground).
        Resetea buffer y fuerza un ciclo de proceso inmediato.

        TAMBIÉN resetea los dedup flags (`_processed_disc_state_code` y
        `_reported_agent_stats_state_code`) — útil para iterar QA del
        parser S18: el usuario presiona F8 y se vuelve a extraer stats
        sin necesidad de salir y volver a entrar al perfil del PJ.

        Emite un diagnóstico visible en el LivePanel para confirmar
        que F8 disparó (antes era silencioso, sin feedback al usuario).
        """
        if self._thread and self._thread.is_alive():
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            # Resetear también el TemporalBuffer del loop. Sin esto, F8
            # quedaba sin emitir [reconocido]/[stats] porque `buffer.add`
            # devuelve None para el mismo código ya emitido. El buffer
            # vive en _run() como `self._buffer` (instance var, ver _run).
            if self._buffer is not None:
                self._buffer.reset()
                log.info("force_scan: TemporalBuffer reseteado para re-emitir")
            log.info("force_scan: dedup flags reseteados, scan forzado")
            if self._on_diagnostic:
                try:
                    self._on_diagnostic("F8: scan manual forzado (dedup reseteado)")
                except Exception:
                    log.exception("Error en on_diagnostic (force_scan)")
            self._force_event.set()

    # ---- Internals --------------------------------------------------------------

    def _run(self) -> None:
        """
        Loop principal — dos velocidades:
        1. Captura rápida cada ~100ms para alimentar buffer temporal.
        2. Procesamiento (OCR + parseo + notify) solo cuando el buffer
           confirma un estado por mayoría de votos.

        El TemporalBuffer es instance var (self._buffer) para que
        force_scan() pueda resetearlo desde otros threads (F8, hook
        de foreground), permitiendo re-emitir [reconocido]/[stats]
        sin necesidad de cambio de estado real.
        """
        self._force_event = threading.Event()
        last_heartbeat = time.monotonic()
        last_process_time = 0.0
        self._buffer = TemporalBuffer(window_size=3)
        buffer = self._buffer  # alias local para el loop

        while not self._stop.is_set():
            if not self._paused.is_set():
                time.sleep(0.5)
                buffer.reset()
                continue

            frame = self._get_frame()
            if frame is None:
                buffer.reset()
                continue

            self._loop_ticks += 1
            now = time.monotonic()

            # ---- Paso 1: clasificar frame individual ----
            raw_state = self._detector.classify(frame)

            # Muestreo RÁPIDO de identidad en S8/S19 (10 fps, no cadencia): el
            # avatar-row es deslizante y se auto-oculta; muestrear en cada frame
            # captura la ventana breve en que el avatar es visible (al seleccionar
            # el PJ). Latchea la identidad para que el log de cadencia la sostenga.
            if raw_state.code in _AGENT_DETAIL_STATES:
                self._update_detail_identity(frame)

            # Fallback deep detect S18: si classify se quedó en S12, intentar
            # detección independiente de templates con OCR confirmatorio de stats.
            # Cierra el gap en .exe a 2560x1440 donde las templates S18 no matchean
            # (ver Documentacion/Dev_IA/2026-05-15_*.md).
            # Gate (2026-06-03): NO correr si hay un tab-bar activo — ahí la familia
            # (S8/S18/S19) ya la resolvió `classify` por tab. Evita re-disparar S18
            # sobre la pestaña Equipamiento. El tentativo visual-solo fue eliminado.
            if raw_state.code == "S12" and detect_active_tab(frame) is None:
                deep = _deep_detect_s18(frame, self._ocr)
                if deep is not None:
                    raw_state = deep

            # Slot detection
            if raw_state.code == "S17":
                raw_state.slot = extract_s17_slot(frame, self._ocr)
            elif raw_state.code == "S9":
                raw_state.slot = extract_s9_slot(frame, self._ocr)

            # ---- Paso 2: alimentar buffer temporal ----
            # Deep detect con alta confianza salta la votación 2/3 para
            # responder en el primer frame (UX < 500 ms).
            if raw_state.method == "deep_detect" and raw_state.confidence >= 0.75:
                voted_state = buffer.promote_now(raw_state)
            else:
                voted_state = buffer.add(raw_state)

            # ---- Paso 3: emitir cuando buffer confirma + re-extraer S18 ----
            if voted_state is not None:
                self._notify_state_change(voted_state)
                self._confirmed_state = voted_state

            # Estado activo: el recién votado, o el último confirmado si el
            # buffer dedupeó (devolvió None por mismo estado). Esto habilita
            # la EXTRACCIÓN CONTINUA de S18: aunque el estado no cambie,
            # re-procesamos en cada ciclo de cadencia para reflejar cambios
            # de agente y re-loggear stats sin requerir F8.
            active_state = voted_state if voted_state is not None else self._confirmed_state
            if active_state is not None:
                cadence_ms = polling_cadence_ms(active_state)
                elapsed_ms = (now - last_process_time) * 1000
                forced = self._force_event.is_set()
                # S18 (stats) y S8/S19 (detalle de agente) se re-procesan en cada
                # ciclo de cadencia aunque el estado no cambie (logging persistente).
                # El resto de estados procesa solo en la transición (voted_state no
                # nulo) o por F8 forzado.
                continuous = active_state.code in _CONTINUOUS_STATES
                should_dispatch = forced or (
                    elapsed_ms >= cadence_ms and (voted_state is not None or continuous)
                )
                if should_dispatch:
                    last_process_time = now
                    self._dispatch_state(frame, active_state)

            # ---- Heartbeat cada 2s ----
            if now - last_heartbeat >= _HEARTBEAT_S:
                last_heartbeat = now
                state_for_log = voted_state or raw_state
                self._emit_diagnostic(
                    f"heartbeat: {self._loop_ticks} capturas, "
                    f"estado={state_for_log.code} slot={state_for_log.slot} "
                    f"conf={state_for_log.confidence:.2f} "
                    f"tmpl={state_for_log.template_name}"
                )

            # ---- Espera corta entre capturas (fast polling) ----
            self._wait_fast()

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
            # Salimos de un agent-stats state → reset para que la próxima
            # entrada a S18 vuelva a loggear "perfil reconocido".
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
            # S17 (disco del PJ actual) conserva la identidad; S3/S6/S7 (drop/
            # tienda) NO son la familia de detalle de agente → resetear latch.
            if state.code != "S17":
                self._reset_detail_identity()
        elif state.code in AGENT_STATS_STATES:
            # Extracción CONTINUA: se invoca en cada ciclo de cadencia mientras
            # se está en S18 (no una sola vez). Auto-detecta cambio de agente.
            self._process_agent_stats_continuous(frame, state)
            # Si salimos de un disc-state, reseteamos su dedup también
            self._processed_disc_state_code = None
        elif state.code in _AGENT_DETAIL_STATES:
            # S8/S19: logging persistente + identidad heredada de S18 (sin stats).
            self._process_agent_detail_continuous(frame, state)
            self._processed_disc_state_code = None
        else:
            # Estado intermedio (S1/S12/S15/etc.) — resetear dedup flags para
            # que la próxima entrada a un capturable o S18 re-dispare/re-loggee.
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
            # Salimos de la familia de detalle de agente → olvidar la identidad
            # latcheada (al re-entrar a un S8 de otro PJ no debe sostener el viejo).
            # PERO solo si es una pantalla no-detalle CONFIRMADA: un fundido de
            # transición entre pestañas (conf~0) NO debe resetear el latch, o
            # parpadea "detecta→no reconoce" (Zhu Yuan, 2026-06-06).
            if state.confidence >= _DETAIL_RESET_MIN_CONF:
                self._reset_detail_identity()

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

    def _process_agent_stats_continuous(self, frame, state: ScreenState) -> None:
        """
        Extracción CONTINUA de stats S18 (punto 2 de la sesión 2026-05-31).

        A diferencia del comportamiento viejo (one-shot por entrada al estado),
        esto se invoca en cada ciclo de cadencia (~1500ms) mientras el usuario
        está en el perfil del agente, y emite los 3 niveles de log pedidos:

          2a) reconocimiento de la pantalla de stats (una vez por entrada)
          2b) extracción de los datos en pantalla (cada ciclo)
          2c) re-log de los stats (vía callback del controller, cada ciclo)

        Además auto-detecta cambio de agente (navegación entre perfiles sin
        salir de S18): el AgentStatsAggregator resetea por cambio de nombre,
        y acá logueamos la transición de forma explícita.
        """
        # 2a) Reconocimiento de pantalla — una sola vez por entrada a S18.
        if not self._agent_stats_screen_logged:
            self._agent_stats_screen_logged = True
            log.info(
                "[S18] Perfil de agente reconocido — extracción continua activa "
                "(conf=%.2f)", state.confidence,
            )

        # 2b) Extracción de datos en pantalla (cada ciclo).
        log.info("[S18] Extrayendo stats de pantalla...")
        result = self._process_agent_stats(frame, state)

        # Detección explícita de cambio de agente para el log.
        if result is not None and getattr(result, "agente_nombre", None):
            nombre = result.agente_nombre
            if self._last_agent_name and nombre != self._last_agent_name:
                log.info(
                    "[S18] Cambio de agente detectado: %s → %s (re-extracción)",
                    self._last_agent_name, nombre,
                )
            self._last_agent_name = nombre
            # Anclar la posición del avatar resaltado para identificar al mismo PJ
            # luego en S8/S19 (donde no hay nombre en pantalla).
            ax = selected_avatar_x(frame)
            if ax is not None:
                self._agent_anchor_x = ax
                self._detail_source = "heredado"
            # Bootstrap del matcher de avatar: aprender (nombre OCR → avatar) para
            # poder nombrar a este PJ luego en S8/S19 aunque se llegue por switch
            # directo (sin pasar por Atributos base).
            try:
                self._identifier.learn(frame, nombre)
            except Exception:
                log.exception("Error en identifier.learn")

    def _update_detail_identity(self, frame) -> None:
        """
        Latchea la identidad del PJ en S8/S19 muestreando el avatar resaltado.
        Se invoca en el loop rápido (10 fps) y también desde el handler de cadencia.

        **Latch POR CONTEXTO (2026-06-06).** La identidad se SOSTIENE; un fallo de
        lectura/match NUNCA la borra. Solo cambia ante EVIDENCIA POSITIVA (un match
        de avatar, que puede ser un PJ distinto). Cierra de raíz los 4 hallazgos del
        primer parseo S8/S19 (ver Dev_IA 2026-06-06 §8):
          - avatar OCULTO (cur_x None) → sostener (brecha B5: ocultar la fila no es
            evidencia de cambio de PJ).
          - PJ en ESQUINA del slider cuyo crop sale degradado → el matcher falla,
            pero sostenemos el último PJ en vez de caer a "sin identificar".
          - el fallo de identificar un PJ NO contamina al ya reconocido (no se borra
            el latch global) → no hace falta re-parsear.

        Reglas:
          - cur_x None (row oculto) → sostener, no tocar nada.
          - cur_x ≈ anchor y la identidad ya está CONFIRMADA (heredado/avatar) →
            estable, nada que hacer.
          - en otro caso correr el matcher:
              match → confirmar (nombre, "avatar"), anclar la posición.
              sin match + hay latch previo → SOSTENER (source "sostenido"), sin
                  anclar la posición (deja re-confirmar en un frame más nítido).
              sin match + sin latch → genuinamente "sin identificar".
        """
        try:
            cur_x = selected_avatar_x(frame)
        except Exception:
            return
        if cur_x is None:
            return  # avatar oculto → sostener latch (sin evidencia de cambio)
        same_pos = (self._agent_anchor_x is not None
                    and abs(cur_x - self._agent_anchor_x) < _AVATAR_X_TOL)
        if same_pos and self._last_agent_name is not None:
            # Misma posición que el anchor con un nombre ya latcheado → es el PJ
            # anclado (heredado). No degradar un match 'avatar' ya confirmado.
            if self._detail_source != "avatar":
                self._detail_source = "heredado"
            return
        # Posición nueva (o sin nombre aún) → matcher de avatar.
        try:
            match = self._identifier.identify(frame)
        except Exception:
            log.exception("Error en identifier.identify")
            match = None
        if match is not None:
            # Evidencia positiva → confirmar (puede ser un cambio real de PJ).
            self._last_agent_name = match[0]
            self._detail_source = "avatar"
            self._agent_anchor_x = cur_x
            return
        # Matcher sin match. Carry-forward: NUNCA borrar un latch ya logrado.
        if self._last_agent_name is not None:
            if self._detail_source != "avatar":
                self._detail_source = "sostenido"
            # NO anclar cur_x: dejar reintentar el matcher en frames más nítidos
            # (clave para el PJ de esquina cuyo crop oscila).
            return
        # Sin latch previo y sin match → genuinamente sin identificar.
        self._last_agent_name = None
        self._detail_source = None
        self._agent_anchor_x = cur_x

    def _reset_detail_identity(self) -> None:
        """Limpia el latch de identidad (al salir de la familia detalle de agente)."""
        self._last_agent_name = None
        self._agent_anchor_x = None
        self._detail_source = None

    def _process_agent_detail_continuous(self, frame, state: ScreenState) -> None:
        """
        Logging PERSISTENTE para S8 (Equipamiento) y S19 (Habilidades).

        Estas pantallas no muestran el nombre del PJ. Emite en cada ciclo la
        identidad LATCHEADA (mantenida por `_update_detail_identity` en el loop
        rápido): heredada de S18 (anchor) o reconocida por el matcher de avatar.
        Si el avatar nunca se pudo leer (sin latch) → "sin identificar".
        """
        # Refrescar el latch con el frame actual (además del muestreo rápido).
        self._update_detail_identity(frame)
        name = self._last_agent_name
        identified = bool(name)
        source = self._detail_source if identified else None

        log.info(
            "[%s] Pantalla detalle reconocida (%s) — PJ=%s identificado=%s (%s)",
            state.code,
            "Habilidades" if state.code == "S19" else "Equipamiento",
            name or "?", identified, source or "-",
        )
        if self._on_agent_detail:
            try:
                self._on_agent_detail(state, name, identified, source)
            except Exception:
                log.exception("Error en on_agent_detail callback")

        # 2c) El re-log de stats lo emite el controller en on_agent_stats
        # ([reconocido]/[stats]/[completo]) y _process_agent_stats loggea el
        # post-merge — ambos se repiten en cada ciclo, según lo pedido.

    @staticmethod
    def _stats_result_is_useful(stats) -> bool:
        """
        Heurística: el resultado es útil si al menos uno de PV/Ataque/Defensa
        salió OK. Estos son los más fáciles de leer (números grandes en su
        línea propia) — si todos fallan, el frame estaba en transición.
        """
        if stats is None:
            return False
        return any(getattr(stats, k, None) is not None for k in ("pv", "ataque", "defensa"))

    def _dump_frame_if_enabled(self, frame, state: ScreenState) -> None:
        """
        Si DANIBOD_DUMP_FRAMES=1, guarda el frame en
        %LOCALAPPDATA%/DaniBOD_ZZZ_Analytics/debug_frames/<state>_<ts>.png.
        Permite QA offline comparando el frame runtime con los fixtures.
        """
        import os
        if os.environ.get("DANIBOD_DUMP_FRAMES") != "1":
            return
        try:
            import cv2
            from pathlib import Path
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
            dump_dir = Path(base) / "DaniBOD_ZZZ_Analytics" / "debug_frames"
            dump_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = dump_dir / f"{state.code}_{ts}_conf{state.confidence:.2f}.png"
            # cv2.imwrite no tolera paths con caracteres especiales — usar imencode + tofile
            import numpy as np
            buf = cv2.imencode(".png", frame)[1]
            buf.tofile(str(path))
            log.info("debug frame dumped: %s", path)
            if self._on_diagnostic:
                self._on_diagnostic(f"frame dumped: {path.name}")
        except Exception as exc:
            log.exception("Error dumping debug frame: %s", exc)

    def _process_agent_stats(self, frame, state: ScreenState):
        """
        Parsea stats S18 y dispara callback. Devuelve el `AgentStatsParsed`
        resultante (o None si hubo excepción) para que el caller
        `_maybe_process_agent_stats` pueda decidir si el resultado es
        utilizable y comprometer el dedup.

        Cualquier excepción se reporta al LivePanel vía `_on_diagnostic`
        (con prefijo `[diag] error...`) para que sea visible incluso en
        `.exe --windowed` donde stderr está suprimido.

        Si DANIBOD_DUMP_FRAMES=1, el frame raw se guarda a
        %LOCALAPPDATA%/DaniBOD_ZZZ_Analytics/debug_frames/.
        """
        self._dump_frame_if_enabled(frame, state)
        try:
            raw_stats = parse_agent_stats(frame, self._ocr)
            # Pasar por el aggregator: si esta captura tiene campos None pero
            # capturas previas del MISMO agente tenían valor, se preservan.
            stats = self._stats_aggregator.merge(raw_stats)
            log.info(
                "Stats agente (post-merge): Nv=%s PV=%s ATK=%s DEF=%s conf=%.2f",
                stats.nivel, stats.pv, stats.ataque, stats.defensa, stats.confianza_global,
            )
        except Exception as exc:
            log.exception("Error parseando stats de agente")
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(
                        f"error parseando stats S18: {type(exc).__name__}: {exc}"
                    )
                except Exception:
                    log.exception("Error en on_diagnostic callback (parse_agent_stats)")
            return None
        if self._on_agent_stats:
            try:
                self._on_agent_stats(stats, state)
            except Exception as exc:
                log.exception("Error en on_agent_stats callback")
                if self._on_diagnostic:
                    try:
                        self._on_diagnostic(
                            f"error en callback agent_stats: {type(exc).__name__}: {exc}"
                        )
                    except Exception:
                        log.exception("Error en on_diagnostic callback (on_agent_stats)")
        return stats

    def _wait_fast(self) -> None:
        """Espera corta entre capturas rápidas (para alimentar buffer)."""
        if self._force_event.wait(timeout=_FAST_CAPTURE_MS / 1000.0):
            self._force_event.clear()

    def _process_disc(self, frame, state: ScreenState) -> None:
        try:
            # S17 (disco equipado, "Personalización de pistas") usa el parser
            # ESPACIAL full-frame — más robusto que el per-ROI a 2560×1440.
            # El resto de disc-states (S3/S6/S7) sigue con parse_modal_detalle.
            if state.code == "S17":
                disc = parse_disc_s17(frame, self._ocr)
            else:
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
