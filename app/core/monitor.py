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
from app.core.capturer import (
    WindowBounds, capture_window, find_zzz_window,
    get_foreground_window, is_zzz_focused,
)
from app.core.detector import (
    ScreenDetector, ScreenState, TemporalBuffer, AGENT_STATS_STATES,
    extract_s17_slot, extract_s9_slot, polling_cadence_ms,
    _deep_detect_s18, detect_active_tab, selected_avatar_x,
    crop_grid_selected_badge, crop_detail_badge, crop_s9_selected_badge,
)
from app.core.stats_vocab import _norm_key
from app.core.parser_disc import DiscParsed, parse_modal_detalle
from app.core.parser_disc_s17 import (
    parse_disc_s17, parse_disc_s17_full, parse_disc_s9, DiscAggregator, disc_is_mature,
)
from app.core.parser_agent_stats import (
    AgentStatsParsed, parse_agent_stats, AgentStatsAggregator, identify_menu_agent,
)
from app.core.agent_identifier import AgentIdentifier
from app.core.ocr_backend import OcrBackend
from app.core.stats_vocab import _norm_key

log = logging.getLogger(__name__)

# Estados donde hay un disco visible para parsear.
# S17 = vista detalle disco en Personalización de pistas (equipamiento PJ).
_NEW_DISC_STATES = {"S3", "S5", "S6", "S7"}   # discos nuevos (drop / afinación / tienda)
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
# S9 = INVENTARIO GLOBAL de discos: panel derecho = disco seleccionado (parse_disc_s9,
# reusa S17), dueño = badge del tile resaltado. Diff máx de firma para "mismo disco".
_S9_SIG_MAX = 3.0
# Tolerancia de posición x del avatar para considerar "mismo PJ" (avatares
# adyacentes distan ~0.04-0.05 norm; media-ranura como margen anti-jitter).
_AVATAR_X_TOL = 0.025
# Identidad de detalle (S8/S19) por DESCRIPTOR PRIMARIO: nº mínimo de frames CONFIABLES
# (matches no-abstenidos) del avatar de la barra superior antes de fijar la identidad. La
# votación multi-frame evita clavarse en un frame malo (esquina del slider/animación); 2 es
# ~0.2 s al loop rápido (10 fps) → robusto y responsivo. Espejo de _S17_OWNER_MIN_SAMPLES.
_DETAIL_MIN_SAMPLES = 2

# Confianza mínima de un estado NO-detalle para resetear el latch de identidad.
# Un fundido de transición entre pestañas (S12/dark_frame_filter, conf~0) NO debe
# olvidar al PJ — eso causaba el parpadeo "detecta→no reconoce" (Zhu Yuan,
# 2026-06-06). Solo una pantalla no-detalle CONFIRMADA (roster/ciudad) resetea.
_DETAIL_RESET_MIN_CONF = 0.50

# Cosecha (Fase 5R.3): estados con avatar/badge útil + cuántos frames por (PJ,estado).
_HARVEST_STATES = {"S8", "S17", "S18", "S19"}
_HARVEST_CAP = 4

# ROI normalizada (x, y, rw, rh) del título del nodo en S13 (selección de set a farmear).
# Calibrada en vivo 2026-07-08; re-ampliada 2026-07-10: los títulos LARGOS envuelven a DOS
# líneas (p.ej. "Un monstruo y un visitante extraños") y el ROI de 1 línea solo agarraba la
# 2ª → OCR leía "extraños" y no matcheaba. El techo sube a 0.165 y el alto crece a 0.08 para
# cubrir ambas líneas [0.165–0.245]; el subtítulo "Atributos potenciados" (y≥0.258) queda
# excluido. PaddleOCR une las 2 líneas → título completo. Ver Ejemplo_6.png (folder 13).
_S13_TITLE_ROI = (0.43, 0.165, 0.35, 0.08)
# Gate RNF-06: diff medio de la firma 32×32 del ROI del título por debajo del cual se
# considera el MISMO nodo en pantalla → no re-OCR. Espejo de _MENU_SIG_MAX (barra de nombre).
_S13_SIG_MAX = 5.0

# Guarda de asignación S17 (latch + avatar). El PJ asignado a un disco equipado
# sale del LATCH (PJ cuya pantalla se ve, ya confiable); el avatar circular S17 se
# usa solo como chequeo mismo/distinto contra ese latch. Medido 2026-06-06 sobre
# crops reales: same-PJ 0.95–0.99, otro PJ ≤ 0.76 → umbral 0.86 separa limpio.
#   sim None  → primera vez del PJ en S17 → confiar latch + aprender (bootstrap).
#   sim ≥ MIN → avatar confirma el latch → asignar.
#   sim < MIN → avatar es de OTRO PJ (disco del grid) → abstener (preservar DB).
_S17_GUARD_MIN = 0.86
# Conf mínima para INTENTAR el desempate por contexto (build) cuando el badge se abstuvo
# por margen chico: solo desempatamos matches VISUALMENTE FUERTES pero ambiguos por
# look-alike (Velina@0.97, Ye Shunguang@0.84). Descarta los reject/low-conf (Ej10/12 @0.50).
_S9_TIEBREAK_CONF_MIN = 0.80
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
# Tope de re-lecturas de la grilla S5 antes de emitir el preview aunque no haya convergido (badge
# genuinamente ilegible). Cubre de sobra la animación de revelado; evita re-OCR indefinido.
_S5_GRID_MAX_TRIES = 6
# Mínimo de tiles (por multiset de slots) que deben cambiar para considerar la grilla una tanda
# NUEVA y re-emitir el preview. Clickear un disco resalta su tile y mete jitter de 1-2 badges → NO
# es una tanda nueva; re-afinar (botón "Afinar ×N") reparte slots al azar → cambia ~todos. Un piso
# en 3 separa el flicker por-clic de la re-afinación real (QA 2026-07-10: el preview spameaba 10
# líneas por cada clic porque el re-parseo leía la tupla apenas distinta cada vez).
_S5_BATCH_MIN_DIFF = 3
# Vigencia (s) del set evocado en S4 para nombrar el preview S5. Una afinación sigue inmediata al
# selector; la ventana generosa cubre re-afinaciones desde la misma pantalla sin volver a S4.
_S5_EVOKED_TTL_S = 600.0

# 5R.L.6 — Refuerzo del reconocimiento del dueño (multi-frame warmup). El disco se EMITE
# apenas el OCR madura, lo que a veces pasa en el 1er frame del disco (al navegar desde un
# disco viejo, la cadencia ya está vencida → dispatch inmediato). Con 1 sola muestra del
# loop de owner, el voto es frágil: la grilla localiza ~81%/frame (ese frame puede ser
# NOLOC) y el detalle (avatar chico, margen chico) se abstiene seguido → el disco sale con
# "dueño incierto" aunque al re-visitarlo (más frames) se reconozca. Fix: si el disco maduró
# pero el dueño quedó INCIERTO, DIFERIR la emisión hasta juntar _S17_OWNER_MIN_SAMPLES
# pasadas del loop rápido (10fps) — cada superficie consigue varios intentos independientes
# y los votos se acumulan. SIN re-OCR (RNF-06): se re-lee el merge con aggregator.current().
# Acotado: si el dueño no aparece tras el warmup (o se llega al techo de ciclos), emite igual
# (incierto/libre, RNF-02 abstención). Los equipados (latch certero) y los ya-votados NO
# esperan → cero latencia extra; el costo se paga solo donde había riesgo de incierto.
_S17_OWNER_MIN_SAMPLES = 4     # pasadas del loop rápido para "calentar" el voto del dueño
_S17_WARM_CADENCE_MS = 100     # mientras calienta, re-chequear el voto rápido (no esperar 1s)

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
# Nombre del set (título): texto estático; un set distinto = diff grande, mismo set = ~0.
# QA 2026-06-20: separa discos de SET distinto en el MISMO slot (Monarca↔Nana, ambos main
# HP 2200, que el detail solo no distinguía). DETAIL bajó 5.0→3.5 para captar mejor las
# diferencias de substats entre discos del MISMO set (el bloque es texto estático → sin
# riesgo de falso-nuevo por animación).
_S17_SIG_NAME_MAX = 3.0
_S17_SIG_DETAIL_MAX = 3.5
_S17_SIG_HEX_MAX = 3.0
# Gate de OCR S18 (RNF-06): umbral de diff de la firma del panel de stats. Sensible
# (bajo) a propósito — errar hacia re-OCR de más (sin riesgo) antes que saltarse un
# cambio real (stats viejos). El cambio de agente es un diff enorme; el shimmer de
# fondo del panel queda por debajo.
_S18_SIG_MAX = 2.5
# Umbral de la componente NOMBRE+banner de la firma S18 (QA 2026-06-20): un cambio de
# agente mueve mucho esta región (nombre/rol/elemento distintos); el shimmer del mismo
# agente queda bien por debajo. Algo más holgado que el de stats por los bordes del texto.
_S18_SIG_NAME_MAX = 3.0
# Gate del menú de personajes S15 (Fase M.1, RNF-06): firma 32×32 gris de la barra del
# nombre (bottom-left); re-OCR solo si cambió el PJ seleccionado. Un cambio de PJ mueve mucho
# el texto del nombre (diffs reales medidos 12-37); el shimmer/anti-aliasing del MISMO PJ
# queda por debajo. Subido 3.0→6.0 (QA 2026-06-21): a 3.0 el ruido del mismo PJ podía cruzar
# el umbral → re-OCR espurio cada segundo (presión de memoria, RNF-06); 6.0 absorbe ese ruido
# y conserva margen amplio (≈2×) contra el cambio real de PJ.
_MENU_SIG_MAX = 6.0
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

# Voto del dueño grid+detail (5R.L.3) — acumuladores SEPARADOS + política con garantía
# RNF-02 (cero wrong). El GRID es la fuente primaria (sus reads son 0-wrong, verificado en
# QA: solo-grilla = 62% ok / 0% wrong). El DETAIL (post-fix L.2b: crop Hough, 90% top-1 /
# 0 wrong cross-domain) SUMA yield en los discos donde el grid da NOLOC, pero su margen
# per-frame es menor → para PROPONER un dueño SIN respaldo del grid exige evidencia
# acumulada fuerte + dominancia (no puede introducir un PJ que el grid nunca propuso salvo
# este guard alto). Calibrables en L.4 (QA en vivo).
# Un voto del detalle YA pasó su propio guard (conf≥0.80 + margen + reject-set en
# `s17_match_detail`), así que UN frame confiable es señal válida. En vivo los discos
# reciben ~1 frame por visita (el usuario navega rápido) → exigir ≥2 frames dejaba a
# Yanagi/Seth (det@1.00/0.81, 1 frame) en "incierto" (bug QA 2026-06-18). Bajado 1.30→0.80
# = "al menos un frame confiable del detalle". La DOMINANCIA sigue cortando empates
# (dos PJs alternando un frame c/u → se abstiene).
_DET_SOLO_MIN_SCORE = 0.80   # suma de conf del detail ganador (≈ 1 frame confiable)
_DET_SOLO_DOMINANCE = 1.50   # ganador ≥ 1.5× el 2º acumulado (sin empate cerrado)

# 5R.L.7.3 — PRESENCIA de avatar en el detalle (¿el crop es una cara o un crop espurio?).
# El localizador del detalle a veces recorta el texto '(N)' del nº de slot en discos LIBRES
# (QA 2026-06-20: '(1)' → conf 0.64-0.66, margen 0.02-0.054, INESTABLE). Un avatar REAL en
# librería matchea a conf ~1.0 (vota); uno sin ref con cara clara tiene margen amplio. El
# texto da conf baja Y margen chico. Cuenta como "avatar presente" (bloquea LIBRE) solo si
# no-rejected y (conf≥CONF o margen≥MARGIN). Calibrado sobre 163 avatares reales (conf p5=1.0,
# margen p5=0.092) + textos conocidos: 0/163 avatares caen ausente; los textos quedan fuera.
_DET_PRESENCE_CONF = 0.86      # = guard de voto: un match así de fuerte ya es un avatar real
_DET_PRESENCE_MARGIN = 0.10    # margen al 2º (avatares reales p5=0.092; textos ≤0.054 casi siempre)


def _vote_winner(votes: dict[str, float]) -> tuple[str | None, float, float]:
    """(nombre, score_1º, score_2º) del dict de votos acumulados, o (None, 0, 0)."""
    if not votes:
        return None, 0.0, 0.0
    ordered = sorted(votes.items(), key=lambda kv: -kv[1])
    name, score = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    return name, score, second


def _decide_s17_owner(grid_votes: dict[str, float],
                      det_votes: dict[str, float],
                      latch: str | None = None) -> tuple[str | None, str | None]:
    """Decide el dueño votado de un disco CANDIDATO combinando grid + detail con
    garantía RNF-02. Devuelve (owner|None, source):
      - grid-PRIMARIO: si el grid votó, manda el grid; el detail solo corrobora (no puede
        introducir otro PJ). source='grid+det' si coinciden, 'grid' si no.
      - detail-SOLO: si el grid no votó (NOLOC), el detail propone dueño SOLO con score
        acumulado ≥ _DET_SOLO_MIN_SCORE y dominancia ≥ _DET_SOLO_DOMINANCE. source='det'.
      - si nada alcanza, (None, None) → incierto (abstención antes que error).
    `latch` (opcional) = agente cuya página se está viendo; activa el guard anti-imán.
    """
    g_name, _gs, _g2 = _vote_winner(grid_votes)
    d_name, d_score, d2 = _vote_winner(det_votes)
    if g_name:
        return g_name, ("grid+det" if d_name == g_name else "grid")
    if d_name and d_score >= _DET_SOLO_MIN_SCORE and d_score >= _DET_SOLO_DOMINANCE * max(d2, 1e-9):
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
        owner_tiebreaker=None,                                  # OwnerTiebreaker opcional
        farm_session=None,                                      # FarmSession opcional (gate S2)
        farm_node_catalog=None,                                 # FarmNodeCatalog opcional (predicción S13)
        set_badge_matcher=None,                                 # SetBadgeMatcher opcional (set por badge S2)
        capture_only_focused: bool = True,                      # gate anti-FP por foco de ventana
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
        # --- S9 (inventario global): mismo patrón aggregator/dedup, estado propio ---
        self._s9_aggregator = DiscAggregator()
        self._s9_agg_sig = None           # firma-ancla del disco S9 que se fusiona
        self._s9_emitted: bool = False    # ya se emitió (persist/log) este disco S9
        self._s9_agg_cycles: int = 0
        self._s9_warming: bool = False     # maduró pero el dueño no resolvió → reintentar badge
        # --- S3 (modal de drop farmeado): mismo patrón aggregator/dedup, sin dueño ni warmup ---
        self._s3_aggregator = DiscAggregator()
        self._s3_agg_sig = None            # firma-ancla del modal de drop que se fusiona
        self._s3_emitted: bool = False
        self._s3_agg_cycles: int = 0
        # Identidades de discos de drop YA emitidos en la sesión de farmeo. Propio de S3 (NO el
        # compartido _disc_emitted_ids, que _reset_detail_identity borra al volver a S2) → así
        # re-abrir un disco ya capturado avisa "ya capturado" y no re-dispara el toast. Se limpia
        # con F8 (o al reiniciar). Limitación: dos farmeos con un disco IDÉNTICO (mismo
        # set+slot+stats) dedupean el 2º — caso raro, aceptado.
        self._s3_emitted_ids: set = set()
        # S5 (resultado de afinación tienda música): mismo patrón continuo que S3 (ficha izquierda,
        # el usuario clickea cada disco de la grilla → se re-extrae). Dedup por identidad propio.
        self._s5_aggregator = DiscAggregator()
        self._s5_agg_sig = None
        self._s5_emitted: bool = False
        self._s5_agg_cycles: int = 0
        self._s5_emitted_ids: set = set()
        # Preview de la grilla de resultado (slots+set de TODOS los discos evocados, antes de ver
        # detalles). `_s5_grid_slots` = secuencia de slots de la última tanda previsualizada; si
        # cambia (re-afinación desde la misma pantalla) → nueva tanda → re-preview. Como el
        # resumen por-disco de S2, pero re-emite por tanda, no solo al entrar.
        self._s5_grid_slots: tuple = ()
        # Set evocado en el selector S4 (id, nombre_canon, ts). El S4 lee el género COMPLETO y limpio;
        # el preview S5 lo usa como nombre del set porque el label del tile se trunca en la celda
        # angosta y los nombres largos no resuelven desde ahí. Válido dentro de la ventana de farmeo.
        self._s4_evoked_set: tuple[int, str, float] | None = None
        # DEBOUNCE de la grilla: la grilla se revela con ANIMACIÓN (los tiles entran escalonados) y
        # el OCR de grilla tarda ~2.7s → un frame temprano lee las filas inferiores en blanco →
        # badge '?'. Confirmamos la lectura con 2 pasadas iguales antes de emitir, y re-chequeamos
        # cada ciclo hasta estabilizar. `_pending` = última secuencia leída sin confirmar;
        # `_settled` = preview de la tanda actual ya finalizado; `_tries` = tope anti-cuelgue.
        self._s5_grid_pending: tuple | None = None
        self._s5_grid_settled: bool = False
        self._s5_grid_tries: int = 0
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
        # Votación multi-frame del descriptor de fila (S8/S19): confianza acumulada por PJ
        # + nº de muestras confiables, para la ranura de avatar actual. Se reinicia al mover
        # el avatar (otro PJ) o al salir de la familia detalle. Ver _DETAIL_MIN_SAMPLES.
        self._detail_votes: dict[str, float] = {}
        self._detail_samples: int = 0
        # Ancla de la VOTACIÓN en curso, separada de `_agent_anchor_x` (ancla de la identidad
        # ya CONFIRMADA). Dos anclas porque el auto-hide de la barra devuelve posiciones
        # espurias del highlight desvaneciéndose: sin separarlas, un parpadeo se confunde con
        # un cambio de PJ y se descartaba al ya reconocido.
        self._detail_vote_x: float | None = None
        # Origen con el que se CONFIRMÓ la ranura ("avatar" | "heredado"). Permite volver a
        # la etiqueta real al re-confirmar, tras haber pasado por "sostenido".
        self._detail_confirmed_source: str | None = None
        # Firma del último log de detalle S8/S19 emitido (edge-triggered): solo se
        # re-loguea cuando (code, name, identified, source) cambia.
        self._last_detail_sig: tuple | None = None
        # Menú de personajes S15 (Fase M.1): firma del nombre (gate RNF-06) + firma del
        # log emitido (edge-triggered). Se resetean al salir de S15 → re-entrar re-loguea.
        self._menu_last_sig = None
        self._last_menu_log_sig: tuple | None = None
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
        # Acumuladores de voto SEPARADOS (5R.L.3): grid (primario, 0-wrong) y detail
        # (boost de yield bajo guard). La decisión la toma `_decide_s17_owner`.
        self._s17_grid_votes: dict[str, float] = {}
        self._s17_det_votes: dict[str, float] = {}
        self._s17_free_evidence: int = 0   # frames con badge sin cara (5R.B)
        self._s17_samples: int = 0         # frames muestreados del disco actual
        # 5R.L.7.3 — PRESENCIA de badge (estructural, desacoplada de identidad): cuántos
        # frames del disco actual tuvieron / no tuvieron avatar de dueño en cada superficie.
        # El detail (loc ~100%) ARBITRA libre/equipado; el grid (post-gate L.7.2) corrobora.
        self._s17_detail_present: int = 0
        self._s17_detail_absent: int = 0
        self._s17_grid_present: int = 0
        self._s17_grid_absent: int = 0
        # 5R.L.6 — warmup del dueño: pasadas TOTALES del loop rápido para el disco actual
        # (cuenta todas, no solo las localizadas) + flag de "maduró pero dueño aún frío".
        self._s17_owner_passes: int = 0
        self._s17_warming: bool = False
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
        # Re-captura QA (DANIBOD_RECAPTURE): desactiva la dedup de sesión por identidad
        # → cualquier disco re-emite al volver a verlo. Para QA (confirmar consistencia,
        # re-testear tras un fix). En producción queda apagado (dedup normal: ahorro de
        # OCR + sin spam). El parpadeo del modelo 3D puede re-emitir el mismo disco, pero
        # parse_id_diag dedupea por id → inofensivo en QA.
        self._recapture_on: bool = bool(os.environ.get("DANIBOD_RECAPTURE"))
        # Última identidad de disco emitida (re-captura estilo S18): re-emite solo al
        # CAMBIAR de disco, no en cada parpadeo del modelo 3D (que reabre la firma visual).
        self._last_emitted_identity = None
        # Cosecha de frames etiquetados por latch (Fase 5R.3, solo si DANIBOD_HARVEST
        # está seteado). Cap por (PJ, estado) para no spamear. Read-only: solo escribe
        # PNGs de frame completo a la carpeta indicada, nunca toca la DB.
        self._harvest_counts: dict[tuple[str, str], int] = {}
        self._window: WindowBounds | None = None
        # Gate anti-FP por foco (RNF-03 friendly): capturar la región de pantalla del
        # juego SOLO cuando ZenlessZoneZero.exe está en primer plano. Si el usuario pone
        # otra ventana encima (p.ej. el Explorador), mss capturaría esos píxeles ajenos →
        # FP en el log. `_focus_paused` es edge-trigger para emitir el diagnóstico 1× por
        # transición (no spamear) mientras el juego esté en segundo plano.
        self._capture_only_focused = capture_only_focused
        self._focus_paused: bool = False
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
        # Desempate de dueño por contexto (build) cuando el badge se abstiene por margen
        # chico entre look-alikes. Opcional: si es None, el comportamiento es el de antes
        # (abstención = sin dueño). Lo inyecta el controller con acceso a la DB.
        self._owner_tiebreaker = owner_tiebreaker
        # Gate de confianza por flujo de farmeo (S13→S14→S2→S3). Opcional: si es None, el
        # resumen S2 sale siempre como tentativo. Lo inyecta el controller. Ver farm_session.py.
        self._farm_session = farm_session
        # Catálogo nodo(S13)→2 sets. Si está presente, en S13 se OCRiza el título del
        # nodo y se predicen los sets que dropea (display-only, ver _process_s13_node_title).
        self._farm_node_catalog = farm_node_catalog
        # Matcher de set por badge del disco (S2). Restringido a la predicción de S13.
        self._set_badge_matcher = set_badge_matcher
        # S2 (resultados de farmeo): resumen display-only 1× por entrada al estado.
        self._s2_reported: bool = False
        # S13 (selección de set a farmear): predicción display-only EDGE-triggered por nodo.
        # Se re-emite al CAMBIAR de nodo (aunque se siga en S13), incl. volver a uno ya visto.
        # `_s13_last_sig` gatea el re-OCR (RNF-06); `_s13_last_node` deduplica la emisión.
        self._s13_last_sig = None
        self._s13_last_node: str | None = None

        # S4 (selector tienda música): predicción display-only edge-triggered por (set, slot).
        # `_s4_last_sig` gatea el re-OCR del género (RNF-06); `_s4_last_key` deduplica la emisión;
        # `_s4_last_set` cachea el último (set_id, género) para no re-resolver si el género no cambió.
        self._s4_last_sig = None
        self._s4_last_key: tuple[int, int | None] | None = None
        self._s4_last_set: tuple[int | None, str | None] | None = None

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
            self._s3_emitted_ids.clear()   # F8 re-captura también los drops S3 ya vistos
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
            if raw_state.code != "S9":
                # Fuera de S9 → olvidar el tracking del disco del inventario global.
                self._reset_s9_disc_tracking()
            if raw_state.code != "S3":
                # Fuera de S3 → olvidar el tracking del modal de drop farmeado.
                self._reset_s3_disc_tracking()

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
                # 5R.L.6: mientras un disco S17 espera calentar el voto del dueño (incierto en
                # el 1er frame), re-chequear rápido en vez de esperar el ciclo completo de 1s.
                # No agrega OCR (el path de warmup re-lee el merge); solo apura la re-decisión.
                if (active_state.code == "S17" and self._s17_warming) or \
                        (active_state.code == "S9" and self._s9_warming):
                    cadence_ms = _S17_WARM_CADENCE_MS
                elapsed_ms = (now - last_process_time) * 1000
                forced = self._force_event.is_set()
                # S18 (stats) y S8/S19 (detalle de agente) se re-procesan en cada
                # ciclo de cadencia aunque el estado no cambie (logging persistente).
                # El resto de estados procesa solo en la transición (voted_state no
                # nulo) o por F8 forzado.
                # S17 es CONTINUO (Fase 1): se re-procesa cada cadencia como S18/S8/S19.
                # S15 (menú de personajes, M.1) también: al cambiar de PJ SIN cambiar de
                # pantalla no hay transición → sin re-procesar quedaba pegado en el 1er PJ
                # (QA 2026-06-21). El gate de firma del nombre evita el re-OCR si no cambió.
                # S13 (selección de nodo a farmear): al cambiar de nodo SIN cambiar de pantalla
                # no hay transición → sin re-procesar quedaba pegado en el 1er nodo (QA
                # 2026-07-08, mismo caso que S15). El gate de firma del título evita el re-OCR
                # si el nodo no cambió.
                # S3 (detalle del drop farmeado): handler CONTINUO con aggregator y techo de
                # ciclos, como S17/S9. Sin re-procesar, el techo (best-effort) nunca se alcanza y
                # un disco que no madura en el 1er frame (p.ej. slot-OCR falla → slot=0) quedaba
                # estancado sin emitir (QA 2026-07-09). El gate _s3_emitted corta el re-OCR al
                # emitir; re-extraer da más chances de leer bien el slot.
                # S10 (modal de mejora): CONTINUO para trackear la subida de nivel PRE→POST. Al
                # entrar dispara el PRE por transición, pero el "Mejorar" NO cambia de pantalla →
                # sin re-despacho, `on_s10_update` nunca vería el nuevo nivel (QA 2026-07-10). El
                # gate por firma de la barra de nivel evita re-OCR mientras no cambie.
                # S20 (popup vuelto de materiales): CONTINUO para refrescar el timer del pendiente
                # cada ciclo mientras el popup se muestra (evita que expire por la espera del click).
                continuous = active_state.code in _CONTINUOUS_STATES or active_state.code in ("S17", "S15", "S9", "S13", "S3", "S4", "S5", "S10", "S20")
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

        # Gate por foco (anti-FP): si el juego NO está en primer plano, no capturamos la
        # región (evita leer píxeles de una ventana ajena superpuesta, p.ej. el Explorador).
        # Edge-trigger: 1 diagnóstico al pausar y 1 al reanudar; NO anular self._window
        # (para no forzar re-búsqueda de ventana en cada frame de pausa).
        if self._capture_only_focused and not is_zzz_focused(
            get_foreground_window(), self._window.hwnd
        ):
            if not self._focus_paused:
                self._focus_paused = True
                self._emit_diagnostic("juego en segundo plano — captura en pausa")
            time.sleep(0.3)
            return None
        if self._focus_paused:
            self._focus_paused = False
            self._emit_diagnostic("juego enfocado — captura reanudada")

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
        # Gate de farmeo: alimentar el contexto de flujo en CADA ciclo (arma con S13/S14).
        if self._farm_session is not None:
            self._farm_session.on_state(state.code, time.monotonic())
        if state.code != "S2":
            self._s2_reported = False
        if state.code != "S13":
            self._s13_last_sig = None
            self._s13_last_node = None
        if state.code != "S4":
            self._s4_last_sig = None
            self._s4_last_key = None
            self._s4_last_set = None
        # Al RE-ENTRAR a S3 (abrir otro disco desde S2), empezar captura fresca: dos discos del
        # mismo set tienen firma parecida y el dedup por firma no siempre los separa. El dedup por
        # IDENTIDAD (_disc_emitted_ids: set+slot+stats) evita emitir dos veces el mismo disco →
        # cada disco abierto se captura, sin duplicar (checklist de farmeo, QA 2026-07-08).
        if state.code == "S3" and prev_code != "S3":
            self._s3_aggregator.reset()
            self._s3_agg_sig = None
            self._s3_emitted = False
            self._s3_agg_cycles = 0
        # S5 (resultado de afinación): al RE-ENTRAR, captura fresca. El dedup por identidad
        # (_s5_emitted_ids) evita re-emitir el mismo disco al clickear entre tiles de la grilla.
        if state.code == "S5" and prev_code != "S5":
            self._s5_aggregator.reset()
            self._s5_agg_sig = None
            self._s5_emitted = False
            self._s5_agg_cycles = 0
            self._s5_grid_slots = ()   # re-entrar → re-emitir el preview de la grilla
            self._s5_grid_pending = None
            self._s5_grid_settled = False
            self._s5_grid_tries = 0
        self._handle_upgrade(frame, state, prev_code)
        # Menú de personajes (Fase M.1): al salir de S15, olvidar la firma del nombre y del
        # log → re-entrar re-identifica y re-loguea. Barato (set a None cada frame no-S15).
        if state.code != "S15":
            self._menu_last_sig = None
            self._last_menu_log_sig = None
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
        elif state.code == "S9":
            # Inventario global de discos: capturar el disco SELECCIONADO (panel derecho,
            # reusa parse_disc_s17 vía parse_disc_s9) + dueño por badge del tile → sync.
            self._process_disc_s9_continuous(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S15":
            # Menú de personajes (Fase M.1): reconocer al PJ SELECCIONADO por el nombre
            # bottom-left → log. Informativo (no escribe DB, no toca el latch de detalle).
            self._process_agent_menu(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S13":
            # Selección de set a farmear: OCR del título del nodo → predecir los 2 sets que
            # dropea (display-only). La predicción se guarda en FarmSession para restringir
            # el matcher de badges en S2. No persiste ni puntúa.
            self._process_s13_node_title(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S4":
            # Selector de tienda de música (Orphie): OCR del género (=set) + slot preseleccionado
            # del hexágono → predecir el farmeo (display-only, alimenta FarmSession como S13).
            self._process_s4_music_selector(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S2":
            # Resultados de farmeo: resumen display-only (discos tier S en la grilla) con el
            # contexto de confianza de FarmSession. No persiste ni puntúa (eso es S3).
            self._process_s2_resultado(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
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

    def _process_s2_resultado(self, frame, state: ScreenState) -> None:
        """Resultados de farmeo (S2): detecta discos tier S en la grilla (display-only) y
        emite un resumen 1× por entrada al estado. El contexto de confianza lo da FarmSession
        (flujo S13→S14→S2 = farmeo real; sin flujo = tentativo). No persiste ni puntúa — la
        captura completa llega al abrir cada disco en S3."""
        if self._s2_reported:
            return
        self._s2_reported = True
        try:
            from app.core.parser_s2 import parse_s2_resultado
            res = parse_s2_resultado(frame)
        except Exception:
            log.exception("Error parseando resultados S2")
            return
        if self._id_diag_on:
            log.info("[s2_diag] has_s_discs=%s gold_frac=%.3f n_s=%d",
                     res.has_s_discs, res.gold_frac, res.n_s_approx)
        armado = self._farm_session is not None and self._farm_session.is_armed(time.monotonic())
        contexto = "flujo" if armado else "tentativo"
        if res.has_s_discs:
            msg = (f"[farmeo] resultados: {res.n_s_approx} disco(s) tier S visibles "
                   f"· contexto={contexto}")
            log.info("Farmeo detectado: %d disco(s) S · contexto=%s", res.n_s_approx, contexto)
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(msg)
                except Exception:
                    log.debug("on_diagnostic S2 falló", exc_info=True)
        # Fase B: detalle por disco (slot + set por badge), restringido a la predicción de S13.
        self._process_s2_tiles(frame, contexto)

    def _process_s2_tiles(self, frame, contexto: str) -> None:
        """Por cada tile de la grilla S2: leer slot (OCR) + reconocer set (badge, restringido a
        los 2 sets predichos en S13) → línea display-only por disco. Sin predicción de S13 →
        abstención (open-set best-effort: futuro). No persiste ni puntúa (RNF-06/RNF-02)."""
        if self._farm_session is None:
            return
        pred = self._farm_session.predicted(time.monotonic())
        node = pred[0] if pred else None
        cand_en = [en for _sid, en in pred[1]] if pred else []
        try:
            from app.core.parser_s2 import tile_boxes, crop_tile_center, read_tile_slot, tile_rarity
            boxes = tile_boxes(frame)
        except Exception:
            log.exception("Error localizando tiles S2")
            return
        # Solo los discos S CONSERVADOS (dorados): los de menor rareza se auto-desmontan y no
        # tienen slot → no vale reportarlos ni cosecharlos (pedido del usuario 2026-07-08).
        s_boxes = [b for b in boxes if tile_rarity(frame, b) == "S"]
        # Cosecha opcional de tiles reales (etiquetados por nodo+slot) para construir refs del
        # matcher (el render de catálogo no transfiere — §8.1). Independiente de la predicción.
        self._maybe_harvest_s2(frame, s_boxes, node)
        if self._set_badge_matcher is None or not cand_en:
            return
        # Etiqueta de los 2 candidatos (para mostrar cuando el matcher se abstiene).
        cand_txt = " o ".join(cand_en)
        for box in s_boxes:
            try:
                slot = read_tile_slot(frame, box, self._ocr)
                center = crop_tile_center(frame, box)
                match = self._set_badge_matcher.identify(center, cand_en)
            except Exception:
                log.debug("tile S2 falló", exc_info=True)
                continue
            slot_txt = str(slot) if slot else "?"
            set_txt = match.name if match.name else f"? ({cand_txt})"
            msg = (f"[disco] slot {slot_txt} · {set_txt} (conf {match.conf:.2f}) "
                   f"· contexto={contexto}")
            log.info("S2 disco: slot=%s set=%s conf=%.2f", slot_txt, set_txt, match.conf)
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(msg)
                except Exception:
                    log.debug("on_diagnostic S2 tile falló", exc_info=True)

    def _maybe_harvest_s2(self, frame, boxes, node: str | None) -> None:
        """Si DANIBOD_S2_HARVEST está seteado, vuelca por cada tile su recorte de centro (arte
        del disco, entrada del matcher) + el tile completo, etiquetados por nodo + slot leído.
        Sirve para construir refs REALES del matcher (etiqueta final = set que confirma S3).
        Solo escribe PNGs; nunca toca la DB. Una pasada por entrada a S2 (guardado por _s2_reported)."""
        import os
        d = os.environ.get("DANIBOD_S2_HARVEST")
        if not d or not boxes:
            return
        try:
            import cv2
            from pathlib import Path
            from app.core.parser_s2 import crop_tile_center, read_tile_slot
            from app.core.stats_vocab import _norm_key
            out = Path(d)
            out.mkdir(parents=True, exist_ok=True)
            node_k = (_norm_key(node) or "sinnodo") if node else "sinnodo"
            ts = int(time.time())
            n = 0
            for box in boxes:
                slot = read_tile_slot(frame, box, self._ocr)
                base = f"{node_k}__slot{slot if slot else 'x'}__r{box.row}c{box.col}__{ts}"
                cv2.imwrite(str(out / f"{base}__center.png"), crop_tile_center(frame, box))
                cv2.imwrite(str(out / f"{base}__tile.png"), frame[box.y0:box.y1, box.x0:box.x1])
                n += 1
            log.info("[s2_harvest] %d tiles volcados a %s (nodo=%s)", n, d, node or "-")
            if self._on_diagnostic:
                self._on_diagnostic(f"[s2_harvest] {n} tiles → {d}")
        except Exception:
            log.debug("s2 harvest falló", exc_info=True)

    @staticmethod
    def _s13_title_signature(frame):
        """Firma 32×32 gris del ROI del título del nodo (S13), sin OCR (RNF-06). Gatea el
        re-OCR: si no cambió el título en pantalla, no vale re-leer. None si no se puede."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            h, w = frame.shape[:2]
            x, y, rw, rh = _S13_TITLE_ROI
            sub = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
            if sub.size == 0:
                return None
            return cv2.cvtColor(
                cv2.resize(sub, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return None

    @staticmethod
    def _s4_genre_signature(frame):
        """Firma 32×32 gris del ROI del nombre del género (S4), sin OCR (RNF-06). Gatea el
        re-OCR: si el género en pantalla no cambió, no vale re-leer. None si no se puede."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            from app.core.parser_s4 import _S4_GENRE_ROI
            h, w = frame.shape[:2]
            x0, y0, x1, y1 = _S4_GENRE_ROI
            sub = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
            if sub.size == 0:
                return None
            return cv2.cvtColor(
                cv2.resize(sub, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return None

    def _process_s4_music_selector(self, frame, state: ScreenState) -> None:
        """Selector de tienda de música (S4): OCR del género (= un set de la DB) + slot
        preseleccionado del hexágono → predecir el farmeo. Guarda la predicción en `FarmSession`
        (como S13). Display-only: emite un diagnóstico, no persiste ni puntúa.

        Edge-triggered por (set_id, slot): mientras se cambia de género/slot el estado sigue
        siendo S4, así que se re-emite al cambiar cualquiera. Gate RNF-06: el género (OCR) solo
        se re-lee si su firma de ROI cambió; el slot (sin OCR) se lee cada frame. Se resetea al
        salir de S4 (ver _dispatch_state)."""
        if self._farm_session is None or self._set_repo is None:
            return
        from app.core.parser_s4 import read_music_genre, read_preselected_slot
        slot = read_preselected_slot(frame)   # barato, sin OCR
        # Gate de re-OCR del género por firma de ROI.
        sig = self._s4_genre_signature(frame)
        unchanged = (sig is not None and self._s4_last_sig is not None
                     and self._sig_component_diff(sig, self._s4_last_sig) <= _S13_SIG_MAX)
        if unchanged and self._s4_last_set is not None:
            set_id, genre = self._s4_last_set
        else:
            self._s4_last_sig = sig
            genre = read_music_genre(frame, self._ocr)
            set_id = self._set_repo.resolve_id(genre) if genre else None
            self._s4_last_set = (set_id, genre)
        if self._id_diag_on:
            log.info("[s4_diag] genre=%r → set_id=%s slot=%s", genre, set_id, slot)
        if set_id is None:
            return   # sin match confiable (frame de transición / género no resuelto) → reintenta
        key = (set_id, slot)
        if key == self._s4_last_key:
            return   # misma (set, slot) ya emitida → no re-loguear
        self._s4_last_key = key
        entry = next((e for e in self._set_repo.get_all() if e.id == set_id), None)
        nombre = entry.nombre if entry else (genre or "")
        nombre_en = entry.nombre_en if entry else ""
        self._s4_evoked_set = (set_id, nombre, time.monotonic())   # nombre limpio para el preview S5
        self._farm_session.set_prediction(nombre, [(set_id, nombre_en)], time.monotonic())
        slot_str = str(slot) if slot else "aleatorio"
        msg = f"[tienda] evoca: {nombre} · slot {slot_str}"
        log.info("Farmeo S4 (tienda música): set '%s' (id=%d) · slot %s", nombre, set_id, slot_str)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.debug("on_diagnostic S4 falló", exc_info=True)

    def _process_s13_node_title(self, frame, state: ScreenState) -> None:
        """Selección de set a farmear (S13): OCR del título del nodo → predecir los 2 sets
        que dropea (`FarmNodeCatalog`) y guardarlos en `FarmSession` para restringir el
        matcher de badges en S2. Display-only: emite un diagnóstico, no persiste ni puntúa.

        EDGE-triggered por nodo (NO 1× por entrada a S13): mientras se navega entre nodos el
        estado sigue siendo S13, así que se re-emite cada vez que CAMBIA el título — incluido
        volver a un nodo ya visto. Gate RNF-06: solo re-OCR si la firma del ROI del título
        cambió (misma selección en pantalla → no re-leer). Sin acumular memoria (solo la última
        firma + el último nodo). Se resetea al salir de S13 (ver _dispatch_state)."""
        if self._farm_node_catalog is None or self._farm_session is None:
            return
        # Gate de re-OCR: si el título en pantalla no cambió, no re-leer (RNF-06).
        sig = self._s13_title_signature(frame)
        if (sig is not None and self._s13_last_sig is not None
                and self._sig_component_diff(sig, self._s13_last_sig) <= _S13_SIG_MAX):
            return
        self._s13_last_sig = sig
        try:
            h, w = frame.shape[:2]
            x, y, rw, rh = _S13_TITLE_ROI
            crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
            if crop.size == 0:
                return
            text, _conf = self._ocr.text(crop, psm=7, lang="spa")
        except Exception:
            log.exception("Error OCR título S13")
            return
        node = self._farm_node_catalog.match_title(text or "")
        if self._id_diag_on:
            log.info("[s13_diag] ocr_title=%r → node=%s", text,
                     node.titulo_es if node else None)
        if node is None:
            return   # sin match confiable (p.ej. frame de transición) → reintenta al cambiar
        if node.titulo_es == self._s13_last_node:
            return   # mismo nodo ya emitido → no re-loguear
        self._s13_last_node = node.titulo_es
        sets = [(s.set_id, s.nombre_en) for s in node.sets]
        self._farm_session.set_prediction(node.titulo_es, sets, time.monotonic())
        names = " / ".join(s.nombre_en for s in node.sets)
        msg = f"[farmeo] nodo: {node.titulo_es} → predice {names}"
        log.info("Farmeo S13: nodo '%s' → sets %s", node.titulo_es, names)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.debug("on_diagnostic S13 falló", exc_info=True)

    def _handle_upgrade(self, frame, state: ScreenState, prev_code: str | None) -> None:
        """Enruta el frame S10 al UpgradeSyncer (PRE al entrar, diff al subir nivel, resumen al
        salir). `prev_code` DEBE ser el estado del ciclo anterior real (viene de `_dispatch_state`,
        NO de `self._last_state`, que ya fue pisado por `_notify_state_change` antes del dispatch)."""
        if self._upgrade_syncer is None:
            return
        if state.code == "S10":
            if prev_code != "S10":
                self._upgrade_syncer.on_s10_enter(frame)
            else:
                self._upgrade_syncer.on_s10_update(frame)
        elif prev_code == "S10":
            self._upgrade_syncer.on_s10_exit()
        # Popup "Materiales recuperados" (vuelto post-mejora): mantiene vivo el pendiente
        # mientras se muestra (exige click manual → demora la S17). S20 es continuo → refresca
        # el timer cada ciclo; el log sale una sola vez (edge en el syncer).
        if state.code == "S20":
            self._upgrade_syncer.on_material_refund()

    @staticmethod
    def _s17_disc_signature(frame):
        """
        Firma HÍBRIDA del disco S17, sin OCR (RNF-06). Devuelve `(sig_name, sig_detail,
        sig_hex)` o None:
          - sig_name: 48×24 gris del TÍTULO del set + slot (x∈[0.31,0.58], y∈[0.05,0.19]).
            Distingue discos de SET distinto en el MISMO slot (caso QA 2026-06-20:
            Monarca↔Nana, ambos main HP 2200 → el detail solo no los separaba; el título
            NO estaba en la firma). Texto estático → sin ruido de animación.
          - sig_detail: 48×48 gris del bloque main+substats (x∈[0.30,0.52], y∈[0.22,0.56]) —
            distingue discos del MISMO set por sus substats.
          - sig_hex: 24×24 gris del hexágono (x∈[0.58,0.95], y∈[0.18,0.88]) — el anillo de
            selección se mueve al cambiar de SLOT (pero NO al navegar candidatos del mismo
            slot: ahí mandan name+detail).
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            name = frame[int(0.05 * H):int(0.19 * H), int(0.31 * W):int(0.58 * W)]
            det = frame[int(0.22 * H):int(0.56 * H), int(0.30 * W):int(0.52 * W)]
            hexr = frame[int(0.18 * H):int(0.88 * H), int(0.58 * W):int(0.95 * W)]
            if name.size == 0 or det.size == 0 or hexr.size == 0:
                return None
            sig_name = cv2.cvtColor(
                cv2.resize(name, (48, 24), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            sig_detail = cv2.cvtColor(
                cv2.resize(det, (48, 48), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            sig_hex = cv2.cvtColor(
                cv2.resize(hexr, (24, 24), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            return (sig_name, sig_detail, sig_hex)
        except Exception:
            return None

    @staticmethod
    def _s9_disc_signature(frame):
        """Firma del disco SELECCIONADO en S9 (panel derecho), sin OCR (RNF-06). Dos
        componentes: título del set (distingue sets) + bloque main/substats (distingue
        discos del mismo set). None si no se puede leer."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            title = frame[int(0.15 * H):int(0.25 * H), int(0.71 * W):int(0.97 * W)]
            body = frame[int(0.28 * H):int(0.66 * H), int(0.71 * W):int(0.97 * W)]
            if title.size == 0 or body.size == 0:
                return None
            sig_t = cv2.cvtColor(
                cv2.resize(title, (48, 24), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            sig_b = cv2.cvtColor(
                cv2.resize(body, (48, 48), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            return (sig_t, sig_b)
        except Exception:
            return None

    def _is_new_s9_disc(self, sig) -> bool:
        """True si la firma indica que el disco S9 mirado cambió (o no había ancla)."""
        if self._s9_agg_sig is None or sig is None:
            return True
        return (self._sig_component_diff(sig[0], self._s9_agg_sig[0]) > _S9_SIG_MAX
                or self._sig_component_diff(sig[1], self._s9_agg_sig[1]) > _S9_SIG_MAX)

    @staticmethod
    def _s3_disc_signature(frame):
        """Firma del modal de drop S3 (centrado), sin OCR (RNF-06). Título (distingue sets) +
        bloque main/substats (distingue discos del mismo set). None si no se puede leer."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            title = frame[int(0.21 * H):int(0.28 * H), int(0.32 * W):int(0.60 * W)]
            body = frame[int(0.39 * H):int(0.61 * H), int(0.32 * W):int(0.68 * W)]
            if title.size == 0 or body.size == 0:
                return None
            sig_t = cv2.cvtColor(
                cv2.resize(title, (48, 24), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            sig_b = cv2.cvtColor(
                cv2.resize(body, (48, 48), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            return (sig_t, sig_b)
        except Exception:
            return None

    def _is_new_s3_disc(self, sig) -> bool:
        """True si la firma indica que el modal de drop cambió (o no había ancla)."""
        if self._s3_agg_sig is None or sig is None:
            return True
        return (self._sig_component_diff(sig[0], self._s3_agg_sig[0]) > _S9_SIG_MAX
                or self._sig_component_diff(sig[1], self._s3_agg_sig[1]) > _S9_SIG_MAX)

    @staticmethod
    def _s5_disc_signature(frame):
        """Firma de la ficha izquierda S5 (resultado de afinación), sin OCR (RNF-06). Título
        (distingue sets) + bloque main/substats (distingue discos del mismo set en distinto slot).
        Detecta el cambio de disco al clickear entre tiles de la grilla. None si no se puede."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            title = frame[int(0.18 * H):int(0.24 * H), int(0.31 * W):int(0.46 * W)]
            body = frame[int(0.31 * H):int(0.56 * H), int(0.31 * W):int(0.47 * W)]
            if title.size == 0 or body.size == 0:
                return None
            sig_t = cv2.cvtColor(
                cv2.resize(title, (48, 24), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            sig_b = cv2.cvtColor(
                cv2.resize(body, (48, 48), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
            return (sig_t, sig_b)
        except Exception:
            return None

    def _is_new_s5_disc(self, sig) -> bool:
        """True si la ficha S5 cambió (se clickeó otro disco) o no había ancla."""
        if self._s5_agg_sig is None or sig is None:
            return True
        return (self._sig_component_diff(sig[0], self._s5_agg_sig[0]) > _S9_SIG_MAX
                or self._sig_component_diff(sig[1], self._s5_agg_sig[1]) > _S9_SIG_MAX)

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
        """Firma del panel S18, sin OCR (RNF-06). Devuelve una TUPLA de dos 32×32 grises de
        la mitad DERECHA (estática, sin el modelo 3D animado de la izquierda):
          [0] NOMBRE+banner (y∈[0.18,0.39]): nombre del PJ + nivel + rol/elemento.
          [1] STATS (y∈[0.39,0.74]): el bloque de atributos.
        El gate re-OCR-ea si CUALQUIERA cambió. La componente de nombre distingue agentes del
        MISMO rol con stats parecidos (N.º 11 vs Sporos, ambos Ataque) — donde el bloque de
        stats solo, a 32×32, diluía la diferencia de dígitos y el gate quedaba pegado (QA
        2026-06-20). None si no se puede leer."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            x0, x1 = int(0.54 * W), int(0.96 * W)

            def _band(y_a, y_b):
                sub = frame[int(y_a * H):int(y_b * H), x0:x1]
                if sub.size == 0:
                    return None
                return cv2.cvtColor(
                    cv2.resize(sub, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
                ).astype(np.float32)

            name_sig = _band(0.18, 0.39)   # nombre + banner rol/elemento (identidad del PJ)
            stats_sig = _band(0.39, 0.74)  # bloque de atributos
            if name_sig is None or stats_sig is None:
                return None
            return (name_sig, stats_sig)
        except Exception:
            return None

    @staticmethod
    def _menu_name_signature(frame):
        """Firma 32×32 gris de la barra del NOMBRE del menú de personajes S15 (bottom-left),
        sin OCR (RNF-06). Gatea el re-OCR: si no cambió el PJ seleccionado, no vale re-leer.
        Banda x∈[0.08,0.26] y∈[0.85,0.93] (= ROI menu_personajes::nombre_seleccionado). None
        si no se puede leer."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            H, W = frame.shape[:2]
            sub = frame[int(0.85 * H):int(0.93 * H), int(0.08 * W):int(0.26 * W)]
            if sub.size == 0:
                return None
            return cv2.cvtColor(
                cv2.resize(sub, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
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
        True si dos firmas híbridas son del MISMO disco: las TRES componentes (nombre,
        detail, hex) dentro de su umbral. Si cualquiera supera su umbral ⇒ disco distinto
        (OR para disparar). El nombre separa sets distintos en el mismo slot; el detail,
        discos del mismo set; el hex, slots distintos.
        """
        if a is None or b is None:
            return False
        return (Monitor._sig_component_diff(a[0], b[0]) <= _S17_SIG_NAME_MAX
                and Monitor._sig_component_diff(a[1], b[1]) <= _S17_SIG_DETAIL_MAX
                and Monitor._sig_component_diff(a[2], b[2]) <= _S17_SIG_HEX_MAX)

    def _reset_s17_disc_tracking(self) -> None:
        """Olvida el disco S17 en fusión (al salir de S17 o forzar re-captura)."""
        self._disc_aggregator.reset()
        self._disc_agg_sig = None
        self._disc_emitted = False
        self._disc_agg_cycles = 0
        self._disc_emitted_ids.clear()
        self._last_emitted_identity = None
        self._s17_assign_sig = None
        # Anchor de flujo (5R.5b): al re-entrar a un slot, el primer disco vuelve a ser
        # el equipado por el latch (estructura del juego) → resetear el slot rastreado.
        self._s17_last_slot = 0
        # Votación del dueño (5R.5c) + evidencia-libre (5R.B): olvidar al salir de S17.
        self._s17_owner_sig = None
        self._s17_grid_votes = {}
        self._s17_det_votes = {}
        self._s17_free_evidence = 0
        self._s17_samples = 0
        self._s17_detail_present = 0
        self._s17_detail_absent = 0
        self._s17_grid_present = 0
        self._s17_grid_absent = 0
        self._s17_owner_passes = 0
        self._s17_warming = False
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
            self._s17_warming = False
        # Gate RNF-06: si este disco YA se emitió (procesado completo) y la firma no cambió,
        # NO re-OCR-earlo cada ciclo — era OCR puro desperdicio que alimentaba el leak nativo
        # de Paddle (la cosecha = parar en discos → este era el driver). El badge del dueño
        # sigue votando aparte en _sample_s17_owner (10 fps) sin OCR.
        if self._disc_emitted:
            return
        # 5R.L.6 — WARMUP del dueño: el disco ya maduró (OCR completo) pero salía con dueño
        # INCIERTO sobre 1 frame. Mientras calienta, NO re-OCR (RNF-06): el loop rápido (10fps)
        # sigue votando aparte; acá solo refrescamos la asignación con los votos nuevos sobre el
        # merge ya logrado (aggregator.current) y emitimos apenas el dueño se resuelve, o tras
        # juntar _S17_OWNER_MIN_SAMPLES pasadas, o al llegar al techo de ciclos.
        if self._s17_warming:
            merged = self._disc_aggregator.current
            if merged is None:
                self._s17_warming = False
            else:
                self._assign_s17_pj(merged, frame)   # re-decide el dueño con más votos (sin OCR)
                warm = self._s17_owner_passes >= _S17_OWNER_MIN_SAMPLES
                ceiling = self._disc_agg_cycles >= _S17_AGG_MAX_CYCLES
                if self._s17_owner_resolved(merged) or warm or ceiling:
                    self._s17_warming = False
                    self._emit_s17_disc(merged, state, True)
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
        ceiling = self._disc_agg_cycles >= _S17_AGG_MAX_CYCLES
        if not (mature or ceiling):
            return
        # Confirmación de UPGRADE — DESACOPLADA de la resolución del DUEÑO. El resumen PRE→POST
        # compara stats; no necesita saber quién equipa el disco. Antes colgaba de `_emit_s17_disc`,
        # que está gateado por el warming del dueño: al volver del popup S20 el disco viene SIN latch
        # y con badge INCIERTO → warming eterno → el resumen NUNCA salía (QA 2026-07-14). En cuanto
        # el disco MADURA (rolls asentados), confirmamos el pendiente que matchee (set+slot). No-op
        # sin pendiente. La emisión normal (log/on_disc/dueño) sigue su curso abajo.
        if self._upgrade_syncer is not None:
            try:
                self._upgrade_syncer.on_post_upgrade_disc(merged)
            except Exception:
                log.debug("on_post_upgrade_disc (s17) falló", exc_info=True)
        # 5R.L.6: maduró pero el dueño quedó INCIERTO y aún no juntamos muestras → DIFERIR la
        # emisión y dejar que el loop rápido caliente el voto (re-chequeo a _S17_WARM_CADENCE_MS,
        # ver run()). Los equipados (latch) y los ya-votados pasan derecho (resolved=True).
        if mature and not ceiling and not self._s17_owner_resolved(merged) \
                and self._s17_owner_passes < _S17_OWNER_MIN_SAMPLES:
            self._s17_warming = True
            return
        self._emit_s17_disc(merged, state, mature)

    def _s17_owner_resolved(self, disc) -> bool:
        """True si el dueño del disco ya quedó DECIDIDO (no hace falta seguir calentando):
        asignado por latch, dueño visual votado, o declarado LIBRE. False = 'incierto'."""
        return bool(disc.agente_asignado_nombre or disc.equip_pj_visual or disc.equip_libre)

    def _emit_s17_disc(self, merged, state: ScreenState, mature: bool) -> None:
        """Emite (dedup + equip_map + id_diag + log + on_disc) un disco S17 ya resuelto.
        Extraído de `_process_disc_s17_continuous` para reusarlo desde el path de warmup."""
        self._disc_emitted = True
        # Dedup por IDENTIDAD: si la firma parpadeó (modelo 3D animado) y este
        # disco ya se emitió en esta sesión S17, no re-emitir (ni re-persistir).
        identity = self._disc_identity(merged)
        if self._recapture_on:
            # Re-captura QA estilo S18: re-emite al CAMBIAR de disco, NO en cada
            # parpadeo del modelo 3D (que reabre la firma visual del MISMO disco). El
            # parpadeo deja la identidad-OCR igual → se saltea; navegar a otro disco la
            # cambia → re-emite (incluso al VOLVER a uno ya visto).
            if identity == self._last_emitted_identity:
                return
        elif identity in self._disc_emitted_ids:
            return
        self._disc_emitted_ids.add(identity)
        self._last_emitted_identity = identity
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
        if state.code == "S3":
            # Drop farmeado: handler CONTINUO con aggregator (parser espacial S3 de 2 columnas).
            self._process_disc_s3_continuous(frame, state)
            return
        if state.code == "S5":
            # Resultado de afinación (tienda música): ficha izquierda del disco SELECCIONADO,
            # handler CONTINUO como S3 (el usuario clickea cada disco de la grilla).
            self._process_disc_s5_continuous(frame, state)
            return
        key = state.code
        if self._processed_disc_state_code == key:
            return
        self._processed_disc_state_code = key
        self._process_disc(frame, state)

    # --- S9: inventario global de discos (replica la captura de S17) -----------
    def _process_disc_s9_continuous(self, frame, state: ScreenState) -> None:
        """S9 CONTINUO: re-extrae el disco SELECCIONADO (panel derecho) y fusiona
        parciales en el aggregator S9, igual que S17. La firma del panel detecta cambio
        de disco y resetea. El dueño = badge del tile resaltado de la grilla. Emite
        (sync vía on_disc) cuando madura o tras el techo de ciclos. Gate RNF-06: una vez
        emitido + firma estable, no re-OCR."""
        sig = self._s9_disc_signature(frame)
        if sig is None:
            return
        if self._is_new_s9_disc(sig):
            self._s9_aggregator.reset()
            self._s9_agg_sig = sig
            self._s9_emitted = False
            self._s9_agg_cycles = 0
            self._s9_warming = False
        if self._s9_emitted:
            return
        # WARMUP del dueño (fix badge=None): el disco ya maduró (stats completas) pero el
        # badge no localizó al dueño en esa cadencia. Reintentar la localización unas
        # cadencias más SIN re-OCR (el aggregator conserva stats + dueño; _assign_s9_owner
        # solo SETEA el dueño, nunca lo borra). Espejo de _s17_warming, pero S9 no tiene loop
        # 10fps → termina por techo de ciclos. Los discos LIBRES esperan el techo y emiten
        # sin dueño (latencia acotada). Re-chequeo acelerado (cadencia de warmup, ver run()).
        if self._s9_warming:
            merged = self._s9_aggregator.current
            if merged is None:
                self._s9_warming = False
            else:
                self._assign_s9_owner(merged, frame)   # reintenta el badge sobre el merge
                self._s9_agg_cycles += 1
                if merged.agente_asignado_nombre or self._s9_agg_cycles >= _S17_AGG_MAX_CYCLES:
                    self._s9_warming = False
                    self._emit_s9_disc(merged, state)
                return
        try:
            # Slot por la ROI del TÍTULO (extract_s9_slot, calibrada): es la lectura
            # más limpia del "(N)" — el panel detalle a veces lo pierde. Fresca del
            # frame actual (no usa state.slot, que en frames continuos viene stale).
            # parse_disc_s9 lo usa como override; si igual se dropeó, infiere por main.
            s9_slot = extract_s9_slot(frame, self._ocr)
            disc = parse_disc_s9(frame, self._ocr, slot=s9_slot)
        except Exception:
            log.exception("Error parseando disco S9")
            return
        self._assign_s9_owner(disc, frame)
        if disc.confianza_global < 0.7:
            return  # frame de transición → no contaminar el aggregator
        merged = self._s9_aggregator.merge(disc)
        self._s9_agg_cycles += 1
        if self._s9_emitted or merged is None:
            return
        mature = disc_is_mature(merged)
        ceiling = self._s9_agg_cycles >= _S17_AGG_MAX_CYCLES
        if not (mature or ceiling):
            return
        # Maduró pero el dueño no resolvió y aún hay margen de ciclos → DIFERIR (warmup): el
        # badge tiene más cadencias para localizar antes de emitir sin dueño.
        if mature and not ceiling and merged.agente_asignado_nombre is None:
            self._s9_warming = True
            return
        self._emit_s9_disc(merged, state)

    def _assign_s9_owner(self, disc, frame) -> None:
        """Dueño del disco S9 por el badge del tile seleccionado (esquina sup-der de la
        grilla). Reusa el matcher de badges de S17 (misma librería). Solo asigna si el
        match es CONFIABLE (no rejected); si no, deja el disco SIN dueño — captura los
        stats igual, no inventa equipamiento (RNF-02). Un disco libre da badge None."""
        try:
            badge = crop_s9_selected_badge(frame)
        except Exception:
            badge = None
        if badge is None:
            if self._id_diag_on:
                log.info("[s9_owner] badge=None (tile sin localizar / disco libre) -> sin dueno")
            return
        try:
            name, conf, rejected = self._identifier.s17_match(badge)
        except Exception:
            return
        if name and not rejected:
            disc.agente_asignado_nombre = name
            disc.agente_asignado_conf = conf
            if self._id_diag_on:
                log.info("[s9_owner] match directo: %s (conf %.2f)", name, conf)
            return
        # Abstención del badge → desempate por CONTEXTO (helper compartido con S17).
        self._tiebreak_owner(disc, badge, tag="s9_owner")

    def _tiebreak_owner(self, disc, badge, tag: str) -> bool:
        """Desempate de dueño por CONTEXTO para un badge que el matcher NO resolvió por sí
        solo (abstención por margen entre look-alikes). Compartido por S9 (`_assign_s9_owner`)
        y S17 (`_assign_s17_pj`, fallback 'incierto'). Solo actúa si NO es reject (un disco
        libre da reject → sin dueño, RNF-02) y el match visual es fuerte (conf≥guard) pero
        quedó suprimido por margen chico. Si el contexto confirma, asigna + nota y devuelve
        True. `tag` = prefijo del log ('s9_owner'/'s17_owner'). No-op si no hay tiebreaker o
        badge. Re-deriva el match completo del badge (incl. reject/conf/top)."""
        if self._owner_tiebreaker is None or badge is None:
            return False
        try:
            r = self._identifier.s17_match_full(badge)
        except Exception:
            return False
        _top_str = ", ".join(f"{n}:{1 - d:.2f}" for n, d in (r.top[:3] if r else []))
        if r is None or r.rejected or r.name is not None or r.conf < _S9_TIEBREAK_CONF_MIN:
            if self._id_diag_on:
                log.info("[%s] sin desempate (conf %.2f, rej=%s) top=[%s]", tag,
                         (r.conf if r else 0.0), (r.rejected if r else "?"), _top_str)
            return False
        try:
            resolved = self._owner_tiebreaker.resolve(disc, r.top)
        except Exception:
            return False
        if resolved:
            owner, reason = resolved
            disc.agente_asignado_nombre = owner
            disc.agente_asignado_conf = r.conf
            disc.notas.append(f"dueno_desempate_{reason}")
            if self._id_diag_on:
                log.info("[%s] DESEMPATE por %s: %s (conf %.2f) top=[%s]",
                         tag, reason, owner, r.conf, _top_str)
            return True
        if self._id_diag_on:
            log.info("[%s] margen sin desempate (set no distingue top-1/top-2) top=[%s]",
                     tag, _top_str)
        return False

    def _emit_s9_disc(self, merged, state: ScreenState) -> None:
        """Emite (dedup por identidad + equip_map + log + on_disc/sync) un disco S9.
        Espejo de `_emit_s17_disc`; comparte el dedup con S17 (un disco es un disco)."""
        self._s9_emitted = True
        identity = self._disc_identity(merged)
        if self._recapture_on:
            if identity == self._last_emitted_identity:
                return
        elif identity in self._disc_emitted_ids:
            return
        self._disc_emitted_ids.add(identity)
        self._last_emitted_identity = identity
        if merged.agente_asignado_nombre:
            self._record_equip_map(identity, merged.agente_asignado_nombre)
        log.info(
            "Disco S9 detectado: set=%s slot=%d main=%s nivel=%d dueno=%s conf=%.2f",
            merged.set_name_canon or merged.set_name_raw, merged.slot,
            merged.main_stat_canon or merged.main_stat_raw, merged.nivel,
            merged.agente_asignado_nombre or "-", merged.confianza_global,
        )
        if self._on_disc:
            try:
                self._on_disc(merged, state)
            except Exception:
                log.exception("Error en on_disc S9")

    def _reset_s9_disc_tracking(self) -> None:
        """Olvida el tracking del disco S9 mirado (al salir de S9)."""
        self._s9_aggregator.reset()
        self._s9_agg_sig = None
        self._s9_emitted = False
        self._s9_agg_cycles = 0
        self._s9_warming = False

    # --- S3: modal de drop farmeado (parser espacial 2 columnas) ----------------
    def _process_disc_s3_continuous(self, frame, state: ScreenState) -> None:
        """S3 CONTINUO: re-extrae el disco del modal de drop (parser espacial 2 columnas) y
        fusiona parciales en el aggregator S3, igual que S9 pero SIN dueño (un drop no está
        equipado) ni warmup. La firma del modal detecta cambio de disco y resetea. Emite vía
        on_disc cuando madura o tras el techo de ciclos. Gate RNF-06: emitido + firma estable →
        no re-OCR."""
        sig = self._s3_disc_signature(frame)
        if sig is None:
            if self._id_diag_on:
                log.info("[s3_diag] sig=None (modal no localizado)")
            return
        if self._is_new_s3_disc(sig):
            self._s3_aggregator.reset()
            self._s3_agg_sig = sig
            self._s3_emitted = False
            self._s3_agg_cycles = 0
        if self._s3_emitted:
            return
        try:
            from app.core.parser_disc_s3 import parse_disc_s3_full
            disc = parse_disc_s3_full(frame, self._ocr)
        except Exception:
            log.exception("Error parseando disco S3 (drop)")
            return
        if disc.confianza_global < 0.7:
            if self._id_diag_on:
                log.info("[s3_diag] conf=%.2f < 0.70 (frame transición) set=%r slot=%s",
                         disc.confianza_global, disc.set_name_raw, disc.slot)
            return  # frame de transición → no contaminar el aggregator
        merged = self._s3_aggregator.merge(disc)
        self._s3_agg_cycles += 1
        if self._s3_emitted or merged is None:
            return
        mature = disc_is_mature(merged)
        ceiling = self._s3_agg_cycles >= _S17_AGG_MAX_CYCLES
        if self._id_diag_on:
            log.info("[s3_diag] conf=%.2f mature=%s cycles=%d set=%r slot=%s main=%s subs=%d",
                     disc.confianza_global, mature, self._s3_agg_cycles,
                     merged.set_name_raw, merged.slot,
                     merged.main_stat_canon or merged.main_stat_raw, len(merged.subs))
        if not (mature or ceiling):
            return
        self._emit_s3_disc(merged, state)

    def _emit_s3_disc(self, merged, state: ScreenState) -> None:
        """Emite (dedup por identidad + log + on_disc) un disco de drop S3. Comparte el dedup
        de identidad con S9/S17 (un disco es un disco). El controller lo enruta a _build_payload
        (score + toast); no persiste en esta fase (display-first)."""
        self._s3_emitted = True
        identity = self._disc_identity(merged)
        set_disp = merged.set_name_canon or merged.set_name_raw
        if self._recapture_on:
            if identity == self._last_emitted_identity:
                return
        elif identity in self._s3_emitted_ids:
            # Re-abriste un disco ya capturado → feedback + NO re-emitir (sin toast).
            log.info("Disco S3 ya capturado: set=%s slot=%d", set_disp, merged.slot)
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(f"[disco] ya capturado: {set_disp} slot {merged.slot}")
                except Exception:
                    log.debug("on_diagnostic S3 ya-capturado falló", exc_info=True)
            return
        self._s3_emitted_ids.add(identity)
        self._last_emitted_identity = identity
        log.info(
            "Disco S3 (drop) detectado: set=%s slot=%d main=%s nivel=%d conf=%.2f",
            merged.set_name_canon or merged.set_name_raw, merged.slot,
            merged.main_stat_canon or merged.main_stat_raw, merged.nivel,
            merged.confianza_global,
        )
        if self._on_disc:
            try:
                self._on_disc(merged, state)
            except Exception:
                log.exception("Error en on_disc S3")

    def _process_disc_s5_continuous(self, frame, state: ScreenState) -> None:
        """S5 CONTINUO: re-extrae la ficha del disco SELECCIONADO del resultado de afinación
        (parser S5 = motor de S3 a 1 columna) y fusiona parciales en el aggregator S5, igual que
        S3 pero sobre la ficha izquierda. La firma detecta el cambio de disco (clickeás otro tile)
        y resetea. Emite vía on_disc al madurar o al techo de ciclos. Gate RNF-06: emitido + firma
        estable → no re-OCR."""
        sig = self._s5_disc_signature(frame)
        if sig is None:
            return
        if self._is_new_s5_disc(sig):
            # El disco enfocado cambió: clickeaste otro disco O re-afinaste (nueva tanda desde la
            # MISMA pantalla de resultados, botón "Afinar ×N"). Re-abrir la evaluación de la grilla
            # (con debounce): si la secuencia de slots cambió, es una tanda nueva → re-preview.
            self._s5_grid_settled = False
            self._s5_grid_pending = None
            self._s5_grid_tries = 0
            self._s5_aggregator.reset()
            self._s5_agg_sig = sig
            self._s5_emitted = False
            self._s5_agg_cycles = 0
        # Re-chequear la grilla CADA ciclo hasta estabilizar (la animación de revelado hace que las
        # filas inferiores lean '?' unos frames). El debounce interno espera 2 lecturas iguales.
        if not self._s5_grid_settled:
            self._maybe_new_s5_batch(frame)
        if self._s5_emitted:
            return
        try:
            from app.core.parser_disc_s3 import parse_disc_s5
            disc = parse_disc_s5(frame, self._ocr)
        except Exception:
            log.exception("Error parseando disco S5 (afinación)")
            return
        if disc.confianza_global < 0.7:
            if self._id_diag_on:
                log.info("[s5_diag] conf=%.2f < 0.70 (frame transición) set=%r slot=%s",
                         disc.confianza_global, disc.set_name_raw, disc.slot)
            return  # frame de transición → no contaminar el aggregator
        merged = self._s5_aggregator.merge(disc)
        self._s5_agg_cycles += 1
        if self._s5_emitted or merged is None:
            return
        mature = disc_is_mature(merged)
        ceiling = self._s5_agg_cycles >= _S17_AGG_MAX_CYCLES
        if self._id_diag_on:
            log.info("[s5_diag] conf=%.2f mature=%s cycles=%d set=%r slot=%s main=%s subs=%d",
                     disc.confianza_global, mature, self._s5_agg_cycles,
                     merged.set_name_raw, merged.slot,
                     merged.main_stat_canon or merged.main_stat_raw, len(merged.subs))
        if not (mature or ceiling):
            return
        self._emit_s5_disc(merged, state)

    def _maybe_new_s5_batch(self, frame) -> None:
        """Chequea si la GRILLA de resultado cambió (re-afinación desde la misma pantalla). Se
        llama cuando el disco enfocado cambió (clickeás o re-afinás). Si la secuencia de slots de
        la grilla difiere de la última → NUEVA tanda: re-emite el preview y limpia el dedup del
        batch (discos nuevos, re-capturables). Si es la misma grilla (solo clickeaste otro disco)
        → no hace nada. También cubre la 1ª emisión al entrar (slots previos vacíos)."""
        try:
            from app.core.parser_disc_s3 import parse_s5_grid
            tiles = parse_s5_grid(frame, self._ocr)
        except Exception:
            log.exception("Error en preview de grilla S5")
            return
        if not tiles:
            return   # frame de transición / grilla aún no visible → reintenta al próximo ciclo
        slots = tuple(s for s, _ in tiles)
        # Debounce: la grilla se revela con animación → una lectura temprana trae '?' (slot 0) en
        # las filas que aún no rindieron. Confirmamos con 2 lecturas consecutivas iguales; mientras
        # difieran (tiles apareciendo) esperamos. Tope anti-cuelgue si nunca converge (badge
        # genuinamente ilegible): a las N pasadas emitimos lo que haya.
        self._s5_grid_tries += 1
        stable = slots == self._s5_grid_pending
        self._s5_grid_pending = slots
        if not (stable or self._s5_grid_tries >= _S5_GRID_MAX_TRIES):
            return
        self._s5_grid_settled = True     # tanda evaluada: dejamos de re-OCR la grilla (RNF-06)
        if 0 in slots:
            return   # lectura con '?' (badge ruidoso, típico del tile seleccionado) → no previsualizar
        if not self._s5_batch_is_new(slots):
            return   # misma tanda (clic entre tiles / jitter de 1-2 badges) → no re-emitir
        self._s5_grid_slots = slots
        self._s5_emitted_ids.clear()     # nueva tanda → discos nuevos, re-capturables
        self._emit_s5_grid_preview(tiles)

    def _s5_batch_is_new(self, slots: tuple) -> bool:
        """True si `slots` es una tanda de afinación NUEVA respecto de la última previsualizada.
        Compara por MULTISET (el orden/tile seleccionado no importa) y exige que difieran ≥
        `_S5_BATCH_MIN_DIFF` posiciones: así el flicker de 1-2 badges al clickear un disco NO
        cuenta como tanda nueva, pero re-afinar (slots al azar) sí. Longitud distinta = nueva."""
        prev = self._s5_grid_slots
        if not prev:
            return True
        if len(slots) != len(prev):
            return True
        diff = sum(1 for a, b in zip(sorted(slots), sorted(prev)) if a != b)
        return diff >= _S5_BATCH_MIN_DIFF

    def _emit_s5_grid_preview(self, tiles) -> None:
        """Emite un resumen display-only de la grilla de resultado: por cada disco evocado,
        `[disco] slot N · <set>` (sin abrir detalle). El slot/set/stats definitivos salen de la
        ficha al clickear cada disco. Resuelve el set al nombre canónico de la DB."""
        if not tiles:
            return
        # Todos los discos de UNA afinación son del mismo set (el género evocado). Nombre del set,
        # por orden de preferencia:
        #  1) el set EVOCADO en el selector S4 (antelación): lo leyó COMPLETO y limpio. El label del
        #     tile se trunca en la celda angosta → los nombres largos ('Balada de la rama y la
        #     espada') no resuelven desde ahí. Válido dentro de la ventana de farmeo.
        #  2) CONSENSO por tile: el set_id más votado entre los tiles que resuelven (robusto al ruido
        #     OCR de un label suelto). Fallback si no venimos del selector S4.
        batch_set = None
        ev = self._s4_evoked_set
        if ev is not None and (time.monotonic() - ev[2]) < _S5_EVOKED_TTL_S:
            batch_set = ev[1]
        if batch_set is None and self._set_repo is not None:
            from collections import Counter
            votes: Counter = Counter()
            for _slot, raw in tiles:
                sid = self._set_repo.resolve_id(raw)
                if sid is not None:
                    votes[sid] += 1
            if votes:
                best_sid = votes.most_common(1)[0][0]
                entry = next((e for e in self._set_repo.get_all() if e.id == best_sid), None)
                if entry:
                    batch_set = entry.nombre
        for slot, set_raw in tiles:
            set_disp = batch_set or set_raw
            slot_str = str(slot) if slot else "?"
            msg = f"[disco] slot {slot_str} · {set_disp}"
            log.info("Afinación S5 (preview grilla): slot %s · set %s", slot_str, set_disp)
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(msg)
                except Exception:
                    log.debug("on_diagnostic S5 grid falló", exc_info=True)

    def _emit_s5_disc(self, merged, state: ScreenState) -> None:
        """Emite (dedup por identidad + log + on_disc) un disco de afinación S5. Mismo dedup de
        identidad y feedback 'ya capturado' que S3 (un disco es un disco). Display-only en esta
        fase (el controller lo enruta a score + toast); no persiste."""
        self._s5_emitted = True
        identity = self._disc_identity(merged)
        set_disp = merged.set_name_canon or merged.set_name_raw
        if self._recapture_on:
            if identity == self._last_emitted_identity:
                return
        elif identity in self._s5_emitted_ids:
            log.info("Disco S5 ya capturado: set=%s slot=%d", set_disp, merged.slot)
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(f"[disco] ya capturado: {set_disp} slot {merged.slot}")
                except Exception:
                    log.debug("on_diagnostic S5 ya-capturado falló", exc_info=True)
            return
        self._s5_emitted_ids.add(identity)
        self._last_emitted_identity = identity
        log.info(
            "Disco S5 (afinación) detectado: set=%s slot=%d main=%s nivel=%d conf=%.2f",
            merged.set_name_canon or merged.set_name_raw, merged.slot,
            merged.main_stat_canon or merged.main_stat_raw, merged.nivel,
            merged.confianza_global,
        )
        if self._on_disc:
            try:
                self._on_disc(merged, state)
            except Exception:
                log.exception("Error en on_disc S5")

    def _reset_s3_disc_tracking(self) -> None:
        """Olvida el tracking del modal de drop S3 (al salir de S3)."""
        self._s3_aggregator.reset()
        self._s3_agg_sig = None
        self._s3_emitted = False
        self._s3_agg_cycles = 0

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

        # Gate RNF-06: saltar el OCR si el panel S18 no cambió desde el último ciclo.
        # La extracción continua existe para detectar cambio de agente; sin cambio visual no
        # hay nada nuevo que extraer ni re-loggear (el log del controller es edge-triggered).
        # Firma de DOS componentes (nombre+banner / stats): re-OCR si CUALQUIERA cambió. La
        # componente de nombre destraba el cambio entre agentes del mismo rol con stats
        # parecidos (antes el bloque de stats solo, a 32×32, no superaba el umbral → pegado).
        sig = self._s18_stats_signature(frame)
        if (sig is not None and self._s18_last_sig is not None
                and self._sig_component_diff(sig[0], self._s18_last_sig[0]) <= _S18_SIG_NAME_MAX
                and self._sig_component_diff(sig[1], self._s18_last_sig[1]) <= _S18_SIG_MAX):
            return
        self._s18_last_sig = sig

        # 2b) Extracción de datos en pantalla (cada ciclo). El log del RESULTADO es
        # edge-triggered (lo emite el controller solo cuando cambia); este marcador
        # per-ciclo queda en debug para no spamear.
        log.debug("[S18] Extrayendo stats de pantalla...")
        result = self._process_agent_stats(frame, state)
        # ¿Extracción UTILIZABLE? Un frame de TRANSICIÓN (al cambiar de agente / panel
        # cargando) trae TODOS los stats en None, aunque el OCR haya leído basura con conf
        # alta (caso 'Area' conf 0.97, QA 2026-06-20). Ancla = PV o Ataque (todo agente real
        # los tiene). Si NO es utilizable:
        #   - NO comprometer el gate → el próximo dispatch reintenta el mismo panel (anti
        #     'S18 pegado'); una lectura buena sí commitea → panel estático se saltea.
        #   - NO tocar el latch ni aprender el avatar → evita el LATCH FANTASMA ('Area') que
        #     después bloqueaba la cosecha vía el cross-check ancla-vs-badge.
        usable = result is not None and (
            getattr(result, "pv", None) is not None
            or getattr(result, "ataque", None) is not None
        )
        if not usable:
            self._s18_last_sig = None

        # Detección explícita de cambio de agente para el log + latch — SOLO si es utilizable.
        if usable and getattr(result, "agente_nombre", None):
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
        Identifica el PJ en S8/S19 por el DESCRIPTOR de la barra superior (fuente
        PRIMARIA — ya no requiere el latch de S18). Se invoca en el loop rápido
        (10 fps) y desde el handler de cadencia.

        El matcher de fila cubre el roster completo y es fiable, pero un frame suelto
        puede salir mal (PJ en la esquina del slider, animación idle). Por eso se
        ACUMULAN VOTOS por PJ sobre la ranura de avatar actual y se fija la identidad
        recién al juntar `_DETAIL_MIN_SAMPLES` matches confiables → el ganador (argmax
        de confianza) manda, un frame malo aislado no queda clavado.

        Dos anclas separadas (clave): `_agent_anchor_x` = dónde se CONFIRMÓ la identidad;
        `_detail_vote_x` = dónde se está votando. El auto-hide de la barra devuelve
        posiciones ESPURIAS del highlight desvaneciéndose; con una sola ancla eso se
        confundía con un cambio de PJ y descartaba al ya reconocido (QA 2026-07-16).

        Reglas (RNF-02, conservador — preferir sostener a mentir):
          - avatar OCULTO (cur_x None) → sostener, sin tocar nada.
          - identidad ya CONFIRMADA en esta ranura → estable, con su etiqueta real.
          - ranura sin confirmar → votar; al llegar a MIN_SAMPLES fijar el argmax ("avatar").
          - sin match + hay identidad previa → SOSTENER ("sostenido"): nunca se borra al
            último reconocido por no poder confirmar (parpadeo/esquina/auto-hide).
          - sin match + sin identidad → "sin identificar" (reintenta en el próximo frame).
        """
        try:
            cur_x = selected_avatar_x(frame)
        except Exception:
            return
        if cur_x is None:
            return  # avatar oculto → sostener (la barra deslizante no da evidencia)
        confirmed_here = (self._agent_anchor_x is not None
                          and abs(cur_x - self._agent_anchor_x) < _AVATAR_X_TOL
                          and self._last_agent_name is not None)
        if confirmed_here:
            # Ranura ya resuelta (match de avatar previo o latch de S18) → estable, sin
            # re-votar. Restaura la etiqueta real si veníamos de un "sostenido".
            if self._detail_confirmed_source is None:
                self._detail_confirmed_source = "heredado"   # latch de S18 (bootstrap)
            self._detail_source = self._detail_confirmed_source
            self._detail_vote_x = cur_x
            return
        # Ranura sin identidad confirmada → votar. Reiniciar solo si la votación es de OTRA
        # posición (deslizó de veras), no por el jitter del mismo highlight.
        if (self._detail_vote_x is None
                or abs(cur_x - self._detail_vote_x) >= _AVATAR_X_TOL):
            self._detail_votes = {}
            self._detail_samples = 0
            self._detail_vote_x = cur_x
        try:
            match = self._identifier.identify(frame)
        except Exception:
            log.exception("Error en identifier.identify")
            match = None
        if match is not None:
            name, conf = match[0], float(match[1])
            self._detail_votes[name] = self._detail_votes.get(name, 0.0) + conf
            self._detail_samples += 1
            if self._detail_samples >= _DETAIL_MIN_SAMPLES:
                self._last_agent_name = max(self._detail_votes, key=self._detail_votes.get)
                self._detail_source = "avatar"
                self._detail_confirmed_source = "avatar"
                self._agent_anchor_x = cur_x      # identidad confirmada en esta ranura
            return
        # El matcher no confirma esta ranura. Carry-forward: NUNCA borrar al último PJ
        # reconocido — se muestra como "sostenido" hasta poder confirmar de nuevo.
        if self._last_agent_name is not None:
            self._detail_source = "sostenido"
            return
        # Sin identidad previa y sin match → sin identificar (se reintenta por frame).
        self._last_agent_name = None
        self._detail_source = None

    def _reset_detail_identity(self) -> None:
        """Limpia el latch de identidad (al salir de la familia detalle de agente)."""
        self._last_agent_name = None
        self._agent_anchor_x = None
        self._detail_source = None
        self._detail_votes = {}
        self._detail_samples = 0
        self._detail_vote_x = None
        self._detail_confirmed_source = None
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

    def _process_agent_menu(self, frame, state: ScreenState) -> None:
        """Menú de personajes (S15, Fase M.1): reconoce al PJ SELECCIONADO leyendo su
        nombre de la barra bottom-left → `identify_menu_agent` → `_match_agent` (rol+elemento
        de la DB). Loguea EDGE-triggered (1× por PJ). Gate RNF-06: re-OCR solo si la firma
        del nombre cambió (cambió la selección). Informativo: no escribe DB ni toca el latch."""
        sig = self._menu_name_signature(frame)
        if (sig is not None and self._menu_last_sig is not None
                and self._sig_component_diff(sig, self._menu_last_sig) <= _MENU_SIG_MAX):
            return                          # mismo PJ seleccionado → no re-OCR
        self._menu_last_sig = sig
        nombre, rol, elemento = identify_menu_agent(frame, self._ocr)
        logsig = (nombre, rol, elemento)
        if logsig == self._last_menu_log_sig:
            return                          # mismo resultado → no re-loguear
        self._last_menu_log_sig = logsig
        log.info(
            "[S15] Menú de personajes reconocido — PJ=%s · rol=%s · elemento=%s",
            nombre or "incierto", rol or "-", elemento or "-",
        )
        if self._on_agent_detail:
            try:
                self._on_agent_detail(state, nombre, bool(nombre), "menu")
            except Exception:
                log.exception("Error en on_agent_detail callback (menú)")

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
            self._s17_grid_votes = {}
            self._s17_det_votes = {}
            self._s17_free_evidence = 0
            self._s17_samples = 0
            self._s17_detail_present = 0
            self._s17_detail_absent = 0
            self._s17_grid_present = 0
            self._s17_grid_absent = 0
            self._s17_owner_passes = 0         # 5R.L.6: reiniciar el warmup del dueño
            if self._id_diag_on:
                self._id_diag = {"samples": 0, "grid_loc": 0, "grid_match": 0,
                                 "det_loc": 0, "det_match": 0, "grid_votes": {}, "det_votes": {}}
        # 5R.L.6: cada pasada del loop rápido (10fps) cuenta para el warmup del dueño,
        # localice o no la grilla (el detalle vota aparte). `_process_disc_s17_continuous`
        # difiere la emisión de discos con dueño INCIERTO hasta juntar varias pasadas.
        self._s17_owner_passes += 1
        badge = crop_grid_selected_badge(frame)
        g_name, g_conf = None, 0.0
        if badge is None:
            self._s17_grid_absent += 1         # gate L.7.2: sin avatar en el tile (libre/NOLOC)
            self._dump_grid_diag(frame, None, None, 0.0, False, sig)   # grid no localizó (NOLOC)
        else:
            self._s17_grid_present += 1        # hay avatar de dueño en el tile (equipado)
            g_name, g_conf, rejected = self._identifier.s17_match(badge)
            self._dump_grid_diag(frame, badge, g_name, g_conf, rejected, sig)
            self._s17_samples += 1
            if g_name:
                self._s17_grid_votes[g_name] = self._s17_grid_votes.get(g_name, 0.0) + float(g_conf)
            elif rejected or g_conf < _S17_FREE_CONF:   # crop sin cara (lock/disco/vacío)
                self._s17_free_evidence += 1
        # DETALLE-badge (5R.C.4 + L.2b/L.3): localiza ~siempre (incl. cuando el grid da
        # NOLOC) → vota a su PROPIO acumulador (separado del grid). `_decide_s17_owner`
        # combina ambos con grid-primario: el detail sube yield en NOLOC del grid sin poder
        # meter wrongs (RNF-02). NO toca _s17_samples/free (la detección LIBRE sigue
        # calibrada por el grid). Inerte hasta que la librería de detalle se cosecha.
        det = crop_detail_badge(frame)
        d_name, d_conf = None, 0.0
        if det is None:
            self._s17_detail_absent += 1       # 5R.L.7.3: el árbitro no vio avatar (libre?)
        else:
            d_name, d_conf, d_margin, d_rej = self._identifier.s17_match_detail(det)
            # ¿el crop es una CARA o un crop espurio (texto '(N)' del nº de slot)? Un avatar
            # real matchea con conf alta O margen claro; el texto da ambos bajos → cuenta como
            # AUSENTE (no bloquea LIBRE). RNF-02: exige ambos bajos (no piso un avatar dudoso).
            if (not d_rej) and (d_conf >= _DET_PRESENCE_CONF or d_margin >= _DET_PRESENCE_MARGIN):
                self._s17_detail_present += 1   # avatar de dueño plausible en el panel
            else:
                self._s17_detail_absent += 1    # crop espurio (texto/ambiguo) → como ausente
            if d_name:
                self._s17_det_votes[d_name] = self._s17_det_votes.get(d_name, 0.0) + float(d_conf)
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
        voted, _src = _decide_s17_owner(
            self._s17_grid_votes, self._s17_det_votes, latch=self._last_agent_name)

        def _top(v):
            return ",".join(f"{k}:{val:.2f}" for k, val in
                            sorted(v.items(), key=lambda kv: -kv[1])[:3]) or "-"

        log.info(
            "[id_diag] id=%s slot=%s assigned=%s voted=%s samples=%d "
            "grid_loc=%d grid_match=%d det_loc=%d det_match=%d grid_votes=[%s] det_votes=[%s]",
            self._identity_to_key(identity), getattr(merged, "slot", "?"), merged.agente_asignado_nombre or "-",
            voted or "-", d.get("samples", 0), d.get("grid_loc", 0), d.get("grid_match", 0),
            d.get("det_loc", 0), d.get("det_match", 0),
            _top(d.get("grid_votes", {})), _top(d.get("det_votes", {})),
        )

    def _s17_voted_owner(self, frame) -> str | None:
        """Dueño ganador del disco mirado por la política grid+detail (`_decide_s17_owner`),
        si la votación del loop rápido corresponde a ESTE disco. None si incierto."""
        if not self._s17_owner_sig_matches(frame):
            return None
        owner, _src = _decide_s17_owner(
            self._s17_grid_votes, self._s17_det_votes, latch=self._last_agent_name)
        return owner

    def _s17_owner_sig_matches(self, frame) -> bool:
        sig = self._s17_disc_signature(frame)
        return not (sig is None or self._s17_owner_sig is None
                    or not self._sig_close(sig, self._s17_owner_sig))

    def _s17_is_libre(self, frame) -> bool:
        """True si el disco mirado está LIBRE (nadie lo equipa). LIBRE GANA A 'INCIERTO'
        (decisión del usuario 2026-06-21): los matchers de badge (grid+detail) son ROBUSTOS
        y 0-wrong → si NADIE votó un dueño, lo más probable es que NO TENGA dueño (un disco
        equipado habría producido un voto). El parpadeo LIBRE↔incierto del QA venía de exigir
        evidencia acumulada (≥2 frames + mayoría) que no se junta navegando rápido.
        Regla: sin votos (grid ni detail) → LIBRE, SALVO que el detalle haya visto un avatar
        REAL de forma DOMINANTE (≥2× los frames ausentes) sin poder nombrarlo — ahí abstenerse
        ('incierto', RNF-02): es el coverage-gap raro (PJ sin refs tipo Lycaon-candidato). La
        presencia espuria del grid (gate leaky, L.7.2) NO bloquea — no votó."""
        if self._s17_grid_votes or self._s17_det_votes or not self._s17_owner_sig_matches(frame):
            return False
        # Sin voto: LIBRE salvo presencia REAL dominante del detalle (avatar visto pero no
        # nombrado). Tolera spikes espurios sueltos del texto '(N)' (no dominantes).
        return self._s17_detail_present < 2 * max(1, self._s17_detail_absent)

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
            voted = self._s17_voted_owner(frame)
            # ANCHOR-WARMUP (QA 2026-06-20): el ancla ("1er disco del slot = equipado por el
            # latch") puede caer sobre un CANDIDATO si el usuario NAVEGÓ dentro del slot. Si
            # finaliza ANTES de que el badge cante, mislabela (Nana de Seth → 'Nicole', el PJ
            # de la página) y queda pegado en agente_asignado. Esperar el voto del badge: si
            # aún no llegó y no calentamos, DIFERIR — no fijar el slot ni cosechar → el próximo
            # frame re-evalúa con el voto listo (el warmup posterga la emisión mientras tanto).
            if voted is None and self._s17_owner_passes < _S17_OWNER_MIN_SAMPLES:
                return
            self._s17_last_slot = slot
            # CROSS-CHECK ancla vs badge (5R.L.4): el ancla asume "1er disco del slot =
            # equipado por el latch", pero esa suposición se ROMPE si el latch quedó viejo
            # (saltaste de página) o si re-entramos a S17 sobre un CANDIDATO → mislabel +
            # (fuera de readonly) cosecha contaminada bajo el nombre del latch. El badge
            # (grilla+detalle) es 0-wrong en QA → si dice OTRO PJ con confianza, le creemos
            # al badge y NO cosechamos (QA 2026-06-19: ancla 3 wrong vs badge 0 wrong).
            if voted and _norm_key(voted) != _norm_key(latch):
                disc.equip_detectado = True
                disc.equip_pj_visual = voted
                disc.equip_libre = False
                self._log_s17_assign(
                    ("anchor_badge_conflict", voted),
                    "[badge] ancla decía '%s' pero el badge dice '%s' → badge (sin cosechar).",
                    latch, voted,
                )
                return
            if badge is not None:                      # cosecha con label CERTERO (badge concuerda)
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
            # La GRILLA no localizó (NOLOC), pero el DETALLE localiza ~100% → puede
            # RESCATAR al dueño (5R.L.4). Antes acá se cortaba sin consultar el voto del
            # detalle → discos con grid-NOLOC quedaban "incierto" aunque el detalle los
            # tuviera (bug QA 2026-06-18: Yanagi det@1.00 → incierto). Consultamos el voto.
            owner = self._s17_voted_owner(frame)
            if owner:
                disc.equip_detectado = True
                disc.equip_pj_visual = owner
                disc.equip_libre = False
                self._log_s17_assign(
                    ("det_owner", owner), "[detalle] grilla NOLOC · dueño=%s (detalle).", owner
                )
                return
            # ÁRBITRO DE PRESENCIA (5R.L.7.3): grid gateado (sin avatar) + detalle sin
            # resolver. Si NINGUNA superficie vio un avatar en ≥2 frames → el disco está
            # LIBRE (estructural, no por identidad). Antes acá se cortaba en "sin asignar"
            # → los discos libres nunca declaraban LIBRE (quedaban en limbo, QA 2026-06-20).
            if self._s17_is_libre(frame):
                disc.equip_detectado = False
                disc.equip_pj_visual = None
                disc.equip_libre = True
                self._log_s17_assign(
                    ("libre",), "[S17] disco LIBRE (sin dueño en grilla ni detalle)."
                )
                return
            disc.equip_pj_visual = None
            if latch:
                self._log_s17_assign(
                    ("no_badge", latch), "[S17] grilla NOLOC y el detalle no resolvió → sin asignar."
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
        # Mismo slot, disco distinto → CANDIDATO. El badge VOTADO (identify vs TODO el roster,
        # 0-wrong) es el dueño real y MANDA — sea el latch (volviste al equipado) u OTRO PJ.
        # NO re-confirmar el latch por un sim-a-latch alto ANTES de mirar el voto: un candidato
        # puede parecerse al PJ de la página (QA 2026-06-20: el badge de Seth vota 0.99 pero
        # sim-a-Nicole 0.91 ≥ guard → lo asignaba a Nicole). El sim-a-latch queda de FALLBACK,
        # solo cuando el voto no resolvió.
        owner = self._s17_voted_owner(frame)
        if owner:
            disc.equip_detectado = True
            disc.equip_pj_visual = owner
            disc.equip_libre = False
            if _norm_key(owner) == _norm_key(latch):
                self._set_latch_assignment(disc, latch, 1.0, "voto=latch")   # volviste al equipado
            else:
                self._log_s17_assign(("grid_owner", owner), "[grilla] disco de otro PJ · dueño=%s.", owner)
            return
        # Sin voto confiable: re-confirmar por sim-a-latch (badge se parece al equipado), o LIBRE
        # consistente, o incierto.
        sim = self._identifier.s17_similarity(badge, latch)
        if sim is not None and sim >= _S17_GUARD_MIN:
            self._set_latch_assignment(disc, latch, round(sim, 3), f"{sim:.3f}")
            return
        if self._s17_is_libre(frame):
            disc.equip_pj_visual = None
            disc.equip_libre = True
            self._log_s17_assign(("grid_libre",), "[grilla] disco LIBRE (no equipado por nadie).")
        else:
            # Antes de declararlo incierto: desempate por CONTEXTO (build/equip) sobre el
            # badge de la grilla — mismo rescate que S9. Solo actúa en este fallback (el
            # ancla/latch/voto previos ya resolvieron lo seguro); confirma el top-1/top-2
            # visual solo si el contexto lo distingue (RNF-02). Asigna por badge (no latch).
            if self._tiebreak_owner(disc, badge, tag="s17_owner"):
                disc.equip_detectado = True
                disc.equip_pj_visual = disc.agente_asignado_nombre
                disc.equip_libre = False
                return
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
