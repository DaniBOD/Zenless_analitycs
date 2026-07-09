"""
Parser ESPACIAL del modal de detalle de drop (S3 — "Detalle del disco desde resultado").

S3 es el modal CENTRADO que aparece al abrir un disco recién farmeado desde la pantalla de
resultados. Estructuralmente es el MISMO panel de detalle que S17/S9 (título con `<set> (<slot>)`,
headers "Atributo principal" / "Atributos secundarios" / "Efecto de conjunto", main + substats con
badges de rolls), pero los substats están en una **grilla 2×2 (2 columnas)** en vez de una sola
columna vertical.

El parser per-ROI viejo (`parse_modal_detalle`) leía mal este modal (cada celda capturaba la
columna vecina → "Ataque 19 Defen", valores en None, slot 0). Este parser reusa TODA la maquinaria
endurecida de `parser_disc_s17` (líneas OCR, detección de headers, `_parse_valor`, canon con unidad,
rescates de rolls "+N" y de valor caído, `disc_is_mature`) y solo cambia el pairing nombre/valor a
DOS columnas.

Layout verificado sobre los 4 fixtures reales (2559×1439, carpeta 02_Detalle_Disco_Desde_Resultado):

    Fábula Yunkui (1)            ← título: <set> (<slot>)
    Nivel 00/15
    Atributo principal           ← HEADER
      PV               550       ← main (col A: nombre xn~0.33 | valor xn~0.46)
    Atributos secundarios        ← HEADER
      Ataque    19   Defensa  4.8 %   ← fila 1: col A | col B
      Daño Crítico  4.8 %             ← fila 2: col A (3er substat)
    Efecto de conjunto           ← HEADER
      Fábula Yunkui
      2 pistas: ...

Sin hexágono (el slot va en el "(N)" del título, que se lee fiable) y sin avatar (un drop no tiene
dueño). Display-only en esta fase: NO persiste.
"""
from __future__ import annotations

import re

import numpy as np

from app.core.parser_disc import DiscParsed, SubstatParsed, _detect_rareza
from app.core.stats_vocab import normalize_stat_name, is_valid_main_for_slot
from app.core.parser_disc_s17 import (
    PanelLayout,
    _Line,
    _strip,
    _norm_key,
    _parse_valor,
    _canon_with_unit,
    _split_rolls,
    _coalesce_rolls_fragments,
    _rescue_roll,
    _rescue_missing_value,
    _RE_NIVEL,
    _RE_TITULO_SLOT,
    _RE_PISTAS,
    _ROW_DY,
)

# Modal centrado: banda horizontal total + las DOS columnas de la grilla 2×2 (calibradas sobre
# los 4 fixtures reales). Cada columna es un `PanelLayout(band_min, band_max, col_split)` →
# reusa tal cual los rescates de rolls/valor, que ya toman layout.
_S3_BAND = (0.32, 0.68)
_S3_COL_A = PanelLayout(0.32, 0.50, 0.43)   # nombres xn<0.43, valores 0.43-0.50
_S3_COL_B = PanelLayout(0.50, 0.68, 0.605)  # nombres 0.50-0.605, valores 0.605-0.68

# Crop del modal para OCR (nativo, lado mayor < 960px → sin downscale del detector). x0.30-0.72,
# y0.18-0.76: abarca título, nivel, main, los 4 substats y la 1ª línea de "Efecto de conjunto".
_S3_MODAL_ROI = (0.30, 0.18, 0.42, 0.58)

_RE_SLOT_PAREN = re.compile(r"\(\s*([1-6])\s*\)")


def _rescue_slot_s3(frame, ocr, titulo_lines, W, H) -> int:
    """Recupera el slot re-OCRizando franjas del título upscaleadas cuando el crop dropea el '(N)'
    fino (el dígito entre paréntesis se cae a veces a resolución nativa). Escanea CADA línea del
    título (no solo la superior): con nombres largos el título se envuelve y el '(N)' queda en la
    línea de abajo. Crop generoso a la derecha (hasta el borde del modal) + upscale ×3. Devuelve
    el primer '(N)' encontrado o 0."""
    if frame is None or ocr is None or not titulo_lines:
        return 0
    try:
        import cv2
        for ln in sorted(titulo_lines, key=lambda l: l.y1):
            hp = max(1, ln.y2 - ln.y1)
            y0 = max(0, ln.y1 - int(0.3 * hp))
            y1 = min(H, ln.y2 + int(0.3 * hp))
            x0 = ln.x1
            x1 = min(W, int(0.68 * W))                # borde derecho del modal (el '(N)' pudo caerse)
            strip = frame[y0:y1, x0:x1]
            if strip.size == 0:
                continue
            up = cv2.resize(strip, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            for t, _c, _bb in ocr.text_with_bboxes(up):
                m = _RE_SLOT_PAREN.search(t)
                if m:
                    return int(m.group(1))
    except Exception:
        return 0
    return 0


def _ocr_s3_lines(frame: np.ndarray, ocr):
    """OCR del modal S3 sobre el FRAME COMPLETO. A diferencia de S17/S9 (que recortan el panel
    por latencia), el crop nativo del modal S3 dropea el '(N)' fino del título (slot) en algunos
    fondos → slot=0. El full-frame lo lee fiable ('(1)/(2)/(4)' verificados) y los substats
    igual; el filtro de banda (`_S3_BAND`) deja solo el modal. S3 es un modal que el usuario abre
    deliberadamente (no el path crítico), así que la latencia extra es aceptable."""
    return ocr.text_with_bboxes(frame)


def _coalesce_wrapped_names(name_lines):
    """Une nombres de substat ENVUELTOS a 2 líneas. En la grilla 2×2 de S3 las columnas son
    angostas y los nombres largos se parten: "Probabilidad de"/"Crítico", "Maestría de"/"Anomalía".
    Sin fusionar, cada mitad se leería como un substat fantasma. Solo fusiona si la 1ª línea NO
    es un stat conocido por sí sola Y la combinación SÍ lo es (gate seguro → cero falsos merges).
    Tolera el badge "+N" de rolls en cualquiera de las dos líneas (lo separa antes de validar)."""
    def _known(txt):
        base, _ = _split_rolls(txt.strip())
        return normalize_stat_name(base) is not None

    out = []
    i, n = 0, len(name_lines)
    while i < n:
        ln = name_lines[i]
        if not _known(ln.txt) and i + 1 < n:
            nxt = name_lines[i + 1]
            hp = max(1, ln.y2 - ln.y1)
            combo = (ln.txt.strip() + " " + nxt.txt.strip()).strip()
            if 0 < (nxt.y1 - ln.y1) <= 2.2 * hp and _known(combo):
                ln.txt = combo
                ln.y2 = max(ln.y2, nxt.y2)   # el bbox del nombre mergeado cubre AMBAS líneas → el
                                             # rescate de valor (crop alineado al nombre) alcanza el
                                             # valor, que se alinea con la 2ª línea (QA 2026-07-09:
                                             # 'Tasa de Perforación' → valor '6 %' se cortaba a 6.9)
                out.append(ln)
                i += 2
                continue
        out.append(ln)
        i += 1
    return out


def _column_substats(sub_region, col: PanelLayout, frame, ocr, W, H, notas, confs):
    """Extrae los substats de UNA columna (nombre izq / valor der dentro de la banda de la
    columna), con los mismos rescates de rolls y valor que S17. Devuelve [(y1, x1, SubstatParsed)]
    para luego mezclar las dos columnas en orden de lectura."""
    names = sorted([ln for ln in sub_region if col.band_min <= ln.xn < col.col_split], key=lambda l: l.y1)
    names = _coalesce_wrapped_names(names)        # une nombres largos partidos a 2 líneas
    names = _coalesce_rolls_fragments(names)       # une badges "+N" huérfanos
    # Descartar fragmentos sin letras (un valor/badge que cayó en la columna de nombre).
    names = [ln for ln in names if any(c.isalpha() for c in ln.txt)]
    vals = sorted([ln for ln in sub_region if col.col_split <= ln.xn <= col.band_max], key=lambda l: l.y1)
    out = []
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
            r = _rescue_roll(frame, nl, ocr, W, H, col)
            if r is not None:
                rolls = r
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
        confs.extend([nl.conf, conf_v])
        out.append((nl.y1, nl.x1, SubstatParsed(
            nombre_raw=nombre, nombre_canon=canon, valor=valor,
            unidad=unidad, rolls=rolls, confianza=round((nl.conf + conf_v) / 2, 3),
        )))
    return out


def _parse_s3_from_lines(lines, W, H, frame=None, ocr=None,
                         band=_S3_BAND, cols=(_S3_COL_A, _S3_COL_B)) -> DiscParsed:
    """Core: parsea una ficha de disco a partir de las líneas OCR con bbox. Reusa la estructura de
    `_parse_s17_from_lines` (headers como delimitadores Y) con pairing de substats por columna(s).
    Parametrizado por `band` (banda horizontal de la ficha) + `cols` (una o más `PanelLayout`): S3
    usa 2 columnas (grilla 2×2); S5 (resultado de afinación) usa 1 (ficha izquierda vertical). El
    main va siempre en `cols[0]`."""
    notas: list[str] = []
    col_a = cols[0]
    L = [_Line(t, c, bb, W) for (t, c, bb) in lines]
    detail = [ln for ln in L if band[0] <= ln.xn <= band[1]]
    detail.sort(key=lambda ln: (ln.y1, ln.x1))

    # --- Headers de sección (delimitadores Y) ---
    y_main = y_subs = y_effect = None
    header_ys: set[int] = set()
    for ln in detail:
        k = _norm_key(ln.txt)
        if y_main is None and k.startswith("atributoprincip"):
            y_main = ln.y1; header_ys.add(ln.y1)
        elif y_subs is None and k.startswith("atributossecundari"):
            y_subs = ln.y1; header_ys.add(ln.y1)
        elif y_effect is None and k.startswith("efectodeconjunt"):
            y_effect = ln.y1; header_ys.add(ln.y1)
    if y_main is None or y_subs is None:
        notas.append("s3_headers_no_detectados")
    _ymain = y_main if y_main is not None else 10**9
    _ysubs = y_subs if y_subs is not None else 10**9
    _yeffect = y_effect if y_effect is not None else 10**9

    confs: list[float] = []

    # --- Nivel ---
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
        set_name_titulo = re.sub(r"\(\s*\d?\s*\)\s*$", "", titulo_raw).strip()
        slot = 0
    if slot == 0:
        # `_RE_TITULO_SLOT` está anclada al final (`\)\s*$`), así que se cae cuando el "(N)" NO
        # queda al final del título unido: con nombres largos el título se ENVUELVE a 2 líneas
        # (el "(N)" va en la de abajo) y/o la insignia de rareza se cuela como token suelto tras
        # el "(N)". Buscar "(N)" SIN ancla en cada línea del título es robusto a ambos casos y no
        # cuesta re-OCR (QA farmeo 2026-07-09, 'Conejo en el país de las maravillas' → slot=0).
        for ln in sorted(titulo_lines, key=lambda l: l.y1):
            ms = _RE_SLOT_PAREN.search(ln.txt)
            if ms:
                slot = int(ms.group(1))
                break
    if slot == 0:
        # Aún nada → el crop nativo dropeó el '(N)' fino: re-OCR upscaleado de la franja del título.
        rs = _rescue_slot_s3(frame, ocr, titulo_lines, W, H)
        if rs:
            slot = rs
    if slot == 0:
        notas.append("slot_no_detectado")

    # --- Main: única fila nombre/valor entre los headers (siempre en la columna A) ---
    main_region = [ln for ln in detail if _ymain < ln.y1 < _ysubs and ln.y1 not in header_ys]
    main_names = [ln for ln in main_region if ln.xn < col_a.col_split]
    # El nombre del main también puede ENVOLVERSE a 2 líneas si es largo ('Tasa de' /
    # 'Perforación'): coalescer igual que los substats, o main_names[0] captura solo 'Tasa de'
    # → main_stat_canon=None (QA farmeo 2026-07-09, Ejemplo_14 'Tasa de Perforación').
    main_names = _coalesce_wrapped_names(main_names)
    main_vals = [ln for ln in main_region if col_a.col_split <= ln.xn <= col_a.band_max]
    main_raw = main_names[0].txt.strip() if main_names else ""
    main_val_raw = main_vals[0].txt if main_vals else ""
    if main_names:
        confs.append(main_names[0].conf)
    if main_vals:
        confs.append(main_vals[0].conf)
    main_valor, main_unidad = _parse_valor(main_val_raw)
    if main_valor is None and main_names:
        # El full-frame dropea el valor chico del main (p.ej. "79") en algunos fondos →
        # rescate por re-OCR upscaleado de la columna de valor (mismo patrón que substats).
        rv = _rescue_missing_value(frame, main_names[0], ocr, W, H, col_a)
        if rv is not None:
            main_valor, main_unidad = rv
    main_canon = _canon_with_unit(main_raw, main_unidad)
    if main_canon and slot >= 1 and not is_valid_main_for_slot(slot, main_canon):
        notas.append(f"main_invalido_slot_{slot}:{main_canon}")

    # --- Substats: grilla 2×2 → extraer cada columna y mezclar en orden de lectura ---
    sub_region = [ln for ln in detail if _ysubs < ln.y1 < _yeffect and ln.y1 not in header_ys]
    pares = []
    for c in cols:
        pares += _column_substats(sub_region, c, frame, ocr, W, H, notas, confs)
    pares.sort(key=lambda t: (t[0], t[1]))   # fila (y), luego columna (x): orden de lectura
    subs = [p[2] for p in pares][:4]          # un disco tiene MÁX 4 substats

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
    set_name_raw = set_name_efecto or set_name_titulo

    confianza_global = (sum(confs) / len(confs)) if confs else 0.0
    if confianza_global < 0.7:
        notas.append("baja_confianza")

    return DiscParsed(
        set_name_raw=set_name_raw,
        set_name_canon=None,
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


def parse_disc_s3_full(frame: np.ndarray, ocr) -> DiscParsed:
    """Parsea el modal de detalle de drop (S3) con OCR espacial de 2 columnas. Display-only."""
    lines = _ocr_s3_lines(frame, ocr)
    H, W = frame.shape[:2]
    parsed = _parse_s3_from_lines(lines, W, H, frame=frame, ocr=ocr)
    # Rareza best-effort por color del borde del icono (no bloquea si falla).
    try:
        from app.core.capturer import crop_named_roi
        roi = crop_named_roi(frame, "modal_detalle_s3", "rareza_borde")
        rar = _detect_rareza(roi)
        if rar != "?":
            parsed.rareza = rar
    except Exception:
        pass
    return parsed


# --- S5: resultado de afinación de la tienda de música (ficha izquierda) ------
# Estructuralmente idéntica a S3/S17 (título "<set> (N)", headers, main, substats, efecto) pero
# la ficha es VERTICAL (1 columna) y ANGOSTA → título y substats largos se ENVUELVEN a 2 líneas,
# igual que en la grilla 2×2 de S3. Por eso reusa el motor de S3 (con su coalescing de nombres
# envueltos + rescate de valor), no el de S17. Una sola columna. Calibrado 2026-07-09 contra las
# 2 capturas de 11_Tienda_Musica_Afinacion.
_S5_BAND = (0.30, 0.50)
_S5_COL = PanelLayout(0.30, 0.50, 0.42)   # band_min, band_max, col_split (nombre <0.42 | valor)


def parse_disc_s5(frame: np.ndarray, ocr) -> DiscParsed:
    """Parsea la ficha del disco SELECCIONADO del resultado de afinación (S5). Reusa el motor de
    S3 con UNA columna. La tienda solo entrega discos de grado S (texto del juego) → rareza='S'.
    Slot del "(N)" del título. Sin dueño (disco recién generado). Display-only."""
    lines = _ocr_s3_lines(frame, ocr)
    H, W = frame.shape[:2]
    parsed = _parse_s3_from_lines(lines, W, H, frame=frame, ocr=ocr, band=_S5_BAND, cols=(_S5_COL,))
    parsed.rareza = "S"
    return parsed
