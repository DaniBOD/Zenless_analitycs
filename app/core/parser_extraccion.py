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
from pathlib import Path

import cv2
import numpy as np

from app.core.parser_s2 import (
    _RARITY_BANDS,
    TileBox,
    read_tile_slot,
    tile_rarity,
)
from app.core.parser_disc_s17 import PanelLayout

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
    """Matcher de dígito que nunca opina → fuerza el camino OCR en `read_tile_slot`.

    Se inyecta cuando el set de refs propio de este modal (`slot_digits_extraccion/`) NO está
    completo. NO se cae al matcher de S2 por default: eso acoplaría este parser a las refs de
    S2 (si algún día se re-siembran, cambiaría de comportamiento solo).
    """
    n_refs = 0

    def identify(self, crop_bgr):   # pragma: no cover - trivial
        return None, 0.0


_NO_SLOT_MATCHER = _AlwaysAbstain()

# Refs del dígito de slot de ESTE modal. Cada pantalla necesita su propio set (ya hay dos:
# `slot_digits/` para S2 y `slot_digits_s5/` para S5) porque `SlotDigitMatcher` resta el
# template PROMEDIO de su set para aislar el residuo del dígito: un badge de otro estilo deja
# un residuo dominado por la diferencia de estilo. Medido 2026-07-16 sobre los 11 tiles dorados
# de los fixtures: las refs de S2 y las de S5 abstienen en los 11 (aportan cero), y usarlas
# como base es peor que nada — un dígito ausente del set se contesta EQUIVOCADO con score ~0.94.
_EXTRACCION_REFS_DIR = Path(__file__).resolve().parent.parent / "resources" / "slot_digits_extraccion"

# GATE DE COMPLETITUD — load-bearing, no es paranoia. Con clases faltantes el matcher no
# abstiene: INVENTA. Leave-one-CLASS-out sobre los 11 tiles: 6 de 11 devolvieron un dígito
# equivocado con score hasta 0.799, SOLAPADO con los aciertos (mínimo 0.755) → no existe umbral
# que los separe. Con las 6 clases, en cambio, es excelente: leave-one-SAMPLE-out da 9/9, con
# los tres '4' en 0.999 (justo los que el OCR no puede leer).
#
# Hoy el set tiene {2,3,4,5,6} y le falta el 1 → el matcher queda APAGADO y el slot sale solo
# por OCR (8/11, 0 errores). Alcanza UNA captura del "Obtenido" con un disco de slot 1 para
# completarlo: `tools/harvest_extraccion_slot_digits.py --write` y se enciende solo, sin tocar
# código. Ver ese script para el detalle de la medición.
_SLOT_CLASSES = frozenset(range(1, 7))

_slot_matcher_extraccion = None
_slot_matcher_loaded = False


def _get_slot_matcher_extraccion():
    """Matcher del dígito de slot de este modal, o `_NO_SLOT_MATCHER` si el set de refs no
    cubre las 6 clases (ver `_SLOT_CLASSES`). Singleton lazy; nunca lanza."""
    global _slot_matcher_extraccion, _slot_matcher_loaded
    if _slot_matcher_loaded:
        return _slot_matcher_extraccion
    _slot_matcher_loaded = True
    _slot_matcher_extraccion = _NO_SLOT_MATCHER
    try:
        from app.core.slot_digit_matcher import SlotDigitMatcher
        m = SlotDigitMatcher.from_resources(refs_dir=_EXTRACCION_REFS_DIR)
        cubiertas = set(getattr(m, "_refs", {}))
        if cubiertas >= _SLOT_CLASSES:
            _slot_matcher_extraccion = m
            log.info("Matcher de slot S22 ACTIVO (%d refs, 6 clases)", m.n_refs)
        else:
            log.info("Matcher de slot S22 apagado: faltan las clases %s → solo OCR",
                     sorted(_SLOT_CLASSES - cubiertas))
    except Exception:
        log.debug("No se pudo cargar el matcher de slot de S22", exc_info=True)
    return _slot_matcher_extraccion


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
    El matcher es el camino PRIMARIO cuando su set de refs está completo; si no, abstiene y
    manda el OCR (ver `_get_slot_matcher_extraccion`).
    """
    return read_tile_slot(frame, box, _get_slot_ocr(),
                          slot_matcher=_get_slot_matcher_extraccion())


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


# --- Panel DETAIL (disco seleccionado) -----------------------------------------------------
# Al clickear un disco de la grilla, el panel derecho muestra el disco COMPLETO: nombre del set
# en TEXTO + slot entre paréntesis, nivel, atributo principal y secundarios con sus valores —
# calidad S17. Resuelve además la abstención del dígito '4' de la grilla: acá el slot es texto.
_DETAIL_PANEL_ROI = (0.55, 0.29, 0.26, 0.52)          # (x, y, w, h) → x 0.55-0.81, y 0.29-0.81
_DETAIL_LAYOUT = PanelLayout(0.55, 0.81, 0.70)        # col_split 0.70: nombres ≤0.65, valores ≥0.74
# Franja del TÍTULO, aparte: cubre las DOS líneas. El nombre del set envuelve cuando es largo
# ("Firmamento llameante (4)") y el "(N)" se cae al segundo renglón → el parse del panel pierde
# el slot. Mismo caso que el título de nodo de S13. `x` corta antes del badge circular de la
# derecha, que el OCR leería como un dígito suelto.
_DETAIL_TITLE_ROI = (0.56, 0.335, 0.20, 0.062)
# Marcador de slot "(N)" del título. El "(" de apertura es OPCIONAL: PaddleOCR lo dropea a
# veces y devuelve solo "N)" (QA en vivo 2026-07-18, Ejemplo_12 'Firmamento llameante' + '1)'
# → el disco NO se detectaba). El ")" de cierre SÍ es obligatorio: es lo que distingue el slot
# de un disco de la cantidad de un material ("×N", sin paréntesis) → sin él, `detail_has_disc`
# daría falsos positivos (RNF-02). Se busca (no se ancla): el nombre es todo lo anterior.
_RE_DETAIL_TITULO = re.compile(r"\(?\s*([1-6])\s*\)")


def _read_detail_title(frame, ocr) -> tuple[str | None, int | None]:
    """(nombre_raw, slot) del título del panel DETAIL, uniendo sus 1-2 líneas.

    PaddleOCR devuelve las líneas por separado y SIN espacios internos
    ('Firmamentollameante' + '(4)'); unirlas reconstruye el título parseable. El nombre sale
    con ruido de tildes ('Salönhuracanado' por 'Salón huracanado'), pero la resolución difusa
    del set (`DiscSetRepo.resolve_id`) lo absorbe — normaliza acentos y espacios.
    """
    if frame is None or ocr is None or getattr(frame, "size", 0) == 0:
        return None, None
    try:
        from app.core.capturer import crop_roi
        strip = crop_roi(frame, _DETAIL_TITLE_ROI)
        if strip is None or getattr(strip, "size", 0) == 0:
            return None, None
        partes = [t for (t, _c, _b) in ocr.text_with_bboxes(strip) if t and t.strip()]
    except Exception:
        return None, None
    if not partes:
        return None, None
    joined = " ".join(partes).strip()
    m = _RE_DETAIL_TITULO.search(joined)
    if not m:
        return None, None
    slot = int(m.group(1))
    nombre = joined[:m.start()].strip()   # el nombre es todo lo anterior al marcador "(N)"
    return (nombre or None), (slot if 1 <= slot <= 6 else None)


def detail_has_disc(frame, ocr) -> bool:
    """True si el panel DETAIL está mostrando un DISCO (y no el ítem por defecto).

    El modal abre con "Crédito proxy" seleccionado y el panel muestra materiales, EXP o denny
    según lo que se clickee. La firma de un disco es el título con "(N)": ningún otro ítem lo
    tiene. Sin esto se parsearía basura como si fuera un disco (RNF-02).
    """
    return _read_detail_title(frame, ocr)[1] is not None


def parse_detail_disc(frame, ocr):
    """Disco seleccionado en el panel DETAIL → `DiscParsed`, o None si no hay disco.

    Reusa el núcleo de S17 (`_parse_s17_from_lines`) con el layout de este panel: la estructura
    es la misma que la del panel lateral de S9 (sin hexágono, ≤4 substats), solo cambia la `x`.
    El título se lee de su propia franja porque envuelve a 2 líneas (ver `_read_detail_title`).
    """
    if frame is None or ocr is None or getattr(frame, "size", 0) == 0:
        return None
    nombre, slot = _read_detail_title(frame, ocr)
    if slot is None:
        return None   # no hay disco seleccionado (o el título no se pudo leer) → no inventar
    try:
        from app.core.capturer import crop_roi
        from app.core.parser_disc_s17 import _norm_key as _nk
        from app.core.parser_disc_s17 import _parse_s17_from_lines
        from app.core.parser_disc_s17 import _S9_JUNK_TOKENS

        H, W = frame.shape[:2]
        x0 = int(_DETAIL_PANEL_ROI[0] * W)
        y0 = int(_DETAIL_PANEL_ROI[1] * H)
        crop = crop_roi(frame, _DETAIL_PANEL_ROI)
        raw = ocr.text_with_bboxes(crop) if (crop is not None and getattr(crop, "size", 0)) else []
        lines = [(t, c, (b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0))
                 for (t, c, b) in raw if _nk(t) not in _S9_JUNK_TOKENS]
        d = _parse_s17_from_lines(lines, W, H, frame=frame, ocr=ocr,
                                  layout=_DETAIL_LAYOUT, detect_slot_hexagon=False,
                                  max_substats=4)
    except Exception:
        log.exception("Error parseando el panel DETAIL de S22")
        return None
    # El título de la franja MANDA sobre lo que el core sacó del panel: acá el nombre del set
    # compite con el junk de los botones (el core llegaba a tomar un '6' suelto como set).
    if nombre:
        d.set_name_raw = nombre
    d.slot = slot
    if "slot_no_detectado" in d.notas:
        d.notas.remove("slot_no_detectado")
    return d


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
