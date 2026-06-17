"""
Hito 2.4.7 / 2.5 — Monitor principal con polling adaptativo · RF-04 §5.
Loop en thread secundario: captura → clasifica → parsea → emite callback.
Integra UpgradeSyncer (S10 PRE/POST) y HotkeyManager (F8/F10).
Hook win32 para EVENT_SYSTEM_FOREGROUND (forzar scan al volver al juego).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from app.core import mem_diag
from app.core.capturer import WindowBounds, capture_window, find_zzz_window
from app.core.detector import (
    ScreenDetector, ScreenState, TemporalBuffer, AGENT_STATS_STATES,
    extract_s17_slot, extract_s9_slot, polling_cadence_ms,
    _deep_detect_s18, detect_active_tab, selected_avatar_x,
    crop_grid_selected_badge, crop_detail_badge,
)
from app.core.stats_vocab import _norm_key
from app.core.parser_disc import DiscParsed, parse_modal_detalle
from app.core.parser_disc_s17 import (
    parse_disc_s17, parse_disc_s17_full, DiscAggregator, disc_is_mature,
)
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

# Cosecha (Fase 5R.3): estados con avatar/badge útil + cuántos frames por (PJ,estado).
_HARVEST_STATES = {"S8", "S17", "S18", "S19"}
_HARVEST_CAP = 4

# Guarda de asignación S17 (latch + avatar). El PJ asignado a un disco equipado
# sale del LATCH (PJ cuya pantalla se ve, ya confiable); el avatar circular S17 se
# usa solo como chequeo mismo/distinto contra ese latch. Medido 2026-06-06 sobre
# crops reales: same-PJ 0.95–0.99, otro PJ ≤ 0.76 → umbral 0.86 separa limpio.
#   sim None  → primera vez del PJ en S17 → confiar latch + aprender (bootstrap).
#   sim ≥ MIN → avatar confirma el latch → asignar.
#   sim < MIN → avatar es de OTRO PJ (disco del grid) → abstener (preservar DB).
_S17_GUARD_MIN = 0.86
# Fase 4 (revisado tras QA 2026-06-09): se CONFÍA EN EL LATCH para asignar el disco
# equipado; `sim` (avatar circular S17) solo decide si re-aprender el descriptor
# (sim baja/ausente → refrescar; self-heal del falso-rechazo de Nangong 0.734). El
# best-match del avatar S17 resultó inservible para rechazar (descriptor 'imán'
# Yixuan ~0.9 contra casi todo) → la discriminación de discos de OTRO PJ se difiere
# a la fase de grilla de candidatos.

# S17 continuo (Fase 1): ciclos de cadencia que se fusionan en el aggregator antes
# de emitir BEST-EFFORT si el disco no maduró (red de seguridad). Si madura antes
# (todos los campos), se emite en ese ciclo. ~5 ciclos cubre OCR no-determinista.
_S17_AGG_MAX_CYCLES = 5

# Firma HÍBRIDA del disco S17 (gobierna la re-captura; BARATA, sin OCR — RNF-06).
# Dos componentes en gris comparadas con OR:
#   - detalle: bloque main + 4 substats (lo que SÍ difiere entre discos del MISMO
#     set; el título/nivel/labels son idénticos y se excluyen para no diluir).
#   - hexágono: las 6 caras + el anillo de selección (cambia al cambiar de slot).
# "Disco nuevo" si CUALQUIER componente supera su umbral. Umbrales calibrados sobre
# capturas reales (14_Slots_equipamiento): TODOS los cambios de slot —incluso
# adyacentes del mismo set, p.ej. 4↔5— superan el umbral (peor caso ~1.6× el
# umbral); frame idéntico = 0. La firma 12×12 vieja NO distinguía slots del mismo
# set (bug QA 2026-06-07). Re-capturar el mismo disco es idempotente (update
# in-place) → se sesga a sensibilidad. Ver Dev_IA 2026-06-07.
_S17_SIG_DETAIL_MAX = 5.0
_S17_SIG_HEX_MAX = 3.0
# Gate de OCR S18 (RNF-06): umbral de diff de la firma del panel de stats. Sensible
# (bajo) a propósito — errar hacia re-OCR de más (sin riesgo) antes que saltarse un
# cambio real (stats viejos). El cambio de agente es un diff enorme; el shimmer de
# fondo del panel queda por debajo.
_S18_SIG_MAX = 2.5
# Throttle del fallback deep_detect S18 sobre S12 (RNF-06): máx 1 intento de OCR cada
# N seg. En pantallas de carga/transición clasificadas como S12, esto corría OCR cada
# frame → spike que colgaba la UI al abrir el juego. Un deep_detect exitoso igual promueve
# de inmediato (promote_now); el throttle solo limita la FRECUENCIA de intentos.
_DEEP_DETECT_MIN_S = 0.8
# Gate de frame para deep_detect (RNF-06): si el frame S12 no cambió desde el último
# intento (pantalla estática/colgada que el classify no reconoce), no re-OCR-earlo —
# era el driver del leak en el tramo S12 (la medición post-gates mostró que S12 seguía
# OCR-eando ~48/min). Umbral sobre la firma whole-frame 32×32.
_S12_SIG_MAX = 2.0
# Watchdog de RAM (RNF-06): defensa en profundidad. Cada ~15s lee el private bytes; al
# cruzar el umbral pide auto-restart del .exe (la cosecha persiste entre reinicios —
# equip_map + npz — así que NO se pierde). Umbral alto: rara vez dispara si los gates de
# OCR funcionan, pero corta antes del cuelgue (~12 GB). Desactivable con DANIBOD_NO_RAM_GUARD=1.
_RAM_RESTART_MB = 6000
_RAM_CHECK_INTERVAL_S = 15.0
# Detector LIBRE/equipado (5R.B): un frame es "evidencia de libre" si el badge cae en
# el reject-set o su conf < _S17_FREE_CONF (nada se parece a una cara → sin dueño). Se
# declara LIBRE solo con ≥ _S17_FREE_MIN_FRAMES de evidencia mayoritaria y cero dueños
# identificados (conservador: ante duda → "dueño incierto").
_S17_FREE_CONF = 0.58
_S17_FREE_MIN_FRAMES = 2

# Intervalo de captura rápida (entre frames para buffer, sin procesar)
_FAST_CAPTURE_MS = 100  # 10 fps — MSS captura en ~20ms, template match en ~50ms


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
        on_ram_critical: Callable[[], None] | None = None,
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
        # S17 CONTINUO + DiscAggregator (Fase 1, 2026-06-07): igual que S18, mientras
        # se mira un disco se re-extrae cada cadencia y se FUSIONAN parciales →
        # converge en pocos ciclos sin necesitar un frame perfecto (mata el
        # "mover y volver"). La firma híbrida del disco detecta CAMBIO de disco y
        # resetea el aggregator (igual que S18 resetea por cambio de agente).
        self._disc_aggregator = DiscAggregator()
        self._disc_agg_sig = None        # firma-ancla del disco que se está fusionando
        self._disc_emitted: bool = False  # ya se emitió (persist/log) este disco
        self._disc_agg_cycles: int = 0    # ciclos fusionados del disco actual
        # Identidades (set_canon, slot, main_canon) ya emitidas en ESTA sesión S17.
        # Desacopla la emisión de los parpadeos de la firma híbrida: el modelo 3D
        # del disco tiene animación idle → la firma cruza el umbral en pantalla
        # estática y resetea el aggregator. Sin esto el MISMO disco quieto se
        # re-emite ~7×. Se limpia al salir de S17 o forzar (F8). RNF-06: sin OCR.
        self._disc_emitted_ids: set = set()
        # Última firma del log "[S17] asignado" (edge-trigger: 1× por cambio).
        self._s17_assign_sig = None
        # Gate de OCR S18 (RNF-06): última firma del panel de stats. Si no cambió, se
        # saltea el OCR (la extracción continua existe para detectar cambio de agente;
        # sin cambio visual no hay nada nuevo que extraer). Self-correcting: cualquier
        # cambio (agente nuevo, level-up) supera el umbral → re-OCR.
        self._s18_last_sig = None
        # Throttle del fallback deep_detect S18 sobre S12 (RNF-06).
        self._last_deep_detect_t = 0.0
        # Firma del último frame S12 al que se le intentó deep_detect (gate anti-re-OCR).
        self._s12_deep_sig = None
        # Watchdog de RAM (RNF-06): pide auto-restart al cruzar el umbral. Dispara 1×.
        self._on_ram_critical = on_ram_critical
        self._ram_restart_fired = False
        self._last_ram_check_t = 0.0
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
        # Firma del último log de detalle S8/S19 emitido (edge-triggered): solo se
        # re-loguea cuando (code, name, identified, source) cambia.
        self._last_detail_sig: tuple | None = None
        # Código del estado del ciclo anterior (para detectar el retroceso S17→S8:
        # Fase 4 — al volver del detalle del disco al hexágono es el MISMO PJ, así
        # que se hereda el latch en vez de re-identificar por avatar).
        self._prev_state_code: str | None = None
        # Slot del último disco S17 asignado — anchor de flujo (5R.5b): un disco en un
        # slot NUEVO es el equipado por el latch (certero); mismo slot = candidato.
        self._s17_last_slot: int = 0
        # Votación del dueño del badge de grilla (5R.5c): el loop rápido (10 fps)
        # samplea el badge y ACUMULA confianza por PJ mientras el MISMO disco está en
        # pantalla. `_assign_s17_pj` usa el ganador en vez de un frame suelto → mata el
        # parpadeo Yuzuha↔incierto (el recorte varía frame a frame por la animación
        # idle del modelo 3D y el resaltado deslizante). Resetea al cambiar de disco.
        self._s17_owner_sig: tuple | None = None
        self._s17_owner_votes: dict[str, float] = {}
        self._s17_free_evidence: int = 0   # frames con badge sin cara (5R.B)
        self._s17_samples: int = 0         # frames muestreados del disco actual
        # Mapa disco→dueño (5R.C): verdad de tierra automática. Si DANIBOD_EQUIP_MAP
        # está seteado, al emitir un disco EQUIPADO (agente_asignado por flujo-ancla,
        # dueño certero) se registra firma_disco→dueño a ese JSON. Readonly-safe (no DB).
        self._equip_map: dict[str, str] = {}
        self._equip_map_loaded: bool = False  # lazy-load del JSON existente 1× por instancia
        self._grid_diag_counts: dict[str, int] = {}  # cap por disco del volcado DANIBOD_GRID_DIAG
        # Instrumentación de identidad (L.0, gated DANIBOD_ID_DIAG): por disco emitido
        # loguea el desglose grid/detalle (loc + match + voto) para cruzar contra el
        # equip_map y ubicar el cuello (localización vs voto vs discriminación). Cero
        # overhead si el flag está apagado.
        self._id_diag_on: bool = bool(os.environ.get("DANIBOD_ID_DIAG"))
        self._id_diag: dict = {}
        # Cosecha de frames etiquetados por latch (Fase 5R.3, solo si DANIBOD_HARVEST
        # está seteado). Cap por (PJ, estado) para no spamear. Read-only: solo escribe
        # PNGs de frame completo a la carpeta indicada, nunca toca la DB.
        self._harvest_counts: dict[tuple[str, str], int] = {}
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
            # S17 continuo: re-emitir el disco actual aunque ya se haya emitido
            # (sin tirar lo fusionado — F8 fuerza el re-log/persist del best-known).
            self._disc_emitted = False
            self._disc_emitted_ids.clear()
            self._s17_assign_sig = None
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

            # Heartbeat de memoria (RNF-06, env-gated DANIBOD_MEM_DIAG). No-op si está
            # apagado; throttle interno ~20s → seguro llamar cada iteración.
            mem_diag.heartbeat({"ticks": self._loop_ticks, "st": raw_state.code})
            # Watchdog de RAM (RNF-06): cota dura con auto-restart. Throttle interno ~15s.
            self._ram_watchdog(now)

            # Muestreo RÁPIDO de identidad en S8/S19 (10 fps, no cadencia): el
            # avatar-row es deslizante y se auto-oculta; muestrear en cada frame
            # captura la ventana breve en que el avatar es visible (al seleccionar
            # el PJ). Latchea la identidad para que el log de cadencia la sostenga.
            if raw_state.code in _AGENT_DETAIL_STATES:
                self._update_detail_identity(frame)
            # Muestreo RÁPIDO del dueño del badge en S17 (10 fps, 5R.5c): vota el dueño
            # del disco mirado en cada frame y lo acumula por firma-de-disco. El badge
            # se decide con ~15 votos/disco en vez de 1 (loop lento) → lectura estable,
            # sin parpadeo. El descriptor cuesta microsegundos; no toca el MSS ni el OCR.
            elif raw_state.code == "S17":
                self._sample_s17_owner(frame)

            # Fallback deep detect S18: si classify se quedó en S12, intentar
            # detección independiente de templates con OCR confirmatorio de stats.
            # Cierra el gap en .exe a 2560x1440 donde las templates S18 no matchean
            # (ver Documentacion/Dev_IA/2026-05-15_*.md).
            # Gate (2026-06-03): NO correr si hay un tab-bar activo — ahí la familia
            # (S8/S18/S19) ya la resolvió `classify` por tab. Evita re-disparar S18
            # sobre la pestaña Equipamiento. El tentativo visual-solo fue eliminado.
            if (raw_state.code == "S12" and detect_active_tab(frame) is None
                    and now - self._last_deep_detect_t >= _DEEP_DETECT_MIN_S):
                # Gate RNF-06: solo intentar deep_detect si el frame S12 CAMBIÓ desde el último
                # intento. Pantalla estática/colgada que el classify deja en S12 → no re-OCR
                # (era el driver del leak en S12). Si no hay firma, se intenta igual (degrada bien).
                s12_sig = self._frame_lo_sig(frame)
                if (self._s12_deep_sig is None or s12_sig is None
                        or self._sig_component_diff(s12_sig, self._s12_deep_sig) > _S12_SIG_MAX):
                    self._s12_deep_sig = s12_sig
                    self._last_deep_detect_t = now
                    deep = _deep_detect_s18(frame, self._ocr)
                    if deep is not None:
                        raw_state = deep

            # Slot detection. S17 ya NO usa gate one-shot: es CONTINUO con aggregator
            # (Fase 1), igual que S18. La firma del disco se evalúa dentro del handler
            # (_process_disc_s17_continuous) para resetear el aggregator al cambiar de
            # disco. El slot lo lee el parser del título cada ciclo (y el aggregator
            # conserva el mejor no-cero).
            if raw_state.code == "S9":
                raw_state.slot = extract_s9_slot(frame, self._ocr)
            elif raw_state.code != "S17":
                # Fuera de S17 → olvidar el tracking del disco mirado.
                self._reset_s17_disc_tracking()

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
                # S17 es CONTINUO (Fase 1): se re-procesa cada cadencia como S18/S8/S19.
                continuous = active_state.code in _CONTINUOUS_STATES or active_state.code == "S17"
                should_dispatch = forced or (
                    elapsed_ms >= cadence_ms and (voted_state is not None or continuous)
                )
                if should_dispatch:
                    last_process_time = now
                    self._dispatch_state(frame, active_state)

            # ---- Espera corta entre capturas (fast polling) ----
            # (Sin heartbeat periódico: el logging es edge-triggered. El cambio de
            #  estado se loguea en _notify_state_change; los stats/detalle, en sus
            #  handlers, solo cuando el dato cambia.)
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

    def _ram_watchdog(self, now: float) -> None:
        """Cota de RAM (RNF-06): cada ~15s lee el private bytes; al cruzar _RAM_RESTART_MB
        pide auto-restart del .exe vía callback (la cosecha persiste → sin pérdida). Dispara
        una sola vez. No-op si DANIBOD_NO_RAM_GUARD está seteado o no hay callback."""
        if (self._ram_restart_fired or self._on_ram_critical is None
                or os.environ.get("DANIBOD_NO_RAM_GUARD")):
            return
        if now - self._last_ram_check_t < _RAM_CHECK_INTERVAL_S:
            return
        self._last_ram_check_t = now
        _ws, priv = mem_diag.mem_counters()
        if 0 < _RAM_RESTART_MB <= priv:
            self._ram_restart_fired = True
            log.critical("[RAM] private=%.0fMB ≥ %dMB → auto-restart del .exe (RNF-06)",
                         priv, _RAM_RESTART_MB)
            self._emit_diagnostic(
                f"RAM alta ({priv / 1024:.1f} GB) — reiniciando la app para liberar memoria "
                f"(la cosecha NO se pierde)")
            try:
                self._on_ram_critical()
            except Exception:
                log.exception("on_ram_critical falló")

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
        prev_code = self._last_state.code if self._last_state is not None else None
        if self._last_state is not None:
            same_code = state.code == self._last_state.code
            same_slot = state.slot == self._last_state.slot
            if same_code and same_slot:
                return
        # Edge-triggered: solo se loguea al cambiar de estado (o de slot en S17).
        slot_txt = f" slot={state.slot}" if state.slot is not None else ""
        log.info("[estado] %s → %s%s (conf=%.2f)",
                 prev_code or "-", state.code, slot_txt, state.confidence)
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception as exc:
                log.exception("Error en on_state_change: %s", exc)
        self._last_state = state

    def _dispatch_state(self, frame, state: ScreenState) -> None:
        """Enruta el frame al handler correspondiente según el estado."""
        prev_code = self._prev_state_code
        self._prev_state_code = state.code
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
            # Retroceso S17→S8 (Fase 4): volvés del detalle del disco al hexágono →
            # es el MISMO PJ. Re-anclar el latch a la posición actual del avatar para
            # que `_update_detail_identity` lo SOSTENGA (heredado) en vez de re-matchear
            # por avatar (que mis-identificaba al volver). Solo si ya hay latch.
            if prev_code == "S17" and self._last_agent_name:
                try:
                    ax = selected_avatar_x(frame)
                except Exception:
                    ax = None
                if ax is not None:
                    self._agent_anchor_x = ax
                    if self._detail_source != "avatar":
                        self._detail_source = "heredado"
                # Re-emitir la identidad al retroceder: la firma edge no cambia
                # (mismo PJ) y el log/UI quedaban sin feedback → el usuario creía que
                # "no reconocía" y volvía a S18. Forzar 1 re-emisión del [S8] PJ=…
                self._last_detail_sig = None
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
        # Cosecha de frames etiquetados (5R.3) — al final, con el latch ya actualizado.
        self._maybe_harvest(frame, state)

    def _maybe_harvest(self, frame, state: ScreenState) -> None:
        """Si DANIBOD_HARVEST está seteado, guarda el frame completo etiquetado por
        el latch (`<pj>__<estado>__<n>.png`) para construir offline el set etiquetado
        del descriptor (harness 5R.2) + la cosecha híbrida. Cap por (PJ, estado).
        Solo escribe PNGs a esa carpeta; nunca toca la DB."""
        import os
        d = os.environ.get("DANIBOD_HARVEST")
        if not d or not self._last_agent_name or state.code not in _HARVEST_STATES:
            return
        key = (self._last_agent_name, state.code)
        if self._harvest_counts.get(key, 0) >= _HARVEST_CAP:
            return
        try:
            import cv2
            from pathlib import Path
            from app.core.stats_vocab import _norm_key
            n = self._harvest_counts.get(key, 0)
            safe = _norm_key(self._last_agent_name) or "x"
            out = Path(d)
            out.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / f"{safe}__{state.code}__{n}.png"), frame)
            self._harvest_counts[key] = n + 1
            if self._on_diagnostic:
                self._on_diagnostic(f"[harvest] {safe} {state.code} #{n}")
        except Exception:
            log.debug("harvest falló", exc_info=True)

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

    @staticmethod
    def _s17_disc_signature(frame):
        """
        Firma HÍBRIDA del disco S17, sin OCR (RNF-06). Devuelve `(sig_detail,
        sig_hex)` o None:
          - sig_detail: 48×48 gris del bloque main+substats (x∈[0.30,0.52],
            y∈[0.22,0.56]) — lo que difiere entre discos del mismo set.
          - sig_hex: 24×24 gris del hexágono (x∈[0.58,0.95], y∈[0.18,0.88]) — el
            anillo de selección se mueve al cambiar de slot.
        Identifica el disco mirado y cambia al navegar la grilla / cambiar de slot
        aunque el set sea el mismo.
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            det = frame[int(0.22 * H):int(0.56 * H), int(0.30 * W):int(0.52 * W)]
            hexr = frame[int(0.18 * H):int(0.88 * H), int(0.58 * W):int(0.95 * W)]
            if det.size == 0 or hexr.size == 0:
                return None
            sig_detail = cv2.cvtColor(
                cv2.resize(det, (48, 48), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            sig_hex = cv2.cvtColor(
                cv2.resize(hexr, (24, 24), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            return (sig_detail, sig_hex)
        except Exception:
            return None

    @staticmethod
    def _frame_lo_sig(frame):
        """Firma whole-frame 32×32 gris, sin OCR (RNF-06). Para gatear deep_detect en S12:
        si el frame no cambió, no vale re-intentar el OCR. None si no se puede leer."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            return cv2.cvtColor(
                cv2.resize(frame, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return None

    @staticmethod
    def _s18_stats_signature(frame):
        """Firma del panel de stats S18, sin OCR (RNF-06). 32×32 gris del panel AGENT
        INFO (x∈[0.54,0.96], y∈[0.39,0.74]) — texto estático en la mitad DERECHA, donde
        NO está el modelo 3D animado del PJ (mitad izquierda). Cambia al cambiar de agente
        o subir de nivel. None si no se puede leer."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            panel = frame[int(0.39 * H):int(0.74 * H), int(0.54 * W):int(0.96 * W)]
            if panel.size == 0:
                return None
            return cv2.cvtColor(
                cv2.resize(panel, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return None

    @staticmethod
    def _sig_component_diff(a, b) -> float:
        """Diff medio absoluto de una componente; inf si falta o cambia de forma."""
        if a is None or b is None or getattr(a, "shape", None) != getattr(b, "shape", None):
            return float("inf")
        return float(np.abs(a - b).mean())

    @staticmethod
    def _sig_close(a, b) -> bool:
        """
        True si dos firmas híbridas son del MISMO disco: AMBAS componentes dentro de
        su umbral. Si cualquiera supera su umbral ⇒ disco distinto (OR para disparar).
        """
        if a is None or b is None:
            return False
        return (Monitor._sig_component_diff(a[0], b[0]) <= _S17_SIG_DETAIL_MAX
                and Monitor._sig_component_diff(a[1], b[1]) <= _S17_SIG_HEX_MAX)

    def _reset_s17_disc_tracking(self) -> None:
        """Olvida el disco S17 en fusión (al salir de S17 o forzar re-captura)."""
        self._disc_aggregator.reset()
        self._disc_agg_sig = None
        self._disc_emitted = False
        self._disc_agg_cycles = 0
        self._disc_emitted_ids.clear()
        self._s17_assign_sig = None
        # Anchor de flujo (5R.5b): al re-entrar a un slot, el primer disco vuelve a ser
        # el equipado por el latch (estructura del juego) → resetear el slot rastreado.
        self._s17_last_slot = 0
        # Votación del dueño (5R.5c) + evidencia-libre (5R.B): olvidar al salir de S17.
        self._s17_owner_sig = None
        self._s17_owner_votes = {}
        self._s17_free_evidence = 0
        self._s17_samples = 0
        self._grid_diag_counts.clear()

    @staticmethod
    def _disc_identity(d) -> tuple:
        """Identidad estable de un disco para dedup de emisión (sin firma visual).
        Normaliza nombre de set y main con `_norm_key` (sin tildes/mojibake): el OCR
        del crop (Fase 2) lee la tilde de forma inestable entre ciclos
        ('Faetón'/'Faeton'/'Faetön') y sin normalizar re-emitía el MISMO disco.

        Incluye los 4 substats (nombre+rolls) porque (set, slot, main) es DEMASIADO
        grueso: en slot 1 el main es siempre HP → dos discos distintos del MISMO set
        en slot 1 colapsaban a la misma identidad y el segundo NUNCA se emitía (bug
        2026-06-12: 'Yanagi no logueaba'). Los substats (nombre canónico + rolls) son
        OCR-estables y distinguen builds; los valores se omiten (más ruidosos)."""
        from app.core.stats_vocab import _norm_key
        subs = tuple(sorted(
            (_norm_key(s.nombre_canon or s.nombre_raw or ""), s.rolls)
            for s in (d.subs or [])
        ))
        return (
            _norm_key(d.set_name_canon or d.set_name_raw or ""),
            d.slot,
            _norm_key(d.main_stat_canon or d.main_stat_raw or ""),
            subs,
        )

    def _is_new_s17_disc(self, sig) -> bool:
        """True si la firma indica que el disco mirado cambió (o no había ancla)."""
        return self._disc_agg_sig is None or not self._sig_close(sig, self._disc_agg_sig)

    @staticmethod
    def _identity_to_key(identity) -> str:
        """Serializa la identidad de disco (`_disc_identity`) a una clave string estable
        para el mapa disco→dueño. Determinista — monitor y harness la computan igual."""
        set_, slot, main, subs = identity
        subs_s = "|".join(f"{n}:{r}" for n, r in subs)
        return f"{set_}#{slot}#{main}#{subs_s}"

    def _record_equip_map(self, identity, owner: str) -> None:
        """Registra firma_disco→dueño (verdad de tierra del flujo-ancla) al JSON apuntado
        por DANIBOD_EQUIP_MAP. No-op si la env no está. Readonly-safe (no toca DB)."""
        import os
        path = os.environ.get("DANIBOD_EQUIP_MAP")
        if not path or not owner:
            return
        key = self._identity_to_key(identity)
        try:
            import json
            from pathlib import Path
            p = Path(path)
            # Lazy-load 1× por instancia: el Monitor se recrea al detener/reanudar
            # captura (o al relanzar la app) → _equip_map vuelve a {}. Sin cargar el
            # JSON existente, el primer write CLOBBEREA los PJs de pases previos.
            # Mergeamos disco como base; lo de esta sesión pisa entradas re-equipadas.
            if not self._equip_map_loaded:
                self._equip_map_loaded = True
                if p.exists():
                    try:
                        disk = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(disk, dict):
                            self._equip_map = {**disk, **self._equip_map}
                    except Exception:
                        log.debug("equip_map load falló", exc_info=True)
            if self._equip_map.get(key) == owner:
                return
            self._equip_map[key] = owner
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._equip_map, ensure_ascii=False, indent=0), encoding="utf-8")
        except Exception:
            log.debug("equip_map write falló", exc_info=True)

    def _process_disc_s17_continuous(self, frame, state: ScreenState) -> None:
        """
        S17 CONTINUO (Fase 1, espejo de la extracción S18): cada cadencia re-extrae
        el disco y FUSIONA parciales en el DiscAggregator. La firma híbrida detecta
        cambio de disco y resetea el aggregator. Emite (persist/log) UNA vez cuando
        el resultado fusionado MADURA (todos los campos), o tras _S17_AGG_MAX_CYCLES
        como red de seguridad. Converge en pocos ciclos → mata el "mover y volver".
        """
        sig = self._s17_disc_signature(frame)
        if sig is None:
            return
        if self._is_new_s17_disc(sig):
            self._disc_aggregator.reset()
            self._disc_agg_sig = sig
            self._disc_emitted = False
            self._disc_agg_cycles = 0
        # Gate RNF-06: si este disco YA se emitió (procesado completo) y la firma no cambió,
        # NO re-OCR-earlo cada ciclo — era OCR puro desperdicio que alimentaba el leak nativo
        # de Paddle (la cosecha = parar en discos → este era el driver). El badge del dueño
        # sigue votando aparte en _sample_s17_owner (10 fps) sin OCR.
        if self._disc_emitted:
            return
        try:
            disc, _face = parse_disc_s17_full(frame, self._ocr)
        except Exception:
            log.exception("Error parseando disco S17")
            return
        self._assign_s17_pj(disc, frame)   # identidad por badge de grilla (5R.5)
        if disc.confianza_global < 0.7:
            return  # frame de transición/baja confianza → no contaminar el aggregator
        merged = self._disc_aggregator.merge(disc)
        self._disc_agg_cycles += 1
        if self._disc_emitted or merged is None:
            return
        mature = disc_is_mature(merged)
        if mature or self._disc_agg_cycles >= _S17_AGG_MAX_CYCLES:
            self._disc_emitted = True
            # Dedup por IDENTIDAD: si la firma parpadeó (modelo 3D animado) y este
            # disco ya se emitió en esta sesión S17, no re-emitir (ni re-persistir).
            identity = self._disc_identity(merged)
            if identity in self._disc_emitted_ids:
                return
            self._disc_emitted_ids.add(identity)
            # Verdad de tierra (5R.C): si el disco está EQUIPADO (agente_asignado por el
            # flujo-ancla = dueño certero), registrar firma→dueño al mapa. Candidatos no
            # setean agente_asignado → no contaminan el mapa.
            if merged.agente_asignado_nombre:
                self._record_equip_map(identity, merged.agente_asignado_nombre)
            if self._id_diag_on:
                self._log_id_diag(merged, identity)
            log.info(
                "Disco detectado: set=%s slot=%d main=%s nivel=%d conf=%.2f (agg %dc%s)",
                merged.set_name_canon or merged.set_name_raw, merged.slot,
                merged.main_stat_canon or merged.main_stat_raw, merged.nivel,
                merged.confianza_global, self._disc_agg_cycles,
                "" if mature else " best-effort",
            )
            if self._on_disc:
                try:
                    self._on_disc(merged, state)
                except Exception:
                    log.exception("Error en on_disc S17")

    def _maybe_process_disc(self, frame, state: ScreenState) -> None:
        """
        S17 → handler CONTINUO con aggregator (Fase 1). S3/S6/S7 → one-shot por código
        (un disco visible; reabrir el estado resetea el dedup).
        """
        if state.code == "S17":
            self._process_disc_s17_continuous(frame, state)
            return
        key = state.code
        if self._processed_disc_state_code == key:
            return
        self._processed_disc_state_code = key
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

        # Gate RNF-06: saltar el OCR si el panel de stats no cambió desde el último ciclo.
        # La extracción continua existe para detectar cambio de agente; sin cambio visual no
        # hay nada nuevo que extraer ni re-loggear (el log del controller es edge-triggered).
        # Self-correcting: cualquier cambio (agente nuevo, level-up) supera _S18_SIG_MAX → OCR.
        sig = self._s18_stats_signature(frame)
        if (sig is not None and self._s18_last_sig is not None
                and self._sig_component_diff(sig, self._s18_last_sig) <= _S18_SIG_MAX):
            return
        self._s18_last_sig = sig

        # 2b) Extracción de datos en pantalla (cada ciclo). El log del RESULTADO es
        # edge-triggered (lo emite el controller solo cuando cambia); este marcador
        # per-ciclo queda en debug para no spamear.
        log.debug("[S18] Extrayendo stats de pantalla...")
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
        # Reset de la firma del log de detalle → re-entrar a S8/S19 loguea 1 vez.
        self._last_detail_sig = None

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

        # Edge-triggered: emitir solo cuando la identidad/estado de detalle cambia
        # (antes se logueaba en cada ciclo de cadencia). Se resetea al salir de la
        # familia detalle (_reset_detail_identity) → re-entrar loguea 1 vez.
        sig = (state.code, name, identified, source)
        if sig == self._last_detail_sig:
            return
        self._last_detail_sig = sig

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
        # ([reconocido]/[stats]/[completo]) EDGE-triggered (solo cuando el resultado
        # cambia). El procesamiento sí corre cada ciclo (madura parciales); el
        # post-merge interno quedó en debug.

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
            # Diagnóstico interno del merge (per-ciclo) → debug. El log user-facing
            # de stats lo emite el controller, edge-triggered (solo al cambiar).
            log.debug(
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

    def _sample_s17_owner(self, frame) -> None:
        """Loop rápido (10 fps, 5R.5c): vota el dueño del badge de la grilla por
        firma-de-disco. Acumula confianza por PJ mientras el MISMO disco está en
        pantalla; al cambiar de disco resetea. Esto elimina el parpadeo: en vez de
        que cada frame suelto cante un resultado (un recorte movido → 'incierto', uno
        nítido → 'Yuzuha'), se junta la evidencia y `_assign_s17_pj` usa el ganador.
        """
        sig = self._s17_disc_signature(frame)
        if sig is None:
            return
        if self._s17_owner_sig is None or not self._sig_close(sig, self._s17_owner_sig):
            self._s17_owner_sig = sig          # disco nuevo → empezar votación limpia
            self._s17_owner_votes = {}
            self._s17_free_evidence = 0
            self._s17_samples = 0
            if self._id_diag_on:
                self._id_diag = {"samples": 0, "grid_loc": 0, "grid_match": 0,
                                 "det_loc": 0, "det_match": 0, "grid_votes": {}, "det_votes": {}}
        badge = crop_grid_selected_badge(frame)
        g_name, g_conf = None, 0.0
        if badge is None:
            self._dump_grid_diag(frame, None, None, 0.0, False, sig)   # grid no localizó (NOLOC)
        else:
            g_name, g_conf, rejected = self._identifier.s17_match(badge)
            self._dump_grid_diag(frame, badge, g_name, g_conf, rejected, sig)
            self._s17_samples += 1
            if g_name:
                self._s17_owner_votes[g_name] = self._s17_owner_votes.get(g_name, 0.0) + float(g_conf)
            elif rejected or g_conf < _S17_FREE_CONF:   # crop sin cara (lock/disco/vacío)
                self._s17_free_evidence += 1
        # DETALLE-badge (5R.C.4): localiza ~siempre (incl. cuando el grid da NOLOC) →
        # suma voto del dueño al MISMO acumulador, subiendo el yield del voto. NO toca
        # _s17_samples/free (la detección LIBRE sigue calibrada por el grid). Inerte
        # (sin voto) hasta que la librería de detalle se cosecha.
        det = crop_detail_badge(frame)
        d_name, d_conf = None, 0.0
        if det is not None:
            d_name, d_conf, _drej = self._identifier.s17_match_detail(det)
            if d_name:
                self._s17_owner_votes[d_name] = self._s17_owner_votes.get(d_name, 0.0) + float(d_conf)
        # Instrumentación L.0 (gated): desglose por-disco grid/detalle (loc + match + voto).
        if self._id_diag_on and self._id_diag:
            d = self._id_diag
            d["samples"] += 1
            if badge is not None:
                d["grid_loc"] += 1
                if g_name:
                    d["grid_match"] += 1
                    d["grid_votes"][g_name] = d["grid_votes"].get(g_name, 0.0) + float(g_conf)
            if det is not None:
                d["det_loc"] += 1
                if d_name:
                    d["det_match"] += 1
                    d["det_votes"][d_name] = d["det_votes"].get(d_name, 0.0) + float(d_conf)

    def _dump_grid_diag(self, frame, badge, name, conf: float, rejected: bool, sig) -> None:
        """Diagnóstico de recortes de badge S17 (gated DANIBOD_GRID_DIAG). Por cada
        frame muestreado vuelca el crop de badge + verdicto en el nombre del archivo
        (o la región de grilla cuando la localización falló), capeado por disco. Para
        auditar por qué un disco posado queda 'incierto'/'no localizado'. No toca DB."""
        import os
        d = os.environ.get("DANIBOD_GRID_DIAG")
        if not d:
            return
        try:
            import hashlib
            import cv2
            from pathlib import Path
            key = hashlib.md5(repr(sig).encode()).hexdigest()[:8]
            cnt = self._grid_diag_counts.get(key, 0)
            if cnt >= 12:
                return
            self._grid_diag_counts[key] = cnt + 1
            outdir = Path(d); outdir.mkdir(parents=True, exist_ok=True)
            if badge is not None and getattr(badge, "size", 0):
                tag = (name or ("REJECT" if rejected else "none")).replace(" ", "").replace(":", "")
                cv2.imwrite(str(outdir / f"{key}_{cnt:02d}_badge_{tag}_{conf:.2f}.png"), badge)
            else:
                from app.core.detector import _GRID_REGION
                H, W = frame.shape[:2]
                x0, y0, x1, y1 = _GRID_REGION
                sub = frame[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
                if sub.size:
                    cv2.imwrite(str(outdir / f"{key}_{cnt:02d}_NOLOC.png"), sub)
        except Exception:
            log.debug("grid_diag dump falló", exc_info=True)

    def _log_id_diag(self, merged, identity: str) -> None:
        """Una línea por disco emitido con el desglose de identificación (L.0, gated
        DANIBOD_ID_DIAG): localización + match de grid vs detalle, voto ganador y dueño
        asignado por flujo-ancla. Cruzable con equip_map por `identity` → ubica el cuello
        (¿NOLOC del grid? ¿el detalle no matchea? ¿el voto elige mal?)."""
        d = self._id_diag or {}
        voted = (max(self._s17_owner_votes.items(), key=lambda kv: kv[1])[0]
                 if self._s17_owner_votes else None)

        def _top(v):
            return ",".join(f"{k}:{val:.2f}" for k, val in
                            sorted(v.items(), key=lambda kv: -kv[1])[:3]) or "-"

        log.info(
            "[id_diag] id=%s slot=%s assigned=%s voted=%s samples=%d "
            "grid_loc=%d grid_match=%d det_loc=%d det_match=%d grid_votes=[%s] det_votes=[%s]",
            identity, getattr(merged, "slot", "?"), merged.agente_asignado_nombre or "-",
            voted or "-", d.get("samples", 0), d.get("grid_loc", 0), d.get("grid_match", 0),
            d.get("det_loc", 0), d.get("det_match", 0),
            _top(d.get("grid_votes", {})), _top(d.get("det_votes", {})),
        )

    def _s17_voted_owner(self, frame) -> str | None:
        """Dueño ganador (mayor confianza acumulada) del disco mirado, si la votación
        del loop rápido corresponde a ESTE disco. None si no hay votos confiables."""
        if not self._s17_owner_votes or not self._s17_owner_sig_matches(frame):
            return None
        return max(self._s17_owner_votes.items(), key=lambda kv: kv[1])[0]

    def _s17_owner_sig_matches(self, frame) -> bool:
        sig = self._s17_disc_signature(frame)
        return not (sig is None or self._s17_owner_sig is None
                    or not self._sig_close(sig, self._s17_owner_sig))

    def _s17_is_libre(self, frame) -> bool:
        """True si el disco mirado está LIBRE (nadie lo equipa). CONSERVADOR: exige que
        NUNCA se haya identificado un dueño y que la evidencia de 'libre' (badge en
        reject-set / conf muy baja) sea consistente y mayoritaria. Un frame malo suelto
        (p.ej. Jane rechazada una vez) NO alcanza → queda 'dueño incierto', no LIBRE."""
        if self._s17_owner_votes or not self._s17_owner_sig_matches(frame):
            return False
        return (self._s17_free_evidence >= _S17_FREE_MIN_FRAMES
                and self._s17_free_evidence >= 0.5 * max(1, self._s17_samples))

    def _assign_s17_pj(self, disc: DiscParsed, frame) -> None:
        """
        Resuelve el DUEÑO de un disco S17 con el badge de la grilla + el latch
        (Fase 5R, descriptor robusto). Recorta el badge del tile seleccionado y lo
        identifica:
          - badge ausente → disco sin dueño visible / no equipado → sin asignar.
          - similitud al latch ≥ guarda (o bootstrap) → disco EQUIPADO del PJ actual
            → trust-latch (asigna + cosecha).
          - similitud < guarda → el badge NO es del latch → candidato de la grilla de
            OTRO PJ → se reporta su dueño (`identify_s17`) SIN asignarlo al latch
            (RNF-02: no corromper la build del latch con un disco ajeno).
        """
        latch = self._last_agent_name
        badge = crop_grid_selected_badge(frame) if frame is not None else None
        disc.equip_detectado = badge is not None
        # --- ANCHOR DE FLUJO (5R.5b) ---------------------------------------------
        # Estructura del juego: al abrir/cambiar de slot, el PRIMER disco mostrado es
        # SIEMPRE el equipado por el latch. Un disco en un slot DISTINTO al último
        # asignado ⇒ es el equipado (certero, no depende del crop del badge). Mismo
        # slot + disco distinto (la firma resetea el aggregator) ⇒ candidato.
        slot = disc.slot or 0
        is_equipped = bool(latch) and slot != 0 and slot != self._s17_last_slot
        if is_equipped:
            self._s17_last_slot = slot
            if badge is not None:                      # cosecha con label CERTERO
                if self._identifier.learn_s17(badge, latch) and self._on_diagnostic:
                    self._on_diagnostic(f"[cosecha] badge de {latch} (slot {slot})")
            # Cosecha PARALELA del detalle-badge (5R.C.4): mismo latch certero, librería
            # propia. Localiza ~siempre (no depende del anillo del tile).
            det = crop_detail_badge(frame) if frame is not None else None
            if det is not None:
                self._identifier.learn_s17_detail(det, latch)
            self._set_latch_assignment(disc, latch, 1.0, "equipado")
            return
        if badge is None:
            disc.equip_pj_visual = None
            if latch:
                self._log_s17_assign(
                    ("no_badge", latch), "[S17] disco sin badge de dueño → sin asignar."
                )
            return
        if not latch:
            owner = self._identifier.identify_s17(badge)
            if owner:
                disc.equip_pj_visual = owner[0]
            self._log_s17_assign(
                ("no_latch", owner[0] if owner else "?"),
                "[S17] sin latch · dueño=%s.", owner[0] if owner else "incierto",
            )
            return
        # Mismo slot, disco distinto → CANDIDATO. Si el badge matchea el latch (volviste
        # al equipado) re-confirma; si no, nombra el dueño SIN asignar al latch.
        sim = self._identifier.s17_similarity(badge, latch)
        if sim is not None and sim >= _S17_GUARD_MIN:
            self._set_latch_assignment(disc, latch, round(sim, 3), f"{sim:.3f}")
            return
        # Decisión 3-vías por VOTACIÓN del loop rápido (5R.5c + 5R.B), no por el frame
        # suelto → sin parpadeo: (1) dueño votado, (2) LIBRE consistente, (3) incierto.
        owner = self._s17_voted_owner(frame)
        if owner:
            disc.equip_pj_visual = owner
            disc.equip_libre = False
            self._log_s17_assign(("grid_owner", owner), "[grilla] disco de otro PJ · dueño=%s.", owner)
        elif self._s17_is_libre(frame):
            disc.equip_pj_visual = None
            disc.equip_libre = True
            self._log_s17_assign(("grid_libre",), "[grilla] disco LIBRE (no equipado por nadie).")
        else:
            disc.equip_pj_visual = None
            disc.equip_libre = False
            self._log_s17_assign(("grid_owner", "?"), "[grilla] disco equipado · dueño incierto.")

    def _set_latch_assignment(self, disc: DiscParsed, latch: str, conf: float, sim_str: str) -> None:
        """Asigna el disco equipado al latch (trust-latch) + log."""
        disc.agente_asignado_nombre = latch
        disc.agente_asignado_conf = conf
        disc.equip_pj_visual = latch
        self._log_s17_assign(
            ("confirm", latch), "[S17] asignado a '%s' (latch; sim=%s).", latch, sim_str
        )

    def _log_s17_assign(self, sig, msg, *args) -> None:
        """Loguea la decisión de asignación S17 edge-triggered: 1× por cambio de
        firma (no en cada ciclo del modelo continuo). Re-loguea al transicionar
        entre equipado/otro-PJ/sin-avatar. Reset en _reset_s17_disc_tracking."""
        if sig == self._s17_assign_sig:
            return
        self._s17_assign_sig = sig
        log.info(msg, *args)

    def _process_disc(self, frame, state: ScreenState) -> None:
        try:
            # S17 (disco equipado, "Personalización de pistas") usa el parser
            # ESPACIAL full-frame — más robusto que el per-ROI a 2560×1440.
            # El resto de disc-states (S3/S6/S7) sigue con parse_modal_detalle.
            if state.code == "S17":
                disc, _face = parse_disc_s17_full(frame, self._ocr)
                self._assign_s17_pj(disc, frame)   # identidad por badge de grilla (5R.5)
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
