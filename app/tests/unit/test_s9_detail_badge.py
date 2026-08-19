"""S9: el avatar del panel de detalle como SEGUNDA superficie para nombrar al dueño.

La grilla no alcanza. Medido el 2026-08-18 en vivo, el badge de un disco de Soukaku da:

    Ben      sim=0.897
    Soukaku  sim=0.897      margen 0.000  → el matcher se abstiene

Y no es un umbral mal puesto: en la superficie `grid`, Ben y Soukaku están separados **1,04–1,14×**
(las refs de Ben están casi tan dispersas entre sí como respecto a Soukaku), así que no existe
umbral que los distinga. En la superficie `detail` la separación por histograma de color es
**8,87×**. La información está; simplemente no se estaba mirando.

Cuando el dueño no se puede nombrar, `persist_s17_disc` descarta el disco entero — se pierden set,
slot, nivel y los cuatro substats, que sí se leyeron bien. Medido: 3 de 38 discos (8 %) en la
corrida real.

## Los dos señuelos de la ROI

El panel derecho tiene tres círculos y sólo uno es el avatar:

    hexágono del nº de slot   izquierda, gris     (sat ~12)
    badge dorado de rareza    abajo               (sat ~119)  ← el más saturado de la zona
    AVATAR DEL DUEÑO          derecha, arriba     (sat ~58)

Elegir "el más saturado" agarra siempre el badge de rareza — daba 0.47 constante en los 14
fixtures, incluidos los discos libres que no tienen avatar. **El discriminador es la POSICIÓN**, no
la saturación: es la tercera vez en este proyecto que la saturación no separa lo que parece.

Y el radio es **una constante**, no el de Hough: es un elemento de UI de tamaño fijo, y detectarlo
sólo mete varianza (misma lección que S30). Medido: con r=18 nombra Soukaku a 0.843; con 22, 25, 26
o 30 se abstiene.
"""
from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")

REPO = Path(__file__).resolve().parents[3]
_S9 = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general"

#: Fixtures cuyo panel de detalle SÍ muestra avatar de dueño (verificado a ojo sobre el recorte).
_CON_AVATAR = ["Ejemplo_1", "Ejemplo_3", "Ejemplo_4", "Ejemplo_5", "Ejemplo_7",
               "Ejemplo_9", "Ejemplo_11", "Ejemplo_13", "Ejemplo_14"]
#: Fixtures sin avatar en el detalle (el disco no lo tiene equipado nadie).
_SIN_AVATAR = ["Ejemplo_2", "Ejemplo_6", "Ejemplo_8", "Ejemplo_10", "Ejemplo_12"]


def _frame(stem: str):
    p = _S9 / f"{stem}.png"
    if not p.exists():
        pytest.skip(f"falta {p.name}")
    return cv2.imread(str(p))


# --- localización -----------------------------------------------------------------------------

@pytest.mark.parametrize("stem", _CON_AVATAR)
def test_localiza_el_avatar_cuando_lo_hay(stem):
    from app.core.detector import crop_s9_detail_badge
    assert crop_s9_detail_badge(_frame(stem)) is not None


@pytest.mark.parametrize("stem", _SIN_AVATAR)
def test_no_inventa_avatar_donde_no_lo_hay(stem):
    """Es lo que hacía la versión por saturación: agarraba el badge de rareza y devolvía un recorte
    para TODOS los discos, incluidos los libres."""
    from app.core.detector import crop_s9_detail_badge
    assert crop_s9_detail_badge(_frame(stem)) is None


def test_el_recorte_usa_el_radio_CONSTANTE_y_no_el_de_hough():
    """El avatar es un elemento de UI de tamaño fijo. Medido: r=18 nombra Soukaku a 0.843; con 22,
    25, 26 o 30 el matcher se abstiene. Sacar el radio de Hough sólo mete varianza (lección de
    S30, y por eso `crop_detail_badge` de S17 ya lo hace así)."""
    from app.core.detector import _S9_DET_R, crop_s9_detail_badge
    c = crop_s9_detail_badge(_frame("Ejemplo_3"))
    assert c is not None
    assert c.shape[0] == c.shape[1] == 2 * _S9_DET_R


# --- dónde vive la otra mitad de la verificación ------------------------------------------------
#
# Que las dos superficies COINCIDAN cuando ambas hablan, y que el detalle RESCATE lo que la grilla
# pierde, no se puede testear acá: `conftest._isolate_avatar_library` redirige la librería de
# avatares a un temp para que ningún test toque la del usuario. Esos assert dependen de los DATOS
# (las refs cosechadas), no del código, así que viven en `tools/audit_s9_surfaces.py` — el mismo
# lugar que `measure_badge_lib.py`, por el mismo motivo.
#
# Medido con esa herramienta el 2026-08-18 sobre los 14 fixtures: 5 coincidencias, 0 desacuerdos,
# 3 rescates (Ejemplo_4 y _5 sin tile, Ejemplo_7 abstención por look-alike).
