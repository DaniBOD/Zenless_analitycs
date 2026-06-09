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
# Badge de rolls huérfano: el juego lo parte a su propia línea cuando el nombre
# del substat es largo (p.ej. "Probabilidad de Crítico" / "+1"). En la columna de
# NOMBRE no hay otros tokens de un solo dígito, así que es seguro detectarlo así.
_RE_ROLLS_FRAGMENT = re.compile(r"^\+?\s*([0-5])$")
_RE_VALOR = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(%?)")
_RE_PISTAS = re.compile(r"^\d+\s*pistas?\s*:", re.IGNORECASE)
_RE_PISTAS_TIER = re.compile(r"^\s*(\d)\s*pistas?\s*:", re.IGNORECASE)
# Brillo (p95 del prefijo "N pistas:") por encima del cual el tier está ACTIVO
# (texto blanco). Medido sobre 8 capturas reales: activo=255, inactivo=142 →
# umbral 190 con margen enorme. El prefijo nunca lleva keywords coloreadas.
_ACTIVE_TIER_BRIGHT_MIN = 190.0

# --- Fase 2 (2026-06-07): OCR sobre CROP nativo del panel (latencia) ---------
# El crop del panel de detalle (lado mayor < 960px = det_limit_side_len) evita el
# downscale del detector DBNet → el texto chico se lee en la 1ª pasada y el OCR
# procesa ~0.85 MP en vez de 3.7 MP (~1.5× más rápido). Calibrado sobre capturas
# reales (Paso 0): abarca título (incl. 2 líneas), nivel, main, 4 substats y la
# línea "4 pistas:" (la usa detect_active_set_tier, hasta y≈0.73).
_S17_DETAIL_PANEL_ROI = (0.27, 0.105, 0.36, 0.645)  # x0.27-0.63 (922px), y0.105-0.75 (928px)
# Franja fina del título (1-2 líneas) para el rescate del slot: el "(N)" se lee
# fiable en una sola línea aunque el crop del panel completo pierda el dígito fino.
_S17_TITLE_STRIP_ROI = (0.29, 0.10, 0.34, 0.085)
_RE_SLOT_PAREN = re.compile(r"\(\s*([1-6])\s*\)")
_RE_INLINE_ROLL = re.compile(r"\+\s*([0-5])\b")


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


def _coalesce_rolls_fragments(name_lines: list["_Line"]) -> list["_Line"]:
    """
    Une badges de rolls '+N' huérfanos con la línea de nombre inmediatamente
    superior en la misma columna.

    Cuando el nombre de un substat es largo (p.ej. "Probabilidad de Crítico"), el
    juego parte el badge "+N" a una línea aparte debajo. PaddleOCR lo devuelve como
    una línea suelta en la columna de nombre; sin fusionarlo, el nombre se leería
    con rolls=0 y el "+N" quedaría como substat fantasma. `name_lines` debe venir
    ordenado por y1 (la línea de nombre antecede a su badge).
    """
    out: list["_Line"] = []
    for ln in name_lines:
        m = _RE_ROLLS_FRAGMENT.match(_strip(ln.txt).strip())
        if m and out:
            parent = out[-1]
            hp = max(1, parent.y2 - parent.y1)
            # solo fusionar si es la línea inmediatamente inferior (badge envuelto)
            if 0 < (ln.y1 - parent.y1) <= 2.0 * hp:
                parent.txt = f"{parent.txt.strip()} +{m.group(1)}"
                continue
        out.append(ln)
    return out


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


# --- Rescate de badge de rolls envuelto -------------------------------------
# Cuando el nombre del substat es largo (p.ej. "Probabilidad de Crítico"), el
# juego parte el badge "+N" (naranja) a la 2ª línea visual. PaddleOCR downscalea
# el frame a 960px y NO detecta ese badge chico → el substat queda con rolls=0.
# Recuperamos N re-OCRizando un crop tight de la banda inmediatamente debajo del
# nombre, con gate por color naranja (los nombres normales son blancos → no
# disparan re-OCR de más).
_BADGE_ORANGE_H = (5, 25)       # rango Hue (OpenCV 0-180) del naranja del badge
_BADGE_ORANGE_SMIN = 120
_BADGE_ORANGE_VMIN = 120
_BADGE_ORANGE_FRAC_MIN = 0.015  # fracción mínima de píxeles naranja (medido ~0.043)
_RE_BADGE_DIGIT = re.compile(r"\+?\s*([0-5])")


def _orange_badge_frac(band) -> float:
    """Fracción de píxeles del naranja del badge "+N" en un recorte BGR (gate)."""
    try:
        import cv2
        if band is None or getattr(band, "size", 0) == 0:
            return 0.0
        hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        orange = (
            (hsv[:, :, 0] >= _BADGE_ORANGE_H[0]) & (hsv[:, :, 0] <= _BADGE_ORANGE_H[1])
            & (hsv[:, :, 1] >= _BADGE_ORANGE_SMIN) & (hsv[:, :, 2] >= _BADGE_ORANGE_VMIN)
        )
        return float(orange.mean())
    except Exception:
        return 0.0


def _ocr_roll_digit(band, ocr, regex) -> int | None:
    """Upscalea x3 y busca un dígito de roll (0-5) en el texto re-OCRizado."""
    try:
        import cv2
        up = cv2.resize(band, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        txt = " ".join(t for t, _c, _bb in ocr.text_with_bboxes(up))
        m = regex.search(txt)
        if m:
            return int(m.group(1))
    except Exception:
        return None
    return None


def _rescue_roll(frame, name_line: "_Line", ocr, W: int, H: int) -> int | None:
    """
    Recupera el badge de rolls "+N" (naranja, chico) que PaddleOCR dropea, en sus
    dos disposiciones:
      - INLINE: a la derecha del nombre, en la misma fila (re-OCR de la fila entera
        del nombre hasta antes de la columna de valor; tolera que el crop nativo
        funda/mal-segmente el "+N" dentro del bbox del nombre — caso Fase 2).
      - ENVUELTO: 2ª línea bajo el nombre cuando es largo (banda generosa, tolera
        ±px del bbox del nombre).
    Gate por color naranja → solo re-OCRiza cuando hay badge presente (no penaliza
    substats legítimos con 0 rolls). Reemplaza al viejo `_rescue_wrapped_roll`
    (que solo miraba abajo y era frágil a px).
    """
    if frame is None or ocr is None or getattr(frame, "size", 0) == 0:
        return None
    try:
        hp = max(1, name_line.y2 - name_line.y1)
        # 1) INLINE — fila completa del nombre, recortada antes de la col. de valor.
        iy0 = max(0, name_line.y1 - int(0.25 * hp))
        iy1 = min(H, name_line.y2 + int(0.25 * hp))
        ix1 = min(W, int((_COL_SPLIT + 0.035) * W))  # ~0.455·W, antes del valor
        inline = frame[iy0:iy1, name_line.x1:ix1]
        if _orange_badge_frac(inline) >= _BADGE_ORANGE_FRAC_MIN:
            d = _ocr_roll_digit(inline, ocr, _RE_INLINE_ROLL)
            if d is not None:
                return d
        # 2) ENVUELTO — badge en la 2ª línea visual, alineado a la izquierda.
        by0 = max(0, name_line.y2 - int(0.15 * hp))
        by1 = min(H, name_line.y2 + int(1.7 * hp))
        bx1 = min(W, name_line.x1 + int(3.6 * hp))
        wrapped = frame[by0:by1, name_line.x1:bx1]
        if _orange_badge_frac(wrapped) >= _BADGE_ORANGE_FRAC_MIN:
            d = _ocr_roll_digit(wrapped, ocr, _RE_BADGE_DIGIT)
            if d is not None:
                return d
    except Exception:
        return None
    return None


def _rescue_slot_from_title(frame, ocr, W: int, H: int) -> int:
    """
    Recupera el slot (1-6) re-OCRizando una franja fina del título cuando el parse
    del crop pierde el "(N)" (el dígito fino entre paréntesis se cae a veces a
    resolución nativa). Al ser 1-2 líneas, la franja lee el "(N)" de forma fiable.
    Devuelve 0 si no se localiza.
    """
    if frame is None or ocr is None or getattr(frame, "size", 0) == 0:
        return 0
    try:
        from app.core.capturer import crop_roi
        strip = crop_roi(frame, _S17_TITLE_STRIP_ROI)
        if strip is None or getattr(strip, "size", 0) == 0:
            return 0
        for t, _c, _bb in ocr.text_with_bboxes(strip):
            m = _RE_SLOT_PAREN.search(t)
            if m:
                return int(m.group(1))
    except Exception:
        return 0
    return 0


def _rescue_missing_value(frame, name_line: "_Line", ocr, W: int, H: int):
    """
    Re-OCRiza el valor de un substat cuando PaddleOCR lo dropeó (dígito chico a baja
    resolución; mismo problema que el badge "+N"). Crop de la columna de valor a la
    derecha del nombre, upscale x3, re-OCR. Devuelve (valor, unidad) o None.
    """
    if frame is None or ocr is None or getattr(frame, "size", 0) == 0:
        return None
    try:
        import cv2
        hp = max(1, name_line.y2 - name_line.y1)
        vx0 = min(W - 1, name_line.x2 + 8)          # a la derecha del nombre
        vx1 = min(W, int(_BAND_X_MAX * W) + int(0.012 * W))
        vy0 = max(0, name_line.y1 - 4)
        vy1 = min(H, name_line.y1 + int(1.1 * hp) + 4)  # alineado a la 1ª línea
        crop = frame[vy0:vy1, vx0:vx1]
        if crop.size == 0 or vx1 - vx0 < 8:
            return None
        up = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        for t, _c, _bb in ocr.text_with_bboxes(up):
            v, u = _parse_valor(t)
            if v is not None:
                return v, u
    except Exception:
        return None
    return None


def _parse_s17_from_lines(
    lines: list[tuple[str, float, tuple[int, int, int, int]]],
    W: int,
    H: int,
    frame=None,
    ocr=None,
) -> DiscParsed:
    """
    Core testeable: parsea S17 a partir de las líneas OCR con bbox.

    `lines` = [(texto, confianza, (x1,y1,x2,y2)), ...] (salida de
    `OcrBackend.text_with_bboxes`). Separado del OCR para testear con
    fixtures cacheadas sin re-correr Paddle.

    `frame`/`ocr` opcionales: si se pasan, se intenta rescatar los badges de rolls
    "+N" envueltos a 2ª línea que PaddleOCR no detecta (re-OCR de crop tight con
    gate naranja). Los tests del core puro los omiten (rolls quedan como se leyeron).
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
        # Prefijos TOLERANTES: el OCR sobre crop nativo a veces trunca/funde el
        # header (p.ej. "Atributo principal" → "Atributoprincipa"). Se usa un
        # prefijo más corto pero todavía distintivo (sin colisión entre los tres).
        if y_main is None and k.startswith("atributoprincip"):
            y_main = ln.y1; header_ys.add(ln.y1)
        elif y_subs is None and k.startswith("atributossecundari"):
            y_subs = ln.y1; header_ys.add(ln.y1)
        elif y_effect is None and k.startswith("efectodeconjunt"):
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

    # Rescate de slot (Fase 2): el crop nativo a veces pierde el "(N)" del título
    # (dígito fino entre paréntesis). Re-OCR de una franja fina lo recupera.
    if slot == 0 and frame is not None and ocr is not None:
        rs = _rescue_slot_from_title(frame, ocr, W, H)
        if rs:
            slot = rs
            if "slot_no_detectado" in notas:
                notas.remove("slot_no_detectado")

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
    sub_names = _coalesce_rolls_fragments(
        sorted([ln for ln in sub_region if ln.xn < _COL_SPLIT], key=lambda l: l.y1)
    )
    # Descartar fragmentos SIN letras (p.ej. '12', '+', un valor/badge que cayó en
    # la columna de nombre): nunca son nombres de stat → si no se filtran generan un
    # substat fantasma con canon=None (regresión QA Burnice Slot6). Los badges "+N"
    # legítimos ya se fusionaron arriba en _coalesce_rolls_fragments.
    sub_names = [ln for ln in sub_names if any(c.isalpha() for c in ln.txt)]
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
        if rolls == 0:
            # El badge "+N" pudo caerse (inline mal segmentado o envuelto a 2ª
            # línea) y Paddle no detectarlo. Rescatar por color+re-OCR (no-op sin
            # frame/ocr). Gate naranja → solo re-OCRiza si hay badge real.
            rescued = _rescue_roll(frame, nl, ocr, W, H)
            if rescued is not None:
                rolls = rescued
        valor = unidad = None
        conf_v = 0.0
        if best_i is not None:
            used_val.add(best_i)
            valor, unidad = _parse_valor(sub_vals[best_i].txt)
            conf_v = sub_vals[best_i].conf
        if valor is None:
            # PaddleOCR dropeó el valor (dígito chico). Rescate por re-OCR upscaleado.
            rv = _rescue_missing_value(frame, nl, ocr, W, H)
            if rv is not None:
                valor, unidad = rv
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
# Fracción mínima de píxeles de BORDE (Canny) dentro del círculo para considerar
# que HAY avatar. Se usa densidad de bordes, NO saturación: en la grilla de
# visualización el arte de fondo borroso puede estar MÁS saturado que un avatar
# (medido 2026-06-07: fondo sin-avatar sat 0.38 > avatar 0.31), pero es LISO → casi
# sin bordes (edgefrac 0.000), mientras que el avatar (anillo + cara) tiene bordes
# nítidos (equipados reales 0.10–0.14). Umbral 0.04 separa con margen enorme.
_S17_AVATAR_EDGE_FRAC_MIN = 0.04


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
    """
    True si dentro del círculo inscripto hay un avatar real, por DENSIDAD DE BORDES
    (Canny), no por saturación. El avatar (anillo circular + cara) tiene bordes
    nítidos; el fondo rayado/arte borroso de un disco sin equipar es liso → casi
    sin bordes. Robusto al caso de la grilla de visualización donde el fondo está
    más saturado que un avatar (2026-06-07).
    """
    try:
        import cv2
        h, w = face.shape[:2]
        side = min(h, w)
        if side < 8:
            return False
        sq = face[:side, :side]
        yy, xx = np.ogrid[:side, :side]
        mask = ((xx - side / 2) ** 2 + (yy - side / 2) ** 2) <= (side / 2 - 1) ** 2
        g = cv2.cvtColor(sq, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(g, 60, 160)
        frac = float((edges[mask] > 0).mean())
        return frac >= _S17_AVATAR_EDGE_FRAC_MIN
    except Exception:
        return True  # ante error, no bloquear (la guarda decide)


def detect_active_set_tier(frame, lines, W, H) -> int | None:
    """
    Tier de conjunto ACTIVO leyendo el color del texto en "Efecto de conjunto":
    el 2pc siempre está blanco (activo); el 4pc está blanco si hay 4+ piezas o
    gris si solo hay 2-3. Devuelve 4 si el 4pc está activo, 2 si solo el 2pc,
    None si no se localiza la línea "4 pistas:".
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    tier4_bb = None
    for (t, _c, bb) in lines:
        m = _RE_PISTAS_TIER.match(_strip(t).strip())
        x1, _y1, _x2, _y2 = bb
        xn = x1 / W if W else 0.0
        if m and 0.30 <= xn <= 0.52 and m.group(1) == "4":
            tier4_bb = bb
            break
    if tier4_bb is None:
        return None
    try:
        import cv2
        x1, y1, x2, y2 = tier4_bb
        xp = x1 + int((x2 - x1) * 0.35)  # solo el prefijo "4 pistas:"
        crop = frame[y1:y2, x1:xp]
        if crop.size == 0:
            return None
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        p95 = float(np.percentile(g, 95))
        return 4 if p95 > _ACTIVE_TIER_BRIGHT_MIN else 2
    except Exception:
        return None


def parse_disc_s17(frame: np.ndarray, ocr: "OcrBackend") -> DiscParsed:
    """
    Extrae el disco equipado de una pantalla S17 (full-frame, espacial).

    Devuelve un `DiscParsed`. La rareza se intenta por color del borde del
    icono (best-effort); el resto sale del OCR espacial.
    """
    parsed, _face = parse_disc_s17_full(frame, ocr)
    return parsed


def _ocr_detail_lines(frame: np.ndarray, ocr: "OcrBackend"):
    """
    OCR del panel de detalle S17 sobre un CROP nativo (Fase 2) y RE-OFFSET de cada
    bbox a coordenadas de frame completo. El crop (lado mayor < 960px) evita el
    downscale del detector → texto chico legible en 1ª pasada y OCR más rápido; el
    offset deja las líneas como si vinieran del frame entero, así el parser espacial
    (filtro de banda, headers, avatar, tier) NO cambia. Fallback al frame completo
    si el crop falla o no devuelve líneas.
    """
    from app.core.capturer import crop_roi
    H, W = frame.shape[:2]
    x0 = int(_S17_DETAIL_PANEL_ROI[0] * W)
    y0 = int(_S17_DETAIL_PANEL_ROI[1] * H)
    crop = crop_roi(frame, _S17_DETAIL_PANEL_ROI)
    if crop is None or getattr(crop, "size", 0) == 0:
        return ocr.text_with_bboxes(frame)
    raw = ocr.text_with_bboxes(crop)
    if not raw:
        return ocr.text_with_bboxes(frame)
    return [(t, c, (b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0)) for (t, c, b) in raw]


def parse_disc_s17_full(frame: np.ndarray, ocr: "OcrBackend"):
    """
    Como `parse_disc_s17` pero corre OCR UNA vez y devuelve también el crop del
    avatar del PJ asignado: `(DiscParsed, face | None)`. El monitor usa esto para
    no re-OCRizar (presupuesto de latencia RF-06 < 500 ms).
    """
    lines = _ocr_detail_lines(frame, ocr)
    H, W = frame.shape[:2]
    parsed = _parse_s17_from_lines(lines, W, H, frame=frame, ocr=ocr)
    # Rareza best-effort por color del icono del disco (no bloquea si falla).
    try:
        from app.core.capturer import crop_named_roi
        roi = crop_named_roi(frame, "modal_detalle_s17", "rareza_borde")
        rar = _detect_rareza(roi)
        if rar != "?":
            parsed.rareza = rar
    except Exception:
        pass
    parsed.set_active_tier = detect_active_set_tier(frame, lines, W, H)
    face = crop_s17_assigned_avatar(frame, lines, W, H)
    return parsed, face


# =====================================================================
# DiscAggregator — convergencia de parciales entre frames (Fase 1, 2026-06-07)
# =====================================================================
# Espejo de AgentStatsAggregator (S18): mientras se mira el MISMO disco, fusiona
# lecturas parciales frame-a-frame conservando el mejor valor conocido de cada
# campo. Así S17 converge en pocos ciclos sin depender de UN frame perfecto
# (mata el "mover y volver"). El monitor lo RESETEA cuando la firma visual indica
# que el disco cambió (igual que S18 resetea por cambio de agente).

def _clone_disc(d: DiscParsed) -> DiscParsed:
    """Copia profunda ligera (subs nueva lista de copias) para no mutar el input."""
    subs = [SubstatParsed(s.nombre_raw, s.nombre_canon, s.valor, s.unidad, s.rolls, s.confianza)
            for s in d.subs]
    nd = DiscParsed(
        set_name_raw=d.set_name_raw, set_name_canon=d.set_name_canon, slot=d.slot,
        main_stat_raw=d.main_stat_raw, main_stat_canon=d.main_stat_canon,
        main_valor=d.main_valor, main_unidad=d.main_unidad, nivel=d.nivel, rareza=d.rareza,
        subs=subs, confianza_global=d.confianza_global, notas=list(d.notas),
        agente_asignado_nombre=d.agente_asignado_nombre, agente_asignado_conf=d.agente_asignado_conf,
        set_active_tier=d.set_active_tier,
        equip_detectado=d.equip_detectado, equip_pj_visual=d.equip_pj_visual,
    )
    return nd


def _merge_subs(base: list, new: list) -> list:
    """Fusiona substats por índice: si el nuevo tiene valor, gana; si no, conserva.
    Rellena nombre_canon faltante. Extiende si el nuevo trae más substats."""
    out = [SubstatParsed(s.nombre_raw, s.nombre_canon, s.valor, s.unidad, s.rolls, s.confianza)
           for s in base]
    for i, ns in enumerate(new):
        if i >= len(out):
            out.append(SubstatParsed(ns.nombre_raw, ns.nombre_canon, ns.valor, ns.unidad, ns.rolls, ns.confianza))
            continue
        b = out[i]
        if ns.valor is not None:
            # El frame nuevo leyó el valor → adoptar la lectura nueva completa.
            out[i] = SubstatParsed(ns.nombre_raw, ns.nombre_canon or b.nombre_canon,
                                   ns.valor, ns.unidad, ns.rolls, ns.confianza)
        else:
            # Sin valor nuevo: conservar, pero completar nombre_canon si faltaba.
            if b.nombre_canon is None and ns.nombre_canon is not None:
                b.nombre_canon = ns.nombre_canon
    return out


def disc_is_mature(d: DiscParsed | None) -> bool:
    """True si el disco fusionado está 'completo' (análogo a missing=[] de S18):
    set resoluble + slot 1..6 + main con valor + 4 substats con valor y nombre."""
    if d is None:
        return False
    if not (d.set_name_canon or d.set_name_raw):
        return False
    if not (1 <= d.slot <= 6):
        return False
    if d.main_valor is None:
        return False
    if len(d.subs) < 4:
        return False
    return all(s.valor is not None and (s.nombre_canon or s.nombre_raw) for s in d.subs[:4])


class DiscAggregator:
    """Acumula DiscParsed parciales del MISMO disco entre frames consecutivos.

    Reglas de merge (preferir lo 'bueno' del frame nuevo, si no conservar):
      - escalares (set/slot/main/nivel/rareza/tier/PJ/equip): adoptar el valor
        nuevo cuando es válido (no None/no vacío/no 'garbage'); si no, conservar.
      - substats: por índice; el frame que leyó el valor gana (ver _merge_subs).
      - confianza_global: máximo visto.
    El RESET lo dispara el monitor por cambio de firma del disco.
    """

    def __init__(self) -> None:
        self._best: DiscParsed | None = None

    @property
    def current(self) -> DiscParsed | None:
        return self._best

    def reset(self) -> None:
        self._best = None

    def merge(self, new: DiscParsed | None) -> DiscParsed | None:
        if new is None:
            return self._best
        if self._best is None:
            self._best = _clone_disc(new)
            return self._best
        b = self._best
        if new.set_name_canon:
            b.set_name_canon = new.set_name_canon
        if new.set_name_raw:
            b.set_name_raw = new.set_name_raw
        if new.slot and 1 <= new.slot <= 6:
            b.slot = new.slot
        if new.main_stat_canon:
            b.main_stat_canon = new.main_stat_canon
        if new.main_stat_raw:
            b.main_stat_raw = new.main_stat_raw
        if new.main_valor is not None:
            b.main_valor = new.main_valor
            b.main_unidad = new.main_unidad
        if new.nivel:
            b.nivel = new.nivel
        if new.rareza and new.rareza != "?":
            b.rareza = new.rareza
        if new.set_active_tier is not None:
            b.set_active_tier = new.set_active_tier
        if new.agente_asignado_nombre:
            b.agente_asignado_nombre = new.agente_asignado_nombre
            b.agente_asignado_conf = new.agente_asignado_conf
        if new.equip_detectado is not None:
            b.equip_detectado = new.equip_detectado
            b.equip_pj_visual = new.equip_pj_visual
        b.confianza_global = max(b.confianza_global, new.confianza_global)
        b.subs = _merge_subs(b.subs, new.subs)
        return b
