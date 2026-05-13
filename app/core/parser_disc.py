"""
Hito 2.4.6 — Parser de disco: frame OCR → DiscParsed · RF-04 §7.2.
Convierte el texto extraído del modal de detalle en un struct validado.
Reutiliza stats_vocab para normalización canónica de nombres.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.core.ocr_backend import OcrBackend

from app.core.capturer import crop_named_roi
from app.core.stats_vocab import normalize_stat_name, parse_value, is_valid_main_for_slot

# Regex para parsear el título del modal: "Nombre del Set (N)"
_RE_TITULO = re.compile(r"^(.+?)\s*\(?(\d)\)?$")

# Regex para nivel: "Nivel 7/15" o "7/15" o simplemente "7"
_RE_NIVEL = re.compile(r"(\d{1,2})\s*/\s*15")

# Regex para substat con rolls: "Daño Crítico +2 18.2%" o "ATK 38"
_RE_SUBSTAT_LINE = re.compile(
    r"^(.+?)"           # nombre (grupo 1)
    r"(?:\s*\+(\d+))?"  # rolls opcionales "+N" (grupo 2)
    r"\s+"
    r"(\d+(?:\.\d+)?%?)$"  # valor (grupo 3)
)

# Regex para extraer valor numérico solo
_RE_NUMERO = re.compile(r"(\d+(?:\.\d+)?)(%?)")

# Mapeo de estado de pantalla a sección de ROIs en rois.toml
_STATE_TO_ROI_SECTION: dict[str, str] = {
    "S3":  "modal_detalle_s3",
    "S6":  "modal_detalle_s6",
    "S7":  "modal_detalle_s7",
    "S10": "modal_upgrade_s10",
    "S17": "modal_detalle_s17",
}


def roi_section_for_state(state_code: str) -> str:
    """Devuelve la sección de rois.toml a usar según el estado detectado."""
    return _STATE_TO_ROI_SECTION.get(state_code, "modal_detalle_s3")


@dataclass
class SubstatParsed:
    nombre_raw: str
    nombre_canon: str | None
    valor: float | None
    unidad: str | None       # 'flat' | '%'
    rolls: int
    confianza: float


@dataclass
class DiscParsed:
    """Resultado estructurado del OCR sobre el modal de detalle de disco."""
    set_name_raw: str
    set_name_canon: str | None
    slot: int
    main_stat_raw: str
    main_stat_canon: str | None
    main_valor: float | None
    main_unidad: str | None  # 'flat' | '%'
    nivel: int
    rareza: str              # 'S' | 'A' | 'B' | '?'
    subs: list[SubstatParsed] = field(default_factory=list)
    confianza_global: float = 0.0
    notas: list[str] = field(default_factory=list)


def _parse_titulo(raw: str) -> tuple[str, int]:
    """Devuelve (set_name_raw, slot). slot=0 si no se puede parsear."""
    m = _RE_TITULO.match(raw.strip())
    if not m:
        return raw.strip(), 0
    return m.group(1).strip(), int(m.group(2))


def _parse_nivel(raw: str) -> int:
    """Extrae el nivel de una cadena como 'Nivel 7/15'."""
    m = _RE_NIVEL.search(raw)
    if m:
        return int(m.group(1))
    # Fallback: primer entero suelto
    m2 = re.search(r"\d+", raw)
    return int(m2.group()) if m2 else 0


def _parse_substat_line(raw: str) -> tuple[str, int, float | None, str | None]:
    """
    Parsea una línea de substat.
    Devuelve (nombre, rolls, valor, unidad).
    """
    raw = raw.strip()
    m = _RE_SUBSTAT_LINE.match(raw)
    if m:
        nombre = m.group(1).strip()
        rolls = int(m.group(2)) if m.group(2) else 0
        val_str = m.group(3)
        if "%" in val_str:
            return nombre, rolls, float(val_str.replace("%", "")), "%"
        else:
            return nombre, rolls, float(val_str), "flat"

    # Fallback: separar por espacio tomando el último token como valor
    parts = raw.rsplit(None, 1)
    if len(parts) == 2:
        nombre = parts[0].strip()
        val_part = parts[1].strip()
        m2 = _RE_NUMERO.fullmatch(val_part)
        if m2:
            val = float(m2.group(1))
            unidad = "%" if m2.group(2) else "flat"
            return nombre, 0, val, unidad

    return raw, 0, None, None


def _detect_rareza(img: np.ndarray) -> str:
    """
    Detecta rareza por el color del borde del icono del disco.
    Dorado (HSV hue ~25-35) = S-rank. Morado (hue ~260-280) = A-rank.
    """
    try:
        import cv2
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # Samplear píxel central (el borde es el contorno exterior)
        h, w = hsv.shape[:2]
        # Tomar una franja del 20% superior donde está el borde del color
        stripe = hsv[:max(1, h // 5), :, 0]  # solo canal hue
        mean_hue = int(stripe.mean())
        if 15 <= mean_hue <= 40:
            return "S"
        elif 130 <= mean_hue <= 160:
            return "A"
        return "?"
    except Exception:
        return "?"


def parse_modal_detalle(
    frame: np.ndarray,
    ocr: "OcrBackend",
    set_repo=None,
    state_code: str = "S3",
) -> DiscParsed:
    """
    Extrae todos los campos del modal de detalle del disco.

    frame      : screenshot completo (BGR numpy array)
    ocr        : backend OCR configurado (Tesseract o Paddle)
    set_repo   : optional DiscSetRepo para validar el nombre del set
    state_code : estado detectado (S3 / S6 / S7 / S10). Define qué sección de
                 rois.toml usar — cada estado tiene layout distinto.
    """
    notas: list[str] = []
    confianzas: list[float] = []
    section = roi_section_for_state(state_code)

    # --- Título (set + slot) ---
    roi_titulo = crop_named_roi(frame, section, "titulo")
    titulo_raw, c_titulo = ocr.text(roi_titulo, psm=7)
    set_name_raw, slot = _parse_titulo(titulo_raw)
    confianzas.append(c_titulo)

    if slot == 0:
        notas.append("slot_no_detectado")

    # --- Nivel ---
    # En S10 (upgrade) NO hay un campo "Nivel X/15" textual; se infiere de exp_actual.
    nivel = 0
    if state_code == "S10":
        try:
            roi_exp = crop_named_roi(frame, section, "exp_actual")
            exp_raw, c_exp = ocr.text(roi_exp, psm=7)
            nivel = _parse_nivel(exp_raw) if "/" in exp_raw else (int(re.search(r"\d+", exp_raw).group()) if re.search(r"\d+", exp_raw) else 0)
            confianzas.append(c_exp)
        except Exception:
            pass
    else:
        roi_nivel = crop_named_roi(frame, section, "nivel")
        nivel_raw, c_nivel = ocr.text(roi_nivel, psm=7)
        nivel = _parse_nivel(nivel_raw)
        confianzas.append(c_nivel)

    # --- Rareza ---
    roi_rareza = crop_named_roi(frame, section, "rareza_borde")
    rareza = _detect_rareza(roi_rareza)

    # --- Main stat ---
    roi_main_n = crop_named_roi(frame, section, "main_stat_nombre")
    roi_main_v = crop_named_roi(frame, section, "main_stat_valor")
    main_raw, c_main_n = ocr.text(roi_main_n, psm=7)
    main_val_raw, c_main_v = ocr.number(roi_main_v)
    confianzas.extend([c_main_n, c_main_v])

    main_canon = normalize_stat_name(main_raw)
    main_unidad = "%" if (main_canon or main_raw or "").endswith("%") else "flat"
    if main_canon and slot >= 1:
        if not is_valid_main_for_slot(slot, main_canon):
            notas.append(f"main_invalido_slot_{slot}:{main_canon}")

    # --- Substats (hasta 4 en grilla 2×2) ---
    sub_keys = ["sub1", "sub2", "sub3", "sub4"]
    subs: list[SubstatParsed] = []

    for key in sub_keys:
        try:
            roi_sn = crop_named_roi(frame, section, f"{key}_nombre")
            roi_sv = crop_named_roi(frame, section, f"{key}_valor")
        except (KeyError, Exception):
            break

        sub_name_raw, c_sn = ocr.text(roi_sn, psm=7)
        sub_val_raw, c_sv = ocr.text(roi_sv, psm=7)
        confianzas.extend([c_sn, c_sv])

        if not sub_name_raw.strip():
            continue  # slot vacío en disco con <4 substats; seguir intentando los demás

        nombre, rolls, valor, unidad = _parse_substat_line(f"{sub_name_raw} {sub_val_raw}")
        canon = normalize_stat_name(nombre)

        if canon is None and nombre:
            notas.append(f"substat_desconocido:{nombre}")

        subs.append(SubstatParsed(
            nombre_raw=nombre,
            nombre_canon=canon,
            valor=valor,
            unidad=unidad,
            rolls=rolls,
            confianza=round((c_sn + c_sv) / 2, 3),
        ))

    # Validación: sum de rolls ≤ 5 por slot
    total_rolls = sum(s.rolls for s in subs)
    if total_rolls > 5:
        notas.append(f"rolls_excedidos:{total_rolls}")

    # --- Nombre canónico del set ---
    set_canon: str | None = None
    if set_repo is not None:
        try:
            sets = {s.nombre: s.id for s in set_repo.get_all()}
            for sn in sets:
                if sn.lower().strip() == set_name_raw.lower().strip():
                    set_canon = sn
                    break
        except Exception:
            pass
    if set_canon is None and set_name_raw:
        notas.append(f"set_desconocido:{set_name_raw}")

    confianza_global = (sum(confianzas) / len(confianzas)) if confianzas else 0.0
    if confianza_global < 0.7:
        notas.append("baja_confianza")

    return DiscParsed(
        set_name_raw=set_name_raw,
        set_name_canon=set_canon,
        slot=slot,
        main_stat_raw=main_raw,
        main_stat_canon=main_canon,
        main_valor=main_val_raw if main_val_raw else None,
        main_unidad=main_unidad,
        nivel=nivel,
        rareza=rareza,
        subs=subs,
        confianza_global=round(confianza_global, 3),
        notas=notas,
    )
