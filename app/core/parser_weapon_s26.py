"""Parser del panel de detalle de W-Engine (S26).

Estructura del panel, de arriba a abajo:

    Petrazufre                    ← nombre (1-2 líneas: los largos envuelven)
    [S] Nivel 60/60      (avatar) ← rareza en badge circular + nivel/máximo + dueño
    ★☆☆☆☆                        ← refinamiento (H3)
    Atributo principal
      Ataque Base            684
    Atributos avanzados
      Ataque                 30 %
    Efecto de amplificador        ← la PASIVA: NO se extrae (ya está en la DB)

Es el mismo panel de una columna que el detalle de disco, con otros headers, así que reusa
la maquinaria de `parser_disc_s17`: `_ocr_detail_lines` (OCR sobre crop nativo con re-offset
de bboxes a coordenadas de frame completo), `_Line`, `_norm_key`, `_parse_valor` y
`_canon_with_unit`.

**Observación pura.** Nada de esto escribe la DB. El catálogo `weapons` se pasa por parámetro
(`catalogo`) en vez de consultarse acá: mantiene el módulo puro y testeable sin DB, y deja la
decisión de qué catálogo usar en el llamador.

Un arma que no está en el catálogo devuelve `nombre_canon=None` y se muestra el crudo — decisión
de Daniel el 2026-07-28. No se da de alta nada: `weapons` tiene 42 armas de menos y completarlo
es una pasada aparte (`audit/weapons_catalog_20260728.md`).
"""
from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple, Sequence

import cv2
import numpy as np

from app.core.detector import (
    _DET_HOUGH_PAD,
    _DET_HOUGH_RMAX_F,
    _DET_HOUGH_RMIN_F,
)
from app.core.parser_disc_s17 import (
    PanelLayout,
    _canon_with_unit,
    _Line,
    _norm_key,
    _ocr_detail_lines,
    _ocr_s9_detail_lines,
    _parse_valor,
    _S9_LAYOUT,
    _strip,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.core.ocr_backend import OcrBackend

log = logging.getLogger(__name__)

# Mismo panel central que el detalle de disco (verificado sobre los 40 fixtures).
_S26_LAYOUT = PanelLayout(0.30, 0.52, 0.42)
# ROI de la firma del handler: el panel entero (nombre, nivel, estrellas y stats). Más ancho que
# el del verify del detector a propósito — acá interesa detectar que cambió el ARMA, no solo que
# la pantalla sigue siendo de arma.
_PANEL_SIG_ROI = (0.30, 0.11, 0.23, 0.40)
# Ídem para el panel DERECHO del inventario (S30). Mismo propósito, otra columna: cubre nombre,
# nivel, estrellas y stats del arma seleccionada, que es lo que cambia al moverse por la grilla.
_S30_PANEL_SIG_ROI = (0.72, 0.16, 0.26, 0.40)

# "Nivel 60/60" (armas) — el denominador es 60 al máximo y 10 en las de rango B sin promocionar,
# así que NO se ancla a un valor fijo. Es lo que distingue esta línea de los "Nivel 60" sueltos
# de los tiles de la grilla, que no traen "/".
_RE_NIVEL_ARMA = re.compile(r"nivel\s*(\d{1,2})\s*/\s*(\d{1,2})", re.I)
# "Ataque Base 684". El valor se lee de la COLUMNA, no del orden de las líneas: PaddleOCR devuelve
# la línea del número con un `y1` unos píxeles MENOR que la de la etiqueta (medido: 448 vs 451,
# 452 vs 454), así que al ordenar por `y1` el número cae ANTES y el texto unido queda
# "594 Ataque Base". Ese detalle rompía 20 de los 40 fixtures — es la misma trampa que el fix v3.0
# de S18: por unos pocos píxeles el orden se da vuelta y una regex direccional falla en la mitad
# de los casos. La columna es estable; el orden no.
_RE_SOLO_NUMERO = re.compile(r"(\d{2,4})")
# Fallback bidireccional para cuando el OCR funde etiqueta y valor en UNA línea.
_RE_ATK_BASE_FUNDIDA = re.compile(
    r"ataque\s*base\D{0,6}(\d{2,4})|(\d{2,4})\D{0,6}ataque\s*base", re.I)
# Corte del nombre del stat contra su valor: "Ataque 30 %" → ("Ataque", "30 %").
_RE_STAT_VALOR = re.compile(r"^(?P<nombre>[^\d]+?)\s*(?P<valor>[\d]+(?:[.,]\d+)?\s*%?)\s*$")

_FUZZY_CUTOFF = 0.84   # mismo corte que el resto del repo para nombres OCReados

# --- Rareza y refinamiento: píxeles ANCLADOS al pill de nivel ----------------------------------
# Un recorte de coordenadas FIJAS no sirve: la fila de estrellas se corre verticalmente ~42 px
# entre un arma de nombre corto y una de nombre largo, porque el nombre envuelve a dos líneas y
# empuja todo el panel (medido: pill.y1 = 251 con una línea, 293/294 con dos). El primer intento
# usaba una banda fija y mezclaba "cuántas estrellas están blancas" con "cuánto de la fila entró
# en la banda" — los valores de un arma de nombre largo caían al 30 % de los de una corta.
#
# Tampoco se hardcodean los centros de las 5 estrellas: los offsets se corren ~12 px entre los dos
# regímenes de nivel, porque el bbox del OCR arranca en la "N" y "Nivel 60/60" es más ancho que
# "Nivel 0/10". Se DETECTAN los 5 blobs por frame (40/40 en los fixtures, espaciado ~42.5 px).
_STARS_DY = (28, 80)       # banda vertical, relativa a pill.y2
_STARS_DX = (-60, 260)     # banda horizontal, relativa a pill.x1
_STAR_COL_MIN = 0.12       # fracción de columna con píxel de estrella para considerarla ocupada
_STAR_RUN_MIN = 8          # ancho mínimo de un blob (los reales miden 24-28 px)
# Llenas 0.342-0.363, vacías EXACTAMENTE 0.000: las grises no tienen un solo píxel sobre V=200.
# La separación no es "≥2×", es absoluta.
_STAR_LLENA_MIN = 0.15

_BADGE_DX = -64            # centro del badge de rareza, relativo a pill.x1
_BADGE_R = 18
_BADGE_PX_MIN = 20         # píxeles saturados mínimos para creerle al hue
# Hue exacto medido en los 40 fixtures, con varianza CERO (son colores planos de UI):
#     S = 22.0    A = 155.0    B = 98.0
# Los rangos son ±10 alrededor de cada uno; no se solapan ni de cerca.
# Se reconfirmaron sobre el panel del INVENTARIO (S30): S = 21.0, A = 155.0, B = 98.0. Es el mismo
# color plano, así que la tabla se comparte entre paneles — lo único que cambia es DÓNDE mirar.
_BADGE_HUE = {"S": (12, 32), "A": (145, 165), "B": (88, 108)}


class PillGeometry(NamedTuple):
    """Dónde caen el badge de rareza y la fila de estrellas RESPECTO DEL PILL "Nivel N/M".

    El pill es el ancla de todo lo posicional (nada fijo funciona en estos paneles), pero el
    LAYOUT alrededor del pill no es el mismo en las dos pantallas que muestran un arma:

        S26 (detalle)     badge a la izquierda y separado · estrellas en una caja DEBAJO
        S30 (inventario)  badge pegado al pill            · estrellas A LA DERECHA, misma fila

    Los dos paneles tienen el pill del MISMO tamaño (190×28 vs 194×31), así que no es cuestión de
    escalar: es otra disposición. Por eso la geometría se pasa como parámetro en vez de derivarse.
    """
    badge_dx: int                  # centro del badge, relativo a pill.x1
    stars_x_from: str              # "x1" | "x2" — borde del pill que ancla la banda horizontal
    stars_dx: tuple[int, int]
    stars_y_from: str              # "y1" | "y2" — borde del pill que ancla la banda vertical
    stars_dy: tuple[int, int]


# Los de siempre (40 fixtures del detalle). Es el default de las dos funciones de lectura, así que
# el camino de S26 no cambia en nada.
_S26_PILL = PillGeometry(_BADGE_DX, "x1", _STARS_DX, "y2", _STARS_DY)

# Panel del inventario, medido sobre los 6 fixtures:
#     badge   dx = pill.x1 + [-28, -24]        ⇒ -26, centrado en el rango
#     estrellas  5 blobs en 6/6, arrancando en pill.x2 + [78, 80], espaciados ~38.7 px, el último
#                termina cerca de pill.x2 + 263
# La banda va de +60 a +290: entra la fila entera con margen a los dos lados y no llega al borde
# del pill (que si no metería un 6º blob del propio texto del nivel).
_S30_PILL = PillGeometry(-26, "x2", (60, 290), "y1", (-8, 45))

# --- Badge del DUEÑO: mismo ancla, otro lado del pill ------------------------------------------
# Offsets medidos sobre los 28 fixtures que tienen avatar visible (ver `read_weapon_owner_badge`):
#     dx = cx - pill.x2 ∈ [163, 165]     dy = cy - pill.cy ∈ [-2, 0]     radio ∈ [23, 30]
_OWNER_DX = 164
_OWNER_DY = -1
# Media ROI de búsqueda. Con 45 px el círculo más grande (r=30) entra entero y sobran 15 px de
# margen para el corrimiento de ±2 px, sin llegar a tocar el texto del nivel ni el arte del arma.
_OWNER_SEARCH = 45
_OWNER_DISCO_R = 20        # disco interior donde se mide la nitidez (bien dentro del avatar)

# Presencia por NITIDEZ (|Laplaciano| medio dentro del disco), no por saturación ni por brillo.
# Medido sobre los 40 fixtures (28 con dueño / 12 libres), separación total:
#
#     métrica            DUEÑO            LIBRE          gap
#     |Laplaciano|    51.98 – 90.43     1.54 – 4.75      11×      ← se usa esta
#     std_in          42.29 – 85.58     2.58 – 13.15      3.2×
#     V_in - V_out    68.20 – 189.46   -5.77 – 13.32      5×
#     área saturada     103 – 7157         0 – 8002    SE SOLAPA  ← la que fallaba
#
# El área saturada —que es lo que usa `crop_detail_badge`— NO discrimina acá: cuatro armas libres
# (Ejemplo_32/33/4/5) tienen un resplandor de color del ARTE DEL ARMA justo detrás del hueco del
# badge, y eso da blobs de hasta 8002 px², más que varios avatares reales. Brillo y saturación
# miden lo mismo que el resplandor; la nitidez no: una cara tiene detalle, un degradé no tiene
# ninguno. Por eso el gap se abre a 11× en vez de solaparse.
_OWNER_NITIDEZ_MIN = 20.0  # 4.2× sobre el libre más alto, 2.6× bajo el dueño más bajo
# ATK base a nivel 60 por rareza — segunda señal INDEPENDIENTE (auditoría del catálogo 2026-07-28,
# 32 muestras a máximo, sin solapes). Solo aplica al máximo: fuera de ahí el ATK no dice nada.
_ATK_MAX_POR_RAREZA = {684: "S", 713: "S", 743: "S", 594: "A", 624: "A"}


@dataclass
class WeaponParsed:
    """Lo que se lee del panel. Campo no leído ⇒ None + nota (RNF-02, nunca un plausible)."""

    nombre_raw: str = ""
    nombre_canon: str | None = None
    nivel: int | None = None
    nivel_max: int | None = None
    atk_base: int | None = None
    stat_avanzado_canon: str | None = None
    stat_avanzado_valor: float | None = None
    stat_avanzado_unidad: str | None = None
    # Se leen por PÍXELES anclados al pill de nivel, no por OCR. Declarados acá —y no asignados
    # al vuelo, como estaban— porque sin el pill no se asignaban nunca y cualquier consumidor
    # (p. ej. `monitor.py`, que arma la firma con `d.refinamiento`) reventaba con AttributeError
    # en vez de ver el None que promete el docstring. Hoy no pasaba de casualidad: el gate del
    # handler exige `nivel`, que sale del mismo pill. Al reusar el parser en otro panel (S30) esa
    # casualidad deja de valer.
    rareza: str | None = None
    refinamiento: int | None = None
    # PJ que la tiene equipada. NO lo llena este módulo: lo resuelve el monitor con la superficie
    # de badge compartida (`crop_detail_badge` + `avatar_detbadge_v2`), que es stateful y vive ahí.
    dueno: str | None = None
    # "equipada" (la lleva el PJ en pantalla) | "otro_pj" | "libre" | "incierto". Lo llena el
    # monitor con `clasificar_tenencia`, que necesita el latch de identidad y el botón de acción.
    tenencia: str = "incierto"
    # Bbox del pill "Nivel N/M". Se expone porque es el ANCLA de todo lo posicional del panel
    # (rareza, refinamiento y el badge del dueño): el monitor lo necesita para recortar el avatar
    # sin volver a OCRizar. None si el pill no se leyó — ahí no se ancla nada.
    pill_bbox: tuple[int, int, int, int] | None = None
    confianza: float = 0.0
    notas: list[str] = field(default_factory=list)

    @property
    def al_maximo(self) -> bool:
        """True si está a nivel máximo. Es la condición que habilita usar el ATK base como
        corroboración de la rareza (S ∈ {684,713,743}, A ∈ {594,624} — hallazgo de la auditoría
        del catálogo). Fuera del máximo el ATK no dice nada."""
        return (self.nivel is not None and self.nivel_max is not None
                and self.nivel == self.nivel_max)


# Tokens compuestos SOLO por caracteres que el OCR confunde entre sí (i, l, 1, |) se colapsan a
# 'i' repetida. Es el arreglo del caso más filoso del catálogo: el OCR lee "Modelo III" como
# "Modelo lll", y con la comparación cruda gana el candidato EQUIVOCADO —
#     "...modelo lll" vs "...modelo ii"  → 0.8837
#     "...modelo lll" vs "...modelo iii" → 0.8636
# o sea que "Modelo III" se reportaría como "Modelo II": dos armas distintas fundidas en una. Y
# como las dos superan el corte de 0.84, subir el umbral no lo arregla; hay que normalizar antes.
#
# Se aplica solo a tokens ENTEROS de ese alfabeto para no tocar palabras reales: en "Llanto
# mielgo" ningún token califica (ambos tienen letras fuera del set), así que queda intacto.
_RE_TOKEN_ROMANO = re.compile(r"^[il1|]+$")


def _norm_nombre(s: str) -> str:
    """Normaliza para el fuzzy: sin acentos, minúscula, sin puntuación, y con los numerales
    romanos ambiguos del OCR colapsados."""
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    tokens = re.sub(r"[^a-z0-9]+", " ", s).split()
    return " ".join("i" * len(t) if _RE_TOKEN_ROMANO.match(t) else t for t in tokens)


def match_catalogo(nombre_raw: str, catalogo: Sequence[str] | None) -> str | None:
    """Resuelve el nombre OCReado contra el catálogo, o None si no hay match confiable.

    El OCR mutila sistemáticamente: 'Última cena' → 'Uitima cena', 'Cañón' → 'Canon',
    'Modelo III' → 'Modelo lll'. Por eso se compara normalizado y con corte 0.84.

    Devolver None es un resultado LEGÍTIMO, no un fallo: el catálogo tiene 42 armas de menos,
    así que lo esperable es que aparezcan armas que no están. Se muestra el crudo.
    """
    if not nombre_raw or not catalogo:
        return None
    clave = _norm_nombre(nombre_raw)
    if not clave:
        return None
    normalizados = {_norm_nombre(c): c for c in catalogo}
    if clave in normalizados:
        return normalizados[clave]
    cerca = difflib.get_close_matches(clave, list(normalizados), n=1, cutoff=_FUZZY_CUTOFF)
    return normalizados[cerca[0]] if cerca else None


def weapon_panel_signature_s30(frame: np.ndarray) -> bytes:
    """Firma del panel derecho del inventario (S30). Ver `weapon_panel_signature`."""
    return _panel_signature(frame, _S30_PANEL_SIG_ROI)


def weapon_panel_signature(frame: np.ndarray) -> bytes:
    """Firma barata (~0.3 ms) del panel, para que el handler no re-OCRee un panel quieto.

    El OCR del panel cuesta ~500 ms y la cadencia de S26 es 1000 ms: sin gate, mirar un arma
    durante diez segundos serían diez OCRs idénticos (RNF-06, CPU < 3 %). Es la misma idea que el
    cache del verify en el detector, pero con ROI propio y otro dueño: acá gatea el handler.
    """
    return _panel_signature(frame, _PANEL_SIG_ROI)


def _panel_signature(frame: np.ndarray, roi: tuple[float, float, float, float]) -> bytes:
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    crop = frame[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)]
    if crop.size == 0:
        return b""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return cv2.resize(gray, (32, 24), interpolation=cv2.INTER_AREA).tobytes()


def _star_runs(band_mask: np.ndarray) -> list[tuple[int, int]]:
    """Blobs horizontales de la fila de estrellas, como pares (col_inicio, col_fin)."""
    ocupada = band_mask.mean(axis=0) > _STAR_COL_MIN
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(ocupada):
        if not ocupada[i]:
            i += 1
            continue
        j = i
        while j < len(ocupada) and ocupada[j]:
            j += 1
        if j - i >= _STAR_RUN_MIN:
            runs.append((i, j))
        i = j
    return runs


def _stars_band(frame: np.ndarray, pill_bbox: tuple[int, int, int, int],
                geom: PillGeometry) -> np.ndarray:
    """Recorte de la fila de estrellas, anclado al pill según la geometría del panel."""
    x1, y1, x2, y2 = pill_bbox
    xa = x1 if geom.stars_x_from == "x1" else x2
    ya = y1 if geom.stars_y_from == "y1" else y2
    return frame[max(0, ya + geom.stars_dy[0]):ya + geom.stars_dy[1],
                 max(0, xa + geom.stars_dx[0]):xa + geom.stars_dx[1]]


def read_refinamiento(frame: np.ndarray, pill_bbox: tuple[int, int, int, int],
                      geom: PillGeometry = _S26_PILL) -> int | None:
    """Refinamiento 1-5 contando estrellas BLANCAS entre las 5 de la fila, o None.

    Devuelve None si no se detectan exactamente 5 estrellas. Es deliberado: sin las 5 no se sabe
    si falta una gris (y el conteo de blancas sigue siendo válido) o si el recorte quedó mal
    ubicado (y entonces cualquier número sería inventado). RNF-02.
    """
    try:
        band = _stars_band(frame, pill_bbox, geom)
        if band.size == 0:
            return None
        hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        poco_sat = hsv[:, :, 1] < 60
        runs = _star_runs((hsv[:, :, 2] > 90) & poco_sat)
        if len(runs) != 5:
            return None
        blanco = (hsv[:, :, 2] > 200) & poco_sat
        llenas = sum(1 for a, b in runs if float(blanco[:, a:b].mean()) > _STAR_LLENA_MIN)
        return llenas if 1 <= llenas <= 5 else None
    except Exception:
        return None


def read_rareza(frame: np.ndarray, pill_bbox: tuple[int, int, int, int],
                geom: PillGeometry = _S26_PILL) -> str | None:
    """Rareza S/A/B por el hue del badge circular a la izquierda del pill de nivel, o None."""
    try:
        x1, y1, _, y2 = pill_bbox
        cx, cy = x1 + geom.badge_dx, (y1 + y2) // 2
        roi = frame[cy - _BADGE_R:cy + _BADGE_R, cx - _BADGE_R:cx + _BADGE_R]
        if roi.size == 0:
            return None
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        m = (hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 90)
        if int(m.sum()) < _BADGE_PX_MIN:
            return None
        hue = float(np.median(hsv[:, :, 0][m]))
        for rar, (lo, hi) in _BADGE_HUE.items():
            if lo <= hue <= hi:
                return rar
        return None
    except Exception:
        return None


@dataclass
class OwnerBadge:
    """Badge del dueño en el panel de arma. Presencia y nombrado van SEPARADOS a propósito
    (la lección del falso-LIBRE, ver `badge_surface`): decir "hay una cara" es mucho más fácil
    que decir de quién es, y el feature que pidió esto solo necesita lo primero."""

    present: bool
    nitidez: float                      # |Laplaciano| medio dentro del disco (la evidencia)
    crop: np.ndarray | None = None      # recorte para nombrar; None si Hough no cerró el círculo


def read_weapon_owner_badge(frame: np.ndarray,
                            pill_bbox: tuple[int, int, int, int] | None) -> OwnerBadge | None:
    """¿Tiene dueño el arma del panel? Anclado al pill de nivel. None si no hay ancla.

    `present=False` en este panel significa **arma libre**: nadie la tiene equipada, y por eso el
    juego no pide confirmación al equiparla (a diferencia del arma de otro PJ, que abre el diálogo
    S23). Ese era el agujero: sin esta señal no se puede distinguir "libre" de "la tiene otro".

    El `crop` conserva el encuadre de `crop_detail_badge` (Hough + `_DET_HOUGH_PAD`) a propósito:
    la librería `avatar_detbadge_v2` se cosechó así y un recorte distinto la volvería inútil para
    nombrar. Lo que cambia es **dónde se busca** y **cómo se decide que hay algo**.

    ## Por qué anclado y no una franja fija

    `crop_detail_badge` busca en `_DET_REGION`, una franja de coordenadas normalizadas FIJAS —
    la misma trampa que ya costó cara con la fila de estrellas: el panel se corre verticalmente
    cuando el nombre del arma envuelve a dos líneas. Con la franja fija, Ejemplo_34 y Ejemplo_39
    dan **falso LIBRE** teniendo avatar: el círculo entra cortado por el borde del recuadro, así
    que lo que se mide no es el avatar. Anclado al pill entran los 28 enteros, con un offset
    rígido de ±2 px en cada eje (de ahí que la ROI de búsqueda sea chica y aun así holgada).

    ## Por qué nitidez y no saturación

    Ver `_OWNER_NITIDEZ_MIN`: cuatro armas libres tienen un resplandor del arte del arma detrás
    del hueco del badge que produce blobs saturados más grandes que los de varios avatares
    reales. Brillo y saturación miden ese resplandor; la nitidez lo ignora.
    """
    if frame is None or getattr(frame, "size", 0) == 0 or not pill_bbox:
        return None
    try:
        H, W = frame.shape[:2]
        _, y1, x2, y2 = pill_bbox
        cx, cy = x2 + _OWNER_DX, (y1 + y2) // 2 + _OWNER_DY
        x0, x1 = cx - _OWNER_SEARCH, cx + _OWNER_SEARCH
        ry0, ry1 = cy - _OWNER_SEARCH, cy + _OWNER_SEARCH
        if x0 < 0 or ry0 < 0 or x1 > W or ry1 > H:
            return None
        sub = frame[ry0:ry1, x0:x1]
        if sub.size == 0:
            return None
        gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY).astype(np.float32)
        n = 2 * _OWNER_SEARCH
        yy, xx = np.mgrid[0:n, 0:n]
        disco = ((xx - _OWNER_SEARCH) ** 2 + (yy - _OWNER_SEARCH) ** 2) < _OWNER_DISCO_R ** 2
        nitidez = float(np.abs(cv2.Laplacian(gray, cv2.CV_32F))[disco].mean())
        if nitidez < _OWNER_NITIDEZ_MIN:
            return OwnerBadge(present=False, nitidez=nitidez)
        # Hay cara. El crop para nombrar es un extra: si Hough no cierra el círculo se devuelve
        # `present=True` igual — perder el nombre no debe convertir un arma con dueño en libre.
        blur = cv2.medianBlur(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), 3)
        circles = cv2.HoughCircles(
            blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=int(0.05 * W),
            param1=120, param2=22,
            minRadius=int(_DET_HOUGH_RMIN_F * W), maxRadius=int(_DET_HOUGH_RMAX_F * W),
        )
        crop = None
        if circles is not None:
            c0 = circles[0][0]
            ccx, ccy = int(x0 + c0[0]), int(ry0 + c0[1])
            r = int(c0[2] * _DET_HOUGH_PAD)
            if r >= 8:
                c = frame[max(0, ccy - r):min(H, ccy + r), max(0, ccx - r):min(W, ccx + r)]
                crop = c if c.size else None
        return OwnerBadge(present=True, nitidez=nitidez, crop=crop)
    except Exception:
        return None


# Tenencia del arma del panel. Habla del ARMA, no del slot destino (que es lo que dice el botón).
TENENCIA = ("equipada", "otro_pj", "libre", "incierto")


def clasificar_tenencia(boton: str | None,
                        badge: OwnerBadge | None,
                        badge_nombre: str | None,
                        pj_en_pantalla: str | None) -> tuple[str, str | None]:
    """Cruza las DOS señales independientes y devuelve `(tenencia, dueño)`.

    Mismo diseño de pinza que el disco libre (`_check_libre_equipado`): cada señal tapa el
    agujero de la otra, y ninguna alcanza sola.

      · **El botón** (`read_s17_action_button`) habla del SLOT DESTINO, no del arma: dice si el
        PJ que estás mirando tiene algo puesto ahí. Es texto en posición fija — la lectura más
        robusta que hay en este panel (40/40 en los fixtures) — pero no sabe de quién es el arma.
      · **El badge** (`read_weapon_owner_badge`) dice si el arma tiene dueño, pero no quién,
        salvo que la librería lo resuelva (hoy casi nunca: le faltan PJs).

    Cruzadas dan lo que ninguna da sola. La clave es que 'Desequipar' **identifica al dueño con
    certeza y sin librería**: si el juego te ofrece desequiparla, la lleva puesta el PJ que estás
    mirando, y a ese lo sabemos por el latch de identidad. Es la única vía de dueño certero
    mientras `avatar_detbadge_v2` siga incompleta.

    'Equipar'/'Reemplazar' dicen lo contrario —no la tiene este PJ— y ahí decide el badge:
    con avatar es de otro, sin avatar está libre. Esa distinción es la que importa río abajo,
    porque **equipar un arma libre no abre diálogo de confirmación** y la de otro PJ sí (S23).
    """
    presente = None if badge is None else badge.present
    if boton == "desequipar":
        # El badge no se consulta: 'Desequipar' es prueba directa. Si además hubiera un badge
        # ausente sería un falso LIBRE, y este orden lo neutraliza (presencia gana a libre).
        return "equipada", pj_en_pantalla
    if presente is None:
        return "incierto", None
    if not presente:
        return "libre", None
    if boton in ("equipar", "reemplazar"):
        return "otro_pj", badge_nombre
    # Hay dueño pero sin botón no se puede saber si es el PJ en pantalla u otro.
    return "incierto", badge_nombre


def _primera_fila(candidatas: list[_Line]) -> list[_Line]:
    """Recorta una sección a su PRIMERA fila visual (etiqueta + valor, que van a la misma altura).

    Dos motivos, los dos medidos sobre los fixtures:

    · Un arma tiene un solo atributo principal y un solo avanzado, así que la primera fila es
      todo lo que hay. Acotar evita depender del header de la sección siguiente como piso: si el
      OCR no lee "Efecto de amplificador", el límite queda en infinito y entraría el texto de la
      PASIVA — que es largo y lleno de números ("aumenta el Ataque en un 3.5 % durante 8 s") y
      produciría un stat inventado.

    · La tolerancia es en Y y no un orden: PaddleOCR devuelve el número con un `y1` unos píxeles
      menor que su etiqueta, así que "misma fila" no significa "mismo y1".
    """
    if not candidatas:
        return []
    y0 = min(ln.y1 for ln in candidatas)
    alto = max(1, max(ln.y2 - ln.y1 for ln in candidatas))
    return [ln for ln in candidatas if ln.y1 - y0 <= 0.8 * alto]


def parse_weapon_s26_from_lines(
    lines: list[tuple[str, float, tuple[int, int, int, int]]],
    W: int,
    H: int,
    catalogo: Sequence[str] | None = None,
    layout: PanelLayout = _S26_LAYOUT,
    frame: np.ndarray | None = None,
    pill_geom: PillGeometry = _S26_PILL,
) -> WeaponParsed:
    """Core testeable: parsea el panel a partir de las líneas OCR con bbox.

    Separado del OCR a propósito, igual que `_parse_s17_from_lines`: permite testear con líneas
    cacheadas sin re-correr Paddle (que es lo caro).

    `frame` opcional: si se pasa, se leen además rareza y refinamiento por píxeles (necesitan la
    imagen). Los tests del core puro lo omiten y esos dos campos quedan en None.
    """
    out = WeaponParsed()
    L = [_Line(t, c, bb, W) for (t, c, bb) in lines]
    detail = [ln for ln in L if layout.band_min <= ln.xn <= layout.band_max]
    detail.sort(key=lambda ln: (ln.y1, ln.x1))
    if not detail:
        out.notas.append("panel_vacio")
        return out

    # --- Headers de sección (delimitadores en Y) ---
    # Prefijos tolerantes por la misma razón que en S17: el OCR sobre crop nativo trunca o funde
    # los headers ("Atributos avanzados" → "Atributosavanzado").
    y_main = y_avanz = y_efecto = None
    header_ys: set[int] = set()
    for ln in detail:
        k = _norm_key(ln.txt)
        if y_main is None and k.startswith("atributoprincip"):
            y_main = ln.y1; header_ys.add(ln.y1)
        elif y_avanz is None and k.startswith("atributosavanzad"):
            y_avanz = ln.y1; header_ys.add(ln.y1)
        elif y_efecto is None and k.startswith("efectodeamplific"):
            y_efecto = ln.y1; header_ys.add(ln.y1)

    if y_main is None or y_avanz is None:
        out.notas.append("s26_headers_no_detectados")
    _ymain = y_main if y_main is not None else 10**9
    _yavanz = y_avanz if y_avanz is not None else 10**9
    _yefecto = y_efecto if y_efecto is not None else 10**9

    confs: list[float] = []

    # --- Nivel / máximo ---
    # El bbox del pill se guarda porque es el ANCLA de la rareza y del refinamiento: las dos se
    # leen por píxeles en posiciones relativas a él, no en coordenadas fijas.
    linea_nivel_y: int | None = None
    pill_bbox: tuple[int, int, int, int] | None = None
    for ln in detail:
        m = _RE_NIVEL_ARMA.search(_strip(ln.txt))
        if m:
            out.nivel, out.nivel_max = int(m.group(1)), int(m.group(2))
            linea_nivel_y = ln.y1
            pill_bbox = (ln.x1, ln.y1, ln.x2, ln.y2)
            out.pill_bbox = pill_bbox
            confs.append(ln.conf)
            break
    if out.nivel is None:
        out.notas.append("nivel_no_leido")

    # --- Nombre: lo que está ARRIBA del nivel (y de 'Atributo principal') ---
    # Se toma como techo el mínimo de los dos porque el nombre puede envolver a 2 líneas y
    # anclar solo en el header dejaría entrar el pill de nivel.
    techo = min(_ymain, linea_nivel_y if linea_nivel_y is not None else 10**9)
    nombre_lines = [
        ln for ln in detail
        if ln.y1 < techo and ln.y1 not in header_ys
        and not _RE_NIVEL_ARMA.search(_strip(ln.txt))
    ]
    out.nombre_raw = " ".join(ln.txt.strip() for ln in nombre_lines).strip()
    confs.extend(ln.conf for ln in nombre_lines)
    if not out.nombre_raw:
        out.notas.append("nombre_no_leido")
    out.nombre_canon = match_catalogo(out.nombre_raw, catalogo)
    if out.nombre_raw and out.nombre_canon is None and catalogo:
        out.notas.append("nombre_fuera_del_catalogo")

    # --- Atributo principal: "Ataque Base N" ---
    # `>` estricto excluye el header; el label "Ataque Base" NO es header y tiene que entrar.
    seccion_main = _primera_fila([ln for ln in detail if _ymain < ln.y1 < _yavanz])
    if seccion_main:
        valores_main = [ln for ln in seccion_main if ln.xn >= layout.col_split]
        for ln in valores_main:
            m = _RE_SOLO_NUMERO.search(ln.txt)
            if m:
                out.atk_base = int(m.group(1))
                break
        if out.atk_base is None:
            # El OCR fundió etiqueta y valor: se busca en el texto unido, en los dos órdenes.
            m = _RE_ATK_BASE_FUNDIDA.search(_strip(" ".join(ln.txt for ln in seccion_main)))
            if m:
                out.atk_base = int(m.group(1) or m.group(2))
        if out.atk_base is not None:
            confs.extend(ln.conf for ln in seccion_main)
    if out.atk_base is None:
        out.notas.append("atk_base_no_leido")

    # --- Atributo avanzado: nombre en la columna izquierda, valor en la derecha ---
    seccion_avanz = _primera_fila(
        [ln for ln in detail if _yavanz < ln.y1 < _yefecto and ln.y1 not in header_ys])
    if seccion_avanz:
        nombres = [ln for ln in seccion_avanz if ln.xn < layout.col_split]
        valores = [ln for ln in seccion_avanz if ln.xn >= layout.col_split]
        crudo_nombre = " ".join(ln.txt.strip() for ln in nombres).strip()
        crudo_valor = " ".join(ln.txt.strip() for ln in valores).strip()
        if not crudo_valor:
            # El OCR fundió nombre y valor en una sola línea: se parten por regex.
            m2 = _RE_STAT_VALOR.match(" ".join(crudo_nombre.split()))
            if m2:
                crudo_nombre, crudo_valor = m2.group("nombre").strip(), m2.group("valor")
        valor, unidad = _parse_valor(crudo_valor)
        out.stat_avanzado_valor, out.stat_avanzado_unidad = valor, unidad
        if crudo_nombre:
            out.stat_avanzado_canon = _canon_with_unit(crudo_nombre, unidad)
        confs.extend(ln.conf for ln in seccion_avanz)
    if out.stat_avanzado_canon is None or out.stat_avanzado_valor is None:
        out.notas.append("stat_avanzado_incompleto")

    # --- Rareza y refinamiento (píxeles, anclados al pill) ---
    if frame is not None and pill_bbox is not None:
        out.rareza = read_rareza(frame, pill_bbox, pill_geom)
        out.refinamiento = read_refinamiento(frame, pill_bbox, pill_geom)
        if out.rareza is None:
            out.notas.append("rareza_no_leida")
        if out.refinamiento is None:
            out.notas.append("refinamiento_no_leido")
        # Corroboración independiente: al máximo, el ATK base determina la rareza por sí solo. Se
        # ANOTA la discrepancia en vez de resolverla — el badge es una lectura directa y el ATK
        # una inferencia, así que no hay motivo para que la inferencia gane; pero callarla sería
        # perder la única verificación cruzada que tenemos.
        if out.rareza and out.al_maximo and out.atk_base in _ATK_MAX_POR_RAREZA:
            por_atk = _ATK_MAX_POR_RAREZA[out.atk_base]
            if por_atk != out.rareza:
                out.notas.append(f"rareza_discrepa_atk:badge={out.rareza},atk={por_atk}")

    out.confianza = round(sum(confs) / len(confs), 3) if confs else 0.0
    return out


def parse_weapon_s26(
    frame: np.ndarray,
    ocr: "OcrBackend",
    catalogo: Sequence[str] | None = None,
) -> WeaponParsed:
    """OCRea el panel de S26 y lo parsea (incluye rareza y refinamiento)."""
    H, W = frame.shape[:2]
    return parse_weapon_s26_from_lines(
        _ocr_detail_lines(frame, ocr), W, H, catalogo=catalogo, frame=frame)


def parse_weapon_s30(
    frame: np.ndarray,
    ocr: "OcrBackend",
    catalogo: Sequence[str] | None = None,
) -> WeaponParsed:
    """El MISMO parser, contra el panel derecho del inventario de amplificadores (S30).

    Las dos pantallas describen un arma con las mismas secciones ("Atributo principal",
    "Atributos avanzados", "Efecto de amplificador"), así que reusar el parser no es un atajo: es
    la misma gramática. Lo único distinto es dónde vive el panel y cómo se acomodan el badge y las
    estrellas alrededor del pill, y las dos cosas ya son parámetros.

    Medido sobre los 6 fixtures: nombre, nivel/máximo, ATK base y stat avanzado salen **6/6**; con
    la geometría del inventario, rareza y refinamiento también.

    Ojo con el nombre crudo: acá el OCR lo maltrata más que en el detalle (`Uitimacena` por
    "Última cena", `Calderodela claridad`). Es `nombre_raw` a propósito — la canonización va
    contra el catálogo con `match_catalogo`, nunca por comparación exacta.
    """
    H, W = frame.shape[:2]
    return parse_weapon_s26_from_lines(
        _ocr_s9_detail_lines(frame, ocr), W, H, catalogo=catalogo, frame=frame,
        layout=_S9_LAYOUT, pill_geom=_S30_PILL)
