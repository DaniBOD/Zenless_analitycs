"""El contador `N/M` del header de la mochila — el denominador de los censos de inventario.

`Pistas de disco [339/3000]` en el inventario de discos (S9), `Amplificadores [57/2000]` en el de
armas (S30). **Es la misma línea de la misma pantalla**, en la misma posición: lo único que cambia
es el rótulo y la capacidad.

Es lo que el censo del roster no tiene. El menú de personajes no trae `N/M`, así que allá el cierre
lo declara el usuario (F8). Acá el denominador está escrito en pantalla, igual que el `N/300` del
desmontaje, y vale la misma doctrina: **el contador es la autoridad del conteo**; la grilla sólo
aparea, porque el viewport no ve todo el inventario.

## Por qué vive acá y no en `parser_disc_s17`

Este header es de la MOCHILA, no de los discos. `detector.py` ya lo trata como compartido —
`_read_inventory_header` sirve a `_verify_s9` y a `_verify_s30`, con caché por frame justamente
porque los dos pagaban el mismo OCR. Que el flujo de armas importara un parser de discos para leer
su propio contador mentiría sobre a quién pertenece.

## El rótulo NO es el ancla; la capacidad sí

Podría parecer que hay que reconocer la palabra ("Pistas de disco" / "Amplificadores"), y sería un
problema: `detector.py` documenta que PaddleOCR nunca lee "Amplificadores" limpio (`Amoplificadores`
×4, `Amolificadores` ×2 sobre 6 fixtures), y por eso allá el ancla es la cola `lificador`.

Pero acá el rótulo no se usa para nada. El ancla es **la capacidad**: sin ella, cualquier par de
números de cualquier pantalla se leería como un inventario — la batería del header superior dice
`237/240`. Con ella, `2000` y `3000` se distinguen solos, y de paso una pantalla no puede hacerse
pasar por la otra.

Medido sobre las 10 capturas reales de `Engines_Triggers/Inventario_general_engines`: la ROI
calibrada para discos contiene el header de armas y Paddle lee `/2000` limpio **10 de 10**. Igual
que en discos (14/14). Por eso NO hay `str.translate` acá: si algún día aparece un `2O00`, ese es
el momento de agregarlo, no antes (RNF-02 — no se inventan arreglos para fallas no observadas).
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.core.ocr_backend import OcrBackend

log = logging.getLogger(__name__)

#: ROI del header, normalizada (x, y, w, h). La misma para las dos pantallas: es la misma línea.
HEADER_ROI = (0.030, 0.100, 0.220, 0.050)

#: Capacidades de la mochila por tipo de inventario. Son el ANCLA de la lectura (ver docstring).
CAPACIDAD_DISCOS = 3000
CAPACIDAD_ARMAS = 2000


def _regex(capacidad: int) -> re.Pattern[str]:
    """Compila (y cachea) el patrón para una capacidad. Cacheado porque el contador se lee con
    cadencia propia durante toda una pasada de censo."""
    pat = _CACHE.get(capacidad)
    if pat is None:
        pat = re.compile(r"(\d{1,4})\s*/\s*" + str(capacidad) + r"(?!\d)")
        _CACHE[capacidad] = pat
    return pat


_CACHE: dict[int, re.Pattern[str]] = {}


def counter_from_text(text: str, capacidad: int) -> int | None:
    """Extrae `N` de un `N/<capacidad>`. `None` si no aparece el ancla o el número es imposible."""
    if not text:
        return None
    m = _regex(capacidad).search(text)
    if m is None:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return n if 0 <= n <= capacidad else None


def parse_inventory_counter(frame: np.ndarray, ocr: OcrBackend, capacidad: int) -> int | None:
    """Cuántos ítems tiene la cuenta, según el header del inventario.

    `None` significa **"no se pudo leer"**, no "cero": quien lo consuma debe declarar el total
    desconocido en vez de sustituirlo por lo que alcanzó a contar en la grilla (que subcuenta
    siempre, porque el viewport no ve todo).
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    try:
        from app.core.capturer import crop_roi
        crop = crop_roi(frame, HEADER_ROI)
        if crop is None or getattr(crop, "size", 0) == 0:
            return None
        rows = ocr.text_with_bboxes(crop)
        if not rows:
            return None
        return counter_from_text(" ".join(t for t, _c, _b in rows), capacidad)
    except Exception:
        log.debug("No se pudo leer el contador del header del inventario", exc_info=True)
        return None
