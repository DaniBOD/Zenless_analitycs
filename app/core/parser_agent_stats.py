"""
Hito 2.8 — Parser de stats de agente: frame OCR → AgentStatsParsed.
Extrae los 11 atributos base del personaje desde la pantalla S18
(Perfil agente → pestaña Atributos base).

Usa PaddleOCR como backend para mejor precisión con texto pequeño
sobre fondo oscuro (configurable via defaults.toml).

Layout (confirmado por DaniBOD):
  Columna izquierda:  Nivel | PV | Defensa | Prob. CRIT | Tasa Anomalía | Tasa Perforación
  Columna derecha:    (vacio) | Ataque | Impacto | Daño CRIT | Maestría Anomalía | Recup. Energía
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.core.ocr_backend import OcrBackend

from app.core.capturer import crop_named_roi


_RE_NIVEL = re.compile(r"(\d{1,2})")
_RE_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_RE_NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)")


@dataclass
class AgentStatsParsed:
    """Resultado estructurado de la extracción de atributos base del agente."""
    nivel: int | None = None
    pv: int | None = None
    ataque: int | None = None
    defensa: int | None = None
    impacto: int | None = None
    prob_crit: float | None = None
    dano_crit: float | None = None
    tasa_anomalia: float | None = None
    maestria_anomalia: float | None = None
    tasa_perforacion: float | None = None
    recuperacion_energia: float | None = None
    confianza_global: float = 0.0
    notas: list[str] = field(default_factory=list)


def _parse_int(raw: str) -> int | None:
    m = _RE_NUMBER.search(raw)
    return int(m.group(1).replace(",", ".").split(".")[0]) if m else None


def _parse_float(raw: str) -> float | None:
    raw = raw.strip()
    m = _RE_PERCENT.search(raw)
    if m:
        return float(m.group(1))
    m = _RE_NUMBER.search(raw)
    if m:
        val = float(m.group(1).replace(",", "."))
        return val
    return None


def _ocr_stat(roi: np.ndarray, ocr: OcrBackend) -> tuple[str, float]:
    """Lee texto de una ROI y devuelve (raw_text, confidence)."""
    if roi is None or roi.size < 100:
        return "", 0.0
    try:
        return ocr.text(roi, psm=7)
    except Exception:
        return "", 0.0


def _ocr_number(roi: np.ndarray, ocr: OcrBackend) -> tuple[float, float]:
    """Lee valor numérico de una ROI."""
    if roi is None or roi.size < 100:
        return None, 0.0
    try:
        return ocr.number(roi)
    except Exception:
        return None, 0.0


def parse_agent_stats(
    frame: np.ndarray,
    ocr: OcrBackend,
) -> AgentStatsParsed:
    """
    Extrae los 11 atributos base desde la pantalla S18.

    Args:
        frame: screenshot completo (BGR numpy array)
        ocr: backend OCR (PaddleOCR recomendado)

    Returns:
        AgentStatsParsed con valores extraídos y confianza global.
    """
    section = "perfil_agente_atributos"
    notas: list[str] = []
    confianzas: list[float] = []

    # --- Nivel ---
    nombre_raw, c_nivel_n = _ocr_stat(crop_named_roi(frame, section, "nivel_nombre"), ocr)
    valor_raw, c_nivel_v = _ocr_stat(crop_named_roi(frame, section, "nivel_valor"), ocr)
    confianzas.extend([c_nivel_n, c_nivel_v])

    nivel_text = f"{nombre_raw} {valor_raw}".strip()
    nivel = _parse_int(nivel_text)
    if nivel is None:
        notas.append("nivel_no_detectado")

    # Helper: parsear stat con nombre + valor
    def _parse_stat(key: str) -> tuple[int | float | None, float, float]:
        n_raw, c_n = _ocr_stat(crop_named_roi(frame, section, f"{key}_nombre"), ocr)
        v_raw, c_v = _ocr_stat(crop_named_roi(frame, section, f"{key}_valor"), ocr)
        return f"{n_raw} {v_raw}".strip(), c_n, c_v

    # --- PV (entero) ---
    text, c1, c2 = _parse_stat("pv")
    confianzas.extend([c1, c2])
    pv = _parse_int(text)

    # --- Ataque (entero) ---
    text, c1, c2 = _parse_stat("ataque")
    confianzas.extend([c1, c2])
    ataque = _parse_int(text)

    # --- Defensa (entero) ---
    text, c1, c2 = _parse_stat("defensa")
    confianzas.extend([c1, c2])
    defensa = _parse_int(text)

    # --- Impacto (entero) ---
    text, c1, c2 = _parse_stat("impacto")
    confianzas.extend([c1, c2])
    impacto = _parse_int(text)

    # --- Probabilidad de CRIT (%) ---
    text, c1, c2 = _parse_stat("prob_crit")
    confianzas.extend([c1, c2])
    prob_crit = _parse_float(text)
    if prob_crit is not None and prob_crit > 1.0:
        prob_crit = prob_crit / 100.0

    # --- Daño CRIT (%) ---
    text, c1, c2 = _parse_stat("dano_crit")
    confianzas.extend([c1, c2])
    dano_crit = _parse_float(text)
    if dano_crit is not None and dano_crit > 1.0:
        dano_crit = dano_crit / 100.0

    # --- Tasa de Anomalía (entero) ---
    text, c1, c2 = _parse_stat("tasa_anomalia")
    confianzas.extend([c1, c2])
    tasa_anomalia = _parse_int(text)

    # --- Maestría de Anomalía (entero) ---
    text, c1, c2 = _parse_stat("maestria_anomalia")
    confianzas.extend([c1, c2])
    maestria_anomalia = _parse_int(text)

    # --- Tasa de Perforación (%) ---
    text, c1, c2 = _parse_stat("tasa_perforacion")
    confianzas.extend([c1, c2])
    tasa_perforacion = _parse_float(text)
    if tasa_perforacion is not None and tasa_perforacion > 1.0:
        tasa_perforacion = tasa_perforacion / 100.0

    # --- Recuperación de Energía (entero) ---
    text, c1, c2 = _parse_stat("recup_energia")
    confianzas.extend([c1, c2])
    recuperacion_energia = _parse_int(text)

    confianza_global = (sum(confianzas) / len(confianzas)) if confianzas else 0.0

    return AgentStatsParsed(
        nivel=nivel,
        pv=pv,
        ataque=ataque,
        defensa=defensa,
        impacto=impacto,
        prob_crit=prob_crit,
        dano_crit=dano_crit,
        tasa_anomalia=tasa_anomalia,
        maestria_anomalia=maestria_anomalia,
        tasa_perforacion=tasa_perforacion,
        recuperacion_energia=recuperacion_energia,
        confianza_global=round(confianza_global, 3),
        notas=notas,
    )
