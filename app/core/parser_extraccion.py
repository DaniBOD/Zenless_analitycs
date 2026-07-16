"""Lectura del modal "Obtenido" (S22): recompensas del farmeo por BATERÍAS (auto-combate).

Es el ÚNICO punto de observación de estos drops: el farmeo por baterías va
`S13 → S21 (usos) → auto-combate → "Obtenido" → S13`, sin pasar nunca por S2 ni S3. Y a
diferencia de S2 —cuya grilla se colapsa con "▼" y cuyo conteo el propio `parser_s2` declara
no confiable— este modal lista TODO, desglosado por corrida.

Alcance: solo los discos **tier S (dorados)**, igual que `parser_s2`. Acá el recorte está
además justificado por una regla del juego (confirmada por el usuario 2026-07-16): el
auto-desmontaje solo alcanza a los tier A, los S nunca. Los discos A que aparecen con badge
"C" fueron auto-desmontados y NUNCA entraron al inventario → reportarlos sería mentir.
"Dorado ⇒ conservado" es por lo tanto un invariante, no un supuesto nuestro.

Display-only: no persiste ni puntúa (RNF-02 / RNF-06).

Geometría (medida 2026-07-16 sobre los 4 fixtures de `20_Extraccion_Baterias/`): las 6
columnas son FIJAS, pero el `y` de las filas se corre con el scroll → las filas se DETECTAN por
las franjas de rareza. Módulo propio a propósito: de `parser_s2` solo se importa lo que es
independiente de su geometría (que es la de S2, no la de acá).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.parser_s2 import (
    _RARITY_BANDS,
    TileBox,
    read_tile_slot,
    tile_rarity,
)

log = logging.getLogger(__name__)

# --- Geometría del viewport y de la grilla -------------------------------------------------
# Lista scrolleable izquierda (excluye el panel "DETAIL" de la derecha, que muestra el ítem
# seleccionado y no aporta nada).
_VIEWPORT_X = (0.200, 0.560)
_VIEWPORT_Y = (0.280, 0.810)

# Centros x de las 6 columnas (paso 0.05586). Constantes en los 4 fixtures.
_COLS_CX = (0.2359, 0.2917, 0.3476, 0.4035, 0.4594, 0.5152)

# Caja del tile respecto del centro de su franja de rareza (borde inferior del icono).
# Los iconos acá son ~64% del tamaño de los de S2 (_TILE_W=0.066): el tile es casi cuadrado.
_TILE_HALF_W = 0.021
_TILE_ABOVE = 0.076
_TILE_BELOW = 0.005

# Detección de filas: componentes conexas de la máscara de rareza que parezcan una FRANJA
# (ancha y baja). Las franjas de una misma fila comparten `cy`; filas distintas están a 0.1230.
_STRIP_MIN_W_PX = 40
_STRIP_MIN_H_PX = 4
_STRIP_MAX_H_PX = 40
_STRIP_MIN_ASPECT = 3.0
_ROW_EPS = 0.05          # separación mínima entre filas distintas (paso real: 0.1230)

# Header de sección ("Con el uso n.º N se obtiene:"), arriba de la PRIMERA fila de la sección.
_HEADER_DY = 0.092       # distancia del header al cy de la franja de su primera fila
_HEADER_HALF_H = 0.016
_HEADER_X = (0.205, 0.400)
_HEADER_UPSCALE = 2      # ver `_read_header_at` (detección de PaddleOCR en bandas chicas)
# Distancia del header de la sección SIGUIENTE al cy de la ÚLTIMA fila de la actual (medido:
# +0.077; el gap entre filas de secciones distintas es 0.171 vs 0.123 intra-sección).
_NEXT_HEADER_DY = 0.077

# El nº de corrida se ancla ENTRE "uso n<basura>" y "se obtiene". Los dos anclajes son
# necesarios, y cada uno lo puso una falla concreta:
#   - Sin la cola: el OCR puede mutilar el "º" en un DÍGITO ('n.9 3') y un patrón laxo
#     (`n\D{0,4}(\d)`) devolvía la corrida **9** en vez de 3. Error silencioso ⇒ RNF-02.
#   - Sin tolerar la falta de espacio: PaddleOCR —el backend PRIMARIO de la app— pega el
#     número al texto ('Con el uso n.*1se obtiene:'), así que exigir `\s+` antes del dígito
#     hacía que NADA se emitiera en producción (Tesseract sí deja el espacio; por eso el bug
#     no aparecía en los tests hasta parametrizarlos por backend).
# Con la cola, el `\S{0,3}` se come la basura del "º" y solo gana el dígito seguido de
# "se obtiene". Si el OCR también rompe la cola → no matchea → abstención (RNF-02).
_RE_HEADER = re.compile(r"uso\s*n\S{0,3}\s*(\d)\s*se\s*obtiene", re.I)

# Flechas de scroll. La AUSENCIA de la de abajo = se llegó al fondo de la lista → la última
# sección visible está completa. Medido: presente ≈0.34 de píxeles claros, ausente = 0.000.
_ARROW_DOWN = (0.3755, 0.801)
_ARROW_UP = (0.3755, 0.296)
_ARROW_HALF_W = 0.012
_ARROW_HALF_H = 0.008
_ARROW_V_MIN = 200
_ARROW_FRAC_MIN = 0.15

# Verificación anti-FP de S22 ("Obtenido" es un título genérico de ZZZ: correo, login, pase).
# Los 4 fixtures dan 12-13 franjas; una pantalla sin grilla de recompensas no llega a 6.
_EXTRACCION_STRIP_MIN = 6


@dataclass(frozen=True)
class DiscoS:
    """Un disco tier S de una corrida. `slot`/`set_name` en None = no confirmado (RNF-02):
    el disco igual cuenta (la franja dorada es evidencia directa), pero no se afirma el dato."""
    slot: int | None
    set_name: str | None
    conf: float


@dataclass(frozen=True)
class Seccion:
    """Los discos S de una corrida. `completa=False` ⇒ puede haber más abajo sin scrollear."""
    n_uso: int
    discos: tuple[DiscoS, ...]
    completa: bool


def _viewport_px(frame: np.ndarray) -> tuple[int, int, int, int]:
    H, W = frame.shape[:2]
    return (int(_VIEWPORT_X[0] * W), int(_VIEWPORT_Y[0] * H),
            int(_VIEWPORT_X[1] * W), int(_VIEWPORT_Y[1] * H))


def _rarity_mask(sub: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask = np.zeros(sub.shape[:2], np.uint8)
    for lo, hi in _RARITY_BANDS:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    return mask


def _strips(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Componentes con forma de franja de rareza dentro del viewport, en px del frame."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return []
    x0, y0, x1, y1 = _viewport_px(frame)
    sub = frame[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    n, _lab, stats, _cent = cv2.connectedComponentsWithStats(_rarity_mask(sub), 8)
    out = []
    for s in stats[1:]:
        sx, sy, sw, sh = int(s[0]), int(s[1]), int(s[2]), int(s[3])
        if sw < _STRIP_MIN_W_PX or not (_STRIP_MIN_H_PX < sh < _STRIP_MAX_H_PX):
            continue
        if sw / max(sh, 1) < _STRIP_MIN_ASPECT:
            continue
        out.append((x0 + sx, y0 + sy, sw, sh))
    return out


def count_rarity_strips_viewport(frame: np.ndarray) -> int:
    """Nº de franjas de rareza en el viewport. Verificación anti-FP de S22 (ver `_verify_s22`)."""
    return len(_strips(frame))


def strip_rows(frame: np.ndarray) -> list[float]:
    """`cy` normalizado de cada FILA de la grilla, de arriba hacia abajo. Las filas se detectan
    (no se hardcodean) porque el scroll las corre; solo las columnas son fijas."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return []
    H = frame.shape[0]
    cys = sorted((sy + sh / 2) / H for _sx, sy, _sw, sh in _strips(frame))
    rows: list[float] = []
    for cy in cys:
        if not rows or cy - rows[-1] > _ROW_EPS:
            rows.append(cy)
    return rows


def _tile_box(frame: np.ndarray, cy: float, cx: float, row: int, col: int) -> TileBox:
    H, W = frame.shape[:2]
    return TileBox(row=row, col=col,
                   x0=int((cx - _TILE_HALF_W) * W), y0=int((cy - _TILE_ABOVE) * H),
                   x1=int((cx + _TILE_HALF_W) * W), y1=int((cy + _TILE_BELOW) * H))


def _fits_in_viewport(frame: np.ndarray, box: TileBox) -> bool:
    """Un tile CLIPEADO por el borde del viewport puede perder el badge de slot o la franja →
    daría un slot inventado. Se descarta entero (RNF-02)."""
    H = frame.shape[0]
    return box.y0 >= int(_VIEWPORT_Y[0] * H) and box.y1 <= int(_VIEWPORT_Y[1] * H)


def gold_boxes(frame: np.ndarray, cy: float, row: int = 0) -> list[TileBox]:
    """Tiles de disco tier S (dorados) de una fila, de izquierda a derecha. Los tiles de otra
    rareza, los materiales y los consumibles quedan fuera por la franja."""
    out = []
    for col, cx in enumerate(_COLS_CX):
        box = _tile_box(frame, cy, cx, row, col)
        if not _fits_in_viewport(frame, box):
            continue
        if tile_rarity(frame, box) == "S":
            out.append(box)
    return out


def crop_slot(frame: np.ndarray, box: TileBox) -> np.ndarray:
    """Esquina sup-izq del tile (tag con el dígito de slot 1-6)."""
    bw, bh = box.x1 - box.x0, box.y1 - box.y0
    return frame[box.y0:box.y0 + int(0.42 * bh), box.x0:box.x0 + int(0.46 * bw)]


def crop_art(frame: np.ndarray, box: TileBox) -> np.ndarray:
    """Arte del disco (centro del tile) → entrada del matcher de sets. Excluye el tag de slot
    (sup-izq) y la franja de rareza (abajo), que contaminarían el color."""
    bw, bh = box.x1 - box.x0, box.y1 - box.y0
    return frame[box.y0 + int(0.20 * bh):box.y0 + int(0.66 * bh),
                 box.x0 + int(0.26 * bw):box.x0 + int(0.80 * bw)]


class _AlwaysAbstain:
    """Matcher de dígito que nunca opina, para forzar el camino OCR en `read_tile_slot`.

    NO se usa `SlotDigitMatcher` acá, ni el de S2 ni uno sembrado con este modal:

    - El de S2 tiene refs del HEXÁGONO de S2; este modal usa un tag rectangular más chico.
      Medido sobre los 11 tiles dorados de los fixtures: abstiene en los 11 (aporta cero). Se
      inyecta este stub igual, en vez de confiar en esa abstención, para no acoplarse a las
      refs de S2: si algún día se re-siembran, este parser cambiaría de comportamiento solo.
    - Sembrar uno propio se probó y se DESCARTÓ (2026-07-16). El matcher resta el template
      promedio de sus refs para aislar el residuo del dígito, así que necesita las 6 clases
      cubiertas (`slot_digits/` y `slot_digits_s5/` tienen 3-8 refs por dígito). Los 4 fixtures
      solo dan 11 tiles: {2:3, 3:1, 4:3, 5:2, 6:2} y CERO del slot 1. Con clases faltantes el
      matcher no abstiene, INVENTA: en leave-one-class-out, 4 de 11 devolvieron un dígito
      equivocado con score sobre el umbral (p.ej. un '5' leído como 6 a 0.71). Un slot 1 real
      se leería mal en silencio → RNF-02. Re-evaluar cuando haya fixtures con slots 1 y 3.

    El OCR solo acierta 8/11 con **0 errores** (falla únicamente el '4', que abstiene). Cambiar
    3 abstenciones por el riesgo de errores silenciosos es justo el trade que RNF-02 prohíbe.
    """
    n_refs = 0

    def identify(self, crop_bgr):   # pragma: no cover - trivial
        return None, 0.0


_NO_SLOT_MATCHER = _AlwaysAbstain()

_slot_ocr_singleton = None


def _get_slot_ocr():
    """Backend de OCR para el DÍGITO DE SLOT: Tesseract, siempre — aunque el primario de la
    app sea PaddleOCR.

    No es una preferencia, es una restricción de RNF-02 medida sobre los 11 tiles dorados de
    los fixtures:

        Tesseract → 8/11 aciertos, **0 errores**, 3 abstenciones (solo el '4')
        PaddleOCR → 7/11 aciertos, **4 ERRORES**, 0 abstenciones

    El camino OCR de `read_tile_slot` está afinado para Tesseract (`psm=10` = un solo carácter,
    binarizado + upscale ×5 + borde). Paddle ignora `psm`, no tiene noción de "un glifo" y
    **nunca abstiene**: ante un dígito difícil devuelve igual su mejor conjetura → cada fallo
    se vuelve un slot equivocado en silencio. En S2 esto nunca se notó porque allá el camino
    primario es `SlotDigitMatcher` y el OCR casi no se usa; acá el matcher está descartado
    (ver `_AlwaysAbstain`), así que el OCR es el único camino y su comportamiento manda.

    Sin Tesseract disponible → None → se abstiene el slot (el disco igual cuenta).
    """
    global _slot_ocr_singleton
    if _slot_ocr_singleton is None:
        try:
            from app.core.ocr_tesseract import TesseractBackend
            _slot_ocr_singleton = TesseractBackend()
        except Exception:
            log.debug("Tesseract no disponible: el slot de S22 se abstiene", exc_info=True)
            _slot_ocr_singleton = False   # sentinela: no reintentar
    return _slot_ocr_singleton or None


def read_slot(frame: np.ndarray, box: TileBox) -> int | None:
    """Dígito de slot del tile, o None si no se puede afirmar.

    NO toma el `ocr` del monitor a propósito: usa Tesseract sí o sí (ver `_get_slot_ocr`).
    """
    return read_tile_slot(frame, box, _get_slot_ocr(), slot_matcher=_NO_SLOT_MATCHER)


def _read_header_at(frame: np.ndarray, cy_header: float, ocr) -> int | None:
    """OCR de la banda de header centrada en `cy_header` → nº de corrida, o None."""
    if ocr is None or frame is None or getattr(frame, "size", 0) == 0:
        return None
    H, W = frame.shape[:2]
    y0 = int((cy_header - _HEADER_HALF_H) * H)
    y1 = int((cy_header + _HEADER_HALF_H) * H)
    if y0 < int(_VIEWPORT_Y[0] * H) or y1 > int(_VIEWPORT_Y[1] * H):
        return None   # fuera del viewport → no se puede afirmar nada
    crop = frame[y0:y1, int(_HEADER_X[0] * W):int(_HEADER_X[1] * W)]
    if crop.size == 0:
        return None
    # Upscale ×2 antes del OCR: la etapa de DETECCIÓN de PaddleOCR (el backend primario de la
    # app) es marginal en esta banda de 46px y a veces devuelve '' o un fragmento ('odtiene'),
    # sobre todo en el header del borde inferior. Su RECONOCIMIENTO lee bien si el texto es
    # más grande — misma lección que el rescate del nivel proyectado en S10. Tesseract no se
    # ve afectado. Barato: 46×499 → 92×998.
    crop = cv2.resize(crop, None, fx=_HEADER_UPSCALE, fy=_HEADER_UPSCALE,
                      interpolation=cv2.INTER_CUBIC)
    try:
        text, _conf = ocr.text(crop, psm=7, lang="spa")
    except Exception:
        return None
    m = _RE_HEADER.search(text or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 9 else None


def read_section_header(frame: np.ndarray, cy: float, ocr) -> int | None:
    """Nº de corrida del header que está sobre la fila `cy`, o None si esa fila no encabeza
    una sección (o el header quedó fuera del viewport / ilegible).

    Es la ÚNICA fuente de agrupación en secciones: se descartó separar por el gap vertical
    entre filas (intra-sección 0.123 vs inter-sección 0.171 → margen chico y frágil). Leer el
    header de cada fila cuesta ≤4 OCRs por frame y no tiene ese filo: sobre una fila que NO
    encabeza sección, el ROI cae en los labels de cantidad de la fila de arriba ("600 1 1") y
    el regex los rechaza."""
    return _read_header_at(frame, cy - _HEADER_DY, ocr)


def next_section_header(frame: np.ndarray, cy_last_row: float, ocr) -> int | None:
    """Nº de la corrida SIGUIENTE si su header ya asoma bajo la última fila de la actual.

    Ver el header de la próxima corrida PRUEBA que la actual no tiene más filas → la cierra.
    Hace falta buscarlo por separado porque el header puede estar en pantalla cuando su primera
    FILA todavía no (queda bajo el viewport): sin esto, una sección así no cerraría nunca —
    al scrollear, sus filas pasan a ser huérfanas y se descartan, así que la evidencia de
    cierre no vuelve a aparecer."""
    return _read_header_at(frame, cy_last_row + _NEXT_HEADER_DY, ocr)


def _arrow_visible(frame: np.ndarray, center: tuple[float, float]) -> bool:
    H, W = frame.shape[:2]
    cx, cy = center
    sub = frame[int((cy - _ARROW_HALF_H) * H):int((cy + _ARROW_HALF_H) * H),
                int((cx - _ARROW_HALF_W) * W):int((cx + _ARROW_HALF_W) * W)]
    if sub.size == 0:
        return False
    v = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)[:, :, 2]
    return float((v > _ARROW_V_MIN).mean()) >= _ARROW_FRAC_MIN


def has_more_below(frame: np.ndarray) -> bool:
    """True si la flecha ▼ está visible ⇒ hay contenido sin scrollear debajo."""
    return _arrow_visible(frame, _ARROW_DOWN)


def has_more_above(frame: np.ndarray) -> bool:
    """True si la flecha ▲ está visible ⇒ hay contenido sin scrollear arriba."""
    return _arrow_visible(frame, _ARROW_UP)


def parse_obtenido(frame, ocr, matcher=None, cand_en: list[str] | None = None) -> list[Seccion]:
    """Secciones (corridas) visibles en el frame, con sus discos tier S.

    Una sección se cierra (`completa=True`) cuando se ve el header de la SIGUIENTE —lo que
    prueba que ya no quedan filas suyas— o cuando no hay ▼ (fondo de la lista). Las filas
    anteriores al primer header visible se descartan: son de una corrida cuyo encabezado quedó
    scrolleado fuera y no se puede afirmar cuál es.

    Una sección sin cerrar NO es un error: se reporta con "≥" y converge cuando el scroll trae
    la evidencia (ver el dedup convergente en `monitor._process_s22_obtenido`).
    """
    rows = strip_rows(frame)
    if not rows:
        return []

    # Agrupar filas por sección usando el header de cada una.
    grupos: list[tuple[int, list[float]]] = []
    for cy in rows:
        n = read_section_header(frame, cy, ocr)
        if n is not None:
            grupos.append((n, [cy]))
        elif grupos:
            grupos[-1][1].append(cy)
        # sin grupo abierto → fila huérfana (header fuera de pantalla) → se descarta

    fondo = not has_more_below(frame)
    out: list[Seccion] = []
    for i, (n_uso, cys) in enumerate(grupos):
        discos: list[DiscoS] = []
        for r, cy in enumerate(cys):
            for box in gold_boxes(frame, cy, row=r):
                slot = read_slot(frame, box)
                nombre, conf = None, 0.0
                if matcher is not None and cand_en:
                    try:
                        m = matcher.identify(crop_art(frame, box), cand_en)
                        nombre, conf = m.name, float(m.conf)
                    except Exception:
                        pass
                discos.append(DiscoS(slot=slot, set_name=nombre, conf=conf))
        # Cierra si hay otra sección agrupada debajo, si el header de la próxima ya asoma, o
        # si se llegó al fondo de la lista. Cualquier otro caso: no se puede afirmar → "≥".
        completa = (i < len(grupos) - 1) or fondo
        if not completa:
            completa = next_section_header(frame, cys[-1], ocr) is not None
        out.append(Seccion(n_uso=n_uso, discos=tuple(discos), completa=completa))
    return out
