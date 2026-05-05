"""
Hito 2.4.4 — Detector de estado de pantalla (S1-S12) · RF-04 §4.
Usa template matching (cv2.matchTemplate TM_CCOEFF_NORMED, threshold 0.85).
Templates en app/resources/templates/. Ver tools/build_templates.py para crearlos.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# Directorio de templates (relativo al package app/)
TEMPLATES_DIR = Path(__file__).parent.parent / "resources" / "templates"

# Threshold por defecto para template matching
MATCH_THRESHOLD = 0.85


@dataclass
class ScreenState:
    """Resultado de la clasificación del frame."""
    code: str          # S1-S12
    confidence: float  # 0-1 (del template match)
    template_name: str # nombre del template que disparó el match


# Descripción de cada estado y su plantilla de detección
_STATE_TEMPLATES: list[dict] = [
    # Cada entrada: code, template_file, descripcion
    {"code": "S2",  "template": "s2_resultado_desafio.png",        "desc": "Resultado del Desafio"},
    {"code": "S5",  "template": "s5_resultado_afinacion.png",       "desc": "Resultado de afinacion"},
    {"code": "S9",  "template": "s9_personalizacion_pistas.png",    "desc": "Inventario discos"},
    {"code": "S11", "template": "s11_desmontaje.png",               "desc": "Pantalla desmontaje"},
    {"code": "S10", "template": "s10_modal_upgrade.png",            "desc": "Modal upgrade"},
    {"code": "S8",  "template": "s8_agente_driver.png",             "desc": "Vista agente equipamiento"},
    {"code": "S3",  "template": "s3_modal_detalle_drop.png",        "desc": "Modal detalle drop"},
    {"code": "S6",  "template": "s6_tienda_detalle_panel.png",      "desc": "Tienda musica panel"},
    {"code": "S7",  "template": "s7_tienda_detalle_full.png",       "desc": "Tienda musica fullscreen"},
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
        Clasifica un frame. Devuelve S12 (negativo) si ningún template hace match.
        El orden de _STATE_TEMPLATES importa: estados más específicos primero.
        """
        if frame is None or frame.size == 0:
            return ScreenState("S12", 0.0, "")

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        best_code = "S12"
        best_conf = 0.0
        best_name = ""

        for entry in self._templates:
            tmpl = entry["img"]
            gray_tmpl = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if tmpl.ndim == 3 else tmpl

            # El template no puede ser más grande que el frame
            fh, fw = gray_frame.shape[:2]
            th, tw = gray_tmpl.shape[:2]
            if th > fh or tw > fw:
                continue

            result = cv2.matchTemplate(gray_frame, gray_tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)

            if max_val >= self._threshold and max_val > best_conf:
                best_conf = max_val
                best_code = entry["code"]
                best_name = entry["name"]

        return ScreenState(best_code, round(best_conf, 3), best_name)

    def classify_batch(self, frames: list[np.ndarray]) -> list[ScreenState]:
        return [self.classify(f) for f in frames]


def polling_cadence_ms(state: ScreenState) -> int:
    """
    Devuelve el intervalo de polling en ms según el estado actual (RF-04 §5).
    """
    cadence = {
        "S1":  4000,  # Patrulla — idle
        "S2":  1000,  # Resultado desafio — breve ventana
        "S3":   500,  # Modal detalle drop — critico
        "S4":  4000,  # Tienda — selector
        "S5":  1000,  # Tienda — resultado afinacion
        "S6":   500,  # Tienda — panel detalle
        "S7":   500,  # Tienda — fullscreen detalle
        "S8":  2000,  # Agente — equipamiento
        "S9":  2000,  # Inventario discos
        "S10":  500,  # Modal upgrade — critico
        "S11": 5000,  # Desmontaje — ignorar
        "S12": 4000,  # Negativo — idle
    }
    return cadence.get(state.code, 3000)
