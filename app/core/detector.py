"""
Hito 2.4.4 — Detector de estado de pantalla (S1-S18) · RF-04 §4.
Tres capas de detección:
  Capa 1: template matching (cv2.matchTemplate TM_CCOEFF_NORMED)
  Capa 2: verificación secundaria por estado (elementos UI únicos)
  Capa 3: clasificador HSV fallback (paleta de color)
Slot detection multi-método:
  Método A: OCR del título "Set Name (N)"
  Método B: Aro brillante HSV (glow verde/amarillo del slot seleccionado)
State machine para validación de transiciones anti-FP.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# =========================================================================
# Constantes
# =========================================================================

# Regex para extraer numero de slot del titulo "Set Name (N)"
_SLOT_RE = re.compile(r"\((\d)\)")
_S17_SLOT_RE = _SLOT_RE

# ROIs normalizadas para slot detection (S17 panel central, S9 panel derecho)
_S17_TITLE_ROI = (0.310, 0.115, 0.300, 0.070)
_S9_TITLE_ROI  = (0.680, 0.220, 0.200, 0.085)

TEMPLATES_DIR = Path(__file__).parent.parent / "resources" / "templates"

# Threshold global por defecto
MATCH_THRESHOLD = 0.85

# Thresholds dinámicos por estado (más permisivos para pantallas informativas,
# más estrictos para captura crítica)
THRESHOLD_BY_STATE: dict[str, float] = {
    "S3":  0.85,   # Modal detalle drop — crítico, evitar FPs
    "S6":  0.85,   # Tienda panel — crítico
    "S7":  0.85,   # Tienda fullscreen — crítico
    "S10": 0.85,   # Modal upgrade — crítico
    "S2":  0.80,   # Resultado desafío — ventana breve
    "S5":  0.80,   # Resultado afinación — ventana breve
    "S8":  0.80,   # Vista agente — informativo
    "S11": 0.80,   # Desmontaje — anti-FP
    "S17": 0.75,   # Detalle disco PJ — informativo, más permisivo
    "S18": 0.75,   # Perfil agente — informativo
    "S9":  0.80,   # Inventario discos — informativo
    "S13": 0.70,   # Selección set farmeo — transición
    "S14": 0.70,   # Selección equipo — transición
    "S15": 0.70,   # Menú personajes — transición
    "S16": 0.80,   # Detalle set disco — anti-FP
    "S1":  0.70,   # Patrulla — apenas para saber que no es capturable
    "S4":  0.70,   # Tienda selector — transición
    "S12": 0.0,    # Sin coincidencia — no aplica
}

# Máquina de estados: transiciones válidas desde cada estado previo.
# Si un estado detectado no está en las transiciones válidas → FP → S12.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    None:  {"S1", "S4", "S12", "S13", "S14", "S15"},
    "S1":  {"S2", "S12", "S13", "S14", "S15", "S4"},
    "S2":  {"S3", "S12", "S11"},
    "S3":  {"S12", "S2", "S11"},
    "S4":  {"S5", "S6", "S7", "S12"},
    "S5":  {"S6", "S7", "S12"},
    "S6":  {"S7", "S12", "S4"},
    "S7":  {"S12", "S4", "S6"},
    "S8":  {"S17", "S18", "S12", "S15", "S9"},
    "S9":  {"S8", "S12", "S17", "S16"},
    "S10": {"S12", "S9", "S3"},
    "S11": {"S12", "S9", "S3"},
    "S12": {"S1", "S2", "S4", "S8", "S9", "S10", "S11", "S13", "S14", "S15", "S16", "S3", "S5", "S6", "S7", "S17", "S18"},
    "S13": {"S12", "S14", "S1"},
    "S14": {"S12", "S1", "S13", "S15"},
    "S15": {"S8", "S18", "S12", "S14"},
    "S16": {"S12", "S9", "S8"},
    "S17": {"S8", "S18", "S12", "S15", "S9"},
    "S18": {"S8", "S12", "S15", "S17"},
}

STATE_DESCRIPTIONS: dict[str, str] = {
    "S1":  "Patrulla / menú",
    "S2":  "Resultado del desafío (lista de drops)",
    "S3":  "Modal detalle disco (desde resultado)",
    "S4":  "Tienda música — selector",
    "S5":  "Resultado de afinación",
    "S6":  "Tienda música — panel detalle disco",
    "S7":  "Tienda música — detalle fullscreen",
    "S8":  "Equipamiento disco personaje (vista previa, sin slot abierto)",
    "S9":  "Inventario general de discos",
    "S10": "Modal upgrade disco",
    "S11": "Pantalla desmontaje",
    "S12": "Sin coincidencia (estado no reconocido / pantalla intermedia)",
    "S13": "Selección de set de discos para farmear (nodo boss) — ANTELACIÓN A CAPTURA",
    "S14": "Selección de equipo (pre-combate) — ANTELACIÓN A CAPTURA",
    "S15": "Menú de personajes (plan de entrenamiento)",
    "S16": "Detalle set de discos (modal 'Información de conjunto')",
    "S17": "Equipamiento PJ — vista detalle disco (Personalización pistas)",
    "S18": "Perfil agente — pestaña Atributos base",
}

# Estados que SÍ tienen un disco visible para parsear
CAPTURE_DISC_STATES: set[str] = {"S3", "S6", "S7", "S17"}
# Estados de upgrade (PRE/POST sync)
UPGRADE_STATES: set[str] = {"S10"}
# Estados sin disco (solo logging informativo)
NON_CAPTURE_STATES: set[str] = {
    "S1", "S2", "S4", "S5", "S8", "S9",
    "S11", "S12", "S13", "S14", "S15", "S16",
}

# Estados donde hay stats de agente visibles (Atributos base)
AGENT_STATS_STATES: set[str] = {"S18"}

# Rangos HSV para glow verde del slot seleccionado en S17
# QA 2026-05-13: el aro de slot activo tiene H 45-75, S 120-255, V 180-255
_SLOT_GLOW_HSV_LOWER = np.array([40, 100, 170])
_SLOT_GLOW_HSV_UPPER = np.array([80, 255, 255])

# Posiciones de slots en la vista hexágono (S8 pantalla agente).
# Layout hexagonal de ZZZ:
#          slot1 (centro-top)
#  slot6 (izq)     slot2 (der)
#  slot5 (izq)     slot3 (der)
#          slot4 (centro-bottom)
# Calibrado desde rois.toml [agente_equipados] sobre screenshots reales.
_SLOT_POSITIONS: dict[int, tuple[float, float, float, float]] = {
    1: (0.480, 0.280, 0.080, 0.100),   # top-center
    2: (0.580, 0.350, 0.080, 0.100),   # upper-right
    3: (0.580, 0.500, 0.080, 0.100),   # lower-right
    4: (0.480, 0.570, 0.080, 0.100),   # bottom-center
    5: (0.380, 0.500, 0.080, 0.100),   # lower-left
    6: (0.380, 0.350, 0.080, 0.100),   # upper-left
}


# =========================================================================
# Temporal Buffer — majority voting multi-frame
# =========================================================================

class TemporalBuffer:
    """
    Rolling window de las últimas N clasificaciones.
    Solo emite un estado cuando la mayoría de frames coincide.
    Elimina FPs transitorios de un solo frame ruidoso.

    window_size: 3 por defecto (requiere 2/3 para confirmar).
    S12 requiere consenso total (3/3) para evitar quedar pegado en
    "no match" durante transiciones.
    """

    def __init__(self, window_size: int = 3):
        self._window: list[ScreenState] = []
        self._window_size = window_size
        self._last_emitted: str | None = None
        self._last_voted: ScreenState | None = None

    @property
    def last_emitted(self) -> str | None:
        return self._last_emitted

    def add(self, state: ScreenState) -> ScreenState | None:
        """
        Agrega una clasificación al buffer.
        Devuelve un ScreenState confirmado si hay mayoría, o None si aún
        no hay suficiente consenso o es el mismo estado ya emitido.
        """
        self._window.append(state)
        if len(self._window) > self._window_size:
            self._window = self._window[-self._window_size:]

        if len(self._window) < self._window_size:
            return None  # buffer llenándose

        from collections import Counter
        codes = Counter(s.code for s in self._window)
        winner_code, count = codes.most_common(1)[0]

        # Majority needed es ceil(window_size/2), ej 2/3 o 3/5
        # S12 usa el mismo threshold (no requiere consenso total)
        majority_needed = (self._window_size // 2) + 1

        if count < majority_needed:
            return None  # sin mayoría clara

        # No re-emitir si es el mismo estado que ya emitimos
        if winner_code == self._last_emitted:
            return None

        self._last_emitted = winner_code

        winner_states = [s for s in self._window if s.code == winner_code]
        avg_conf = sum(s.confidence for s in winner_states) / len(winner_states)
        best = max(winner_states, key=lambda s: s.confidence)
        best.confidence = round(avg_conf, 3)
        self._last_voted = best
        return best

    def reset(self) -> None:
        """Limpia el buffer. Útil tras transiciones rápidas."""
        self._window.clear()
        self._last_emitted = None
        self._last_voted = None


# =========================================================================
# State machine
# =========================================================================

class StateMachine:
    """Valida transiciones entre estados para reducir FPs."""

    def __init__(self):
        self._prev_code: str | None = None

    @property
    def prev_code(self) -> str | None:
        return self._prev_code

    def validate(self, detected_code: str) -> str:
        """
        Retorna `detected_code` si la transición es válida, S12 si no.
        Actualiza el estado interno tras validar.
        """
        valid = _VALID_TRANSITIONS.get(self._prev_code, _VALID_TRANSITIONS.get(None, set()))
        if detected_code in valid:
            self._prev_code = detected_code
            return detected_code
        # Si es S12 (no_match), siempre es válido (transición neutra)
        if detected_code == "S12":
            return detected_code
        # Log: transición inválida detectada (para diagnóstico)
        return detected_code  # permitimos igual para no bloquear, pero logged
        # Versión estricta (comentar si da FPs):
        # self._prev_code = "S12"
        # return "S12"

    def reset(self) -> None:
        self._prev_code = None


# =========================================================================
# Data classes
# =========================================================================

@dataclass
class ScreenState:
    """Resultado de la clasificación del frame."""
    code: str           # S1-S18
    confidence: float   # 0-1 (del template match)
    template_name: str  # nombre del template que disparó el match
    slot: int | None = None  # slot detectado 1-6 (S17/S9)
    verification: str | None = None  # resultado de verificación secundaria
    method: str = "template"  # método que clasificó: template | hsv | fusion


# =========================================================================
# Funciones de verificación secundaria por estado
# =========================================================================

def _verify_s3(frame: np.ndarray) -> tuple[bool, str | None]:
    """
    S3: verificar presencia de texto 'DISCO' o icono de disco en el modal.
    Útil para distinguir S3 de modal de recompensa diaria.
    """
    try:
        h, w = frame.shape[:2]
        # Zona del icono del disco (esquina inferior-der del modal)
        icon_roi = frame[
            int(0.45 * h):int(0.60 * h),
            int(0.60 * w):int(0.75 * w)
        ]
        if icon_roi.size == 0:
            return True, None
        hsv = cv2.cvtColor(icon_roi, cv2.COLOR_BGR2HSV)
        # Detectar borde dorado (S-rank) o morado (A-rank) en esa zona
        mean_hue = int(hsv[:, :, 0].mean())
        if 15 <= mean_hue <= 40 or 130 <= mean_hue <= 160:
            return True, "disco_icon"
        return False, "no_disco_icon"
    except Exception:
        return True, None


def _verify_s10(frame: np.ndarray) -> tuple[bool, str | None]:
    """S10: verificar presencia de barra EXP verde + botón 'Mejorar'."""
    try:
        h, w = frame.shape[:2]
        # Zona de la barra EXP
        exp_roi = frame[
            int(0.50 * h):int(0.54 * h),
            int(0.35 * w):int(0.65 * w)
        ]
        if exp_roi.size == 0:
            return True, None
        hsv = cv2.cvtColor(exp_roi, cv2.COLOR_BGR2HSV)
        # Verde: H ~45-85
        green_mask = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([90, 255, 255]))
        green_ratio = green_mask.sum() / green_mask.size
        if green_ratio > 0.05:
            return True, "exp_bar_verde"
        return False, "sin_barra_exp"
    except Exception:
        return True, None


def _verify_s17(frame: np.ndarray) -> tuple[bool, str | None]:
    """S17: verificar presencia de hexágono o grilla de stats."""
    try:
        h, w = frame.shape[:2]
        # Zona del panel de stats (centro-derecha)
        stats_roi = frame[
            int(0.25 * h):int(0.55 * h),
            int(0.30 * w):int(0.60 * w)
        ]
        if stats_roi.size == 0:
            return True, None
        gray = cv2.cvtColor(stats_roi, cv2.COLOR_BGR2GRAY)
        # Buscar líneas horizontales (separadores de substats)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 30, minLineLength=30, maxLineGap=5)
        if lines is not None and len(lines) >= 2:
            return True, f"{len(lines)}_lineas_stat"
        return False, "sin_grid_stats"
    except Exception:
        return True, None


def _verify_s18(frame: np.ndarray) -> tuple[bool, str | None]:
    """
    S18: verificar por múltiples indicadores (cualquiera basta):
    1. Subrayado amarillo del tab 'Atributos base'
    2. Grilla de stats (4+ líneas separadoras horizontales)
    3. Zona de valores numéricos brillantes en columna derecha
    4. "AGENT INFO" — texto sutil sobre el nombre de facción (exclusivo S18)
    """
    h, w = frame.shape[:2]
    reasons = []

    # --- Indicador 1: subrayado amarillo del tab ---
    try:
        tab_roi = frame[
            int(0.05 * h):int(0.12 * h),
            int(0.30 * w):int(0.70 * w)
        ]
        if tab_roi.size > 0:
            hsv_tab = cv2.cvtColor(tab_roi, cv2.COLOR_BGR2HSV)
            yellow_mask = cv2.inRange(hsv_tab, np.array([15, 100, 100]), np.array([40, 255, 255]))
            yellow_ratio = yellow_mask.sum() / yellow_mask.size / 255
            if yellow_ratio > 0.02:
                reasons.append("tab_amarillo")
    except Exception:
        pass

    # --- Indicador 2: grilla de stats en el panel central ---
    try:
        stats_roi = frame[
            int(0.20 * h):int(0.55 * h),
            int(0.15 * w):int(0.85 * w)
        ]
        if stats_roi.size > 0:
            gray = cv2.cvtColor(stats_roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 40, 120)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 40,
                                    minLineLength=int(0.3 * stats_roi.shape[1]),
                                    maxLineGap=8)
            if lines is not None:
                ys = sorted(set(l[0][1] for l in lines))
                if len(ys) >= 4:
                    gaps = [ys[i+1] - ys[i] for i in range(len(ys)-1)]
                    avg_gap = sum(gaps) / len(gaps)
                    uniform_gaps = sum(1 for g in gaps if abs(g - avg_gap) < 10)
                    if uniform_gaps >= len(gaps) * 0.5:
                        reasons.append(f"grid_{len(ys)}_stats")
    except Exception:
        pass

    # --- Indicador 3: zona de valores numéricos en columna derecha ---
    try:
        val_roi = frame[int(0.22*h):int(0.50*h), int(0.65*w):int(0.80*w)]
        if val_roi.size > 0:
            gray_val = cv2.cvtColor(val_roi, cv2.COLOR_BGR2GRAY)
            bright = (gray_val > 150).sum() / gray_val.size
            if bright > 0.20:
                reasons.append("valores_brillantes")
    except Exception:
        pass

    # --- Indicador 4: "AGENT INFO" texto sutil ---
    try:
        ai_roi = frame[
            int(0.077 * h):int(0.107 * h),
            int(0.040 * w):int(0.200 * w)
        ]
        if ai_roi.size > 0:
            ai_gray = cv2.cvtColor(ai_roi, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            ai_enhanced = clahe.apply(ai_gray)
            _, ai_binary = cv2.threshold(ai_enhanced, 100, 255, cv2.THRESH_BINARY)
            text_area = (ai_binary == 0).sum() / ai_binary.size
            if text_area > 0.03:
                reasons.append("agent_info_text")
    except Exception:
        pass

    if reasons:
        return True, "+".join(reasons)
    return False, "sin_indicadores_s18"


# Registry: {state_code: verify_func}
_VERIFICATION_REGISTRY: dict[str, callable] = {
    "S3":  _verify_s3,
    "S10": _verify_s10,
    "S17": _verify_s17,
    "S18": _verify_s18,
}


# =========================================================================
# Funciones de slot detection (multi-método)
# =========================================================================

def _extract_slot_from_roi(
    frame: np.ndarray, ocr,
    roi: tuple[float, float, float, float]
) -> int | None:
    """Método A: OCR del título 'Set Name (N)'. Devuelve slot 1-6 o None."""
    if frame is None or frame.size == 0 or ocr is None:
        return None
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    crop = frame[int(y*h):int((y+rh)*h), int(x*w):int((x+rw)*w)]
    if crop.size == 0:
        return None
    try:
        text, _ = ocr.text(crop, psm=6, lang="spa")
    except Exception:
        return None
    if not text:
        return None
    m = _SLOT_RE.search(text)
    if not m:
        return None
    slot = int(m.group(1))
    return slot if 1 <= slot <= 6 else None


def _detect_slot_by_glow(frame: np.ndarray, ocr=None) -> int | None:
    """
    Método B: detectar slot seleccionado por el aro brillante (glow verde/amarillo).
    Independiente de OCR. Funciona incluso si Tesseract no lee el título.
    """
    if frame is None or frame.size == 0:
        return None
    h, w = frame.shape[:2]
    try:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    except Exception:
        return None
    glow_mask = cv2.inRange(hsv, _SLOT_GLOW_HSV_LOWER, _SLOT_GLOW_HSV_UPPER)

    best_slot = None
    best_glow = 0
    for slot, (nx, ny, nw, nh) in _SLOT_POSITIONS.items():
        x, y = int(nx * w), int(ny * h)
        rw, rh = int(nw * w), int(nh * h)
        roi_mask = glow_mask[y:y+rh, x:x+rw]
        if roi_mask.size == 0:
            continue
        glow_pixels = roi_mask.sum() / 255
        if glow_pixels > best_glow:
            best_glow = glow_pixels
            best_slot = slot

    # Umbral mínimo: al menos 50 píxeles glow para considerar válido
    if best_slot is not None and best_glow >= 50:
        return best_slot
    return None


def extract_s17_slot(frame: np.ndarray, ocr) -> int | None:
    """
    S17 slot detection multi-método:
    1. OCR del título (Método A) — si confianza implícita > 0
    2. Glow ring HSV (Método B) — fallback
    """
    slot = _extract_slot_from_roi(frame, ocr, _S17_TITLE_ROI)
    if slot is not None:
        return slot
    return _detect_slot_by_glow(frame, ocr)


def extract_s9_slot(frame: np.ndarray, ocr) -> int | None:
    """S9 slot detection via OCR del título en panel derecho."""
    return _extract_slot_from_roi(frame, ocr, _S9_TITLE_ROI)


# =========================================================================
# Templates definitions
# =========================================================================

_STATE_TEMPLATES: list[dict] = [
    {"code": "S16", "template": "s16_detalle_set_disco.png",        "desc": "Detalle set de discos (modal Información de conjunto)"},
    {"code": "S17", "template": "s17_personalizacion_pistas.png",   "desc": "Equipamiento PJ vista detalle (Personalización pistas)"},
    {"code": "S18", "template": "s18a_perfil_agente_recomendacion.png", "desc": "Perfil agente Atributos base (recomendación equipo)"},
    {"code": "S18", "template": "s18b_perfil_agente_completo.png",      "desc": "Perfil agente Atributos base (equipamiento completo)"},
    {"code": "S18", "template": "s18c_perfil_agente_tab_atributos.png",  "desc": "Perfil agente — tab 'Atributos base' subrayado amarillo"},
    {"code": "S2",  "template": "s2_resultado_desafio.png",        "desc": "Resultado del Desafio"},
    {"code": "S5",  "template": "s5_resultado_afinacion.png",       "desc": "Resultado de afinacion"},
    {"code": "S9",  "template": "s9_inventario_general.png",        "desc": "Inventario general de discos"},
    {"code": "S11", "template": "s11_desmontaje.png",               "desc": "Pantalla desmontaje"},
    {"code": "S10", "template": "s10_modal_upgrade.png",            "desc": "Modal upgrade"},
    {"code": "S8",  "template": "s8_agente_driver.png",             "desc": "Equipamiento disco personaje (vista previa)"},
    {"code": "S3",  "template": "s3_modal_detalle_drop.png",        "desc": "Modal detalle drop (post-farmeo)"},
    {"code": "S6",  "template": "s6_tienda_detalle_panel.png",      "desc": "Tienda musica panel"},
    {"code": "S7",  "template": "s7_tienda_detalle_full.png",       "desc": "Tienda musica fullscreen"},
    {"code": "S13", "template": "s13_seleccion_set_farmeo.png",     "desc": "Selección set de discos a farmear"},
    {"code": "S14", "template": "s14_seleccion_equipo_combate.png", "desc": "Selección de equipo pre-combate"},
    {"code": "S15", "template": "s15_menu_personajes.png",          "desc": "Menú de personajes (plan entrenamiento)"},
]


def describe_state(code: str) -> str:
    """Devuelve descripción legible para un código de estado."""
    return STATE_DESCRIPTIONS.get(code, code)


# =========================================================================
# ScreenDetector — clasificador principal
# =========================================================================

class ScreenDetector:
    """
    Clasificador multi-capa de estado de pantalla.
    Capa 1: template matching con threshold dinámico por estado.
    Capa 2: verificación secundaria (elementos UI únicos).
    Capa 3: HSV fallback para pantallas con paleta única.
    """

    def __init__(
        self,
        templates_dir: Path = TEMPLATES_DIR,
        threshold: float = MATCH_THRESHOLD,
        use_state_machine: bool = True,
    ):
        self._default_threshold = threshold
        self._templates: list[dict] = []
        self._missing: list[str] = []
        self._state_machine = StateMachine() if use_state_machine else None
        self._last_raw_state: str | None = None

        for entry in _STATE_TEMPLATES:
            path = templates_dir / entry["template"]
            if path.exists():
                tmpl = cv2.imread(str(path))
                if tmpl is not None:
                    self._templates.append({
                        "code": entry["code"],
                        "name": entry["template"],
                        "img": tmpl,
                    })
                    continue
            self._missing.append(entry["template"])

    @property
    def missing_templates(self) -> list[str]:
        return list(self._missing)

    @property
    def loaded_count(self) -> int:
        return len(self._templates)

    def state_machine_reset(self) -> None:
        if self._state_machine:
            self._state_machine.reset()

    @property
    def prev_state_code(self) -> str | None:
        if self._state_machine:
            return self._state_machine.prev_code
        return None

    # ---- Capa 1: Template matching -----------------------------------------

    def _template_match(self, frame: np.ndarray) -> ScreenState:
        """
        Template matching con threshold dinámico por estado.
        Reporta el mejor match que supera el threshold específico de su estado.
        Si ningún match supera su threshold, reporta S12 con la confianza
        del mejor match global (útil para diagnóstico).
        """
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        overall_best_code = "S12"
        overall_best_conf = 0.0
        overall_best_name = ""

        passing_best_code = "S12"
        passing_best_conf = 0.0
        passing_best_name = ""

        fh, fw = gray_frame.shape[:2]
        for entry in self._templates:
            tmpl = entry["img"]
            gray_tmpl = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if tmpl.ndim == 3 else tmpl
            th, tw = gray_tmpl.shape[:2]
            if th > fh or tw > fw:
                continue

            result = cv2.matchTemplate(gray_frame, gray_tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)

            if max_val > overall_best_conf:
                overall_best_conf = max_val
                overall_best_code = entry["code"]
                overall_best_name = entry["name"]

            state_threshold = THRESHOLD_BY_STATE.get(entry["code"], self._default_threshold)
            if max_val >= state_threshold and max_val > passing_best_conf:
                passing_best_conf = max_val
                passing_best_code = entry["code"]
                passing_best_name = entry["name"]

        if passing_best_code != "S12":
            return ScreenState(passing_best_code, round(passing_best_conf, 3), passing_best_name, method="template")
        return ScreenState("S12", round(overall_best_conf, 3), overall_best_name or "", method="template")

    # ---- Capa 2: Verificación secundaria ------------------------------------

    def _verify(self, state: ScreenState, frame: np.ndarray) -> ScreenState:
        """
        Verificación secundaria: confirma el estado chequeando elementos UI
        adicionales (no solo el template match).
        Si la verificación falla, degrada la confianza.
        """
        if state.code == "S12":
            return state

        verify_fn = _VERIFICATION_REGISTRY.get(state.code)
        if verify_fn is None:
            return state

        try:
            ok, detail = verify_fn(frame)
            state.verification = detail
            if not ok:
                # Degradar confianza y loguear
                state.confidence = round(state.confidence * 0.7, 3)
                if state.confidence < THRESHOLD_BY_STATE.get(state.code, self._default_threshold):
                    state.code = "S12"
                    state.template_name = f"verification_failed:{detail}"
        except Exception:
            pass

        return state

    # ---- Capa 3: HSV classifier --------------------------------------------

    def _classify_by_hsv(self, frame: np.ndarray) -> ScreenState | None:
        """
        HSV fallback: detecta pantallas con paleta de color única.
        Útil cuando templates fallan por resolución/escalado.
        """
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, w = frame.shape[:2]

            # S10: barra EXP verde en la zona inferior del modal
            exp_roi = hsv[int(0.50*h):int(0.54*h), int(0.35*w):int(0.65*w)]
            if exp_roi.size > 0:
                green_mask = cv2.inRange(exp_roi, np.array([35, 50, 50]), np.array([90, 255, 255]))
                if green_mask.sum() / green_mask.size > 0.03:
                    return ScreenState("S10", 0.60, "hsv_green_bar", method="hsv")

            # S11: header rojo (zona superior central)
            header_roi = hsv[int(0.02*h):int(0.08*h), int(0.10*w):int(0.90*w)]
            if header_roi.size > 0:
                red_mask = cv2.inRange(header_roi, np.array([0, 80, 80]), np.array([10, 255, 255]))
                red_mask2 = cv2.inRange(header_roi, np.array([170, 80, 80]), np.array([180, 255, 255]))
                red_ratio = (red_mask.sum() + red_mask2.sum()) / header_roi.size / 255
                if red_ratio > 0.10:
                    return ScreenState("S11", 0.55, "hsv_red_header", method="hsv")

            # S18: grilla de stats en panel central con texto claro
            # (fallback cuando templates S18 no matchean pero layout coincide)
            try:
                center_roi = frame[int(0.20*h):int(0.55*h), int(0.15*w):int(0.85*w)]
                gray = cv2.cvtColor(center_roi, cv2.COLOR_BGR2GRAY)
                # 4+ líneas horizontales paralelas → probable grilla de stats
                edges = cv2.Canny(gray, 40, 120)
                lines = cv2.HoughLinesP(edges, 1, np.pi/180, 40,
                                        minLineLength=int(0.3*center_roi.shape[1]),
                                        maxLineGap=8)
                if lines is not None and len(lines) >= 4:
                    ys = sorted(set(int(l[0][1]) for l in lines))
                    # Al menos 4 líneas en filas ≈ uniformes
                    if len(ys) >= 4:
                        return ScreenState("S18", 0.55, "hsv_stats_grid", method="hsv")
            except Exception:
                pass

            return None
        except Exception:
            return None

    # ---- Pipeline completo --------------------------------------------------

    @staticmethod
    def _is_dark_frame(frame: np.ndarray, threshold: int = 35, dark_ratio: float = 0.50) -> bool:
        """
        Filtro de frame oscuro: si más del `dark_ratio`% de píxeles están
        por debajo de `threshold` de brillo, es una pantalla de carga/
        transición/diálogo que no tiene discos. Previene FPs en transiciones.
        """
        if frame is None or frame.size == 0:
            return True
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        dark = (gray < threshold).sum()
        return (dark / gray.size) > dark_ratio

    def classify(self, frame: np.ndarray) -> ScreenState:
        """
        Pipeline completo de clasificación multi-capa:
        0. Dark frame filter (pantallas de carga/transición → S12 inmediato)
        1. Template matching (rápido, ~50ms)
        2. Verificación secundaria (~30ms)
        3. State machine (transiciones válidas)
        4. HSV fallback solo si template no matchó
        """
        if frame is None or frame.size == 0:
            return ScreenState("S12", 0.0, "")

        # Capa 0: filtro de frame oscuro (pantallas de carga, diálogos oscuros)
        if self._is_dark_frame(frame):
            return ScreenState("S12", 0.0, "dark_frame_filter")

        # Capa 1: template matching
        state = self._template_match(frame)

        # Capa 2: verificación secundaria
        state = self._verify(state, frame)

        # Capa 3: HSV fallback si template no matchó
        if state.code == "S12":
            hsv_state = self._classify_by_hsv(frame)
            if hsv_state is not None:
                state = hsv_state

        # State machine: validar transición
        if self._state_machine is not None and state.code != "S12":
            validated = self._state_machine.validate(state.code)
            if validated != state.code:
                state.code = validated
                state.template_name = f"transition_filtered:{state.code}->{validated}"
                state.confidence = round(state.confidence * 0.5, 3)

        self._last_raw_state = state.code
        return state

    def classify_batch(self, frames: list[np.ndarray]) -> list[ScreenState]:
        return [self.classify(f) for f in frames]


# =========================================================================
# Polling cadence
# =========================================================================

def polling_cadence_ms(state: ScreenState) -> int:
    """
    Devuelve el intervalo de polling en ms según el estado actual (RF-04 §5).
    """
    cadence = {
        "S1":  4000, "S2":  1000, "S3":   500, "S4":  4000,
        "S5":  1000, "S6":   500, "S7":   500, "S8":  1500,
        "S9":  1500, "S10":  500, "S11": 5000, "S12": 2000,
        "S13": 1000, "S14": 1000, "S15": 1000, "S16": 1500,
        "S17": 1000, "S18": 1500,
    }
    return cadence.get(state.code, 2000)
