"""Parser S10 — modal de MEJORA (upgrade) de disco.

Reusa los helpers de bajo nivel de `parser_disc_s17` (pairing nombre/valor, badges
"+N", rescates de roll/valor, canon con unidad) pero con lógica ESPACIAL propia,
porque el modal S10 difiere del detalle S17 en tres cosas:

  1. El panel de detalle vive a la DERECHA (xn∈[0.44,0.90]), no en la franja central.
  2. Los substats están en una grilla 2×2 (DOS columnas nombre/valor), no en una sola.
  3. El nivel viene de la BARRA chevron (pill izq = nivel, centro = "N/M" exp o "MAX",
     pill der = nivel), no del texto "Nivel N/15". No hay "Efecto de conjunto".

Layout verificado sobre 3 estados reales 2559×1439 (nivel0 / nivel12 / MAX15,
folders 05/06/07):

    Fábula Yunkui (1)              ← título arriba-izq del modal (xn≈0.13, y≈0.16)
    Atributo principal            ← HEADER (y≈0.27)
      PV                 1870     ← main: nombre(xn≈0.46) | valor(xn≈0.63)  [+ EMPTY der]
    Atributos secundarios         ← HEADER (y≈0.35)
      Ataque       19   Defensa +1   9.6 %     ← fila 1: col izq | col der
      Daño Crítico 4.8% Perforación +2  27     ← fila 2
      [ 12 ]  [ 940/5760 ]  [ 12 ]   ← barra nivel (y≈0.51): PRE=exp / MAX="MAX"

Display-only: produce un `DiscParsed` con nivel + substats/rolls; el set se canoniza
en el caller (monitor) contra `disc_sets`. Sin persistencia (RNF-01 no aplica).
"""
from __future__ import annotations

import re

import numpy as np

from app.core.parser_disc import DiscParsed, SubstatParsed
from app.core.parser_disc_s17 import (
    _Line,
    _canon_with_unit,
    _coalesce_rolls_fragments,
    _norm_key,
    _parse_valor,
    _rescue_missing_value,
    _rescue_roll,
    _split_rolls,
    _strip,
    PanelLayout,
    _RE_TITULO_SLOT,
    _ROW_DY,
)
from app.core.stats_vocab import is_valid_main_for_slot

# --- Bandas normalizadas del modal S10 (x = borde IZQUIERDO del token, como _Line.xn) ---
# Panel de detalle derecho.
_PANEL_X_MIN = 0.44
_PANEL_X_MAX = 0.92
# Título "Set (slot)": arriba-izquierda del modal, sobre la imagen del disco.
_TITLE_X_MAX = 0.44
_TITLE_Y_MAX = 0.26
# Substats en 2 columnas. Cada columna tiene su propio split nombre/valor.
_SUB_COL_L = PanelLayout(band_min=0.44, band_max=0.66, col_split=0.58)   # nombre 0.46 / valor 0.63
_SUB_COL_R = PanelLayout(band_min=0.66, band_max=0.92, col_split=0.80)   # nombre 0.68 / valor 0.85
# Main: única fila; nombre a la izq del split, valor a la der (EMPTY a la derecha no OCRea).
_MAIN_SPLIT = 0.58
# Barra de nivel: y del bloque + bandas x de los 3 segmentos.
_LEVEL_Y_MIN = 0.48
_LEVEL_Y_MAX = 0.56
_LEVEL_LEFT_X = (0.48, 0.60)    # pill izquierdo = nivel ACTUAL
_LEVEL_CENTER_X = (0.60, 0.76)  # centro = "N/M" (exp) o "MAX"
_LEVEL_RIGHT_X = (0.76, 0.90)   # pill derecho = nivel PROYECTADO (tras "Mejorar")

_RE_NIVEL_NUM = re.compile(r"(\d{1,2})")


def parse_disc_s10(frame: np.ndarray, ocr) -> DiscParsed:
    """Parsea el modal de upgrade (S10) a `DiscParsed`. Display-only.

    Devuelve nivel (de la barra chevron), main, hasta 4 substats con rolls, y el
    nombre del set desde el título. `maxed` se refleja como nota 's10_max' y nivel=15.
    """
    lines = ocr.text_with_bboxes(frame)
    H, W = frame.shape[:2]
    return _parse_s10_from_lines(lines, W, H, frame=frame, ocr=ocr)


def _parse_s10_from_lines(
    lines: list[tuple[str, float, tuple[int, int, int, int]]],
    W: int,
    H: int,
    frame=None,
    ocr=None,
) -> DiscParsed:
    """Core testeable (sin OCR): parsea el modal S10 desde líneas OCR con bbox."""
    notas: list[str] = []
    confs: list[float] = []
    L = [_Line(t, c, bb, W) for (t, c, bb) in lines]

    # --- Título "Set (slot)" (arriba-izquierda del modal) ---
    title_lines = sorted(
        [ln for ln in L if ln.xn < _TITLE_X_MAX and (ln.y1 / H) < _TITLE_Y_MAX
         and any(ch.isalpha() for ch in ln.txt)],
        key=lambda l: l.y1,
    )
    titulo_raw = " ".join(ln.txt for ln in title_lines).strip()
    for ln in title_lines:
        confs.append(ln.conf)
    m = _RE_TITULO_SLOT.match(titulo_raw)
    if m:
        set_name_raw = m.group(1).strip()
        slot = int(m.group(2))
    else:
        # El OCR pudo dropear el ')' de cierre (p.ej. 'Fábula Yunkui(1'): buscar '(N'
        # tolerante al paréntesis faltante. El slot es 1-6.
        m2 = re.search(r"\(\s*([1-6])\s*\)?", titulo_raw)
        slot = int(m2.group(1)) if m2 else 0
        set_name_raw = re.sub(r"\s*\(\s*\d?\s*\)?\s*$", "", titulo_raw).strip()
        if slot == 0:
            notas.append("slot_no_detectado")

    # --- Panel de detalle derecho ---
    panel = [ln for ln in L if _PANEL_X_MIN <= ln.xn <= _PANEL_X_MAX]
    panel.sort(key=lambda ln: (ln.y1, ln.x1))

    # Headers de sección (delimitadores Y). Prefijos tolerantes (mismo criterio S17).
    y_main = y_subs = None
    header_ys: set[int] = set()
    for ln in panel:
        k = _norm_key(ln.txt)
        if y_main is None and k.startswith("atributoprincip"):
            y_main = ln.y1; header_ys.add(ln.y1)
        elif y_subs is None and k.startswith("atributossecundari"):
            y_subs = ln.y1; header_ys.add(ln.y1)
    if y_main is None or y_subs is None:
        notas.append("s10_headers_no_detectados")
    _ymain = y_main if y_main is not None else 10 ** 9
    _ysubs = y_subs if y_subs is not None else 10 ** 9

    # --- Barra de nivel (delimita el final de los substats por arriba) ---
    nivel, maxed, y_level, proyectado = _read_level_bar(panel, W, H)
    if maxed:
        notas.append("s10_max")
    else:
        notas.append("s10_pre")
    if nivel is None:
        notas.append("s10_nivel_no_detectado")
        nivel = 0
    # Nivel PROYECTADO: si la pill derecha supera a la actual, hay materiales cargados y un
    # salto pendiente al hacer "Mejorar" (0→15, 5→10, …). Es el "después" del antes/después,
    # legible en un frame ESTABLE (a diferencia del MAX real que auto-cierra). RF-05.
    if proyectado is not None and proyectado > nivel:
        notas.append(f"s10_target:{proyectado}")
    _ylevel = y_level if y_level is not None else int(0.49 * H)

    # --- Main stat: fila entre 'Atributo principal' y 'Atributos secundarios' ---
    main_region = [ln for ln in panel if _ymain < ln.y1 < _ysubs and ln.y1 not in header_ys]
    main_names = [ln for ln in main_region if ln.xn < _MAIN_SPLIT]
    main_vals = [ln for ln in main_region if _MAIN_SPLIT <= ln.xn < 0.75]  # excluye EMPTY (der)
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

    # --- Substats: grilla 2×2, cada columna con su propio split nombre/valor ---
    sub_region = [ln for ln in panel if _ysubs < ln.y1 < _ylevel and ln.y1 not in header_ys]
    subs: list[SubstatParsed] = []
    for col in (_SUB_COL_L, _SUB_COL_R):
        subs.extend(_parse_sub_column(sub_region, col, frame, ocr, W, H, notas))
    # Orden: columna izq (arriba→abajo) y luego columna der. El diff PRE/POST matchea
    # por canon, así que el orden no afecta la correctitud — solo la legibilidad del log.

    total_rolls = sum(s.rolls for s in subs)
    if total_rolls > 5:
        notas.append(f"rolls_excedidos:{total_rolls}")

    confianza_global = (sum(confs) / len(confs)) if confs else 0.0
    if confianza_global < 0.7:
        notas.append("baja_confianza")

    return DiscParsed(
        set_name_raw=set_name_raw,
        set_name_canon=None,   # se canoniza contra disc_sets en el caller (monitor)
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


def _parse_sub_column(sub_region, col: PanelLayout, frame, ocr, W, H, notas) -> list[SubstatParsed]:
    """Parsea UNA columna del 2×2: pares nombre(izq)/valor(der) dentro de la banda `col`."""
    band = [ln for ln in sub_region if col.band_min <= ln.xn < col.band_max]
    names = _coalesce_rolls_fragments(
        sorted([ln for ln in band if ln.xn < col.col_split], key=lambda l: l.y1)
    )
    names = [ln for ln in names if any(c.isalpha() for c in ln.txt)]
    vals = sorted([ln for ln in band if ln.xn >= col.col_split], key=lambda l: l.y1)
    out: list[SubstatParsed] = []
    used: set[int] = set()
    for nl in names:
        best_i, best_dy = None, _ROW_DY + 1
        for i, vl in enumerate(vals):
            if i in used:
                continue
            dy = abs(vl.y1 - nl.y1)
            if dy < best_dy:
                best_dy, best_i = dy, i
        nombre, rolls = _split_rolls(nl.txt)
        if rolls == 0:
            rescued = _rescue_roll(frame, nl, ocr, W, H, col)
            if rescued is not None:
                rolls = rescued
        valor = unidad = None
        conf_v = 0.0
        if best_i is not None:
            used.add(best_i)
            valor, unidad = _parse_valor(vals[best_i].txt)
            conf_v = vals[best_i].conf
        if valor is None:
            rv = _rescue_missing_value(frame, nl, ocr, W, H, col)
            if rv is not None:
                valor, unidad = rv
        canon = _canon_with_unit(nombre, unidad)
        if canon is None and nombre:
            notas.append(f"substat_desconocido:{nombre}")
        out.append(SubstatParsed(
            nombre_raw=nombre, nombre_canon=canon, valor=valor,
            unidad=unidad, rolls=rolls, confianza=round((nl.conf + conf_v) / 2, 3),
        ))
    return out


def _read_level_bar(panel, W, H) -> tuple[int | None, bool, int | None, int | None]:
    """Lee la barra de nivel chevron. Devuelve (nivel, maxed, y_barra, proyectado).

    pill izquierdo = nivel ACTUAL (dígito); centro = 'N/M' (PRE) o 'MAX' (maxeado);
    pill derecho = nivel PROYECTADO tras "Mejorar" (== actual si no hay materiales cargados).
    """
    band = [ln for ln in panel if _LEVEL_Y_MIN <= (ln.y1 / H) <= _LEVEL_Y_MAX]
    if not band:
        return None, False, None, None
    y_bar = min(ln.y1 for ln in band)
    left = [ln for ln in band if _LEVEL_LEFT_X[0] <= ln.xn < _LEVEL_LEFT_X[1]]
    center = [ln for ln in band if _LEVEL_CENTER_X[0] <= ln.xn < _LEVEL_CENTER_X[1]]
    right = [ln for ln in band if _LEVEL_RIGHT_X[0] <= ln.xn < _LEVEL_RIGHT_X[1]]
    maxed = any("max" in _strip(ln.txt).lower() for ln in center)
    nivel = None
    if left:
        m = _RE_NIVEL_NUM.search(left[0].txt)
        if m:
            nivel = int(m.group(1))
    if nivel is None and maxed:
        nivel = 15
    proyectado = None
    if right:
        m = _RE_NIVEL_NUM.search(right[0].txt)
        if m:
            proyectado = int(m.group(1))
    return nivel, maxed, y_bar, proyectado
