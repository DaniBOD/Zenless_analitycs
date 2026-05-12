"""
Hito 2.4.4 — Detector de estado de pantalla (S1-S12) · RF-04 §4.
Usa template matching (cv2.matchTemplate TM_CCOEFF_NORMED, threshold 0.85).
Templates en app/resources/templates/. Ver tools/build_templates.py para crearlos.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# Regex para extraer el numero de slot del titulo "Set Name (N)".
# Compartido entre S17 (vista detalle disco en PJ) y S9 (inventario con
# disco seleccionado) — ambas pantallas tienen el patron "(N)" en el
# titulo donde N es el slot 1-6.
_SLOT_RE = re.compile(r"\((\d)\)")
# Alias retro-compat (algun test antiguo todavia usa _S17_SLOT_RE).
_S17_SLOT_RE = _SLOT_RE

# ROI normalizada del titulo en S17 (panel central):
_S17_TITLE_ROI = (0.310, 0.115, 0.300, 0.070)
# ROI normalizada del titulo en S9 (panel detalle derecho con disco
# seleccionado). QA 2026-05-12: validado 6/6 contra ejemplos en
# 09_Inventario_discos_general/ con conf 0.76-0.92.
# El ROI evita el icono del disco a la derecha (esa region distorsiona OCR).
_S9_TITLE_ROI = (0.680, 0.220, 0.200, 0.085)

# Directorio de templates (relativo al package app/)
TEMPLATES_DIR = Path(__file__).parent.parent / "resources" / "templates"

# Threshold por defecto para template matching.
# QA 2026-05-11 (segunda iteración):
#  - 0.85 inicial: muy estricto, S12 en pantallas reales.
#  - 0.70: mejor recall pero produce false positives (ej. pantalla de
#    "selección de equipo" matcheaba S7 con conf 0.99 por matching de
#    elementos UI genéricos como botón retorno).
#  - 0.85 (final): balance correcto cuando los templates son específicos.
MATCH_THRESHOLD = 0.85

# Descripciones humanas de cada estado para el log y la UI
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

# Estados donde NO hay disco para capturar (logging informativo, no error).
# S17 técnicamente muestra detalles de un disco equipado, pero por ahora lo
# marcamos non-capture porque la captura desde esta pantalla requiere ROIs
# nuevas y deteccion de slot 1-6 (pendiente).
NON_CAPTURE_STATES = {"S1", "S2", "S4", "S5", "S8", "S9", "S11", "S12", "S13", "S14", "S15", "S16", "S17", "S18"}
# Estados donde SÍ hay un disco visible para parsear
CAPTURE_DISC_STATES = {"S3", "S6", "S7"}
# Estados de upgrade (PRE/POST sync, no es captura de drop)
UPGRADE_STATES = {"S10"}


def describe_state(code: str) -> str:
    """Devuelve descripción legible para un código de estado (S1-S12)."""
    return STATE_DESCRIPTIONS.get(code, code)


def _extract_slot_from_roi(frame: np.ndarray, ocr, roi: tuple[float, float, float, float]) -> int | None:
    """
    Helper genérico: OCR del titulo "Set Name (N)" en una ROI normalizada
    y extrae N (1-6) via regex. Compartido por S17 y S9.

    Devuelve int 1..6 o None si no se puede extraer.
    """
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


def extract_s17_slot(frame: np.ndarray, ocr) -> int | None:
    """
    S17 (vista detalle disco en PJ): OCR del titulo "Set Name (N)" del
    panel central. Devuelve slot 1..6 o None.
    """
    return _extract_slot_from_roi(frame, ocr, _S17_TITLE_ROI)


def extract_s9_slot(frame: np.ndarray, ocr) -> int | None:
    """
    S9 (inventario discos con disco seleccionado): OCR del titulo
    "Set Name (N)" del panel detalle derecho. Devuelve slot 1..6 o None.

    Si el inventario S9 no tiene disco seleccionado, este OCR retorna None
    (no hay "(N)" en el panel). Eso permite distinguir S9-sin-seleccion
    (state.slot == None) de S9-con-disco-seleccionado (state.slot 1-6).
    """
    return _extract_slot_from_roi(frame, ocr, _S9_TITLE_ROI)


@dataclass
class ScreenState:
    """Resultado de la clasificación del frame."""
    code: str          # S1-S18
    confidence: float  # 0-1 (del template match)
    template_name: str # nombre del template que disparó el match
    # Numero de slot 1-6 dentro de S17 (vista detalle disco en PJ).
    # None para todos los demás estados o si OCR del titulo falla.
    slot: int | None = None


# Descripción de cada estado y su plantilla de detección.
# ORDEN IMPORTA: estados más específicos primero (los que matchean menos cosas
# generales). Si un template más genérico está antes y matchea, ya no se evalúan
# los siguientes a menos que tengan conf más alta.
_STATE_TEMPLATES: list[dict] = [
    # S16, S17, S18 van PRIMERO porque sus templates pueden superponerse con
    # elementos similares a S3/S6/S7/S8 — si matchean, su match más alto
    # debe ganar para evitar FP.
    {"code": "S16", "template": "s16_detalle_set_disco.png",        "desc": "Detalle set de discos (modal Información de conjunto)"},
    {"code": "S17", "template": "s17_personalizacion_pistas.png",   "desc": "Equipamiento PJ vista detalle (Personalización pistas)"},
    # S18 tiene dos variantes (mismo code, distinto template) porque la
    # card Agent Info muestra "Recomendación de mejora prioritaria" SI el
    # PJ no tiene equipamiento full, o "Equipamiento completo" si lo tiene.
    # Cualquiera de las dos basta para identificar la pantalla.
    {"code": "S18", "template": "s18a_perfil_agente_recomendacion.png", "desc": "Perfil agente Atributos base (recomendación equipo)"},
    {"code": "S18", "template": "s18b_perfil_agente_completo.png",      "desc": "Perfil agente Atributos base (equipamiento completo)"},
    # QA 2026-05-12: tercer trigger universal — tab "Atributos base" con
    # subrayado amarillo. Garantiza S18 cuando estás en esa pestaña, sin
    # depender de qué card Agent Info muestre (recomendación/completo).
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
    # Pantallas adicionales detectadas durante QA (no son capturables pero
    # debemos clasificarlas para no producir false positives).
    {"code": "S13", "template": "s13_seleccion_set_farmeo.png",     "desc": "Selección set de discos a farmear"},
    {"code": "S14", "template": "s14_seleccion_equipo_combate.png", "desc": "Selección de equipo pre-combate"},
    {"code": "S15", "template": "s15_menu_personajes.png",          "desc": "Menú de personajes (plan entrenamiento)"},
]

# Estados de captura activa (donde se debe procesar el disco)
CAPTURE_STATES = {"S3", "S6", "S7"}
# Estados que indican modal de detalle (misma acción que S3)
DETAIL_STATES = {"S3", "S6", "S7"}
# Estados ignorados activamente
IGNORE_STATES = {"S1", "S4", "S11", "S12"}


class ScreenDetector:
    """
    Clasifica cada frame del juego en uno de los estados S1-S12.
    Carga los templates al inicializar y cachea los que existan.
    Si un template no existe, ese estado no se puede detectar.
    """

    def __init__(self, templates_dir: Path = TEMPLATES_DIR, threshold: float = MATCH_THRESHOLD):
        self._threshold = threshold
        self._templates: list[dict] = []  # {code, name, img}
        self._missing: list[str] = []

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

    def classify(self, frame: np.ndarray) -> ScreenState:
        """
        Clasifica un frame. Devuelve S12 si ningún template supera el threshold,
        pero en ese caso `confidence` reporta el max parcial conseguido (útil
        para diagnóstico: '¿qué tan cerca estuvimos?').
        """
        if frame is None or frame.size == 0:
            return ScreenState("S12", 0.0, "")

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        # Buscamos el mejor match global (sin filtrar por threshold todavía)
        overall_best_code = "S12"
        overall_best_conf = 0.0
        overall_best_name = ""

        # Y el mejor match que supere el threshold
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

            if max_val >= self._threshold and max_val > passing_best_conf:
                passing_best_conf = max_val
                passing_best_code = entry["code"]
                passing_best_name = entry["name"]

        if passing_best_code != "S12":
            return ScreenState(passing_best_code, round(passing_best_conf, 3), passing_best_name)
        # No hay match — reportamos el mejor parcial para que se vea en el log
        return ScreenState("S12", round(overall_best_conf, 3), overall_best_name or "")

    def classify_batch(self, frames: list[np.ndarray]) -> list[ScreenState]:
        return [self.classify(f) for f in frames]


def polling_cadence_ms(state: ScreenState) -> int:
    """
    Devuelve el intervalo de polling en ms según el estado actual (RF-04 §5).
    QA 2026-05-12: bajadas las cadencias de S13/S14/S15/S16/S17/S18 a
    1000-1500ms porque el usuario reportaba pasar por menu personajes y
    atributos sin que el detector alcanzara a clasificarlos.
    """
    cadence = {
        "S1":  4000,  # Patrulla — idle
        "S2":  1000,  # Resultado desafio — breve ventana
        "S3":   500,  # Modal detalle drop — critico
        "S4":  4000,  # Tienda — selector
        "S5":  1000,  # Tienda — resultado afinacion
        "S6":   500,  # Tienda — panel detalle
        "S7":   500,  # Tienda — fullscreen detalle
        "S8":  1500,  # Agente — equipamiento (preview)
        "S9":  1500,  # Inventario discos
        "S10":  500,  # Modal upgrade — critico
        "S11": 5000,  # Desmontaje — ignorar
        "S12": 2000,  # Negativo — pollear seguido para cazar transiciones
        "S13": 1000,  # Selección set farmeo — pantalla intermedia
        "S14": 1000,  # Selección equipo pre-combate — idem
        "S15": 1000,  # Menú personajes — usuario pasa rápido a Atributos
        "S16": 1500,  # Detalle set disco
        "S17": 1000,  # Detalle disco PJ — clickea entre slots
        "S18": 1500,  # Perfil agente Atributos base
    }
    return cadence.get(state.code, 2000)
