"""Parser del diálogo de sustitución de disco entre PJs (S23).

El juego muestra: *"{PJ_origen} equipa actualmente {Set} ({slot}). ¿Deseas sustituirlo?"* con
botones Cancelar/Confirmar. El diálogo da el **PJ que actualmente tiene el disco** (origen, que lo
va a PERDER), el **set** y el **slot**. NO da el PJ destino (el que lo equipa) — ese es el PJ cuya
pantalla de equipamiento se está viendo (el latch), y lo resuelve el monitor.

Este parser es PURO: OCRea la banda de texto y devuelve los campos CRUDOS (origen/set/slot).
La resolución a IDs (origen→agente, set→disc_set) la hace el monitor con sus repos, igual que
`parse_detail_disc` deja el set crudo para que `DiscSetRepo.resolve_id` lo absorba (RNF-02: el OCR
rompe tildes/espacios). Display de por sí; el write a DB lo decide el flujo de confirmación S17.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Banda del texto del diálogo (1 o 2 líneas, centrado). Misma región que `_S23_TEXT_ROI` del
# detector (medida sobre los 7 fixtures de 15_sustitucion_disco_confirmacion, 2559×1439).
_TEXT_ROI = (0.10, 0.44, 0.80, 0.12)   # x, y, w, h

# "{PJ} equipa actualmente {Set} ({slot})". PJ y Set pueden tener espacios (p.ej. "Nangong Yu",
# "Balada de la rama y la espada"), así que ambos son lazy. El "(" de apertura es OPCIONAL: el OCR
# a veces lo come (mismo patrón que el título del panel DETAIL de S22, QA 2026-07-18) — el ")" de
# cierre sí es obligatorio. `equipa actualmente` es el ancla que separa origen de set.
_RE_SUSTITUCION = re.compile(
    r"(?P<pj>.+?)\s+equipa\s+actualmente\s+(?P<set>.+?)\s*\(?\s*(?P<slot>[1-6])\s*\)",
    re.IGNORECASE,
)

# SEGUNDA pasada (rescate): el OCR confunde el dígito del slot con letras de forma parecida.
# Visto en vivo el 2026-07-20: "Salón huracanado (1)" salió como "(i)" → la regex estricta no
# matcheaba y el parser devolvía None SIN pending y SIN toast. Como el dominio está acotado
# (slot 1-6) y el contexto no es ambiguo, rescatarlo no es inventar (RNF-02).
# Acá el "(" es OBLIGATORIO (a diferencia de la pasada estricta): sin el paréntesis, una letra
# final del nombre del set podría colarse como slot. Solo corre si la estricta falla, así que
# el camino normal no cambia.
_SLOT_OCR_ALIAS = {"i": "1", "l": "1", "|": "1", "¡": "1", "z": "2", "s": "5", "b": "6"}
_RE_SUSTITUCION_LAX = re.compile(
    r"(?P<pj>.+?)\s+equipa\s+actualmente\s+(?P<set>.+?)\s*\(\s*(?P<slot>[il|¡zsb])\s*\)",
    re.IGNORECASE,
)


# El diálogo del W-ENGINE (S29) es la misma frase sin el sufijo de slot:
#     "Ben equipa actualmente Cilindro neumático de Bigger. ¿Deseas sustituirlo?"
# El nombre del arma termina en el punto que abre "¿Deseas sustituirlo?". Ese punto es el ancla
# de cierre: sin él el `.+?` lazy se comería la pregunta entera. Si el OCR se lo come, el parser
# se abstiene (RNF-02) — el ruteo a S29 ya ocurrió igual, esto solo pone nombres en el log.
#
# `e[qg]uipa` y no `equipa`: PaddleOCR lee **"eguipa"** en 2 de los 4 fixtures (Zhu Yuan, Billy
# Estelar). Es la confusión q↔g, del mismo tipo acotado que el alias de dígito del slot, y no
# aflojar el ancla dejaría el estado mudo la mitad de las veces.
#
# OJO — `_RE_SUSTITUCION` (la del disco) tiene el mismo `equipa` rígido. Hoy no falla porque los
# 7 fixtures de disco salen limpios con Paddle, pero el modo de fallo es el mismo y ese camino
# ESCRIBE la DB. No se toca acá a propósito: aflojar el parser del swap de discos pide su propio
# QA (RNF-01/02).
_RE_SUSTITUCION_ARMA = re.compile(
    r"(?P<pj>.+?)\s+e[qg]uipa\s+actualmente\s+(?P<arma>[^.]+?)\s*\.",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SustitucionParsed:
    """Campos crudos del diálogo de sustitución. `origin_raw`/`set_raw` traen ruido de OCR
    (tildes/espacios) → los resuelve el monitor con los resolvers fuzzy."""
    origin_raw: str
    set_raw: str
    slot: int
    conf: float


@dataclass(frozen=True)
class SustitucionArmaParsed:
    """Campos crudos del diálogo de sustitución de un W-Engine (S29). Sin slot: un arma no vive
    en un slot, y esa ausencia es justamente lo que separa este diálogo del de disco."""
    origin_raw: str
    weapon_raw: str
    conf: float


def _ocr_dialog_text(frame: np.ndarray, ocr) -> str:
    """Texto de la banda del diálogo, reconstruido de los tokens OCR ordenados por (y, x) y
    unidos con espacios. Robusto al backend: PaddleOCR quita los espacios internos y devuelve las
    líneas sueltas; unir por posición reconstruye 'equipa actualmente' en ambos backends."""
    from app.core.capturer import crop_roi
    try:
        crop = crop_roi(frame, _TEXT_ROI)
    except Exception:
        return ""
    if crop is None or getattr(crop, "size", 0) == 0:
        return ""
    try:
        rows = ocr.text_with_bboxes(crop)
    except Exception:
        log.debug("OCR del diálogo S23 falló", exc_info=True)
        return ""
    # Ordenar por fila (y1) y luego por x1 → orden de lectura; unir con espacios.
    rows = sorted(rows, key=lambda r: (r[2][1], r[2][0]))
    return " ".join(t for (t, _c, _b) in rows if t and t.strip()).strip()


def parse_sustitucion(frame: np.ndarray, ocr) -> SustitucionParsed | None:
    """Parsea el diálogo S23 → (origen_raw, set_raw, slot), o None si no matchea (RNF-02: no
    inventar). El slot se valida 1-6."""
    if frame is None or ocr is None or getattr(frame, "size", 0) == 0:
        return None
    text = _ocr_dialog_text(frame, ocr)
    if not text:
        return None
    m = _RE_SUSTITUCION.search(text)
    if m:
        slot_raw = m.group("slot")
    else:
        m = _RE_SUSTITUCION_LAX.search(text)
        if not m:
            return None
        slot_raw = _SLOT_OCR_ALIAS.get(m.group("slot").lower())
        if slot_raw is None:
            return None
        log.debug("S23: slot rescatado de %r → %r", m.group("slot"), slot_raw)
    slot = int(slot_raw)
    if not (1 <= slot <= 6):
        return None
    origin = m.group("pj").strip()
    set_raw = m.group("set").strip()
    if not origin or not set_raw:
        return None
    return SustitucionParsed(origin_raw=origin, set_raw=set_raw, slot=slot, conf=1.0)


def parse_sustitucion_arma(frame: np.ndarray, ocr) -> SustitucionArmaParsed | None:
    """Parsea el diálogo S29 (sustitución de W-Engine) → (origen_raw, arma_raw), o None.

    **Display-only.** A diferencia de `parse_sustitucion`, esto no arma ningún pending ni alimenta
    un write: hoy solo pone nombres en el log para que el estado sea verificable en el QA en vivo.
    Se abstiene si aparece un sufijo de slot — eso sería el diálogo de un disco mal ruteado, y
    leerlo como arma taparía el problema en vez de mostrarlo."""
    if frame is None or ocr is None or getattr(frame, "size", 0) == 0:
        return None
    text = _ocr_dialog_text(frame, ocr)
    if not text:
        return None
    if _RE_SUSTITUCION.search(text) or _RE_SUSTITUCION_LAX.search(text):
        return None
    m = _RE_SUSTITUCION_ARMA.search(text)
    if not m:
        return None
    origin = m.group("pj").strip()
    weapon = m.group("arma").strip()
    if not origin or not weapon:
        return None
    return SustitucionArmaParsed(origin_raw=origin, weapon_raw=weapon, conf=1.0)
