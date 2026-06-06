"""
Parser S17 — Disco equipado en vista "Personalización de pistas de disco".

Hito 2.x (2026-06-02). Reemplaza el path per-ROI de `parse_modal_detalle` para
S17 por un parseo ESPACIAL full-frame (bboxes de PaddleOCR), siguiendo el mismo
patrón que hizo robusto a S18: no depende de coordenadas mágicas por campo, sino
de la estructura visual real (headers de sección + 2 columnas nombre/valor).

Layout de S17 (verificado contra 8 capturas reales 2559×1439):

    Jazz caótico (1)            ← título: <set> (<slot>)   [puede ocupar 2 líneas]
    Nivel 15/15                 ← nivel del disco
    Atributo principal          ← HEADER
      PV               2200     ← main: nombre(izq) | valor(der), misma fila
    Atributos secundarios       ← HEADER
      Ataque           3 %      ← substat (0 rolls)
      Daño Crítico +1  9.6 %    ← substat (+N = rolls)
      Ataque +1        38
      Maestría de Anomalía +2  27
    Efecto de conjunto          ← HEADER
      Jazz caótico              ← set name (lectura limpia, 1 línea)
      2 pistas: ...             ← bonus 2pc (descripción)
      4 pistas: ...             ← bonus 4pc (descripción)

El panel de detalle vive en la franja horizontal x∈[0.30, 0.52] del frame; a la
izquierda está el grid de discos (x<0.28) y a la derecha el hexágono de equipados
(x>0.55) — ambos se filtran por X normalizada. Nombre vs valor se separan por el
umbral x≈0.42.

NOTA (alcance, 2026-06-02): el estado activo 2pc/4pc NO se lee acá (S17 muestra la
*descripción* de ambos tiers, no cuál está activo). Eso se deriva contando discos
equipados del mismo set → pertenece a S8. Acá: set, slot, main, 4 substats (rolls),
nivel.
"""
from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.core.ocr_backend import OcrBackend

from app.core.parser_disc import DiscParsed, SubstatParsed, _detect_rareza
from app.core.stats_vocab import normalize_stat_name, is_valid_main_for_slot

# Franja horizontal (x normalizada) del panel de detalle central.
_BAND_X_MIN = 0.30
_BAND_X_MAX = 0.52
# Umbral que separa columna de NOMBRE (izq) de columna de VALOR (der).
_COL_SPLIT = 0.42
# Tolerancia vertical (px) para emparejar nombre↔valor de la misma fila.
_ROW_DY = 40

_RE_TITULO_SLOT = re.compile(r"^(.*?)\s*\(\s*(\d)\s*\)\s*$")
_RE_NIVEL = re.compile(r"nivel\s*(\d{1,2})\s*/\s*15")
_RE_ROLLS = re.compile(r"^(.*?)\s*\+\s*(\d+)\s*$")
_RE_VALOR = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(%?)")
_RE_PISTAS = re.compile(r"^\d+\s*pistas?\s*:", re.IGNORECASE)


def _strip(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    )


def _norm_key(s: str) -> str:
    """Normaliza para matchear headers: sin acentos, minúscula, solo alfanumérico."""
    return re.sub(r"[^a-z0-9]+", "", _strip(s).lower())


def _parse_valor(raw: str) -> tuple[float | None, str | None]:
    """'3 %'→(3.0,'%') · '2200'→(2200.0,'flat') · '9.6 %'→(9.6,'%')."""
    if not raw:
        return None, None
    m = _RE_VALOR.search(raw)
    if not m:
        return None, None
    val = float(m.group(1).replace(",", "."))
    unidad = "%" if m.group(2) == "%" else "flat"
    return val, unidad


def _split_rolls(nombre_raw: str) -> tuple[str, int]:
    """'Ataque +3'→('Ataque',3) · 'PV+1'→('PV',1) · 'Ataque'→('Ataque',0)."""
    m = _RE_ROLLS.match(nombre_raw.strip())
    if m:
        return m.group(1).strip(), int(m.group(2))
    return nombre_raw.strip(), 0


def _canon_with_unit(nombre: str, unidad: str | None) -> str | None:
    """
    Canoniza el nombre del stat teniendo en cuenta la unidad del valor.

    PV/Ataque/Defensa son ambiguos por nombre: el mismo label "Ataque" es ATK
    (flat) o ATK% según la unidad del valor ("38" vs "3 %"). El resto de stats
    ya codifican su unidad en el nombre canónico (Daño Crítico siempre %, etc.).
    """
    canon = normalize_stat_name(nombre)
    if canon in ("HP", "ATK", "DEF") and unidad == "%":
        return canon + "%"
    return canon


class _Line:
    __slots__ = ("txt", "conf", "x1", "y1", "x2", "y2", "xn")

    def __init__(self, txt, conf, bb, W):
        self.txt = txt
        self.conf = conf
        self.x1, self.y1, self.x2, self.y2 = bb
        self.xn = self.x1 / W if W else 0.0


def _parse_s17_from_lines(
    lines: list[tuple[str, float, tuple[int, int, int, int]]],
    W: int,
    H: int,
) -> DiscParsed:
    """
    Core testeable: parsea S17 a partir de las líneas OCR con bbox.

    `lines` = [(texto, confianza, (x1,y1,x2,y2)), ...] (salida de
    `OcrBackend.text_with_bboxes`). Separado del OCR para testear con
    fixtures cacheadas sin re-correr Paddle.
    """
    notas: list[str] = []
    L = [_Line(t, c, bb, W) for (t, c, bb) in lines]
    # Solo el panel de detalle central (excluye grid izq + hexágono der).
    detail = [ln for ln in L if _BAND_X_MIN <= ln.xn <= _BAND_X_MAX]
    detail.sort(key=lambda ln: (ln.y1, ln.x1))

    # --- Headers de sección (delimitadores Y) ---
    y_main = y_subs = y_effect = None
    header_ys: set[int] = set()
    for ln in detail:
        k = _norm_key(ln.txt)
        if y_main is None and k.startswith("atributoprincipal"):
            y_main = ln.y1; header_ys.add(ln.y1)
        elif y_subs is None and k.startswith("atributossecundario"):
            y_subs = ln.y1; header_ys.add(ln.y1)
        elif y_effect is None and k.startswith("efectodeconjunto"):
            y_effect = ln.y1; header_ys.add(ln.y1)

    if y_main is None or y_subs is None:
        notas.append("s17_headers_no_detectados")

    _ymain = y_main if y_main is not None else 10**9
    _ysubs = y_subs if y_subs is not None else 10**9
    _yeffect = y_effect if y_effect is not None else 10**9

    confs: list[float] = []

    # --- Nivel: 'Nivel N/15' (el '/15' lo distingue de los 'Nivel 15' del grid) ---
    nivel = 0
    for ln in detail:
        m = _RE_NIVEL.search(_strip(ln.txt).lower())
        if m:
            nivel = int(m.group(1)); confs.append(ln.conf); break

    # --- Título (set + slot): líneas arriba de 'Atributo principal', excluido nivel ---
    titulo_lines = [
        ln for ln in detail
        if ln.y1 < _ymain
        and not _RE_NIVEL.search(_strip(ln.txt).lower())
        and ln.y1 not in header_ys
    ]
    titulo_raw = " ".join(ln.txt for ln in sorted(titulo_lines, key=lambda l: l.y1)).strip()
    for ln in titulo_lines:
        confs.append(ln.conf)
    m = _RE_TITULO_SLOT.match(titulo_raw)
    if m:
        set_name_titulo = m.group(1).strip()
        slot = int(m.group(2))
    else:
        set_name_titulo = titulo_raw
        slot = 0
        notas.append("slot_no_detectado")

    # --- Main stat: única fila nombre/valor entre 'Atributo principal' y 'Atributos secundarios' ---
    main_region = [ln for ln in detail if _ymain < ln.y1 < _ysubs and ln.y1 not in header_ys]
    main_names = [ln for ln in main_region if ln.xn < _COL_SPLIT]
    main_vals = [ln for ln in main_region if ln.xn >= _COL_SPLIT]
    main_raw = main_names[0].txt.strip() if main_names else ""
    main_val_raw = main_vals[0].txt if main_vals else ""
    if main_names:
        confs.append(main_names[0].conf)
    if main_vals:
        confs.append(main_vals[0].conf)
    main_valor, main_unidad = _parse_valor(main_val_raw)
    main_canon = _canon_with_unit(main_raw, main_unidad)
    if main_canon and slot >= 1 and not is_valid_main_for_slot(slot, main_canon):
        notas.append(f"main_invalido_slot_{slot}:{main_canon}")

    # --- Substats: pares nombre(izq)/valor(der) entre 'Atributos secundarios' y 'Efecto de conjunto' ---
    sub_region = [ln for ln in detail if _ysubs < ln.y1 < _yeffect and ln.y1 not in header_ys]
    sub_names = sorted([ln for ln in sub_region if ln.xn < _COL_SPLIT], key=lambda l: l.y1)
    sub_vals = sorted([ln for ln in sub_region if ln.xn >= _COL_SPLIT], key=lambda l: l.y1)
    subs: list[SubstatParsed] = []
    used_val: set[int] = set()
    for nl in sub_names:
        # emparejar con el valor de la fila más cercana en Y (no usado aún)
        best_i, best_dy = None, _ROW_DY + 1
        for i, vl in enumerate(sub_vals):
            if i in used_val:
                continue
            dy = abs(vl.y1 - nl.y1)
            if dy < best_dy:
                best_dy, best_i = dy, i
        nombre, rolls = _split_rolls(nl.txt)
        valor = unidad = None
        conf_v = 0.0
        if best_i is not None:
            used_val.add(best_i)
            valor, unidad = _parse_valor(sub_vals[best_i].txt)
            conf_v = sub_vals[best_i].conf
        canon = _canon_with_unit(nombre, unidad)
        if canon is None and nombre:
            notas.append(f"substat_desconocido:{nombre}")
        confs.extend([nl.conf, conf_v])
        subs.append(SubstatParsed(
            nombre_raw=nombre, nombre_canon=canon, valor=valor,
            unidad=unidad, rolls=rolls, confianza=round((nl.conf + conf_v) / 2, 3),
        ))

    total_rolls = sum(s.rolls for s in subs)
    if total_rolls > 5:
        notas.append(f"rolls_excedidos:{total_rolls}")

    # --- Set name desde 'Efecto de conjunto' (1ª línea no-"N pistas:"), lectura más limpia ---
    set_name_efecto = ""
    if y_effect is not None:
        effect_lines = sorted(
            [ln for ln in detail if ln.y1 > _yeffect and ln.y1 not in header_ys],
            key=lambda l: l.y1,
        )
        for ln in effect_lines:
            if not _RE_PISTAS.match(ln.txt.strip()):
                set_name_efecto = ln.txt.strip()
                break

    # Preferir el nombre del bloque de efecto (1 línea limpia) sobre el título (puede venir partido)
    set_name_raw = set_name_efecto or set_name_titulo

    confianza_global = (sum(confs) / len(confs)) if confs else 0.0
    if confianza_global < 0.7:
        notas.append("baja_confianza")

    return DiscParsed(
        set_name_raw=set_name_raw,
        set_name_canon=None,   # se canoniza contra disc_sets en el caller/sync
        slot=slot,
        main_stat_raw=main_raw,
        main_stat_canon=main_canon,
        main_valor=main_valor,
        main_unidad=main_unidad,
        nivel=nivel,
        rareza="?",
        subs=subs,
        confianza_global=round(confianza_global, 3),
        notas=notas,
    )


# --- Avatar del PJ asignado (a la derecha de "Nivel X/15") -------------------
# Localización verificada sobre crops reales 2557×1439 (2026-06-06): el avatar
# circular está en X casi fijo (centro xn≈0.503) y su Y SIGUE a la barra de nivel
# (que se desplaza según el set ocupe 1 o 2 líneas). Anclamos cx a xn fijo y cy al
# centro de la línea de nivel del panel de detalle; el lado ≈ 1.05× alto del pill.
_S17_AVATAR_CX_NORM = 0.503
_S17_AVATAR_HALF_FACTOR = 1.05
# Fracción mínima de píxeles saturados dentro del círculo para considerar que HAY
# avatar (el fondo rayado del panel es casi gris → baja saturación). Calibrado
# conservador: discos equipados reales miden >> este piso; un disco sin equipar
# (sin avatar) cae por debajo. Ante duda, el caller igual abstiene por la guarda.
_S17_AVATAR_MIN_SAT_FRAC = 0.06


def _detail_level_bbox(lines, W) -> tuple[int, int, int, int] | None:
    """Bbox de la línea 'Nivel N/15' del panel de detalle (xn en [0.30, 0.52])."""
    for (t, _c, bb) in lines:
        x1, y1, x2, y2 = bb
        if "/15" in t and 0.30 <= (x1 / W if W else 0) <= 0.52:
            return (x1, y1, x2, y2)
    return None


def crop_s17_assigned_avatar(frame, lines, W, H):
    """
    Recorta el avatar circular del PJ asignado (a la derecha de 'Nivel X/15').
    Devuelve el crop BGR cuadrado o None si no se localiza la barra de nivel o si
    no hay avatar (disco sin equipar — baja saturación dentro del círculo).
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    bb = _detail_level_bbox(lines, W)
    if bb is None:
        return None
    x1, y1, x2, y2 = bb
    hpill = max(1, y2 - y1)
    cy = (y1 + y2) // 2
    cx = int(_S17_AVATAR_CX_NORM * W)
    half = int(_S17_AVATAR_HALF_FACTOR * hpill)
    if half < 8:
        return None
    y0, y1c = max(0, cy - half), min(H, cy + half)
    x0, x1c = max(0, cx - half), min(W, cx + half)
    face = frame[y0:y1c, x0:x1c]
    if face.size == 0:
        return None
    # Detección de ausencia (disco sin equipar): círculo casi sin píxeles saturados.
    if not _has_avatar_content(face):
        return None
    return face


def _has_avatar_content(face) -> bool:
    """True si dentro del círculo inscripto hay suficiente contenido saturado."""
    try:
        import cv2
        h, w = face.shape[:2]
        side = min(h, w)
        sq = face[:side, :side]
        yy, xx = np.ogrid[:side, :side]
        mask = ((xx - side / 2) ** 2 + (yy - side / 2) ** 2) <= (side / 2 - 1) ** 2
        hsv = cv2.cvtColor(sq, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1][mask]
        if sat.size == 0:
            return False
        frac = float((sat > 60).mean())
        return frac >= _S17_AVATAR_MIN_SAT_FRAC
    except Exception:
        return True  # ante error, no bloquear (la guarda decide)


def parse_disc_s17(frame: np.ndarray, ocr: "OcrBackend") -> DiscParsed:
    """
    Extrae el disco equipado de una pantalla S17 (full-frame, espacial).

    Devuelve un `DiscParsed`. La rareza se intenta por color del borde del
    icono (best-effort); el resto sale del OCR espacial.
    """
    parsed, _face = parse_disc_s17_full(frame, ocr)
    return parsed


def parse_disc_s17_full(frame: np.ndarray, ocr: "OcrBackend"):
    """
    Como `parse_disc_s17` pero corre OCR UNA vez y devuelve también el crop del
    avatar del PJ asignado: `(DiscParsed, face | None)`. El monitor usa esto para
    no re-OCRizar (presupuesto de latencia RF-06 < 500 ms).
    """
    lines = ocr.text_with_bboxes(frame)
    H, W = frame.shape[:2]
    parsed = _parse_s17_from_lines(lines, W, H)
    # Rareza best-effort por color del icono del disco (no bloquea si falla).
    try:
        from app.core.capturer import crop_named_roi
        roi = crop_named_roi(frame, "modal_detalle_s17", "rareza_borde")
        rar = _detect_rareza(roi)
        if rar != "?":
            parsed.rareza = rar
    except Exception:
        pass
    face = crop_s17_assigned_avatar(frame, lines, W, H)
    return parsed, face
