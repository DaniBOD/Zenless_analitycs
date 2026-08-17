"""
Hito 2.4.7 / 2.5 — Monitor principal con polling adaptativo · RF-04 §5.
Loop en thread secundario: captura → clasifica → parsea → emite callback.
Integra UpgradeSyncer (S10 PRE/POST) y HotkeyManager (F9/F10).
Hook win32 para EVENT_SYSTEM_FOREGROUND (forzar scan al volver al juego).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from app.core import mem_diag, metrics
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
    AgentStatsParsed, parse_agent_stats, AgentStatsAggregator, read_menu_agent,
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

# Estados que se RE-DESPACHAN mientras siguen en pantalla, además de los de arriba.
#
# El criterio es uno solo: **el contenido cambia sin que cambie la pantalla**. Un modal donde el
# usuario mueve un slider, una grilla por la que scrollea, un panel de detalle que sigue a la
# selección. Sin re-despacho, de esas pantallas solo se ve el PRIMER frame — y el síntoma es
# siempre el mismo y siempre desconcertante: "reconoció el primero y después nada", sin una sola
# línea de error, porque nunca se llega al handler.
#
# Estar acá NO significa pagar OCR por ciclo: cada handler tiene su propio gate (por firma del
# panel, por índice, por hash de la selección) que corta antes de trabajar de más (RNF-06).
#
# Vivía como un literal dentro del loop, donde nada podía verificarlo; se extrajo cuando el QA del
# 2026-08-07 encontró que S30 faltaba.
_REDISPATCH_STATES = frozenset({
    "S17", "S15", "S13", "S3", "S4", "S5", "S10", "S20", "S25",
    "S9",         # inventario de discos: el panel derecho sigue al tile seleccionado
    "S30",        # inventario de amplificadores: misma pantalla, misma razón
    "S26",        # detalle de W-Engine: se cambia de arma sin salir
    "S21", "S22",  # farmeo por baterías: slider y scroll de la lista
    "S11", "S24",  # desmontaje: se tildan discos uno a uno; el modal vive hasta el Confirmar
    "S27", "S28",  # gacha: se navega el riel; y la grilla puede llegar en plena transición
})
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

# ROIs normalizadas (x, y, rw, rh) del modal de USOS de batería (S21), calibradas 2026-07-16
# contra los 4 fixtures (OCR limpio en los 4).
_S21_USOS_ROI = (0.320, 0.548, 0.360, 0.042)    # barra "Cantidad consumida × N"
_S21_STOCK_ROI = (0.400, 0.395, 0.190, 0.045)   # "Batería etérea × 8" (stock disponible)
# S21 NO usa gate de firma (a diferencia del resto de estados con re-OCR). Bug de QA en vivo
# 2026-07-18: el usuario puso 1 uso, movió el slider a 4 y el "Obtenido" quedó en `uso 4/1`.
# Causa medida sobre los 4 fixtures reales (×1/×2/×3/×4): la señal visual de un cambio de valor
# es DEMASIADO CHICA para gatear con confianza — la barra "Cantidad consumida × N" cambia un solo
# dígito (diff 32×32 ≈ 0.5) y hasta incluyendo la perilla del slider el diff es ≈3, y ese número
# ENCOGE cuanto más pasos tenga el slider (con más stock, un paso adyacente mueve la perilla
# menos) → ningún umbral fijo es robusto. Como S21 es un modal breve, se OCRea en cada ciclo y se
# deduplica por VALOR (`_s21_last_usos`), que ya es el mecanismo de correctitud. Así es imposible
# perder un cambio de slider (RNF-06 ok: OCR chico ~1×/s solo mientras el modal está abierto).
# El regex ANCLA en "consumida" a propósito: el modal tiene otro "× 8" (el stock) en el mismo
# eje vertical y un "1 … 4" de slider debajo. Un `×\s*(\d)` suelto leería el número equivocado
# si el ROI se corre — un error silencioso, que es justo lo que RNF-02 prohíbe.
# El "×" (U+00D7) sale del OCR como 'x' o '*' → la clase de caracteres es obligatoria.
_RE_S21_USOS = re.compile(r"consumida\s*[x×*]\s*(\d+)", re.I)
_RE_S21_STOCK = re.compile(r"[x×*]\s*(\d+)\s*$")

# S23 (sustitución de disco entre PJs): el diálogo no revela si se confirmó o canceló; la
# confirmación es ver, después, ese disco (set+slot) equipado por el PJ DESTINO en el flujo S17.
# NO hay ventana de reloj (se quitó el TTL de 120s el 2026-07-20): el pending vive hasta
# consumirse, hasta que otro S23 lo reemplace, o hasta cerrar la app. Ver `_check_swap_owner`.

# ROI (x, y, rw, rh) del viewport scrolleable del modal "Obtenido" (S22), para la firma que
# gatea el re-parseo. Espeja _VIEWPORT_X/_Y de parser_extraccion.
_S22_VIEWPORT_ROI = (0.200, 0.280, 0.360, 0.530)
_S22_SIG_MAX = 5.0
# Marca de "sección ya cerrada" en `_s22_seen` (no vuelve a emitirse nunca).
_S22_SEC_CERRADA = -1
# ROI del panel DETAIL (disco seleccionado). Firma PROPIA, separada de la de la grilla: al
# clickear otro disco el viewport izquierdo casi no cambia (solo se corre el borde amarillo de
# selección, que a 32×32 se pierde) mientras que el panel cambia entero. Con una sola firma, el
# gate de la grilla bloquearía el re-parseo del disco. Espeja `parser_extraccion._DETAIL_PANEL_ROI`.
_S22_DETAIL_ROI = (0.55, 0.29, 0.26, 0.52)
# Umbral MUY por debajo del de la grilla (5.0), y es deliberado: dos paneles de disco son
# estructuralmente IDÉNTICOS (título, nivel, main, subs) y difieren solo en el TEXTO, que a
# 32×32 en gris queda hecho puré. Medido sobre los 11 ejemplos, el diff entre discos DISTINTOS
# va de 2.5 a 6.4 (subir a 64×64 o 96×96 no separa: el mínimo sigue en ~3) → con 5.0 se perdían
# 6 de 10 discos. Con el panel quieto el diff es ~0, así que 1.0 deja 2.5× de margen.
#
# El gate es una OPTIMIZACIÓN, no corrección: quien garantiza que no se repita una línea es el
# dedup por identidad (`_s22_disc_ids`). Por eso conviene errar hacia re-parsear — un disco
# perdido es un bug; un OCR de más, solo costo (acotado: 2 llamadas por ciclo de 700ms).
_S22_DETAIL_SIG_MAX = 1.0

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
# Resets consecutivos de la firma SIN llegar a emitir que se consideran patológicos. Si la firma
# cambia en cada ciclo, el aggregator se reinicia sin parar: `_disc_agg_cycles` vuelve a 0, el techo
# de arriba NUNCA se alcanza, el disco no madura, y el handler devuelve en silencio — para siempre.
# Es lo que pasó en el QA del 2026-07-23 (6 min en S17 sin una sola línea, con el OCR corriendo).
# 3 = por encima del jitter normal de un disco recién abierto, muy por debajo de un trabe real.
_S17_SIG_RESET_ALERT = 3
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


def _hex_center_mask(n: int = 24) -> "np.ndarray":
    """Máscara del centro del hexágono S17 — la zona ANIMADA que hay que excluir de la firma.

    El ROI `hex` (x∈[0.58,0.95], y∈[0.18,0.88]) existe para detectar el cambio de SLOT: el anillo
    de selección salta entre los 6 círculos del borde. Pero el ROI también abarca el arte del
    centro (el W-Engine sobre un fondo con movimiento), que cambia SOLO — y con eso alcanzaba para
    que la firma se considerara "otro disco" en cada ciclo. Efecto: el aggregator se reiniciaba sin
    parar, `_disc_agg_cycles` volvía a 0, el techo nunca llegaba y el handler devolvía en silencio
    para siempre (QA 2026-07-23: 6 min en S17 sin una línea; medido hex=5.5 contra un umbral de 3.0,
    con name=0.6 y detail=1.3 perfectamente estables).

    Centro en (0.42, 0.45) del ROI y radio 0.23 — medido sobre capturas reales 2557×1439. Los 6
    círculos de slot quedan a ≥0.24 del centro, así que la máscara no toca lo que da la señal útil.
    """
    yy, xx = np.ogrid[:n, :n]
    return ((xx - 0.42 * n) ** 2 + (yy - 0.45 * n) ** 2) <= (0.23 * n) ** 2


_S17_HEX_CENTER_MASK = _hex_center_mask()
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
# Latido del loop (QA 2026-07-25): el monitor estuvo 8 minutos sin escribir una línea mientras la
# pantalla cambiaba tres veces, y descartar causas llevó media mañana porque desde afuera un loop
# muerto, uno girando en vacío y una pantalla quieta se ven idénticos. `_note_stall` cubre los
# returns de los HANDLERS; esto cubre el loop mismo.
#   - Si la app estuvo callada _HEARTBEAT_SILENCIO_S, late (prueba de vida).
#   - Cada _HEARTBEAT_BASE_S late igual, aunque haya actividad: da la regla para medir ciclos/s
#     cuando después hay que diagnosticar rendimiento.
_HEARTBEAT_SILENCIO_S = 60.0
_HEARTBEAT_BASE_S = 600.0
# Topes de ascensión que puede mostrar el pill "Nv. X/Y" de un W-Engine. Sirven de firma
# estructural de la pantalla: un DISCO tope en 15 y por ahí se cuela un panel de discos parseado
# como arma (ver `_parece_panel_de_arma`). Confirmado contra la pantalla por Daniel 2026-08-12.
_TOPES_ASCENSION_ARMA = frozenset({10, 20, 30, 40, 50, 60})
# Voto/presencia del dueño (5R.L.3 → L.8): la maquinaria vive en el módulo REUSABLE
# `app/core/owner_vote.py` (OwnerVoteAccumulator + decide_owner) para que futuras
# pantallas (S9 inventario global, S23 reemplazo) la instancien sin re-implementar la
# política. Historia/calibración: grid-primario 0-wrong; detail-solo 1 frame confiable
# (QA 2026-06-18); presencia estructural gana a LIBRE (QA 2026-07-18). Los alias de
# abajo preservan los nombres históricos que importan los tests.
from app.core.owner_vote import (  # noqa: E402
    _DET_SOLO_DOMINANCE,
    _DET_SOLO_MIN_SCORE,
    OwnerVoteAccumulator,
    decide_owner as _decide_s17_owner,
)
from app.core.owner_vote import DETAIL as _SURF_DET, GRID as _SURF_GRID  # noqa: E402

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
    Integra UpgradeSyncer para S10 y HotkeyManager para F9/F10.
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
        on_replacement: Callable[[dict], None] | None = None,   # reemplazo S23 OBSERVADO (toast)
        # Tanda de desmontaje cerrada (S24 OBSERVADO). Callback PROPIO y no `on_replacement`:
        # el payload del reemplazo resuelve avatares y logo de dos PJs, que acá no existen — es
        # un lote de discos destruidos, no un swap.
        on_teardown: Callable[[dict], None] | None = None,
        on_weapon_seen: Callable[[dict], None] | None = None,
        on_agent_detail: Callable[[ScreenState, str | None, bool, str | None], None] | None = None,
        agent_identifier: AgentIdentifier | None = None,
        on_ram_critical: Callable[[], None] | None = None,
        owner_tiebreaker=None,                                  # OwnerTiebreaker opcional
        farm_session=None,                                      # FarmSession opcional (gate S2)
        farm_node_catalog=None,                                 # FarmNodeCatalog opcional (predicción S13)
        set_badge_matcher=None,                                 # SetBadgeMatcher opcional (set por badge S2)
        capture_only_focused: bool = False,                     # gate anti-FP por foco: OFF por defecto
        censo=None,                                             # RosterCensus opcional (censo de cuenta)
        on_census_progress: Callable[[dict], None] | None = None,
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
        # Reemplazo S23 confirmado por OBSERVACIÓN (cambio de dueño por badge) → toast. Es
        # independiente de la persistencia a propósito: el toast afirma lo que se vio, no lo que
        # la DB logró escribir — por eso sale también en read-only. Ver `_check_swap_owner`.
        self._on_replacement = on_replacement
        self._on_teardown = on_teardown
        self._on_weapon_seen = on_weapon_seen
        # Censo de cuenta: OPCIONAL y apagado por defecto. La app se usa la enorme mayoría del
        # tiempo sin censar, y ese camino no debe pagar nada ni cambiar de conducta. A diferencia
        # de `TeardownBatch`, no se construye perezoso: abrir una corrida decide la reanudación
        # multi-sesión, que es cosa del arranque de la app y no del handler.
        self._census = censo
        self._on_census_progress = on_census_progress
        # S26 (detalle de W-Engine, RF-15): firma del panel para no re-OCRear un panel quieto, y
        # firma del último log para no repetir la misma línea. Observación pura: no escribe DB.
        self._s26_panel_sig: bytes | None = None
        self._s26_last_log_sig: tuple | None = None
        # S30 (inventario de amplificadores): mismo gate por firma, otro panel. No lleva votación
        # de dueño ni memoria de tenencia — acá no hay toast que decidir, solo log. `last_log_sig`
        # es lo que mantiene el log edge-triggered: la firma de píxeles gatea el OCR, esta gatea
        # la LÍNEA (sin ella el log se vuelve un heartbeat, QA 2026-08-07).
        self._s30_panel_sig: bytes | None = None
        self._s30_last_log_sig: tuple | None = None
        # Votos del DUEÑO acumulados sobre el arma que se está mirando (`_s26_owner_key` la
        # identifica; al cambiar de arma la votación arranca limpia). Nombrar con UN frame
        # suelto daba dueños que oscilaban entre dos PJs con el panel quieto (QA 2026-07-31).
        self._s26_owner_key: tuple | None = None
        self._s26_owner_votes: dict[str, float] = {}
        # Última tenencia vista por arma. NO se limpia al salir de S26: equipar un arma te saca y
        # te devuelve a la pantalla, y si se olvidara justo ahí, el único cambio que hay para
        # avisar se perdería. Acotado para que una sesión larga no lo haga crecer sin techo.
        self._s26_tenencia_vista: dict[tuple, str] = {}
        # Pares (PJ, arma) ya cosechados para la librería del detalle. Como `_s26_tenencia_vista`,
        # NO se limpia al salir de S26: el dedup es POR SESIÓN, no por entrada a la pantalla —
        # si se limpiara, salir y volver sería la forma trivial de cosechar diez veces la misma, y
        # `add_reference` desaloja la ref más vieja pasadas 10 (las de los discos, justamente las
        # del encuadre diverso).
        self._s26_harvested: set[tuple[str, tuple]] = set()
        # Última línea de `[id_diag/arma]` emitida, para no repetirla (ver `_log_weapon_id_diag`).
        self._weapon_diag_sig: tuple | None = None
        # FRESCURA (QA-06): cuándo se VIO por primera vez un estado nuevo en el loop rápido, y
        # cuál era. Se cierra al emitirse el log de cambio de estado. Ver `_notify_state_change`.
        self._frescura_estado_visto: str | None = None
        self._frescura_estado_t: float | None = None
        # Tanda de desmontaje en curso (S11). Se crea perezosamente al entrar a la pantalla.
        self._teardown = None
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
        # re-emite ~7×. Se limpia al salir de S17 o al forzar re-scan (foreground). RNF-06: sin OCR.
        self._disc_emitted_ids: set = set()
        # Diagnóstico de trabes (returns tempranos mudos) — ver `_note_stall`. {scope: (motivo, n)}
        self._stalls: dict[str, tuple[str, int]] = {}
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
        # con el re-scan de foreground (o al reiniciar). Limitación: dos farmeos con un disco IDÉNTICO (mismo
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
        # Latido del loop: contadores de la ventana en curso. `_hb_last_log_t` lo estampa el
        # handler `_LogClock` con CADA línea de la app, así el latido sabe si hubo silencio real
        # (y no solo silencio del propio monitor).
        self._hb_ticks = 0
        self._hb_nulls = 0
        self._hb_excepciones = 0
        self._hb_ultimo_error: str | None = None
        self._hb_last_t = 0.0
        self._hb_last_log_t = 0.0
        self._log_clock: "logging.Handler | None" = None
        # Último estado confirmado por votación. Persiste aunque el buffer
        # dedupee (devuelva None por mismo estado), para permitir
        # re-extracción CONTINUA de S18 sin requerir cambio de estado ni re-scan.
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
        # ORIGEN del latch actual: "menu" | "s18" | "avatar" | None. Distinto de `_detail_source`,
        # que dice cómo se sostiene AHORA y se degrada a "sostenido" apenas el matcher no confirma
        # un frame. Acá interesa de dónde SALIÓ el nombre: "menu"/"s18" son un nombre LEÍDO de la
        # pantalla (la evidencia más fuerte que hay), "avatar" es un matcher. Sobrevive al
        # carry-forward y solo se limpia al resetear la identidad.
        self._latch_origen: str | None = None
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
        # 5R.L.8 — el estado de voto/presencia del disco actual vive en el acumulador
        # reusable (app/core/owner_vote.py): votos separados grid (primario, 0-wrong) /
        # detail (boost bajo guard), presencia estructural por superficie (el detail
        # arbitra LIBRE) y las pasadas del warmup. Los nombres `_s17_*` históricos
        # quedan como properties de compatibilidad (tests + call sites).
        self._s17_vote = OwnerVoteAccumulator()
        # Último recorte BUENO del detalle-badge para el disco actual: (firma, crop). El recorte
        # es intermitente —Hough cierra el círculo en unos frames y en otros no— y la cosecha de
        # rescate corría sobre el frame de la decisión, que podía ser justo uno de los malos:
        # Lycaon falló 3 de 3 con `det_loc=1 samples=2`, o sea que el recorte SÍ había salido en
        # ese disco y se tiró. Se guarda solo si pasó el clasificador cara-vs-texto, y atado a la
        # firma para no arrastrar la cara de otro disco. Uno solo, no historial (RNF-06).
        self._s17_det_crop: tuple | None = None
        # Rescate de cosecha esperando recorte: (firma, latch, voted). La decisión del dueño corre
        # durante el warmup del disco (~2 pasadas) y ahí el recorte puede no haber salido nunca;
        # el pendiente estira la ventana a todo el rato que el disco esté en pantalla. Se cobra en
        # el loop rápido y se cancela ante cualquier cambio (ver `_collect_pending_rescue`).
        self._s17_rescue_pending: tuple | None = None
        # flag de "maduró pero dueño aún frío" (warmup 5R.L.6).
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
        # consecutivas. OCR es no-determinista frame-a-frame; tras 2-3 ciclos
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
        # S21 (modal de usos de batería): previa display-only EDGE-triggered por valor de N.
        # Se re-emite al mover el slider (sigue siendo S21). Sin gate de firma (ver nota en
        # `_S21_USOS_ROI`): `_s21_last_usos` deduplica la emisión por valor.
        self._s21_last_usos: int | None = None
        # S27 (banner de sintonización): canal seleccionado, display-only EDGE-triggered por
        # índice. Se re-emite al moverse por el riel (se sigue en S27), no 1× por entrada.
        self._s27_last_canal: int | None = None
        # S28 (grilla de resultados): resumen display-only, deduplicado por la firma de las 10
        # rarezas. La pantalla es estática y espera input, así que sin dedup se re-emitiría en
        # cada ciclo de polling.
        self._s28_last_sig: str | None = None
        # Identificador de recompensas: se construye perezosamente (carga librerías de
        # referencia desde disco) y solo si se llega a ver una grilla.
        self._gacha_identifier = None
        # S23 (sustitución de disco): swap PENDIENTE de confirmar. Se arma al ver el diálogo y se
        # consume cuando S17 muestra ese disco en manos del destino. NO expira por reloj. Persiste
        # al SALIR de S23 (la confirmación llega después, en S17). `_s23_last_key` deduplica el log
        # tentativo mientras el diálogo está en pantalla (se resetea al salir de S23).
        self._pending_swap: dict | None = None
        # Flanco del log del check de dueño: (seq del pending, desenlace). El chequeo corre en el
        # ciclo continuo (varias veces por segundo) y sin esto loguearía en loop — RNF-06. El
        # `seq` identifica al pending sin usar `id()`, que Python reutiliza tras el gc.
        self._swap_seq: int = 0
        self._swap_check_mark: tuple | None = None
        self._s23_last_key: tuple | None = None
        # S29 (sustitución de ARMA): mismo dedup por flanco, sin pending — el flujo de W-Engines
        # es display-only por ahora, así que no hay nada que confirmar después.
        self._s29_last_key: tuple | None = None
        # Botón de acción de S17 ("Equipar"/"Reemplazar"/"Desequipar"): 2ª señal del feature
        # "disco libre equipado" (2026-07-22). `_btn_read_key` gatea la RELECTURA (RNF-06): es
        # una llamada extra a OCR y solo cambia en transiciones reales — abrir otro disco, o que
        # el badge aparezca/desaparezca. Ambas cosas ya se computan cada ciclo y son baratas.
        self._s17_action_btn: str | None = None
        self._btn_read_key: tuple | None = None
        # Resets de firma encadenados SIN emisión de por medio (ver `_S17_SIG_RESET_ALERT`).
        self._s17_sig_resets: int = 0
        # S22 (modal "Obtenido"): dedup CONVERGENTE por corrida. {n_uso: nº de discos ya
        # emitidos} o _S22_SEC_CERRADA si ya se emitió completa. `_s22_last_sig` gatea el
        # re-parseo (RNF-06): con el scroll quieto no hay nada nuevo que leer.
        self._s22_last_sig = None
        self._s22_seen: dict[int, int] = {}
        # S22 panel DETAIL (disco seleccionado): firma propia + dedup por IDENTIDAD del disco
        # (no por posición): el usuario puede volver a clickear el mismo disco.
        self._s22_detail_sig = None
        self._s22_disc_ids: set = set()

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
        self._install_log_clock()
        self._thread = threading.Thread(target=self._run, name="zzz-monitor", daemon=True)
        self._thread.start()
        self._hook_foreground()
        self._register_hotkeys()
        log.info("Monitor arrancado.")

    def _install_log_clock(self) -> None:
        """Estampa la hora de la última línea de log de la app, para que el latido distinga
        "nadie logueó nada" de "el monitor no logueó pero el resto sí"."""
        if self._log_clock is not None:
            return
        monitor = self

        class _LogClock(logging.Handler):
            def emit(self, record):        # sin formatear: solo la marca de tiempo
                monitor._hb_last_log_t = time.monotonic()

        self._log_clock = _LogClock(level=logging.INFO)
        logging.getLogger("app").addHandler(self._log_clock)
        self._hb_last_log_t = time.monotonic()

    def stop(self) -> None:
        # Quién pidió la parada. El 2026-07-25 el log decía "Monitor detenido." y no había forma
        # de saber si fue el usuario, el watcher de ventana o un cierre de la app — y esa duda
        # cambió por completo el diagnóstico.
        import traceback as _tb
        quien = "".join(_tb.format_stack(limit=3)[:-1]).strip().splitlines()
        origen = quien[-2].strip() if len(quien) >= 2 else "?"
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._log_clock is not None:
            logging.getLogger("app").removeHandler(self._log_clock)
            self._log_clock = None
        # El buffer de métricas escribe cada 100 muestras; sin este flush, la cola de la última
        # sesión se pierde — y en una pasada corta esa cola puede ser TODO lo medido.
        n = metrics.flush()
        if n:
            log.info("[metrics] %d muestras de latencia volcadas a %s", n, metrics.db_path())
        log.info("Monitor detenido · pedido desde: %s", origen)

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
        Fuerza un scan inmediato. Hoy lo dispara el hook de foreground
        (EVENT_SYSTEM_FOREGROUND) cuando ZZZ vuelve al frente.
        Resetea buffer y fuerza un ciclo de proceso inmediato.

        TAMBIÉN resetea los dedup flags (`_processed_disc_state_code` y
        `_reported_agent_stats_state_code`) para re-emitir el best-known
        al reenfocar el juego, sin necesidad de salir y volver a entrar
        al perfil del PJ.

        Emite un diagnóstico visible en el LivePanel para confirmar
        que el re-scan disparó (antes era silencioso, sin feedback).
        """
        if self._thread and self._thread.is_alive():
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            # S17 continuo: re-emitir el disco actual aunque ya se haya emitido
            # (sin tirar lo fusionado — el re-scan fuerza el re-log/persist del best-known).
            self._disc_emitted = False
            self._disc_emitted_ids.clear()
            self._s3_emitted_ids.clear()   # re-captura también los drops S3 ya vistos
            self._s17_assign_sig = None
            # Resetear también el TemporalBuffer del loop. Sin esto, el re-scan
            # quedaba sin emitir [reconocido]/[stats] porque `buffer.add`
            # devuelve None para el mismo código ya emitido. El buffer
            # vive en _run() como `self._buffer` (instance var, ver _run).
            if self._buffer is not None:
                self._buffer.reset()
                log.info("force_scan: TemporalBuffer reseteado para re-emitir")
            log.info("force_scan: dedup flags reseteados, scan forzado")
            if self._on_diagnostic:
                try:
                    self._on_diagnostic("re-scan forzado (foreground · dedup reseteado)")
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
        force_scan() pueda resetearlo desde otros threads (hook
        de foreground), permitiendo re-emitir [reconocido]/[stats]
        sin necesidad de cambio de estado real.
        """
        self._force_event = threading.Event()
        last_process_time = 0.0
        self._buffer = TemporalBuffer(window_size=3)
        buffer = self._buffer  # alias local para el loop

        while not self._stop.is_set():
            # El latido va en los TRES caminos del loop, incluidos los dos que hacen `continue`.
            # Justamente esos dos eran los mudos: pausado y frame-nulo no dejaban rastro alguno.
            self._hb_ticks += 1
            if not self._paused.is_set():
                self._heartbeat(time.monotonic(), "pausado")
                time.sleep(0.5)
                buffer.reset()
                continue

            frame = self._get_frame()
            if frame is None:
                self._hb_nulls += 1
                self._heartbeat(time.monotonic(), "sin-frame")
                buffer.reset()
                continue

            self._loop_ticks += 1
            # `monotonic` acá es `GetTickCount64()`: resolución 15.625 ms (la declara de frente,
            # a diferencia de `thread_time` — ver el docstring de `test_bench_censo_bajo_3ms`).
            # Como gobierna el `elapsed_ms >= cadence_ms` de abajo, toda cadencia se redondea
            # hacia arriba al próximo múltiplo de tick: los 100 ms nominales disparan a ~109 ms,
            # o sea ~9.1 fps en vez de 10. Medido y DEJADO ASÍ a propósito (2026-08-12): el 9 % no
            # justifica tocar el loop caliente. Si algún día una cadencia tiene que ser exacta,
            # el cambio es pasar esta línea a `perf_counter` — no ajustar las constantes.
            now = time.monotonic()

            # ---- Paso 1: clasificar frame individual ----
            raw_state = self._detector.classify(frame)

            # Heartbeat de memoria (RNF-06, env-gated DANIBOD_MEM_DIAG). No-op si está
            # apagado; throttle interno ~20s → seguro llamar cada iteración.
            mem_diag.heartbeat({"ticks": self._loop_ticks, "st": raw_state.code})
            # Watchdog de RAM (RNF-06): cota dura con auto-restart. Throttle interno ~15s.
            self._ram_watchdog(now)
            # Latido: throttle interno, seguro llamarlo en cada iteración.
            self._heartbeat(now, raw_state.code)

            # FRESCURA (QA-06 · §10 del doc de latencia): marcar el PRIMER frame en que se ve el
            # estado nuevo. `classify` corre en cada tick rápido, así que ese instante es el cambio
            # de pantalla con un error acotado por el período del loop (~109 ms) — no hace falta que
            # el usuario cronometre nada. El cierre está en `_notify_state_change`.
            if (raw_state.code != self._frescura_estado_visto
                    and raw_state.code != (self._confirmed_state.code
                                           if self._confirmed_state is not None else None)):
                self._frescura_estado_visto = raw_state.code
                self._frescura_estado_t = now

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
            # de agente y re-loggear stats sin requerir re-scan.
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
                # nulo) o por re-scan forzado (foreground).
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
                # S21/S22 (farmeo por baterías): CONTINUOS porque su contenido cambia SIN cambiar
                # de pantalla — mover el slider en S21, scrollear la lista en S22. Sin re-despacho
                # solo se vería el primer frame de cada uno. El gate por firma evita el re-trabajo.
                # S11/S24 (desmontaje): CONTINUOS porque su contenido cambia SIN cambiar de
                # pantalla — el usuario tilda discos uno a uno en S11, y S24 vive hasta que
                # aprieta Confirmar. Sin re-despacho solo se vería el primer frame de cada uno.
                # S27 (banner): CONTINUO porque el canal seleccionado cambia SIN cambiar de
                # pantalla — el usuario navega el riel. S28 (grilla) también, porque la pantalla
                # es estática y espera input: si el primer frame llega en plena transición, sin
                # re-despacho no habría segunda oportunidad. En ambos el dedup (por índice de
                # canal / por firma de rarezas) evita re-emitir lo mismo.
                continuous = (active_state.code in _CONTINUOUS_STATES
                              or active_state.code in _REDISPATCH_STATES)
                should_dispatch = forced or (
                    elapsed_ms >= cadence_ms and (voted_state is not None or continuous)
                )
                if should_dispatch:
                    last_process_time = now
                    # Costo del ciclo, ETIQUETADO POR PANTALLA: es lo que compite con la cadencia.
                    # Si un `dispatch:SXX` se acerca a su `polling_cadence_ms`, ese estado tiene el
                    # loop saturado y ahí sí la latencia de cómputo pasa a ser el problema. Sin
                    # esta separación no se distingue "tarda en enterarse" de "tarda en procesar".
                    with metrics.measure_block(f"dispatch:{active_state.code}"):
                        self._safe_dispatch(frame, active_state)

            # ---- Espera corta entre capturas (fast polling) ----
            # (Sin heartbeat periódico: el logging es edge-triggered. El cambio de
            #  estado se loguea en _notify_state_change; los stats/detalle, en sus
            #  handlers, solo cuando el dato cambia.)
            self._wait_fast()

    def _heartbeat(self, now: float, state_code: str | None) -> None:
        """Prueba de vida del loop. Late solo cuando hace falta: tras un tramo de silencio de la
        app, o cada `_HEARTBEAT_BASE_S` como línea de base.

        Reporta lo que el 2026-07-25 no se pudo saber del log: cuántos ciclos giró el loop (¿está
        vivo?), cuántos frames vinieron nulos (¿llega imagen?), en qué estado está, y si algún
        handler viene lanzando excepciones."""
        silencio = now - self._hb_last_log_t
        if silencio < _HEARTBEAT_SILENCIO_S and (now - self._hb_last_t) < _HEARTBEAT_BASE_S:
            return
        tanda = "-"
        if self._teardown is not None and self._teardown.abierta:
            tanda = f"abierta({self._teardown.declarado})"
        log.info("[hb] %d ciclos · frames_nulos=%d · estado=%s · tanda=%s · excepciones=%d",
                 self._hb_ticks, self._hb_nulls, state_code or "-", tanda, self._hb_excepciones)
        self._hb_last_t = now
        self._hb_ticks = 0
        self._hb_nulls = 0

    def _safe_dispatch(self, frame, state: ScreenState) -> None:
        """Despacha atrapando cualquier excepción del handler.

        Sin esto, un `raise` en un `_process_*` termina el thread del monitor: la app queda VIVA
        y CIEGA, sin toast, sin log y sin forma de notarlo desde adentro. Peor en el .exe, donde
        el traceback va a un stderr bufferizado que puede no vaciarse nunca.

        El traceback se loguea una vez por firma de fallo — una pantalla que rompe el handler se
        queda en pantalla y el log se llenaría de tracebacks idénticos. El contador sí sigue
        subiendo y lo canta el latido, para que el problema no desaparezca del registro."""
        try:
            self._dispatch_state(frame, state)
        except Exception as exc:
            self._hb_excepciones += 1
            firma = f"{state.code}:{type(exc).__name__}:{exc}"
            if firma != self._hb_ultimo_error:
                self._hb_ultimo_error = firma
                log.exception("handler de %s falló — el loop sigue vivo", state.code)

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
        # FRESCURA: se cierra acá el cronómetro que abrió el loop rápido al VER el estado nuevo.
        # Lo que queda medido es la pantalla-a-log completa: espera del tick + votación 2/3 del
        # buffer temporal + clasificación. La demora del buffer es real y cuenta — es el precio
        # que se paga por no reportar transiciones espurias.
        if self._frescura_estado_t is not None and self._frescura_estado_visto == state.code:
            metrics.registrar("frescura_estado_a_log",
                              (time.time() - self._frescura_estado_t) * 1000.0)
            self._frescura_estado_t = None
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
        if state.code != "S21":
            self._s21_last_usos = None
        # Gacha: el canal se resetea al salir del banner. La firma de la grilla NO se resetea en
        # S12: entre S28 y volver al banner pasa la animación, y resetear ahí haría re-emitir el
        # mismo resultado al re-entrar. Solo se limpia al volver a ver el banner.
        if state.code != "S27":
            self._s27_last_canal = None
        if state.code == "S27":
            self._s28_last_sig = None
        if state.code != "S23":
            self._s23_last_key = None   # el pending_swap PERSISTE (se confirma en S17); solo el dedup del log resetea
        if state.code != "S29":
            self._s29_last_key = None
        if state.code != "S22":
            self._s22_last_sig = None
            self._s22_seen = {}
            self._s22_detail_sig = None
            self._s22_disc_ids = set()
        if state.code != "S4":
            self._s4_last_sig = None
            self._s4_last_key = None
            self._s4_last_set = None
        if state.code != "S26":
            # Fuera de S26 → olvidar el arma mirada, así al volver se re-emite.
            self._reset_s26_tracking()
        if state.code != "S30":
            self._s30_panel_sig = None      # ídem para el inventario
            self._s30_last_log_sig = None
        # Tanda de desmontaje: se abandona al llegar a CUALQUIER pantalla confirmada que no sea
        # la propia grilla, el modal de commit, o un S12. Va acá arriba y no en el `else` final
        # porque los estados con handler propio (S9, S17, S8…) nunca llegan al `else` — un bug
        # que atrapó el test: salir a S9 dejaba la tanda viva y la commiteaba el S24 siguiente.
        #
        # S12 y S25 están exceptuados a propósito. S25 es el diálogo de confirmación de grado S
        # (antes caía a S12); S12 sigue siendo la transición cuando la selección NO tiene grado S
        # y no hay diálogo. Matar la tanda en cualquiera de los dos haría que el desmontaje por
        # ese camino NUNCA se registre — y para cuando se detecta, los discos ya no existen.
        if (self._teardown is not None and self._teardown.abierta
                and state.code not in ("S11", "S12", "S24", "S25")
                and state.confidence >= _DETAIL_RESET_MIN_CONF):
            self._reset_teardown("salió de la pantalla")
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
            # Volver del modal de mejora (S10) o del vuelto de materiales (S20) NO es una tanda
            # nueva: es la MISMA grilla de afinación, solo que el disco quedó mejorado → conservar
            # los slots para no re-emitir el preview (10 líneas redundantes por cada mejora,
            # QA 2026-07-16). Re-entrar desde cualquier otro lado sí re-previsualiza.
            if prev_code not in ("S10", "S20"):
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
        elif state.code == "S26":
            # Detalle de W-Engine (RF-15). Observación pura: log + toast, cero escrituras a la DB.
            self._process_s26_weapon_detail(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S30":
            # Inventario de amplificadores (RF-15 tramo 2). Display-only y SIN toast: recorrer la
            # grilla es lectura, no novedad.
            self._process_s30_weapon_inventory(frame, state)
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
        elif state.code == "S27":
            # Banner de sintonización: reportar el canal seleccionado (display-only). Es además
            # la ANTELACIÓN a la captura: ver S27 significa que puede venir una tirada.
            self._process_s27_banner(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S28":
            # Grilla de resultados del x10: las 10 recompensas. Display-only, no persiste.
            self._process_s28_resultados(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S21":
            # Modal de usos de batería: OCR del nº de corridas a lanzar con el auto-combate
            # (display-only). Se guarda en FarmSession para que el "Obtenido" posterior sepa
            # cuántos usos esperar. No persiste ni puntúa.
            self._process_s21_usos(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S22":
            # Modal "Obtenido": los drops del farmeo por baterías. Única ventana donde existen
            # (con auto-combate no hay S2 ni S3). Display-only: no persiste ni puntúa.
            self._process_s22_obtenido(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S23":
            # Diálogo de sustitución de disco entre PJs: arma el swap pendiente (origen del
            # diálogo + destino = latch). La confirmación llega DESPUÉS en S17, así que este modal
            # NO debe resetear el latch de identidad (cae en el `else` de abajo, que lo resetearía
            # a conf alta) → se maneja acá explícitamente, preservando `_last_agent_name`.
            self._process_s23_sustitucion(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S29":
            # Diálogo de sustitución de un W-ENGINE. Va acá y no en el `else` por la MISMA razón
            # que S23: es un modal sobre el flujo de equipamiento, y el `else` resetearía el latch
            # de identidad a conf alta (el diálogo matchea ~0.999) justo cuando el PJ que estás
            # mirando es el dato que hace falta al volver a S26.
            self._process_s29_sustitucion_arma(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S11":
            # Pantalla de desmontaje: se SIGUE la selección del usuario (tildes + contador) y se
            # anota cada disco que marca. Display-only — la bitácora va a un archivo en `audit/`,
            # nunca a la DB (RNF-01).
            self._process_s11_desmontaje(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S25":
            # Diálogo de confirmación del desmontaje. NO commitea: el usuario todavía puede
            # cancelar. Solo deja constancia y avisa, porque acá el header queda tapado y el
            # contador ilegible (QA 2026-07-25) — sin esta línea el sistema parece mudo justo
            # en el momento de mayor tensión del flujo.
            self._process_s25_confirmacion(frame, state)
            self._processed_disc_state_code = None
            self._reported_agent_stats_state_code = None
            self._agent_stats_screen_logged = False
        elif state.code == "S24":
            # Modal "Obtenido": la PRUEBA de que el desmontaje ocurrió → commit de la tanda.
            self._process_s24_obtenido(frame, state)
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

    def _diag(self, msg: str) -> None:
        """Emite una línea al panel de diagnóstico, si hay sink. Nunca propaga: un error del
        consumidor de UI no puede tumbar el hilo del monitor."""
        if not self._on_diagnostic:
            return
        try:
            self._on_diagnostic(msg)
        except Exception:
            log.exception("Error en on_diagnostic")

    # ---- Desmontaje: seguimiento de la selección (S11) y commit (S24) --------------------
    def _teardown_batch(self):
        """La tanda en curso, creándola si hace falta."""
        if self._teardown is None:
            from app.core.teardown_batch import TeardownBatch
            self._teardown = TeardownBatch()
        return self._teardown

    def _process_s11_desmontaje(self, frame, state: ScreenState) -> None:
        """Sigue la selección de discos a desmontar (S11), display-only.

        Tres señales del MISMO frame, con autoridades distintas:
          - contador `N/300` → cuántos (global, sobrevive al scroll);
          - tildes por celda → cuál acaba de cambiar (barato, sin OCR);
          - panel DETAIL → qué es ese disco (OCR, solo cuando hay algo que aparear).

        Que el censo y el parseo salgan del mismo frame es lo que hace sólido el apareo: un delta
        de una sola celda confirmado por el contador prueba que fue el único click de la ventana.
        """
        from app.core import parser_desmontaje as pd
        from app.core.teardown_batch import TeardownBatch  # noqa: F401  (documenta la dependencia)

        batch = self._teardown_batch()
        if batch.ensure_open(ts=time.monotonic()):
            log.info("[desmontaje] tanda abierta")

        tildes = pd.tilde_cells(frame)
        counter = pd.parse_header_counter(frame, self._ocr)
        scroll = pd.scroll_pos(frame)

        if counter is None:
            # La autoridad del conteo no se pudo leer. Se sigue observando (el censo puede
            # servir para el próximo ciclo) pero NO se atribuye nada, y el trabe se canta: este
            # es justo el return que en otros handlers quedó mudo por minutos.
            self._note_stall("S11/contador", "no se pudo leer el contador N/300")
        else:
            self._clear_stall("S11/contador")

        decision = batch.observe(tildes=tildes, counter=counter, scroll=scroll,
                                ts=time.monotonic())
        for linea in decision.logs:
            log.info("[desmontaje] %s", linea)
            self._diag(f"[desmontaje] {linea}")

        cell = decision.cell_a_capturar
        if cell is None:
            if counter:
                self._note_stall("S11", f"sin cambios que aparear · {counter}/300")
            return
        self._clear_stall("S11")

        from app.core.parser_disc_s3 import parse_disc_s11
        disc = parse_disc_s11(frame, self._ocr)
        if disc is None or (disc.confianza_global or 0.0) < 0.70:
            conf = 0.0 if disc is None else (disc.confianza_global or 0.0)
            self._note_stall("S11/detalle", f"panel ilegible (conf={conf:.2f})")
            return
        self._clear_stall("S11/detalle")

        set_id = self._resolve_set_id_safe(disc.set_name_raw)
        batch.attach(cell, disc, set_id=set_id)
        log.info("[desmontaje] +1 → %s/300 · %s", counter, self._fmt_teardown_disc(disc))
        self._diag(f"[desmontaje] +1 → {counter}/300 · {self._fmt_teardown_disc(disc)}")

    @staticmethod
    def _fmt_teardown_disc(disc) -> str:
        """Una línea legible del disco anotado (mismo espíritu que el resto de los logs)."""
        nombre = disc.set_name_canon or disc.set_name_raw or "?"
        main = disc.main_stat_canon or disc.main_stat_raw or "?"
        uni = "%" if disc.main_unidad == "%" else ""
        subs = " / ".join(
            f"{(s.nombre_canon or s.nombre_raw or '?')}"
            f"{('+' + str(s.rolls)) if s.rolls else ''} {s.valor if s.valor is not None else '?'}"
            for s in (disc.subs or [])
        )
        return f"{nombre} ({disc.slot}) Nv{disc.nivel} · {main} {disc.main_valor}{uni} · {subs}"

    def _resolve_set_id_safe(self, raw: str | None) -> int | None:
        """`set_id` del catálogo, o None. Lectura pura: la bitácora no escribe la DB (RNF-01)."""
        if not raw:
            return None
        try:
            from app.db.connection import get_connection
            from app.db.repositories import DiscSetRepo
            con = get_connection()
            return DiscSetRepo(con).resolve_id(raw)
        except Exception:
            return None

    def _process_s25_confirmacion(self, frame, state: ScreenState) -> None:
        """Diálogo de confirmación del desmontaje (selección con grado S).

        No lee nada de la pantalla y no commitea: el usuario todavía puede cancelar, y darlo por
        hecho registraría discos que siguen existiendo. Lo único que hace es dejar constancia en
        la tanda y cantar una línea por flanco.

        Vale la pena igual porque es el punto ciego del flujo: el diálogo tapa el header, el
        contador `N/300` se vuelve ilegible y el handler de S11 deja de tener autoridad de conteo.
        El conteo declarado ya está congelado por construcción (sin S11 no hay `observe`), así que
        acá alcanza con decírselo al usuario."""
        batch = self._teardown
        if batch is None or not batch.abierta or batch.committed:
            self._note_stall("S25", "diálogo de desmontaje sin tanda abierta")
            return
        self._clear_stall("S25")
        if not batch.marcar_confirmacion():
            return          # ya se cantó: el diálogo es continuo
        n = batch.declarado
        cuantos = "conteo desconocido" if n is None else f"{n} declarados"
        linea = f"confirmación de grado S · {cuantos} · esperando el Obtenido"
        log.info("[desmontaje] %s", linea)
        self._diag(f"[desmontaje] {linea}")

    def _process_s24_obtenido(self, frame, state: ScreenState) -> None:
        """Commit de la tanda: el modal "Obtenido" es la prueba de que el desmontaje ocurrió.

        Si el usuario cancela, este modal nunca aparece y la tanda muere por abandono sin dejar
        registro. El modal es CONTINUO (vive hasta el Confirmar), así que el gate de idempotencia
        de `commit()` corre en cada ciclo."""
        batch = self._teardown
        if batch is None or not batch.abierta or batch.committed:
            self._note_stall("S24", "Obtenido sin tanda de desmontaje abierta")
            return
        self._clear_stall("S24")

        from app.core import parser_desmontaje as pd
        from app.core.teardown_batch import write_teardown_record

        materiales = pd.parse_obtenido_materiales(frame, self._ocr)
        registro = batch.commit(materiales=materiales, ts=time.monotonic())
        if registro is None:
            return

        conteo = registro["conteo"]
        destino = write_teardown_record(registro)
        corrob = conteo.get("corroborado")
        marca = " ✓" if corrob else (" ⚠ no coincide" if corrob is False else "")
        resumen = (f"tanda cerrada · {conteo['declarado']} desmontados "
                   f"({conteo['capturados']} con datos, {conteo['faltantes']} sin)"
                   f"{' · material ×' + str(conteo['material_primero']) + marca if conteo['material_primero'] is not None else ''}")
        log.info("[desmontaje] %s", resumen)
        self._diag(f"[desmontaje] {resumen}")
        if destino is not None:
            log.info("[desmontaje] → %s", destino)
            self._diag(f"[desmontaje] → {destino}")
        for aviso in registro.get("avisos", []):
            self._diag(f"[desmontaje] ⚠ {aviso}")

        if self._on_teardown:
            try:
                self._on_teardown({
                    "total": conteo["declarado"],
                    "con_datos": conteo["capturados"],
                    "faltantes": conteo["faltantes"],
                    "modo": registro.get("modo"),
                    "archivo": str(destino) if destino else None,
                })
            except Exception:
                log.exception("Error en on_teardown (toast de desmontaje)")

    def _reset_teardown(self, motivo: str) -> None:
        """Cierra la tanda sin registrar (el usuario se fue de la pantalla sin desmontar)."""
        batch = self._teardown
        if batch is None or not batch.abierta:
            return
        declarado = batch.declarado or 0
        batch.drop(motivo)
        if declarado:
            log.info("[desmontaje] tanda abandonada · %d tildados, sin desmontar", declarado)
            self._diag(f"[desmontaje] tanda abandonada · {declarado} tildados, sin desmontar")

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

    def _process_s27_banner(self, frame, state: ScreenState) -> None:
        """Banner de sintonización (S27): qué canal está seleccionado. Display-only.

        EDGE-triggered por índice de canal: mientras se navega el riel el estado sigue siendo
        S27, así que se re-emite al cambiar de canal. Sin OCR — el canal sale del realce
        amarillo del marco de la pastilla, medido 6/6 sobre los banners de 3.1."""
        try:
            from app.core.parser_gacha_banner import selected_channel
            sel = selected_channel(frame)
        except Exception:
            log.exception("Error leyendo el canal del banner (S27)")
            return
        if sel is None or sel.idx == self._s27_last_canal:
            return
        self._s27_last_canal = sel.idx
        msg = f"[gacha] canal #{sel.idx} · {sel.tipo}"
        log.info("Gacha S27: canal #%d (%s) realce=%.4f", sel.idx, sel.tipo, sel.score)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.exception("on_diagnostic S27")

    def _process_s28_resultados(self, frame, state: ScreenState) -> None:
        """Grilla de resultados (S28): las 10 recompensas del x10. Display-only.

        Se reporta SIEMPRE lo que es verdad y barato: rareza de cada tile, la etiqueta `NEW!` y
        el nombre del ítem cuando el matcher puede afirmarlo. Hoy eso alcanza a los W-Engines
        rango B; agentes y engines A/S se reportan por rareza sin nombre, porque el matcher
        todavía no los identifica (ver `app/core/gacha_identity`). Preferimos "sin identificar"
        antes que un nombre inventado (RNF-02)."""
        try:
            from app.core.parser_gacha_result import parse_grid
            tiles = parse_grid(frame)
        except Exception:
            log.exception("Error parseando la grilla de sintonización (S28)")
            return
        if not tiles:
            return
        sig = "".join((t.rarity or "?") + ("*" if t.is_new else "") for t in tiles)
        if sig == self._s28_last_sig:
            return
        self._s28_last_sig = sig

        if self._gacha_identifier is None:
            try:
                from app.core.gacha_identity import GachaIdentifier
                self._gacha_identifier = GachaIdentifier()
            except Exception:
                log.exception("No pude construir el identificador de recompensas")

        partes: list[str] = []
        for t in tiles:
            nombre = None
            if self._gacha_identifier is not None:
                try:
                    nombre = self._gacha_identifier.identify(frame, t).name
                except Exception:
                    log.exception("Error identificando el tile %d", t.idx)
            etiqueta = nombre or "?"
            partes.append(f"{t.rarity or '?'}{'*' if t.is_new else ''}:{etiqueta}")

        n_s = sum(1 for t in tiles if t.rarity == "S")
        n_a = sum(1 for t in tiles if t.rarity == "A")
        nuevos = sum(1 for t in tiles if t.is_new)
        cabecera = f"[gacha] {len(tiles)} recompensas · {n_s} S · {n_a} A"
        if nuevos:
            cabecera += f" · {nuevos} nuevo(s)"
        msg = cabecera + " → " + " ".join(partes)
        log.info("Gacha S28: %s", msg)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.exception("on_diagnostic S28")

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

    def _ocr_s21_roi(self, frame, roi, rx) -> int | None:
        """OCR de una ROI del modal S21 → el entero que capture `rx`, o None si no matchea."""
        try:
            h, w = frame.shape[:2]
            x, y, rw, rh = roi
            crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
            if crop.size == 0:
                return None
            text, _conf = self._ocr.text(crop, psm=7, lang="spa")
        except Exception:
            log.exception("Error OCR ROI S21")
            return None
        m = rx.search(text or "")
        return int(m.group(1)) if m else None

    def _process_s21_usos(self, frame, state: ScreenState) -> None:
        """Modal de usos de batería (S21): OCR de "Cantidad consumida × N" → cuántas corridas
        va a lanzar el auto-combate. Se guarda en `FarmSession` (el "Obtenido" posterior lo usa
        como denominador de "uso 2/4") y se emite la previa cruzándolo con el nodo predicho en
        S13. Display-only: no persiste ni puntúa.

        EDGE-triggered por VALOR (NO 1× por entrada a S21): mover el slider cambia N sin salir
        del modal, así que se re-emite cada vez que N cambia. Sin gate de firma (ver nota en
        `_S21_USOS_ROI`): se OCRea cada ciclo y `_s21_last_usos` deduplica por valor — la señal
        visual de un cambio de slider es demasiado chica para gatear con confianza. Se resetea al
        salir de S21 (ver _dispatch_state)."""
        if self._farm_session is None:
            return

        n_usos = self._ocr_s21_roi(frame, _S21_USOS_ROI, _RE_S21_USOS)
        if self._id_diag_on:
            log.info("[s21_diag] usos=%s", n_usos)
        if n_usos is None or not (1 <= n_usos <= 9):
            return   # ilegible o fuera de rango → no inventar (RNF-02); reintenta al cambiar
        if n_usos == self._s21_last_usos:
            return   # mismo valor ya emitido → no re-loguear
        self._s21_last_usos = n_usos

        ts = time.monotonic()
        self._farm_session.set_usos(n_usos, ts)

        # Stock: dato secundario. Si no se lee, se OMITE del mensaje (nunca se inventa).
        stock = self._ocr_s21_roi(frame, _S21_STOCK_ROI, _RE_S21_STOCK)

        pred = self._farm_session.predicted(ts)
        if pred is not None:
            node, sets = pred
            names = " / ".join(en for _sid, en in sets)
            ctx = f"nodo: {node} → predice {names}"
        else:
            # N es un dato LEÍDO de la pantalla, no inferido → se reporta igual, degradado.
            ctx = "sin nodo predicho"
        msg = f"[extracción] {n_usos} uso(s) de batería · {ctx}"
        if stock is not None:
            msg += f" · stock {stock}"
        log.info("Extracción S21: %d uso(s) · %s · stock=%s", n_usos, ctx, stock)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.debug("on_diagnostic S21 falló", exc_info=True)

    # --- S23: sustitución de disco entre PJs ---------------------------------
    def _agent_roster(self) -> list[str]:
        """Nombres del roster (para resolver el PJ origen del diálogo). Reusa el roster que ya
        carga el AgentIdentifier desde la tabla `agents`; [] si no hay identifier."""
        ai = self._identifier
        if ai is None:
            return []
        try:
            ai._load_roster()
            return list((ai._roster_norm or {}).values())
        except Exception:
            return []

    def _resolve_agent_name(self, raw: str | None) -> str | None:
        """OCR de un nombre de PJ → nombre canónico del roster. Exacto (normalizado) → fuzzy
        difflib con guarda (patrón de `farm_nodes._resolve`). None si no hay match seguro — el OCR
        del origen ('7ixuan' por 'Yixuan') se absorbe acá. Sin roster → None (el caller degrada)."""
        if not raw:
            return None
        from app.core.stats_vocab import _norm_key
        roster = self._agent_roster()
        if not roster:
            return None
        key = _norm_key(raw)
        for n in roster:
            if _norm_key(n) == key:
                return n
        import difflib
        scored = sorted(
            ((difflib.SequenceMatcher(None, key, _norm_key(n)).ratio(), n) for n in roster),
            reverse=True,
        )
        if scored and scored[0][0] >= 0.72 and (len(scored) < 2 or scored[0][0] - scored[1][0] >= 0.06):
            return scored[0][1]
        return None

    def _dump_s23_fallo(self, frame) -> None:
        """Guarda el frame de un S23 que el parser NO pudo leer, para reproducir offline.

        Una vez por trabe (el primer ciclo), no por ciclo: S23 corre a 1000ms y el diálogo dura
        varios segundos. Sin esto no hay forma de saber QUÉ leyó el OCR — el frame se pierde."""
        if self._stalls.get("S23", ("", 0))[1] != 1:
            return
        try:
            import cv2
            from datetime import datetime
            from pathlib import Path
            p = Path("audit") / "s23_parse_fallo"
            p.mkdir(parents=True, exist_ok=True)
            f = p / f"s23_{datetime.now():%Y%m%d_%H%M%S}.png"
            cv2.imwrite(str(f), frame)
            log.info("[S23] frame guardado para diagnóstico: %s", f)
        except Exception:
            log.debug("dump S23 falló", exc_info=True)

    def _process_s23_sustitucion(self, frame, state: ScreenState) -> None:
        """Diálogo de sustitución: arma el swap PENDIENTE {origen, set, slot, destino=latch}. El
        check del dueño ocurre después en S17 (`_check_swap_owner`), que decide toast y hint.
        Acá solo se loguea la intención (tentativo): ver el diálogo NO prueba que se haya confirmado
        (se puede cancelar) → si no llega el disco, el pending expira por TTL en silencio."""
        from app.core.parser_sustitucion import parse_sustitucion
        d = parse_sustitucion(frame, self._ocr)
        if d is None:
            # El detector ve el diálogo (conf alta) pero el parser no lo lee → sin pending, sin
            # toast, y antes esto era MUDO: desde afuera "no reconoce el swap" no distinguía
            # entre no-detectado y no-parseado (QA 2026-07-20, intento con Soukaku).
            self._note_stall("S23", "el parser no leyó el diálogo")
            self._dump_s23_fallo(frame)
            return
        self._clear_stall("S23")
        set_id = None
        set_name = None
        if self._set_repo is not None:
            try:
                set_id = self._set_repo.resolve_id(d.set_raw)
                if set_id is not None:
                    entry = next((e for e in self._set_repo.get_all() if e.id == set_id), None)
                    set_name = entry.nombre if entry else None
            except Exception:
                log.debug("resolve set S23 falló", exc_info=True)
        origin = self._resolve_agent_name(d.origin_raw) or d.origin_raw.strip()
        dest = self._last_agent_name   # PJ cuya pantalla de equipamiento se está viendo (destino)

        # Dedup del log mientras el diálogo sigue en pantalla (S23 dura varios ciclos).
        key = (origin, set_id if set_id is not None else d.set_raw, d.slot, dest)
        if key == self._s23_last_key:
            return
        self._s23_last_key = key

        self._swap_seq += 1
        self._pending_swap = {
            "seq": self._swap_seq,          # identifica ESTE pending para el flanco del log
            "origin_kind": "pj",            # ver `_arm_libre_pending` para el otro origen
            "origin_name": origin,
            "set_id": set_id,
            "set_name": set_name or d.set_raw,
            "slot": d.slot,
            "dest_name": dest,
            "ts": time.monotonic(),
        }
        self._swap_check_mark = None        # pending nuevo → el check vuelve a loguear
        set_disp = set_name or d.set_raw
        msg = f"[reemplazo] {set_disp} slot {d.slot} · {origin} → {dest or '?'} (pendiente)"
        log.info("Sustitución S23 (pendiente): %s", msg)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.debug("on_diagnostic S23 falló", exc_info=True)

    def _process_s29_sustitucion_arma(self, frame, state: ScreenState) -> None:
        """Diálogo de sustitución de un W-Engine. **Display-only**: deja una línea por flanco y
        nada más — ni pending, ni DB, ni toast (ver el diálogo no prueba que se confirme).

        Este estado nació para que el diálogo del arma dejara de caer en S23, donde
        `parse_sustitucion` fallaba —lo correcto, no tiene slot— y volcaba un PNG de diagnóstico
        por cada reemplazo, ensuciando `audit/s23_parse_fallo/` y disfrazando los fallos reales
        (QA 2026-07-30). Acá no hay volcado: que el parser de discos no lea esto es el diseño.

        El texto trae **PJ + arma escritos por el juego**, que es verdad de tierra sin librería de
        badges de por medio. Hoy solo se loguea; el día que el flujo de armas escriba la DB, esta
        es la fuente del origen."""
        from app.core.parser_sustitucion import parse_sustitucion_arma
        d = parse_sustitucion_arma(frame, self._ocr)
        if d is None:
            self._note_stall("S29", "el parser no leyó el diálogo del arma")
            return
        self._clear_stall("S29")
        origin = self._resolve_agent_name(d.origin_raw) or d.origin_raw.strip()
        dest = self._last_agent_name    # PJ cuya pantalla se está viendo (destino del arma)

        # Dedup por flanco: el diálogo dura varios ciclos.
        key = (origin, d.weapon_raw, dest)
        if key == self._s29_last_key:
            return
        self._s29_last_key = key

        msg = f"[reemplazo arma] {d.weapon_raw} · {origin} → {dest or '?'} (pendiente)"
        log.info("Sustitución de W-Engine S29 (display-only): %s", msg)
        self._diag(msg)

    def _refresh_action_button(self, merged, frame, badge_present: bool = False) -> None:
        """Relee el botón de acción de S17 y lo cachea en `_s17_action_btn`.

        Gate RNF-06: es una llamada EXTRA a OCR, así que solo se relee cuando cambia
        `(identidad del disco, badge presente?)`. Las dos ya se computan cada ciclo y son
        baratas (el badge es un crop + Canny).

        **Excepción (QA 2026-07-23, caso A):** con un pendiente LIBRE abierto sobre ESTE disco,
        el gate se saltea y se relee en cada ciclo. Esa clave no alcanzaba: al equipar un disco
        libre en un slot VACÍO no cambia la identidad (es el mismo disco) ni `badge_present` (ya
        estaba en True por el voto previo) → el botón quedaba cacheado en 'equipar' para siempre
        y el check se abstenía con "solo badge" eternamente. El bypass está acotado al disco que
        hay que confirmar, que es exactamente cuando la respuesta importa."""
        if frame is None or merged is None:
            return
        try:
            identity = self._disc_identity(merged)
        except Exception:
            return
        key = (identity, bool(badge_present))
        if key == self._btn_read_key and not self._btn_gate_bypassed(identity):
            return
        self._btn_read_key = key
        try:
            from app.core.parser_disc_s17 import read_s17_action_button
            self._s17_action_btn = read_s17_action_button(frame, self._ocr)
        except Exception:
            log.debug("lectura del botón de acción S17 falló", exc_info=True)
            self._s17_action_btn = None

    def _btn_gate_bypassed(self, identity) -> bool:
        """¿Hay un pendiente LIBRE abierto sobre ESTE disco? Entonces el botón se relee siempre.

        Acotado a propósito: solo el disco del pendiente, y solo con origen LIBRE (el pendiente
        de S23 no consulta el botón). Fuera de eso rige el gate normal."""
        ps = self._pending_swap
        return (ps is not None and ps.get("origin_kind") == "libre"
                and self._same_disc_fuzzy(ps.get("identity"), identity))

    def _arm_libre_pending(self, merged) -> None:
        """Arma el pendiente de un disco LIBRE que el usuario podría estar por equipar.

        Es el espejo del diálogo S23, pero con evidencia MUCHO más débil: ver un disco libre no
        compromete a nada (podés estar mirando). Por eso el que decide es el CHECK, no esto —
        armar es gratis y no afirma nada.

        Se exigen las DOS señales desde el arranque: `equip_libre` (badge ausente) y un botón que
        solo aparece en discos libres. LIBRE es la lectura más frágil del sistema de badges (falso
        LIBRE de Jane, 2026-07-19 → "presencia gana a LIBRE"), y el botón —texto de posición fija—
        la confirma por una vía independiente.

        Un pendiente nuevo SUPERA al anterior (sea LIBRE o de S23): las dos acciones son
        mutuamente excluyentes y la última intención es la que vale."""
        if merged is None or not merged.equip_libre:
            return
        if self._s17_action_btn not in ("equipar", "reemplazar"):
            return
        latch = self._last_agent_name
        if not latch:
            return   # sin destino no hay nada que afirmar después (RNF-02)
        slot = merged.slot or 0
        set_name = merged.set_name_canon or merged.set_name_raw or ""
        if not slot or not set_name:
            return
        try:
            identity = self._disc_identity(merged)
        except Exception:
            return
        ps = self._pending_swap
        if (ps is not None and ps.get("origin_kind") == "libre"
                and ps.get("dest_name") == latch
                and self._same_disc_fuzzy(ps.get("identity"), identity)):
            return   # ya armado para este disco y este PJ → no re-loguear ni re-armar por
                     # parpadeo de substats (RNF-06; QA 2026-07-23 re-logueaba a conf 0.89)
        set_id = None
        if self._set_repo is not None:
            try:
                set_id = self._set_repo.resolve_id(set_name)
            except Exception:
                set_id = None
        self._swap_seq += 1
        self._pending_swap = {
            "seq": self._swap_seq,
            "origin_kind": "libre",
            "origin_name": "LIBRE",
            "identity": identity,
            "set_id": set_id,
            "set_name": set_name,
            "slot": slot,
            "dest_name": latch,
            "ts": time.monotonic(),
        }
        self._swap_check_mark = None
        msg = (f"[equipado] {set_name} slot {slot} · LIBRE → {latch} "
               f"(pendiente · botón '{self._s17_action_btn}')")
        log.info("%s", msg)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.debug("on_diagnostic armado libre falló", exc_info=True)

    def _check_libre_equipado(self, merged, ps: dict) -> None:
        """CHECK observacional del disco LIBRE: ¿lo equipó al PJ que está mirando?

        Exige que las DOS señales volteen juntas: el badge pasa a nombrar al destino Y el botón
        pasa a "Desequipar". Cada una tapa el agujero de la otra — el badge puede dar un falso
        LIBRE/falso dueño, y el botón no dice quién es el dueño. Para un falso positivo tendrían
        que fallar las dos a la vez y de forma coherente.

        Dos diferencias deliberadas con el pendiente de S23:
          - **Identidad COMPLETA** (set, slot, main, {substat+rolls}), no solo set+slot. Sin esto
            hay un falso positivo concreto: mirás un Jazz Caótico slot 1 libre, NO lo equipás, y
            más tarde entrás a un PJ que ya tiene uno puesto → "antes LIBRE, ahora ese PJ".
          - **Muere al cambiar de PJ.** El diálogo S23 es un compromiso explícito y por eso su
            pendiente vive hasta consumirse; mirar un disco libre no compromete nada. Un disco
            libre se equipa al PJ que estás mirando, en la misma visita."""
        from app.core.stats_vocab import _norm_key
        dest = ps.get("dest_name")
        latch = self._last_agent_name
        if latch and dest and _norm_key(latch) != _norm_key(dest):
            log.info("[equipado] pendiente descartado · cambiaste de %s a %s sin equipar",
                     dest, latch)
            self._pending_swap = None
            self._swap_check_mark = None
            return
        try:
            cur_id = self._disc_identity(merged)
            if not self._same_disc_fuzzy(cur_id, ps.get("identity")):
                # El disco en pantalla no es el del pendiente. Era el ÚNICO desenlace del check
                # que salía mudo; se loguea por flanco (una vez por pendiente) para no volver a
                # perseguir "no saltó el toast" a ciegas (QA 2026-07-23). Incluye ambas
                # identidades: si el fuzzy alguna vez se queda corto ante ruido de OCR, acá se ve.
                if self._swap_check_mark != (ps.get("seq"), "nomatch"):
                    self._swap_check_mark = (ps.get("seq"), "nomatch")
                    log.info("[equipado] check dueño · %s slot %s · no coincide con el disco del "
                             "pendiente (armado=%r ahora=%r) → se abstiene",
                             ps.get("set_name"), ps.get("slot"), ps.get("identity"), cur_id)
                return
        except Exception:
            return

        owner = merged.agente_asignado_nombre or merged.equip_pj_visual
        btn = self._s17_action_btn
        if not owner:
            outcome = "incierto"                 # sigue sin dueño → todavía no lo equipó
        elif dest and _norm_key(owner) != _norm_key(dest):
            outcome = "otro"                     # lo equipó otro PJ (¿?) → abstenerse
        elif btn != "desequipar":
            outcome = "solo badge"               # el badge dice dueño pero el botón no confirma
        else:
            outcome = "cambió"                   # las dos señales voltearon → lo equipó

        marca = (ps.get("seq"), outcome)
        if self._swap_check_mark != marca:
            self._swap_check_mark = marca
            etiqueta = "CAMBIÓ ✓" if outcome == "cambió" else outcome
            msg = (f"[equipado] check dueño · {ps['set_name']} slot {ps['slot']}: "
                   f"LIBRE → {owner or '?'} · botón '{btn or '?'}' · {etiqueta}")
            log.info("%s", msg)
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(msg)
                except Exception:
                    log.debug("on_diagnostic check libre falló", exc_info=True)

        if outcome != "cambió":
            return
        # Confirmado. A diferencia del reemplazo NO se marca `swap_origin_hint`/`swap_fresh`: no
        # hay fila de origen que mover (el disco no era de nadie), así que la persistencia sigue
        # su camino normal sin pistas nuestras. Este feature es puramente observacional.
        self._pending_swap = None
        self._swap_check_mark = None
        if self._on_replacement:
            try:
                self._on_replacement({
                    "kind": "equipado",
                    "set_name": ps["set_name"], "slot": ps["slot"],
                    "from_name": None, "to_name": owner,
                })
            except Exception:
                log.exception("Error en on_replacement (toast de equipado)")

    def _check_swap_owner(self, merged, state: ScreenState) -> None:
        """CHECK observacional del reemplazo: ¿el disco del swap pendiente cambió de dueño?

        Es el corazón del feature (rediseño 2026-07-20). El toast es una afirmación sobre lo que
        se VE en pantalla —"este disco cambió de manos"— así que se decide acá, mirando el dueño
        por badge, y NO en la persistencia. Antes colgaba de que la transacción SQL moviera una
        fila (`SyncResult.moved`), lo que lo hacía imposible de validar en read-only y lo mataba
        ante cualquier desincronización DB↔juego, aunque el swap hubiera ocurrido a la vista.

        Origen = el diálogo S23 (la pantalla dice quién lo tiene). Destino = el PJ cuyo
        equipamiento se está viendo. Confirmación = ver ese disco ahora en manos del destino.

        Cuatro desenlaces, TODOS logueados (antes esto era mudo y "no saltó el toast" no
        distinguía entre canceló, incierto o roto). Solo `cambió` afirma el reemplazo; el resto
        se abstiene y NO consume el pending (RNF-02: nunca afirmar lo no visto).

        FRESCURA = "no superado todavía", NO "dentro de N segundos": el pending no expira por
        reloj, vive hasta consumirse acá, hasta que otro S23 lo reemplace, o hasta cerrar la app.
        Es seguro porque exigimos ver el disco en manos del DESTINO: si cancelaste, no pasa."""
        ps = self._pending_swap
        if ps is None:
            return
        if ps.get("origin_kind") == "libre":
            self._check_libre_equipado(merged, ps)
            return
        slot = merged.slot or 0
        merged_set = merged.set_name_canon or merged.set_name_raw or ""
        if not slot or not merged_set:
            return   # todavía no sabemos qué disco es → aún no hay nada que chequear
        if slot != ps["slot"]:
            return   # otro slot → no es el disco del swap
        from app.core.stats_vocab import _norm_key
        merged_set_id = None
        if self._set_repo is not None:
            try:
                merged_set_id = self._set_repo.resolve_id(merged_set)
            except Exception:
                merged_set_id = None
        set_ok = (ps["set_id"] is not None and merged_set_id == ps["set_id"]) or \
                 _norm_key(merged_set) == _norm_key(ps["set_name"])
        if not set_ok:
            return   # otro set → no es el disco del swap

        # --- Es EL disco del swap: de acá en adelante el resultado SIEMPRE se loguea ---
        # Dueño CERTERO (ancla/latch) o, si no lo hay, el OBSERVADO por badge. El observado cubre
        # el caso real visto en QA: "[badge] ancla decía X pero el badge dice Y" — ahí el badge
        # tiene razón y el ancla se equivocó; exigir solo el certero perdía esos swaps.
        owner = merged.agente_asignado_nombre or merged.equip_pj_visual
        origin, dest = ps["origin_name"], ps["dest_name"]
        if not owner:
            outcome = "incierto"      # equipado sin nombre, o libre → esperar más votos
        elif _norm_key(owner) == _norm_key(origin):
            outcome = "sin cambio"    # sigue con el origen → se canceló el reemplazo
        elif dest and _norm_key(owner) != _norm_key(dest):
            outcome = "otro"          # ni origen ni destino → algo no cierra, abstenerse
        else:
            outcome = "cambió"        # está en manos del destino → el reemplazo ocurrió

        # Log por FLANCO (RNF-06): el ciclo continuo repite el chequeo muchas veces por segundo.
        marca = (ps.get("seq"), outcome)
        if self._swap_check_mark != marca:
            self._swap_check_mark = marca
            etiqueta = "CAMBIÓ ✓" if outcome == "cambió" else outcome
            msg = (f"[reemplazo] check dueño · {ps['set_name']} slot {ps['slot']}: "
                   f"{origin} → {owner or '?'} · {etiqueta}")
            log.info("%s", msg)
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(msg)
                except Exception:
                    log.debug("on_diagnostic check swap falló", exc_info=True)

        if outcome != "cambió":
            return
        # Confirmado: marcar el disco (la persistencia usará el hint para MOVER la fila sin
        # duplicar) y avisar al toast. Son dos consumidores independientes: el toast sale igual
        # aunque la persistencia esté gateada por read-only.
        merged.swap_origin_hint = origin
        merged.swap_fresh = True
        self._pending_swap = None
        self._swap_check_mark = None
        if self._on_replacement:
            try:
                self._on_replacement({
                    "kind": "reemplazo",
                    "set_name": ps["set_name"], "slot": ps["slot"],
                    "from_name": origin, "to_name": owner,
                })
            except Exception:
                log.exception("Error en on_replacement (toast de reemplazo)")

    @staticmethod
    def _s22_viewport_signature(frame):
        """Firma 32×32 gris del viewport scrolleable (S22), sin OCR (RNF-06). Gatea el
        re-parseo: con el scroll quieto no hay nada nuevo que leer. Es lo que hace viable la
        cadencia de 700 ms (el trabajo pesado corre solo mientras se scrollea)."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            h, w = frame.shape[:2]
            x, y, rw, rh = _S22_VIEWPORT_ROI
            sub = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
            if sub.size == 0:
                return None
            return cv2.cvtColor(
                cv2.resize(sub, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return None

    @staticmethod
    def _fmt_seccion(sec, n_total: int | None, cand_en: list[str]) -> str:
        """Una corrida → una línea display-only.

        Cada disco muestra LO QUE SE SABE de él y nada más (RNF-02): "slot 2 Wuthering Salon"
        si se leyeron los dos, "slot 2" o "Wuthering Salon" si solo uno. Nunca un "slot ?" ni
        un set adivinado. El conteo siempre se afirma —la franja dorada es evidencia directa—
        y el "≥" marca que puede haber más discos sin scrollear.
        """
        uso = f"uso {sec.n_uso}" + (f"/{n_total}" if n_total else "")
        n = len(sec.discos)
        conteo = f"{n} discos S" if sec.completa else f"≥{n} discos S"

        items, sin_datos = [], 0
        for d in sec.discos:
            if d.slot is not None and d.set_name:
                items.append(f"slot {d.slot} {d.set_name}")
            elif d.slot is not None:
                items.append(f"slot {d.slot}")
            elif d.set_name:
                items.append(d.set_name)
            else:
                sin_datos += 1

        if items:
            cuerpo = f"{conteo}: " + ", ".join(items)
            if sin_datos:
                cuerpo += f" (+{sin_datos} sin identificar)"
        else:
            cuerpo = conteo
        partes = [f"[extracción] {uso}", cuerpo]

        # Si NINGÚN set se confirmó, enumerar el universo que predijo el nodo es honesto y
        # útil (mismo formato que `_process_s2_tiles`); elegir uno sin evidencia, no.
        if not any(d.set_name for d in sec.discos) and cand_en:
            partes.append("set: " + " o ".join(cand_en))
        return " · ".join(partes)

    @staticmethod
    def _s22_detail_signature(frame):
        """Firma 32×32 gris del panel DETAIL (S22), sin OCR (RNF-06). Gatea el re-parseo del
        disco seleccionado: si el panel no cambió, es el mismo disco."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        try:
            import cv2
            h, w = frame.shape[:2]
            x, y, rw, rh = _S22_DETAIL_ROI
            sub = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
            if sub.size == 0:
                return None
            return cv2.cvtColor(
                cv2.resize(sub, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
            ).astype(np.float32)
        except Exception:
            return None

    @staticmethod
    def _fmt_stat(nombre: str, valor, unidad: str | None) -> str:
        if valor is None:
            return nombre
        num = f"{valor:g}"
        return f"{nombre} {num}%" if unidad == "%" else f"{nombre} {num}"

    def _process_s22_detail(self, frame, state: ScreenState) -> None:
        """Panel DETAIL de S22: el disco que el usuario tiene seleccionado, COMPLETO (set en
        texto + slot + nivel + main + substats). Es la fuente autoritativa del slot — la grilla
        se abstiene en el '4' — y la única que da los stats.

        Dedup por IDENTIDAD del disco (no por posición): volver a clickear el mismo disco no
        re-loguea, pero dos discos distintos del mismo set/slot sí se distinguen (la identidad
        incluye los substats). Display-only: no persiste ni puntúa."""
        # Gate propio (RNF-06): mismo panel = mismo disco = nada nuevo que leer.
        sig = self._s22_detail_signature(frame)
        if (sig is not None and self._s22_detail_sig is not None
                and self._sig_component_diff(sig, self._s22_detail_sig) <= _S22_DETAIL_SIG_MAX):
            return
        self._s22_detail_sig = sig
        try:
            from app.core.parser_extraccion import parse_detail_disc
            d = parse_detail_disc(frame, self._ocr)
        except Exception:
            log.exception("Error parseando el panel DETAIL de S22")
            return
        if d is None:
            return   # no hay disco seleccionado (el modal abre en "Crédito proxy"), o ilegible

        # Canon del set: resolución DIFUSA (el OCR rompe las tildes — 'Salönhuracanado' por
        # 'Salón huracanado'). La comparación exacta de `parse_modal_detalle` no serviría acá.
        if self._set_repo is not None and not d.set_name_canon and d.set_name_raw:
            try:
                sid = self._set_repo.resolve_id(d.set_name_raw)
                if sid is not None:
                    entry = next((e for e in self._set_repo.get_all() if e.id == sid), None)
                    if entry is not None:
                        d.set_name_canon = entry.nombre
            except Exception:
                log.debug("No se pudo resolver el set del disco S22", exc_info=True)

        set_disp = d.set_name_canon or d.set_name_raw or "set no identificado"
        identity = self._disc_identity(d)
        if identity in self._s22_disc_ids:
            # Avisar en vez de callar: el silencio se lee como "no lo detectó" (QA en vivo
            # 2026-07-16 — el disco ya se había leído al arrancar, porque el juego lo tenía
            # seleccionado, y al clickearlo después no pasaba nada). Mismo feedback que S5.
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(f"[disco] ya capturado: {set_disp} slot {d.slot}")
                except Exception:
                    log.debug("on_diagnostic S22 ya-capturado falló", exc_info=True)
            return
        self._s22_disc_ids.add(identity)

        partes = [f"[disco] {set_disp} · slot {d.slot}", f"nivel {d.nivel}/15"]
        main = d.main_stat_canon or d.main_stat_raw
        if main:
            partes.append(self._fmt_stat(main, d.main_valor, d.main_unidad))
        subs = [self._fmt_stat(s.nombre_canon or s.nombre_raw, s.valor, s.unidad)
                for s in (d.subs or []) if (s.nombre_canon or s.nombre_raw)]
        if subs:
            partes.append("subs: " + ", ".join(subs))
        msg = " · ".join(partes)
        log.info("Disco S22 (extracción): %s", msg)
        if self._on_diagnostic:
            try:
                self._on_diagnostic(msg)
            except Exception:
                log.debug("on_diagnostic disco S22 falló", exc_info=True)

        # Toast + recomendación, igual que el detalle de un drop S3 (mismo tipo de disco: un
        # drop nuevo, sin dueño). El panel DETAIL de S22 es la vista autoritativa del disco, así
        # que al mirarlo el usuario espera la MISMA recomendación (Equipar/Mejorar/…) que le da
        # el "Ver" (S6/S7) — era el único camino de detalle que no toastaba (QA en vivo
        # 2026-07-18). El controller enruta S22 al recommender (no a persistencia): display-only.
        d.rareza = "S"   # invariante del "Obtenido": todo drop conservado es tier S (dorado)
        if self._on_disc:
            try:
                self._on_disc(d, state)
            except Exception:
                log.exception("Error en on_disc S22 (detalle)")

    def _process_s22_obtenido(self, frame, state: ScreenState) -> None:
        """Modal "Obtenido" (S22): los drops del farmeo por baterías.

        Dos lecturas INDEPENDIENTES, cada una con su gate: la GRILLA (una línea por corrida) y
        el panel DETAIL (el disco seleccionado, completo). El detalle va primero: el gate de la
        grilla hace return, y clickear un disco cambia el panel entero pero apenas mueve el
        viewport izquierdo (solo el borde de selección) → detrás del gate de la grilla el disco
        no se leería nunca."""
        if self._farm_session is None:
            return   # sin contexto de farmeo no hay par de sets útil; y un FP no debe hablar
        self._process_s22_detail(frame, state)
        self._process_s22_grid(frame, state)

    def _process_s22_grid(self, frame, state: ScreenState) -> None:
        """Grilla de S22: UNA LÍNEA POR CORRIDA al verla mientras se scrollea (decisión del
        usuario: un total al cerrar mentiría si no se scrollea hasta el fondo). El dedup es
        CONVERGENTE: una sección que todavía no se probó completa sale con "≥" y se re-emite
        —una sola vez más, ya sin "≥"— cuando el scroll trae la evidencia de cierre. Una vez
        cerrada, nunca más. Display-only: no persiste ni puntúa."""
        # Gate de re-parseo: si el viewport no cambió, no hay nada nuevo (RNF-06).
        sig = self._s22_viewport_signature(frame)
        if (sig is not None and self._s22_last_sig is not None
                and self._sig_component_diff(sig, self._s22_last_sig) <= _S22_SIG_MAX):
            return
        self._s22_last_sig = sig

        ts = time.monotonic()
        pred = self._farm_session.predicted(ts)
        cand_en = [en for _sid, en in pred[1]] if pred else []
        n_total = self._farm_session.usos(ts)

        try:
            from app.core.parser_extraccion import parse_obtenido
            secs = parse_obtenido(frame, self._ocr, self._set_badge_matcher, cand_en)
        except Exception:
            log.exception("Error parseando el modal 'Obtenido' (S22)")
            return

        for sec in secs:
            prev = self._s22_seen.get(sec.n_uso)
            if prev == _S22_SEC_CERRADA:
                continue                      # ya se emitió completa
            if prev is not None and len(sec.discos) <= prev and not sec.completa:
                continue                      # no creció ni cerró → no re-loguear
            self._s22_seen[sec.n_uso] = _S22_SEC_CERRADA if sec.completa else len(sec.discos)
            msg = self._fmt_seccion(sec, n_total, cand_en)
            # Loguear el mensaje ENTERO (no solo el conteo): el log es la única traza del QA
            # en vivo, y sin los slots/sets no se puede contrastar contra lo que se ve.
            log.info("Extracción S22: %s · completa=%s", msg, sec.completa)
            if self._id_diag_on:
                log.info("[s22_diag] uso=%s discos=%s", sec.n_uso,
                         [(d.slot, d.set_name, d.conf) for d in sec.discos])
            if self._on_diagnostic:
                try:
                    self._on_diagnostic(msg)
                except Exception:
                    log.debug("on_diagnostic S22 falló", exc_info=True)

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
            # Anular el centro ANIMADO (ver `_hex_center_mask`): el anillo de selección de los 6
            # slots —lo único que esta componente aporta— vive en el borde, así que se conserva.
            sig_hex[_S17_HEX_CENTER_MASK] = 0.0
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
        self._stalls.pop("S17", None)
        self._stalls.pop("S17/firma", None)
        self._s17_assign_sig = None
        # Anchor de flujo (5R.5b): al re-entrar a un slot, el primer disco vuelve a ser
        # el equipado por el latch (estructura del juego) → resetear el slot rastreado.
        self._s17_last_slot = 0
        # Votación del dueño (5R.5c/L.8): olvidar al salir de S17.
        self._s17_owner_sig = None
        self._s17_det_crop = None
        self._s17_rescue_pending = None
        self._s17_vote.reset()
        self._s17_warming = False
        self._grid_diag_counts.clear()
        # Botón de acción: olvidar la lectura y su gate. El `_pending_swap` NO se toca — sobrevive
        # a salir de S17 a propósito (el reemplazo se confirma al volver), y el pendiente LIBRE
        # tiene su propia muerte por cambio de PJ en `_check_libre_equipado`.
        self._s17_action_btn = None
        self._btn_read_key = None
        self._s17_sig_resets = 0

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

    def _disc_emit_key(self, identity, merged):
        """Clave de dedup de EMISIÓN = identidad + dueño equipado.

        La identidad de `_disc_identity` es ciega al dueño a propósito (dos discos distintos no
        deben colapsar). Pero para el dedup eso hacía que un disco visto LIBRE y luego EQUIPADO
        no se re-emitiera nunca: misma identidad → cortaba (QA 2026-07-23, "no volvió a salir el
        detalle al equiparlo"). Metiendo el dueño certero en la clave, la transición
        LIBRE→equipado es una clave nueva y el detalle vuelve a emitirse, mientras que el parpadeo
        del modelo 3D (que no cambia ni identidad ni dueño) sigue deduplicado."""
        from app.core.stats_vocab import _norm_key
        owner = merged.agente_asignado_nombre
        return (identity, _norm_key(owner) if owner else None)

    @staticmethod
    def _same_disc_fuzzy(id_a, id_b) -> bool:
        """¿Son el MISMO disco tolerando ruido de substats en el OCR?

        Exige (set, slot, main) EXACTOS y que los nombres de substat coincidan salvo, a lo
        sumo, UNO (los `rolls` —lo más ruidoso— no entran). Se usa SOLO en el check del
        pendiente LIBRE: ahí el disco puede leerse sucio entre armar y confirmar (QA
        2026-07-23, disco B a conf 0.89 → la identidad exacta parpadeaba y el check salía
        mudo). Con la identidad exacta de `_disc_identity` seguimos deduplicando emisión.

        El límite es inherente y aceptado (elección de Daniel): un disco que difiere de otro
        en exactamente un substat es indistinguible de una lectura sucia del mismo — pero para
        un falso positivo tendrían que ser gemelos casi idénticos del mismo set/slot/main sobre
        el mismo PJ, caso en que igual son intercambiables y el toast no miente."""
        if id_a[:3] != id_b[:3]:
            return False
        names_a = {s[0] for s in id_a[3]}
        names_b = {s[0] for s in id_b[3]}
        need = max(len(names_a), len(names_b)) - 1   # tolera 1 substat mal leído
        return len(names_a & names_b) >= max(need, 0)

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

    def _note_stall(self, scope: str, reason: str) -> None:
        """Registra que un handler está TRABADO en un return temprano (sin producir resultado).

        Estos returns eran mudos y desde afuera se veían todos iguales: en el QA del 2026-07-20
        el handler S17 estuvo 8m42s sin emitir y el log no decía absolutamente nada; más tarde
        el diálogo S23 se detectaba (conf=1.00) pero el parser devolvía None, también en
        silencio — y ambos se veían como 'no reconoce el swap'. Se loguea por FLANCO (al empezar
        el trabe y al salir), no por ciclo, para no inundar el log ni pagar RNF-06."""
        if self._stalls.get(scope, (None, 0))[0] == reason:
            prev = self._stalls[scope]
            self._stalls[scope] = (reason, prev[1] + 1)
            return
        self._stalls[scope] = (reason, 1)
        log.info("[%s] sin resultado — %s", scope, reason)

    def _clear_stall(self, scope: str) -> None:
        """Cierra un trabe abierto por `_note_stall` (el handler volvió a avanzar)."""
        prev = self._stalls.pop(scope, None)
        if prev is None:
            return
        log.info("[%s] destrabado tras %d ciclo(s) — %s", scope, prev[1], prev[0])

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
            self._note_stall("S17", "firma no calculable")
            return
        if self._is_new_s17_disc(sig):
            # Diagnóstico del trabe MUDO (QA 2026-07-23): un reset devuelve `_disc_agg_cycles` a 0,
            # así que si la firma cambia en cada ciclo el techo nunca llega, el disco nunca madura y
            # el handler devuelve en silencio indefinidamente. Contar los resets SIN emisión de por
            # medio es lo que distingue "el usuario navega discos" (resets con emisión entre medio)
            # de "la firma es inestable" (resets encadenados). `_note_stall` lo loguea por flanco.
            if self._disc_agg_sig is not None:
                self._s17_sig_resets += 1
                if self._s17_sig_resets == _S17_SIG_RESET_ALERT:
                    # Desglose por componente UNA sola vez (al cruzar el umbral): sin esto el log
                    # dice "la firma cambia" y hay que adivinar cuál de las tres ROIs es la
                    # inestable. Va aparte de `_note_stall` porque este texto cambia en cada
                    # ciclo y el dedup por razón no lo filtraría → inundaría el log (RNF-06).
                    d = [self._sig_component_diff(a, b) for a, b in zip(sig, self._disc_agg_sig)]
                    log.info(
                        "[S17] firma inestable · name=%.1f/%.1f detail=%.1f/%.1f hex=%.1f/%.1f "
                        "(el que supera su umbral es el ROI culpable)",
                        d[0], _S17_SIG_NAME_MAX, d[1], _S17_SIG_DETAIL_MAX,
                        d[2], _S17_SIG_HEX_MAX,
                    )
                if self._s17_sig_resets >= _S17_SIG_RESET_ALERT:
                    # Scope PROPIO, no "S17": ese lo limpia el chequeo de confianza en CADA ciclo
                    # (el parse anda bien, lo que falla es la firma), así que compartirlo hacía
                    # alternar nota/destrabe sin parar — inundó el log en el QA 2026-07-23.
                    # Este se limpia solo al emitir de verdad.
                    self._note_stall(
                        "S17/firma",
                        "la firma cambia en cada ciclo — el aggregator se reinicia y el disco "
                        "nunca madura",
                    )
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
            # Con un pendiente LIBRE abierto, EQUIPAR ocurre DESPUÉS de que el disco emitió (se
            # vio libre y maduró). Equipar en un slot vacío cambia la firma (sin disco → disco
            # con badge) y dispara un reset que re-corre el check; pero equipar por "Reemplazar"
            # la cambia MUCHO menos → sin reset, este gate cortaba mudo y el check nunca corría
            # (QA 2026-07-23, "sigo cambiando discos y no lo detecta" — 74s sin una línea). El
            # badge del dueño se muestrea a 10fps aparte, así que acá refrescamos dueño+botón
            # sobre el merge ya logrado y confirmamos, SIN re-OCR del disco entero. Acotado: solo
            # con un pendiente libre vivo, que es exactamente la ventana en que importa.
            ps = self._pending_swap
            if ps is not None and ps.get("origin_kind") == "libre":
                merged = self._disc_aggregator.current
                if merged is not None:
                    self._assign_s17_pj(merged, frame)   # refresca dueño (badge) y botón
                    self._check_swap_owner(merged, state)
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
                self._assign_s17_pj(merged, frame)   # re-decide el dueño (y refresca el botón)
                self._check_swap_owner(merged, state)   # el dueño acaba de refrescarse
                self._arm_libre_pending(merged)      # DESPUÉS del check: no auto-confirmarse
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
            # frame de transición/baja confianza → no contaminar el aggregator
            self._note_stall("S17", f"conf={disc.confianza_global:.2f} < 0.70")
            return
        self._clear_stall("S17")
        merged = self._disc_aggregator.merge(disc)
        self._disc_agg_cycles += 1
        # CHECK del reemplazo S23 — DESACOPLADO de la emisión, igual que la confirmación de
        # upgrade de más abajo y por el mismo motivo: `_emit_s17_disc` está gateado por la
        # madurez del disco y el warming del dueño, y en QA hubo trabes de 8m42s sin emitir con
        # un swap real perdido en el medio. El chequeo solo necesita (set, slot, dueño), que ya
        # están en el merge parcial.
        if merged is not None:
            # El botón ya lo refrescó `_assign_s17_pj` unas líneas más arriba, sobre el mismo frame.
            self._check_swap_owner(merged, state)
            # El armado va DESPUÉS del check, a propósito: si armara antes, el pendiente recién
            # creado podría confirmarse en el mismo ciclo contra su propio estado inicial.
            self._arm_libre_pending(merged)
        if self._disc_emitted or merged is None:
            return
        mature = disc_is_mature(merged)
        ceiling = self._disc_agg_cycles >= _S17_AGG_MAX_CYCLES
        if not (mature or ceiling):
            # Los primeros ciclos acá son NORMALES (el aggregator todavía está fusionando). Solo
            # es trabe si el contador ya pasó el techo esperado y aun así no maduró — la otra
            # forma del silencio, distinta a la de la firma inestable de arriba.
            if self._disc_agg_cycles >= _S17_AGG_MAX_CYCLES - 1:
                self._note_stall("S17", "el disco no madura y el techo de ciclos no avanza")
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

    def _maybe_harvest_detail_despite_veto(self, frame, latch: str, voted: str) -> None:
        """Cosecha SOLO la librería del detalle cuando el veto del cross-check lo produjo el grid
        y el detalle no tuvo nada que decir.

        El QA del 2026-07-31 midió el veto que dejó a 6 PJs sin cosechar. Sobre la página de
        Velina: `grid_votes=[Remielle Dan:0.90]`, `det_loc=2 det_match=0 det_votes=[-]`. El veto
        salió del GRID, que discrepa desde otro recorte y otra librería; el detalle ni opinó.
        Bloquear con eso la cosecha del detalle la deja sin poder crecer nunca: un PJ no entra a
        la librería porque no está en la librería.

        Se exigen TRES confirmaciones independientes antes de aprender, porque el riesgo real es
        el inverso (que el grid tenga razón, el disco sea de otro PJ y guardemos su cara bajo el
        nombre equivocado — el patrón Ben=Soukaku):

          1. la librería del DETALLE no tiene refs del latch ⇒ no puede opinar sobre él;
          2. el latch es un nombre LEÍDO en pantalla (menú o S18), no sostenido por matcher;
          3. el botón dice 'desequipar' — o sea el juego afirma que ESE PJ lo lleva puesto.

        La (1) fue primero "el detalle se abstuvo", y el QA mostró que ese proxy es demasiado
        estricto: sobre Rina (0 refs de detalle) la superficie NO se abstuvo, votó `Lucía:1.72`.
        Abstenerse y nombrar a otro son la misma situación —una librería sin el PJ verdadero— y
        solo la segunda bloqueaba. Lo que importa es si la superficie PUEDE opinar, no si opinó.

        Si alguna falla no se cosecha, y se deja dicho cuál: sin esa línea, la regla que no
        dispara es indistinguible de la que no existe.
        """
        faltan = []
        if self._identifier.knows_detail_badge(latch):
            faltan.append("el detalle SÍ tiene refs suyas (puede opinar, y discrepa)")
        if self._latch_origen not in ("menu", "s18"):
            faltan.append(f"latch de origen '{self._latch_origen}' (no leído en pantalla)")
        if self._s17_action_btn != "desequipar":
            faltan.append(f"botón={self._s17_action_btn!r} (no confirma que lo lleve puesto)")
        if faltan:
            self._log_s17_assign(
                ("veto_detalle_no_rescatado", latch),
                "[badge] no rescato la cosecha del detalle para '%s': %s.",
                latch, " · ".join(faltan),
                razonamiento=True,
            )
            return
        det = crop_detail_badge(frame) if frame is not None else None
        origen = "de este frame"
        if det is None:
            # Hough no cerró el círculo en ESTE frame. Pero el recorte es intermitente, no
            # imposible: el loop rápido guarda el último BUENO del disco actual, y ese sirve igual
            # (misma pantalla, mismo disco, ya validado como cara). Es lo que dejó a Lycaon afuera
            # 3 de 3 veces con `det_loc=1 samples=2` — el recorte existía y se descartaba.
            det = self._reuse_det_crop(frame)
            origen = "guardado del mismo disco"
        if det is None:
            # Ni este frame ni ninguno anterior. En vez de perder el tiro, queda PENDIENTE: el
            # loop rápido lo cobra apenas salga un recorte bueno de este mismo disco. La ventana
            # del rescate era el warmup del disco —2 pasadas— y con el recorte saliendo ~1 de
            # cada 4 veces, Lycaon perdió 3 de 3 (det_loc 1, 0, 0). Pendiente, la ventana pasa a
            # ser todo el rato que el disco esté en pantalla.
            self._s17_rescue_pending = (self._s17_owner_sig, latch, voted)
            self._log_s17_assign(
                ("veto_detalle_sin_recorte", latch),
                "[badge] el rescate del detalle de '%s' queda PENDIENTE: el recorte del badge no "
                "salió todavía (Hough no cerró) — se cosecha solo apenas salga uno bueno.",
                latch,
            )
            return
        if self._identifier.learn_s17_detail(det, latch):
            self._s17_rescue_pending = None
            self._log_s17_assign(
                ("cosecha_detalle_pese_al_veto", latch),
                "[cosecha] detalle de '%s' (recorte %s) PESE al veto del grid (que votó '%s'): el "
                "detalle no tiene refs suyas, el nombre se leyó en pantalla y el botón dice "
                "desequipar.",
                latch, origen, voted,
            )
        elif self._identifier.detail_is_near_duplicate(det, latch):
            # No falló nada: la librería YA tenía esta imagen. Distinguirlo importa porque el
            # rescate se da por cumplido —no queda pendiente— y porque "la librería no aceptó"
            # manda a buscar un problema que no existe.
            self._s17_rescue_pending = None
            self._log_s17_assign(
                ("cosecha_detalle_clon", latch),
                "[cosecha] el detalle de '%s' ya tenía esta misma imagen → no se duplica.",
                latch,
            )
        else:
            self._log_s17_assign(
                ("veto_detalle_no_aprendido", latch),
                "[badge] el rescate de '%s' pasó los 3 checks pero la librería NO aceptó la ref.",
                latch,
            )

    def _collect_pending_rescue(self, sig, det) -> None:
        """Cobra un rescate PENDIENTE con el primer recorte bueno que aparezca del mismo disco.

        Lo llama el loop rápido (10 fps) con un `det` ya validado como CARA. Las 3
        confirmaciones se hicieron al decidir el disco; acá se re-verifica lo que pudo cambiar
        entre medio, porque el pendiente sobrevive frames:

          - la FIRMA, que es lo que ata la cara a un disco (sin esto se cosecha la cara del
            disco siguiente bajo el nombre del anterior);
          - el LATCH, porque si el PJ cambió el nombre ya no describe lo que estamos mirando;
          - que el detalle SIGA sin refs del latch — si entró por otro disco mientras tanto, la
            regla de rescate ya no aplica (existe para superficies que no pueden opinar).

        Cualquiera que falle CANCELA el pendiente en vez de dejarlo colgado: un pendiente viejo
        buscando su momento es exactamente cómo se cosecha la cara equivocada.
        """
        pend = self._s17_rescue_pending
        if not pend:
            return
        sig_pend, latch, voted = pend
        if not self._sig_close(sig, sig_pend):
            self._s17_rescue_pending = None
            return
        if self._last_agent_name != latch or self._identifier.knows_detail_badge(latch):
            self._s17_rescue_pending = None
            return
        self._s17_rescue_pending = None
        if self._identifier.learn_s17_detail(det, latch):
            log.info("[cosecha] detalle de '%s' PENDIENTE cobrado: el recorte salió bueno unos "
                     "frames después de la decisión (el grid había votado '%s').", latch, voted)

    def _reuse_det_crop(self, frame):
        """El último recorte BUENO del detalle-badge, SOLO si es del disco que está en pantalla.

        El riesgo de reusar un recorte es cosechar la cara del disco anterior bajo el nombre de
        este, así que la firma manda: si no se puede confirmar que es el mismo disco, no se
        reusa. Sin firma del frame actual (el recorte de firma también falla a veces) tampoco —
        "no sé si es el mismo" se trata como "no es" (RNF-02).
        """
        if not self._s17_det_crop:
            return None
        sig_crop, det = self._s17_det_crop
        sig_now = self._s17_disc_signature(frame) if frame is not None else None
        if sig_now is None or sig_crop is None or not self._sig_close(sig_now, sig_crop):
            return None
        return det

    def _s17_owner_resolved(self, disc) -> bool:
        """True si el dueño del disco ya quedó DECIDIDO (no hace falta seguir calentando):
        asignado por latch, dueño visual votado, o declarado LIBRE. False = 'incierto'."""
        return bool(disc.agente_asignado_nombre or disc.equip_pj_visual or disc.equip_libre)

    def _emit_s17_disc(self, merged, state: ScreenState, mature: bool) -> None:
        """Emite (dedup + equip_map + id_diag + log + on_disc) un disco S17 ya resuelto.
        Extraído de `_process_disc_s17_continuous` para reusarlo desde el path de warmup."""
        # (El check del reemplazo S23 ya NO vive acá: corre en el ciclo continuo, apenas se
        # conocen set+slot+dueño, sin esperar a que el disco madure. Ver `_check_swap_owner`.)
        self._disc_emitted = True
        # Llegamos a emitir → la cadena de resets (si la hubo) no era patológica.
        self._s17_sig_resets = 0
        self._clear_stall("S17/firma")
        # Dedup por IDENTIDAD: si la firma parpadeó (modelo 3D animado) y este
        # disco ya se emitió en esta sesión S17, no re-emitir (ni re-persistir).
        identity = self._disc_identity(merged)
        emit_key = self._disc_emit_key(identity, merged)
        if self._recapture_on:
            # Re-captura QA estilo S18: re-emite al CAMBIAR de disco, NO en cada
            # parpadeo del modelo 3D (que reabre la firma visual del MISMO disco). El
            # parpadeo deja la identidad-OCR igual → se saltea; navegar a otro disco la
            # cambia → re-emite (incluso al VOLVER a uno ya visto).
            if emit_key == self._last_emitted_identity:
                return
        elif emit_key in self._disc_emitted_ids:
            return
        self._disc_emitted_ids.add(emit_key)
        self._last_emitted_identity = emit_key
        # Verdad de tierra (5R.C): si el disco está EQUIPADO (agente_asignado por el
        # flujo-ancla = dueño certero), registrar firma→dueño al mapa. Candidatos no
        # setean agente_asignado → no contaminan el mapa.
        if merged.agente_asignado_nombre:
            self._record_equip_map(identity, merged.agente_asignado_nombre)
        if self._id_diag_on:
            self._log_id_diag(merged, identity)
        # LA línea del evento (un evento, una línea). Lleva el DUEÑO adentro: antes salía en una
        # línea aparte —`[S17] asignado a 'X'`— y había que aparearlas por cercanía en el archivo.
        # Con el dueño acá, esa otra pasa a DEBUG por redundante y el log queda con una línea
        # autocontenida por disco, que es lo que permite usarlo como señal (para cronometrar la
        # frescura, o para seguir un censo de ~300 discos sin perderse).
        dueno = merged.agente_asignado_nombre or merged.equip_pj_visual
        if dueno:
            tenencia = f"dueño={dueno}"
        elif merged.equip_libre:
            tenencia = "LIBRE"
        else:
            tenencia = "dueño=?"
        log.info(
            "Disco detectado: set=%s slot=%d main=%s nivel=%d %s conf=%.2f (agg %dc%s)",
            merged.set_name_canon or merged.set_name_raw, merged.slot,
            merged.main_stat_canon or merged.main_stat_raw, merged.nivel, tenencia,
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
        emit_key = self._disc_emit_key(identity, merged)
        if self._recapture_on:
            if emit_key == self._last_emitted_identity:
                return
        elif emit_key in self._disc_emitted_ids:
            return
        self._disc_emitted_ids.add(emit_key)
        self._last_emitted_identity = emit_key
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
        # Confirmación de UPGRADE desde la TIENDA DE MÚSICA: ese flujo es S5→S10→S5 y NUNCA pasa
        # por el inventario (S17), así que la S5 posterior ES la pantalla autoritativa del estado
        # final (trae el nivel real —15 al maxear— y los rolls asentados). Igual que en S17, va
        # DESACOPLADA de `_emit_s5_disc`: el dedup por identidad puede bloquear la emisión (un
        # upgrade sin cambio de roll conserva la identidad) pero el resumen debe salir igual.
        if self._upgrade_syncer is not None:
            try:
                self._upgrade_syncer.on_post_upgrade_disc(merged)
            except Exception:
                log.debug("on_post_upgrade_disc (s5) falló", exc_info=True)
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
            self._latch_origen = "s18"     # nombre LEÍDO por OCR del panel, no matcheado
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
                self._latch_origen = "avatar"
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

    def _seed_identity_from_menu(self, nombre: str) -> None:
        """Siembra el latch de identidad con el PJ SELECCIONADO en el menú (S15).

        El nombre del menú está ESCRITO en pantalla y ya viene canonicalizado contra el
        roster (`read_menu_agent` abstiene si no matchea, RNF-02), así que es la
        evidencia más barata y más certera de identidad que ve el sistema. Hasta el QA del
        2026-07-30 se logueaba y se tiraba: entrando al Equipamiento desde el menú, S8 salía
        `PJ=?` y había que desviarse por S18 (que lee el nombre por OCR) para que apareciera.

        NO se ancla en `_agent_anchor_x`: la siembra es un punto de partida, no una
        confirmación. Al aparecer la barra de avatares, `_update_detail_identity` vota como
        siempre y el avatar puede CORREGIR al menú — que es lo que corresponde si el usuario
        deslizó de PJ al entrar. Y como el latch queda en None sólo por reset explícito, un
        frame de transición del menú (OCR abstiene) no lo borra.
        """
        if nombre != self._last_agent_name:
            # PJ distinto → la votación acumulada es de otro; empezar limpio y forzar que
            # S8/S19 re-emita la línea de identidad (la firma edge no cambiaría sola).
            self._detail_votes = {}
            self._detail_samples = 0
            self._detail_vote_x = None
            self._detail_confirmed_source = None
            self._agent_anchor_x = None
            self._last_detail_sig = None
        self._last_agent_name = nombre
        self._detail_source = "menu"
        self._latch_origen = "menu"

    def _reset_detail_identity(self) -> None:
        """Limpia el latch de identidad (al salir de la familia detalle de agente)."""
        self._last_agent_name = None
        self._agent_anchor_x = None
        self._detail_source = None
        self._latch_origen = None
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

    def _reset_s26_tracking(self) -> None:
        """Al salir de S26, olvidar el arma mirada (así al volver se re-emite)."""
        self._s26_panel_sig = None
        self._s26_last_log_sig = None
        self._s26_owner_key = None
        self._s26_owner_votes = {}

    def _process_s26_weapon_detail(self, frame, state: ScreenState) -> None:
        """Detalle de W-Engine (S26, RF-15): nombre, nivel, rareza, refinamiento, ATK y stat.

        **Observación pura: no escribe la DB.** Ni acá ni en el catálogo — un arma que no está en
        `weapons` se muestra con el nombre CRUDO y no se da de alta (decisión de Daniel: la tabla
        tiene 42 armas de menos y completarla es una pasada aparte).

        Gate RNF-06: el OCR del panel cuesta ~500 ms y la cadencia es 1000 ms, así que solo corre
        cuando la firma del panel cambió (cambió de arma). Sin eso, mirar un arma diez segundos
        serían diez OCRs idénticos.
        """
        from app.core.owner_vote import decide_owner
        from app.core.parser_disc_s17 import read_s17_action_button
        from app.core.parser_weapon_s26 import (
            clasificar_tenencia,
            parse_weapon_s26,
            read_weapon_owner_badge,
            weapon_panel_signature,
        )

        sig = weapon_panel_signature(frame)
        if sig and sig == self._s26_panel_sig:
            return                      # panel quieto: ni stall ni OCR, es el camino normal
        self._s26_panel_sig = sig

        d = parse_weapon_s26(frame, self._ocr, catalogo=self._weapon_catalog())
        if not d.nombre_raw or d.nivel is None:
            self._note_stall("S26/detalle", f"panel ilegible (notas={','.join(d.notas) or '-'})")
            return
        if not self._parece_panel_de_arma(d):
            return
        self._clear_stall("S26/detalle")

        # --- Tenencia: ¿la lleva el PJ en pantalla, otro, o está libre? ---
        # Dos señales independientes (ver `clasificar_tenencia`). El badge va ANCLADO al pill,
        # no a la franja fija de `crop_detail_badge`: esa franja da falso LIBRE cuando el nombre
        # del arma envuelve a dos líneas y corre el panel.
        badge = read_weapon_owner_badge(frame, d.pill_bbox)
        # El dueño se vota a través de FRAMES, no se decide con uno suelto. El recorte lo produce
        # un Hough por frame: si el círculo se corre unos píxeles el recorte cambia, y un match
        # ajustado se da vuelta — en el QA del 2026-07-31 el dueño alternaba Grace↔Miyabi cada
        # ciclo con el panel QUIETO. Es el mismo remedio que ya estabilizó la identidad en S8/S19.
        arma_key = (d.nombre_canon or d.nombre_raw, d.nivel, d.refinamiento, d.atk_base)
        if arma_key != self._s26_owner_key:
            self._s26_owner_key = arma_key
            self._s26_owner_votes = {}
        badge_nombre = None
        res_dbg = None          # el MatchResult crudo, para el diagnóstico de abstenciones
        badge_crudo = None      # top-1 de ESTE frame, ya canonizado: es lo que veta la cosecha
        if badge is not None and badge.crop is not None and self._identifier is not None:
            try:
                res = self._identifier.surfaces["detail"].match(badge.crop)
                res_dbg = res
                crudo = res.name if res else None
                # Se CANONICALIZA contra el roster antes de reportar. La librería compartida tiene
                # al menos un label con mojibake ('n.Âº11' = N.º 11 guardado con UTF-8 leído como
                # latin-1), y sin este paso ese texto corrupto llegaría al log y al toast como si
                # fuera el nombre del PJ. Un nombre que no resuelve se descarta: preferimos
                # "incierto" antes que basura (RNF-02).
                canon = self._identifier._canonical_name(crudo) if crudo else None
                if crudo and canon is None:
                    log.debug("S26: dueño %r no resuelve al roster → incierto", crudo)
                badge_crudo = canon
                if canon:
                    conf = float(getattr(res, "conf", 1.0) or 0.0)
                    self._s26_owner_votes[canon] = self._s26_owner_votes.get(canon, 0.0) + conf
            except Exception:
                log.debug("S26: fallo al nombrar el badge del dueño", exc_info=True)
        if self._s26_owner_votes:
            badge_nombre, _fuente = decide_owner(
                {}, self._s26_owner_votes, latch=self._last_agent_name)
        if len(self._s26_owner_votes) > 1:
            # El badge nombró a DOS PJs distintos para la MISMA arma. Un arma tiene un solo dueño,
            # así que acá el matcher no es fiable — y no hay forma de saber cuál de los dos es el
            # bueno, porque el que puntea más alto puede ser el equivocado (en el QA ganaba Grace
            # y el arma era de Miyabi). Abstención PEGAJOSA hasta cambiar de arma: RNF-02, un
            # "sin identificar" es información honesta y un nombre equivocado no.
            if badge_nombre is not None:
                log.debug("S26: el badge osciló entre %s → dueño incierto",
                          ", ".join(sorted(self._s26_owner_votes)))
            badge_nombre = None
        # El botón se lee derecho, sin el gate de caché de S17: ese gate está armado sobre la
        # identidad de un DISCO. Acá no hace falta — este handler ya corre solo cuando cambió la
        # firma del panel, así que es un OCR por arma mirada, no por ciclo.
        try:
            boton = read_s17_action_button(frame, self._ocr)
        except Exception:
            log.debug("S26: lectura del botón de acción falló", exc_info=True)
            boton = None
        d.tenencia, d.dueno = clasificar_tenencia(
            boton, badge, badge_nombre, self._last_agent_name)
        cosecha = self._maybe_harvest_weapon_owner(d, badge, badge_nombre, arma_key, badge_crudo)
        if self._id_diag_on:
            if cosecha:
                outcome = cosecha
            elif len(self._s26_owner_votes) > 1:
                outcome = "osciló"
            elif badge_nombre:
                outcome = "nombrado"
            elif badge is None or badge.crop is None:
                outcome = "noloc"
            else:
                outcome = "abstuvo"
            self._log_weapon_id_diag("S26", badge, res_dbg, self._last_agent_name, outcome)

        logsig = (d.nombre_canon or d.nombre_raw, d.nivel, d.rareza, d.refinamiento,
                  d.tenencia, d.dueno)
        if logsig == self._s26_last_log_sig:
            self._note_stall("S26", "misma arma ya reportada")
            return
        self._clear_stall("S26")
        self._s26_last_log_sig = logsig

        nombre = d.nombre_canon or f"{d.nombre_raw} (sin catálogo)"
        stat = ""
        if d.stat_avanzado_canon and d.stat_avanzado_valor is not None:
            unidad = " %" if d.stat_avanzado_unidad == "%" else ""
            stat = f"{d.stat_avanzado_canon} {d.stat_avanzado_valor:g}{unidad}"
        tenencia = {
            "equipada": f"EQUIPADA por {d.dueno}" if d.dueno else "EQUIPADA (PJ sin identificar)",
            "otro_pj": f"la tiene {d.dueno}" if d.dueno else "la tiene otro PJ (sin identificar)",
            "libre": "LIBRE",
            "incierto": "tenencia incierta",
        }[d.tenencia]
        linea = (f"[S26] W-Engine — {nombre} · {d.rareza or '?'} · Nv {d.nivel}/{d.nivel_max} · "
                 f"P{d.refinamiento or '?'} · ATK base {d.atk_base or '?'} · {stat or 'stat ?'}"
                 f" · {tenencia}")
        log.info(linea)
        self._diag(linea)
        for n in d.notas:
            if n.startswith("rareza_discrepa_atk"):
                log.warning("[S26] ⚠ %s", n)
                self._diag(f"[S26] ⚠ {n}")

        # --- ¿Esto es NOTICIA o es una lectura más? ---
        # El monitor reporta siempre lo que vio (el evento alimenta el panel en vivo); lo que
        # calcula acá es si además hay un CAMBIO, y la UI decide con eso si interrumpe con un
        # toast. Abrir un arma para mirarla no es noticia — el usuario la está viendo. Hoy el
        # único cambio observable es la TENENCIA (equipar/desequipar/reemplazar); cuando las
        # armas sincronicen a la DB, el disparador pasa a ser la escritura, como en discos.
        # "incierto" no cuenta como cambio en ninguna punta: no saber no es una novedad.
        previa = self._s26_tenencia_vista.get(arma_key)
        self._s26_tenencia_vista[arma_key] = d.tenencia
        if len(self._s26_tenencia_vista) > 64:      # techo: sesión larga, no fuga
            self._s26_tenencia_vista.pop(next(iter(self._s26_tenencia_vista)))
        cambio = (previa is not None and previa != d.tenencia
                  and "incierto" not in (previa, d.tenencia))

        if self._on_weapon_seen:
            try:
                self._on_weapon_seen({
                    "nombre": nombre,
                    "cambio": cambio,
                    "tenencia_previa": previa,
                    "en_catalogo": d.nombre_canon is not None,
                    "rareza": d.rareza,
                    "nivel": d.nivel,
                    "nivel_max": d.nivel_max,
                    "refinamiento": d.refinamiento,
                    "atk_base": d.atk_base,
                    "stat": stat,
                    "dueno": d.dueno,
                    "tenencia": d.tenencia,
                })
            except Exception:
                log.exception("Error en on_weapon_seen (toast de W-Engine)")

    def _process_s30_weapon_inventory(self, frame, state: ScreenState) -> None:
        """Inventario de amplificadores (S30): lee el arma SELECCIONADA del panel derecho.

        **Display-only y sin toast, a diferencia de S26.** Acá el usuario recorre la grilla y cada
        tile que toca es una lectura, no una novedad: interrumpir por cada una sería exactamente lo
        que Daniel vetó ("un toast avisa de CAMBIOS, no de lecturas"). Va al log y al panel en vivo.

        El parser es el MISMO de S26 (`parse_weapon_s30`): las dos pantallas describen un arma con
        las mismas secciones, y lo único distinto —dónde vive el panel y cómo se acomodan badge y
        estrellas alrededor del pill— son parámetros. Medido sobre los 6 fixtures: los 6 campos
        salen 6/6 y la canonización contra `weapons` acierta 6/6, incluidos los que el OCR maltrata
        ("Uitimacena" → "Última cena", "Modeloll" → "Modelo II").

        **Dueño**: el avatar vive arriba, en la fila de dos circulitos bajo el nombre (el izquierdo
        es la especialidad), no al lado del pill como en S26 — por eso tiene su propia lectura,
        `read_weapon_owner_badge_s30`. Sin avatar el arma está LIBRE. El recorte conserva el
        encuadre de la librería `avatar_detbadge_v2`, así que nombrar es el mismo camino que S26.

        Gate RNF-06 por firma del panel + **dedup del log por contenido**: el log de este proyecto
        es edge-triggered, dice CAMBIOS. Las dos cosas hacen falta y ninguna reemplaza a la otra —
        la firma ahorra el OCR, el dedup evita repetir la línea si el OCR devuelve lo mismo.
        """
        from app.core.parser_weapon_s26 import (
            parse_weapon_s30,
            read_weapon_owner_badge_s30,
            weapon_panel_signature_s30,
        )

        sig = weapon_panel_signature_s30(frame)
        if sig and sig == self._s30_panel_sig:
            return                      # panel quieto: ni stall ni OCR, es el camino normal
        self._s30_panel_sig = sig

        d = parse_weapon_s30(frame, self._ocr, catalogo=self._weapon_catalog())
        if not d.nombre_raw or d.nivel is None:
            self._note_stall("S30/inventario", f"panel ilegible (notas={','.join(d.notas) or '-'})")
            return
        self._clear_stall("S30/inventario")

        # --- Dueño ---
        badge = read_weapon_owner_badge_s30(frame, d.pill_bbox)
        dueno = None
        res_dbg = None          # el MatchResult crudo, para el diagnóstico de abstenciones
        if badge is not None and badge.crop is not None and self._identifier is not None:
            try:
                res = self._identifier.surfaces["detail"].match(badge.crop)
                res_dbg = res
                crudo = res.name if res else None
                # Canonicalizar contra el roster antes de reportar: la librería compartida tiene
                # algún label con mojibake, y sin este paso llegaría al log como si fuera un
                # nombre. Lo que no resuelve se descarta — antes "incierto" que basura (RNF-02).
                dueno = self._identifier._canonical_name(crudo) if crudo else None
            except Exception:
                log.debug("S30: fallo al nombrar el badge del dueño", exc_info=True)
        if badge is None:
            tenencia = "dueño ?"
        elif not badge.present:
            tenencia = "LIBRE"
        else:
            # "hay alguien, no sé quién" es una salida legítima, no un fallo: `BadgeSurface` separa
            # presencia de nombrado a propósito, y la librería del detalle todavía tiene PJs flacos.
            tenencia = f"la tiene {dueno}" if dueno else "con dueño (sin identificar)"
        # Diagnóstico ANTES del dedup de log: la línea de S30 se emite una sola vez por arma, pero
        # el diagnóstico habla de CADA evaluación del badge — que es lo que se quiere medir.
        # S30 no cosecha (ver `_maybe_harvest_weapon_owner`): acá solo se observa.
        if self._id_diag_on:
            if badge is None or badge.crop is None:
                _outcome = "noloc"
            elif dueno:
                _outcome = "nombrado"
            else:
                _outcome = "abstuvo"
            self._log_weapon_id_diag("S30", badge, res_dbg, self._last_agent_name, _outcome)

        nombre = d.nombre_canon or d.nombre_raw
        stat = (f"{d.stat_avanzado_canon} {d.stat_avanzado_valor:g}{d.stat_avanzado_unidad or ''}"
                if d.stat_avanzado_canon and d.stat_avanzado_valor is not None else None)

        # Dedup por CONTENIDO. El gate de firma es de píxeles y basta para el costo de OCR, pero no
        # garantiza que lo LEÍDO haya cambiado: cualquier temblor en el panel lo cruza y el log
        # pasaría a ser un heartbeat repitiendo la misma arma (QA 2026-08-07: 110 líneas, 9 armas
        # distintas). El log de este proyecto reporta cambios, no lecturas.
        log_sig = (nombre, d.rareza, d.nivel, d.nivel_max, d.refinamiento, d.atk_base, stat,
                   tenencia)
        if log_sig == self._s30_last_log_sig:
            return
        self._s30_last_log_sig = log_sig

        linea = (f"[S30] Inventario W-Engine — {nombre} · {d.rareza or '?'} · "
                 f"Nv {d.nivel}/{d.nivel_max} · P{d.refinamiento or '?'} · "
                 f"ATK base {d.atk_base or '?'} · {stat or 'stat ?'} · {tenencia}"
                 f"{'' if d.nombre_canon else ' · ⚠ fuera del catálogo'}")
        log.info(linea)
        self._diag(linea)
        for n in d.notas:
            if n.startswith("rareza_discrepa_atk"):
                log.warning("[S30] ⚠ %s", n)
                self._diag(f"[S30] ⚠ {n}")

    def _parece_panel_de_arma(self, d) -> bool:
        """¿Lo que se parseó puede ser un W-Engine? Falso ⇒ el handler se calla del todo.

        QA en vivo 2026-08-12: el detector siguió diciendo S26 unos 15 ciclos DESPUÉS de que la
        pantalla ya era S17, y este handler corrió sobre un panel de DISCOS. Leyó el set del disco
        como nombre del arma y emitió `W-Engine — Jazz ca6tico (1) · Nv 15/15 · ATK base 2200`: un
        arma inventada con números de disco. Además cosechó un badge bajo esa procedencia falsa.

        El tell **no es el catálogo**. `weapons` está incompleto a propósito (42 armas de menos) y
        por eso un arma fuera de catálogo se reporta igual: *no estar en el catálogo* no significa
        *no ser un arma*, y vetar por ahí bloquearía las 42. El tell es ESTRUCTURAL: el pill de un
        W-Engine muestra un tope de ascensión múltiplo de 10 hasta 60, y 15 es el tope de un disco.

        Un tope ilegible (`None`) NO veta: eso es ignorancia, no evidencia de estar en otra
        pantalla — la misma distinción que en el veto de la cosecha, donde un matcher sin opinión
        deja pasar y uno en desacuerdo frena.
        """
        if d.nivel_max is None or d.nivel_max in _TOPES_ASCENSION_ARMA:
            return True
        self._note_stall("S26/detalle",
                         f"el panel no es de un arma (tope Nv {d.nivel_max}, "
                         f"esperado uno de {sorted(_TOPES_ASCENSION_ARMA)})")
        return False

    def _maybe_harvest_weapon_owner(self, d, badge, badge_nombre, arma_key,
                                    badge_crudo=None) -> str | None:
        """Cosecha el badge del dueño a la librería del DETALLE cuando la etiqueta es certera.

        Las pantallas de armas venían CONSUMIENDO `avatar_detbadge_v2` sin alimentarla nunca: el
        único punto que cosechaba esa superficie era el flujo de discos, así que poder nombrar al
        dueño de un arma dependía de que alguien hubiera paseado antes por los discos de ese PJ.
        Acá se cierra el circuito, y se cierra con la MISMA disciplina que en discos.

        La etiqueta sale de `tenencia == "equipada"`, que significa que el botón dijo *Desequipar*:
        el juego afirma que el PJ del latch la lleva puesta. **No sale del badge** — cosechar con
        la etiqueta que produjo el propio matcher lo realimenta con sus aciertos y sus errores, que
        es el efecto "imán" que ya costó una re-cosecha en julio. Por eso S30 no cosecha: ahí el
        dueño sale del badge y no hay botón que confirme nada.

        El recorte sirve tal cual: `read_weapon_owner_badge` conserva a propósito el encuadre de
        `crop_detail_badge` (regla like-with-like de la Fase 5R).

        No lleva gate de readonly propio: `BadgeSurface.learn` ya respeta `DANIBOD_BADGE_HARVEST`.

        Devuelve el desenlace (`cosechado` / `veto_conflicto` / `veto_techo`) o None si no había
        nada que cosechar, para que el diagnóstico de `_log_weapon_id_diag` lo reporte: un veto
        silencioso es indistinguible de "no pasó nada", que es la lección de los QA mudos.
        """
        if self._identifier is None or d.tenencia != "equipada" or not d.dueno:
            return None
        if badge is None or badge.crop is None:
            return None                             # Hough no cerró: no hay nada que guardar
        # `present` es la PRESENCIA estructural (¿esto es una cara?). Hay que exigirla explícitamente
        # porque 'Desequipar' resuelve la tenencia SIN consultar el badge: un recorte de nitidez baja
        # —el falso LIBRE— llegaría hasta acá con tenencia "equipada" y se aprendería un no-avatar
        # bajo el nombre de un PJ. Leer y aprender piden evidencia distinta.
        if not badge.present:
            return None
        canon = self._identifier._canonical_name(d.dueno)
        if not canon:
            return None
        # Las dos señales en desacuerdo. Se le cree al badge —0-wrong en QA— y no se aprende nada:
        # una de las dos está mal y no sabemos cuál, así que aprender sería etiquetar una cara con
        # el nombre de otro PJ. Misma regla que el flujo-ancla de discos.
        #
        # Se mira el match CRUDO de este frame (`badge_crudo`), no solo el consenso `badge_nombre`.
        # `decide_owner` exige 0.80 acumulado para PROPONER un dueño, y con 0.74 de un frame
        # devuelve None: en el QA del 2026-08-10 eso dejó pasar un `top=Billy conf=0.74
        # margin=0.15` bajo el latch 'Lycaon' y se aprendió la cara de Billy como Lycaon. El
        # `name` crudo ya viene gateado por el matcher (min_conf 0.45 / min_margin 0.04), o sea
        # "tengo una opinión" — y para NEGARSE A APRENDER eso tiene que alcanzar, aunque no
        # alcance para nombrar. Cuando el matcher no opina (margen ~0, el caso de un PJ con una
        # sola ref) `badge_crudo` es None y la cosecha sigue: es justo para lo que existe.
        for otro in (badge_crudo, badge_nombre):
            if otro and _norm_key(otro) != _norm_key(canon):
                return "veto_conflicto"
        clave = (canon, arma_key)
        if clave in self._s26_harvested:
            return None
        from app.core.avatar_descriptor import _MAX_REFS_PER_NAME
        if self._identifier.detail_refs_count(canon) >= _MAX_REFS_PER_NAME:
            self._s26_harvested.add(clave)          # no reintentar por cada frame
            return "veto_techo"
        # El dedup de `_s26_harvested` es por SESIÓN: al volver mañana, la misma arma del mismo PJ
        # se cosecha de nuevo y entra un clon (Lycaon terminó con dos refs a 0.000, QA 2026-08-11).
        # Dedupear por CONTENIDO cubre eso y además la misma cara vista desde otra pantalla, que
        # una clave (PJ, arma) no podría atrapar.
        if self._identifier.detail_is_near_duplicate(badge.crop, canon):
            self._s26_harvested.add(clave)
            return "veto_clon"
        if self._identifier.learn_s17_detail(badge.crop, canon):
            self._s26_harvested.add(clave)
            log.info("[cosecha] detalle-badge de '%s' desde el arma '%s' (botón 'desequipar')",
                     canon, arma_key[0])
            return "cosechado"
        return None

    def _log_weapon_id_diag(self, pantalla: str, badge, res, latch, outcome: str) -> None:
        """Una línea por badge de arma evaluado (gated `DANIBOD_ID_DIAG`).

        `MatchResult` ya trae `conf`, `margin` y el `top` **aunque se abstenga**
        (`avatar_descriptor.py`): hasta ahora esa evidencia se descartaba, y por eso el QA del
        2026-08-07 pudo decir "nombre 3/7" pero no *cuáles* falló. Sin el top-1 de una abstención
        no se puede distinguir "le faltan refs a este PJ" de "el recorte no matchea nada".

        Las distancias del `top` van tal cual: **más chico es más parecido**.
        """
        if not self._id_diag_on:
            return
        loc = 1 if (badge is not None and getattr(badge, "crop", None) is not None) else 0
        top = ",".join(f"{n}:{dist:.2f}" for n, dist in (getattr(res, "top", None) or [])[:3])
        # Dedup por CONTENIDO, igual que la línea [S30]: el gate de firma es de píxeles y el arte
        # 3D del arma se mueve solo, así que la misma evaluación cruza el gate una y otra vez (18
        # líneas idénticas en el QA del 2026-08-11). Un diagnóstico repetido es tan ilegible como
        # no tenerlo. Si cambia cualquier número, vuelve a loguear.
        firma = (pantalla, loc, top, f"{getattr(res, 'conf', 0.0):.2f}", latch, outcome)
        if firma == self._weapon_diag_sig:
            return
        self._weapon_diag_sig = firma
        log.info(
            "[id_diag/arma] pantalla=%s loc=%d top=%s conf=%.2f margin=%.2f rejected=%d "
            "latch=%s outcome=%s",
            pantalla, loc, top or "-", float(getattr(res, "conf", 0.0) or 0.0),
            float(getattr(res, "margin", 0.0) or 0.0), int(bool(getattr(res, "rejected", False))),
            latch or "-", outcome,
        )

    def _weapon_catalog(self) -> list[str] | None:
        """Nombres ESPAÑOLES de `weapons`, cacheados. None si la DB no está disponible.

        Read-only: es un SELECT. Si falla, el parser sigue funcionando y devuelve el nombre crudo
        — la canonización es una mejora, no un requisito."""
        cache = getattr(self, "_weapon_catalog_cache", None)
        if cache is not None:
            return cache or None
        nombres: list[str] = []
        try:
            from app.db.connection import get_connection
            con = get_connection()
            nombres = [r[0] for r in con.execute(
                "select nombre from weapons where nombre is not null and nombre != 'Sin arma'")]
        except Exception:
            log.debug("S26: no se pudo leer el catálogo de weapons", exc_info=True)
        self._weapon_catalog_cache = nombres
        return nombres or None

    def _process_agent_menu(self, frame, state: ScreenState) -> None:
        """Menú de personajes (S15, Fase M.1): reconoce al PJ SELECCIONADO leyendo su
        nombre de la barra bottom-left → `read_menu_agent` → `_match_agent_scored` (rol+elemento
        de la DB). Loguea EDGE-triggered (1× por PJ). Gate RNF-06: re-OCR solo si la firma
        del nombre cambió (cambió la selección). No escribe la DB de dominio ni toca el latch.

        Si hay una corrida de censo abierta, cada cambio de selección deja una observación. El
        gate de firma es lo que vuelve barato el recorrido: ~51 OCR por pasada en vez de uno por
        frame de animación."""
        sig = self._menu_name_signature(frame)
        if (sig is not None and self._menu_last_sig is not None
                and self._sig_component_diff(sig, self._menu_last_sig) <= _MENU_SIG_MAX):
            return                          # mismo PJ seleccionado → no re-OCR
        self._menu_last_sig = sig
        lectura = read_menu_agent(frame, self._ocr)
        nombre, rol, elemento = lectura.nombre, lectura.rol, lectura.elemento
        if nombre:
            self._seed_identity_from_menu(nombre)
        # Antes del dedup del log: ese `return` es por MENSAJE repetido, y el censo cuenta
        # observaciones — volver a pasar por un PJ ya visto no imprime, pero sí acumula.
        self._observe_census(lectura)
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

    def _observe_census(self, lectura) -> None:
        """Alimenta la corrida de censo con lo leído en S15.

        Observación pura: **no toca la DB de dominio**. El estado del censo vive en `census.db`,
        y esa separación es lo que vuelve estructural —y no disciplinar— que observar no
        contamine el dominio. No-op si no hay corrida, que es el caso normal."""
        censo = self._census
        if censo is None or not censo.abierta:
            return
        from app.core.census import MenuSighting
        try:
            d = censo.observe(MenuSighting(
                nombre=lectura.nombre, texto_crudo=lectura.texto_crudo, conf=lectura.conf,
                candidato=lectura.candidato, score=lectura.score, motivo=lectura.motivo,
            ), ts=time.time())
        except Exception:
            log.exception("Error acumulando la observación del censo")
            return
        for linea in d.logs:
            log.info("[censo] %s", linea)
        if d.estado != d.estado_previo and self._on_census_progress:
            try:
                self._on_census_progress({**censo.resumen(), "clave": d.clave,
                                          "estado": d.estado, "es_nuevo": d.es_nuevo})
            except Exception:
                log.exception("Error en on_census_progress callback")

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
            self._s17_vote.reset()
            self._s17_det_crop = None          # la cara guardada era del disco anterior
            self._s17_rescue_pending = None    # y el rescate pendiente, del disco anterior
            if self._id_diag_on:
                self._id_diag = {"samples": 0, "grid_loc": 0, "grid_match": 0,
                                 "det_loc": 0, "det_match": 0, "grid_votes": {}, "det_votes": {}}
        # 5R.L.6: cada pasada del loop rápido (10fps) cuenta para el warmup del dueño,
        # localice o no la grilla (el detalle vota aparte). `_process_disc_s17_continuous`
        # difiere la emisión de discos con dueño INCIERTO hasta juntar varias pasadas.
        self._s17_vote.passes += 1
        badge = crop_grid_selected_badge(frame)
        g_name, g_conf = None, 0.0
        if badge is None:
            self._s17_vote.mark_absent(_SURF_GRID)   # gate L.7.2: sin avatar (libre/NOLOC)
            self._dump_grid_diag(frame, None, None, 0.0, False, sig)   # grid no localizó (NOLOC)
        else:
            self._s17_vote.mark_present(_SURF_GRID)  # hay avatar de dueño en el tile
            g_name, g_conf, rejected = self._identifier.s17_match(badge)
            self._dump_grid_diag(frame, badge, g_name, g_conf, rejected, sig)
            if g_name:
                self._s17_vote.vote(_SURF_GRID, g_name, g_conf)
        # DETALLE-badge (5R.C.4 + L.2b/L.3): localiza ~siempre (incl. cuando el grid da
        # NOLOC) → vota a su PROPIO acumulador (separado del grid). `decide()` combina
        # ambos con grid-primario: el detail sube yield en NOLOC del grid sin poder
        # meter wrongs (RNF-02). Inerte hasta que la librería de detalle se cosecha.
        det = crop_detail_badge(frame)
        d_name, d_conf = None, 0.0
        if det is None:
            self._s17_vote.mark_absent(_SURF_DET)    # sin avatar en el panel (libre?)
        else:
            d_name, d_conf, _d_margin, _d_rej = self._identifier.s17_match_detail(det)
            # PRESENCIA ESTRUCTURAL (5R.L.8): ¿el crop es una CARA o el texto '(N)'?
            # Clasificador cara-vs-texto (`s17_detail_is_face`, anclas -ico + reject de
            # texto), INDEPENDIENTE del naming: un avatar real que el matcher no puede
            # nombrar (gap de refs) cuenta como presente igual. Antes se exigía
            # conf/margen del matcher → avatar no-nombrable contaba ausente → falso
            # LIBRE (Jane desde Velina, QA 2026-07-18).
            if self._identifier.s17_detail_is_face(det):
                self._s17_vote.mark_present(_SURF_DET)  # avatar de dueño (nombrable o no)
                # Guardar el recorte para la cosecha de rescate: es CARA (no el texto '(N)') y
                # es de ESTE disco. Que el matcher no sepa nombrarla es justamente el caso que
                # la cosecha viene a resolver, así que no se exige nombre.
                self._s17_det_crop = (sig, det)
                self._collect_pending_rescue(sig, det)  # ¿había un rescate esperando este crop?
            else:
                self._s17_vote.mark_absent(_SURF_DET)   # crop espurio (texto) → ausente
            if d_name:
                self._s17_vote.vote(_SURF_DET, d_name, d_conf)
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
        voted, _src = self._s17_vote.decide(latch=self._last_agent_name)

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
        owner, _src = self._s17_vote.decide(latch=self._last_agent_name)
        return owner

    def _s17_owner_sig_matches(self, frame) -> bool:
        sig = self._s17_disc_signature(frame)
        return not (sig is None or self._s17_owner_sig is None
                    or not self._sig_close(sig, self._s17_owner_sig))

    def _s17_is_libre(self, frame) -> bool:
        """True si el disco mirado está LIBRE (nadie lo equipa). PRESENCIA GANA A LIBRE
        (5R.L.8, decisión del usuario 2026-07-19 — REEMPLAZA "LIBRE gana a incierto" de
        2026-06-21): un avatar LOCALIZADO en el detalle, aunque el matcher no pueda
        nombrarlo, prueba que el disco ESTÁ equipado → nunca LIBRE (falso LIBRE = riesgo
        real con la escritura de Fase 5/S23). La regla vieja asumía "matchers 0-wrong ⇒
        sin voto = sin dueño", pero se rompía con dueños no-nombrables (gap de refs:
        Jane visto desde Velina, QA 2026-07-18).
        Regla: sin votos ∧ firma vigente ∧ detail_present == 0 → LIBRE. La presencia es
        ESTRUCTURAL (crop no rechazado; el texto '(N)' cae en el reject-set → ausente),
        así que un libre real sigue saliendo con 1 solo frame (sin parpadeo). Un único
        frame con cara bloquea LIBRE hasta el reset por cambio de disco. La presencia
        espuria del grid (gate leaky en libres, L.7.2) sigue SIN participar."""
        if not self._s17_owner_sig_matches(frame):
            return False
        return self._s17_vote.is_libre()

    # ---- Compat 5R.L.8: nombres históricos del estado de voto/presencia ----------
    # El estado vive en `self._s17_vote` (OwnerVoteAccumulator, módulo reusable).
    # Estas properties preservan los nombres `_s17_*` que usan tests y call sites.

    @property
    def _s17_grid_votes(self) -> dict:
        return self._s17_vote.votes(_SURF_GRID)

    @_s17_grid_votes.setter
    def _s17_grid_votes(self, v: dict) -> None:
        self._s17_vote.set_votes(_SURF_GRID, v)

    @property
    def _s17_det_votes(self) -> dict:
        return self._s17_vote.votes(_SURF_DET)

    @_s17_det_votes.setter
    def _s17_det_votes(self, v: dict) -> None:
        self._s17_vote.set_votes(_SURF_DET, v)

    @property
    def _s17_detail_present(self) -> int:
        return self._s17_vote.present(_SURF_DET)

    @_s17_detail_present.setter
    def _s17_detail_present(self, n: int) -> None:
        self._s17_vote.set_present(_SURF_DET, n)

    @property
    def _s17_detail_absent(self) -> int:
        return self._s17_vote.absent(_SURF_DET)

    @_s17_detail_absent.setter
    def _s17_detail_absent(self, n: int) -> None:
        self._s17_vote.set_absent(_SURF_DET, n)

    @property
    def _s17_grid_present(self) -> int:
        return self._s17_vote.present(_SURF_GRID)

    @_s17_grid_present.setter
    def _s17_grid_present(self, n: int) -> None:
        self._s17_vote.set_present(_SURF_GRID, n)

    @property
    def _s17_grid_absent(self) -> int:
        return self._s17_vote.absent(_SURF_GRID)

    @_s17_grid_absent.setter
    def _s17_grid_absent(self, n: int) -> None:
        self._s17_vote.set_absent(_SURF_GRID, n)

    @property
    def _s17_owner_passes(self) -> int:
        return self._s17_vote.passes

    @_s17_owner_passes.setter
    def _s17_owner_passes(self, n: int) -> None:
        self._s17_vote.passes = int(n)

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
        # El botón se lee ACÁ, antes de que el ancla decida: es la única señal que puede
        # desmentirla (ver el guard más abajo).
        self._refresh_action_button(disc, frame, badge_present=badge is not None)
        # --- ANCHOR DE FLUJO (5R.5b) ---------------------------------------------
        # Estructura del juego: al abrir/cambiar de slot, el PRIMER disco mostrado es
        # SIEMPRE el equipado por el latch. Un disco en un slot DISTINTO al último
        # asignado ⇒ es el equipado (certero, no depende del crop del badge). Mismo
        # slot + disco distinto (la firma resetea el aggregator) ⇒ candidato.
        slot = disc.slot or 0
        is_equipped = bool(latch) and slot != 0 and slot != self._s17_last_slot
        # GUARD POR BOTÓN (2026-07-23, FP encontrado por Daniel): el ancla es una suposición
        # ESTRUCTURAL, y el botón inferior es una afirmación DIRECTA sobre la relación entre el
        # disco en pantalla y el slot del PJ:
        #     Desequipar → este disco lo lleva puesto el PJ   ⇒ el ancla vale
        #     Equipar    → el slot está VACÍO, no hay equipado ⇒ el ancla es falsa
        #     Reemplazar → el slot tiene otro disco, este es candidato ⇒ el ancla es falsa
        # El caso que lo destapó: Velina con el slot 1 vacío. Sin equipado, el "primer disco"
        # es un candidato libre — y el badge NO puede corregirlo, porque su AUSENCIA no cuenta
        # como evidencia en contra (regla "presencia gana a LIBRE", 5R.L.8). Así el ancla ganaba
        # por default y le atribuía a Velina un disco que no era suyo.
        # Es un GUARD, no un reemplazo: solo se abstiene ante evidencia positiva en contra; si el
        # OCR no leyó el botón (None), el comportamiento es el de siempre.
        if is_equipped and self._s17_action_btn in ("equipar", "reemplazar"):
            is_equipped = False
            self._log_s17_assign(
                ("anchor_btn_veto", self._s17_action_btn),
                "[botón] el ancla decía 'equipado por %s' pero el botón dice '%s' → NO es el "
                "equipado (slot vacío o candidato).", latch, self._s17_action_btn,
                razonamiento=True,
            )
        voted = self._s17_voted_owner(frame) if is_equipped else None
        if is_equipped:
            # ANCHOR-WARMUP (QA 2026-06-20): el ancla ("1er disco del slot = equipado por el
            # latch") puede caer sobre un CANDIDATO si el usuario NAVEGÓ dentro del slot. Si
            # finaliza ANTES de que el badge cante, mislabela (Nana de Seth → 'Nicole', el PJ
            # de la página) y queda pegado en agente_asignado. Esperar el voto del badge: si
            # aún no llegó y no calentamos, DIFERIR — no fijar el slot ni cosechar → el próximo
            # frame re-evalúa con el voto listo (el warmup posterga la emisión mientras tanto).
            if voted is None and self._s17_owner_passes < _S17_OWNER_MIN_SAMPLES:
                return
            # GUARD POR LATCH SOSTENIDO (2026-08-15, agujero que destapó el QA de discos y que
            # Daniel había notado a ojo en S8). `_detail_source == "sostenido"` significa, exacto:
            # la barra de avatares está VISIBLE, NO estamos en la ranura donde se confirmó la
            # identidad, y el matcher no pudo reconocer al PJ ⇒ **la selección se movió y no
            # sabemos hacia quién**. `_last_agent_name` es el del PJ ANTERIOR.
            #
            # El cross-check de abajo no cubre esto: solo ataja cuando el badge dice OTRO PJ. Y los
            # dos fallos están CORRELACIONADOS — el latch se sostiene porque el matcher de fila no
            # reconoce a ese PJ, y el badge calla porque el de grilla/detalle tampoco (misma causa:
            # refs flacas). Justo cuando el latch está viejo, la guarda que debería atraparlo está
            # muda, y el ancla asignaba con conf 1.0 + cosechaba bajo ese nombre.
            #
            # Es un GUARD, no un reemplazo: solo desactiva el ANCLA. Se cae al camino por evidencia
            # (voto, sim-a-latch, LIBRE, desempate por contexto), que puede resolverlo igual de
            # bien o declararlo incierto — lo que no puede es afirmar certeza sin confirmación.
            # Si el badge SÍ vota, `voted` no es None y esto no se activa: sostenido no es veneno,
            # es falta de confirmación.
            if voted is None and self._detail_source == "sostenido":
                is_equipped = False
                self._log_s17_assign(
                    ("anchor_latch_stale", latch),
                    "[latch] el ancla decía 'equipado por %s' pero ese latch está SOSTENIDO (la "
                    "barra se movió y el avatar no se reconoció) y el badge no vota → sin "
                    "confirmación independiente, no se asigna por ancla.", latch,
                    razonamiento=True,
                )
        if is_equipped:
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
                    razonamiento=True,
                )
                self._maybe_harvest_detail_despite_veto(frame, latch, voted)
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
            # PRESENCIA sin naming (5R.L.8): el detalle VIO un avatar (crop no rechazado)
            # pero nadie pudo nombrarlo → el disco ESTÁ equipado por alguien desconocido.
            # Reportar "equipado · dueño incierto" (honesto, RNF-02) — nunca dejarlo en
            # limbo ni LIBRE (el falso LIBRE habilitaría un reemplazo erróneo en Fase 5).
            if self._s17_detail_present > 0 and self._s17_owner_sig_matches(frame):
                disc.equip_detectado = True
                disc.equip_pj_visual = None
                disc.equip_libre = False
                self._log_s17_assign(
                    ("presencia_incierto",),
                    "[S17] equipado · dueño incierto (avatar visto, no identificado).",
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
        # DEBUG: el QUIÉN ya viaja en la línea de "Disco detectado"; lo que agrega esta es CÓMO se
        # decidió (`sim=`), que es razonamiento. Se ve con `DANIBOD_LOG_DEBUG=1`.
        self._log_s17_assign(
            ("confirm", latch), "[S17] asignado a '%s' (latch; sim=%s).", latch, sim_str,
            razonamiento=True,
        )

    def _log_s17_assign(self, sig, msg, *args, razonamiento: bool = False) -> None:
        """Loguea la decisión de asignación S17 edge-triggered: 1× por cambio de
        firma (no en cada ciclo del modelo continuo). Re-loguea al transicionar
        entre equipado/otro-PJ/sin-avatar. Reset en _reset_s17_disc_tracking.

        `razonamiento=True` manda la línea a DEBUG en vez de INFO. La regla es **un evento, una
        línea**: en INFO va QUÉ pasó (a quién se asignó el disco, si está libre, si es de otro PJ);
        el PORQUÉ —qué guarda vetó al ancla, qué señal discrepó— es material de depuración y se ve
        con `DANIBOD_LOG_DEBUG=1`.

        Por qué importa (medido sobre el QA del 2026-08-15): un disco emitía 4-7 líneas y varias
        salían IDÉNTICAS entre discos distintos, porque el mensaje no dice de cuál habla. Con 12-47
        segundos entre ellas no eran repeticiones sino eventos reales indistinguibles — y eso es lo
        que impide usar el log como señal para cronometrar o para seguir un censo.
        """
        if sig == self._s17_assign_sig:
            return
        self._s17_assign_sig = sig
        (log.debug if razonamiento else log.info)(msg, *args)

    def _process_disc(self, frame, state: ScreenState) -> None:
        try:
            # S17 (disco equipado, "Personalización de pistas") usa el parser
            # ESPACIAL full-frame — más robusto que el per-ROI a 2560×1440.
            if state.code == "S17":
                disc, _face = parse_disc_s17_full(frame, self._ocr)
                self._assign_s17_pj(disc, frame)   # identidad por badge de grilla (5R.5)
            elif state.code in ("S6", "S7"):
                # Vista individual del disco: parser ESPACIAL de 2 columnas (motor de S3). El
                # per-ROI leía mal esta pantalla igual que el modal S3 — cada celda se comía la
                # columna vecina y partía los nombres largos en substats fantasma con valores
                # rescatados de otra fila (medido 2026-07-16 sobre los 3 fixtures).
                from app.core.parser_disc_s3 import parse_disc_s7
                disc = parse_disc_s7(frame, self._ocr)
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

    def cerrar_censo(self) -> dict | None:
        """Cierra la pasada de censo en curso (hotkey F8). Devuelve el registro, o None si no
        había ninguna abierta.

        **El cierre es una declaración del usuario, no una inferencia.** El sistema no puede
        saber si el recorrido llegó al final —el menú no tiene contador de agentes—, así que no
        debe cerrarse solo. Corolario asumido: una pasada que nunca se cierra no produce
        huérfanos, y eso es correcto.

        Es también el único momento en que el censo escribe la DB de dominio, y solo para anotar
        (RNF-01 + gate de readonly dentro de `marcar_huerfanos_en_dominio`).
        """
        censo = self._census
        if censo is None or not censo.abierta:
            log.info("[censo] no hay ninguna pasada abierta que cerrar")
            return None
        from app.core.census import write_census_report
        registro = censo.cerrar(ts=time.time())
        if registro is None:
            return None
        r = registro["resumen"]
        log.info("[censo] pasada cerrada — %d/%d vistos · %d dudosos · %d huérfanos · %d no "
                 "reconocidos", r["vistos"], r["total_db"], r["dudosos"], r["huerfanos"],
                 r["nuevos"])
        try:
            from datetime import datetime as _dt

            from app.core.census_store import marcar_huerfanos_en_dominio
            marcar_huerfanos_en_dominio(registro["huerfanos"],
                                        fecha=_dt.now().strftime("%Y-%m-%d"))
        except Exception:
            log.exception("[censo] no se pudieron marcar los huérfanos")
        try:
            write_census_report(registro)
        except Exception:
            log.exception("[censo] no se pudo escribir el reporte")
        return registro

    def _register_hotkeys(self) -> None:
        from app.core.hotkeys import HotkeyManager
        hk = HotkeyManager()
        hk.on("f10", self.toggle_pause)
        hk.on("f8", self.cerrar_censo)
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
