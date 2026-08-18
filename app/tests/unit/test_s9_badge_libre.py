"""S9: distinguir un disco LIBRE de un tile que no se pudo leer.

Hasta acá las dos cosas salían igual —`crop_s9_selected_badge` devolvía `None`— y esa igualdad es
lo que bloquea el censo de discos: **72 de 367 discos no tienen dueño**, y sin poder afirmar "este
disco está libre" el sistema no puede persistirlos sin arriesgarse a inventar un equipamiento.

Lo notable es que la información no faltaba: la función ya sabía cuál de los dos casos era y lo
tiraba al colapsar ambos en `None`.

## Por qué NITIDEZ y no el gate que ya estaba

El gate `_grid_badge_present` pide blob saturado + anillo de Hough. Medido sobre estos mismos
fixtures, da `True` en los **4 libres**: la esquina de un tile libre tiene la barra amarilla de
nivel y el arte gris del disco, con saturación y circularidad de sobra. Es el hallazgo que ya
estaba escrito para S17 (`audit/free_disc_presence_validation_20260620.md`: *"no existe umbral que
la separe"*) y para las armas en RF-15 (*"el área saturada SE SOLAPA"*).

La nitidez (|Laplaciano| medio del disco interior) mide otra cosa: **una cara tiene detalle, un
degradé no tiene ninguno**. Medido sobre los 11 tiles etiquetados de este folder:

    equipado   55.89 – 81.44
    libre      12.51 – 15.70        gap 3.56×

Y sobre los 504 tiles de la grilla completa de los 14 fixtures, la distribución es bimodal con la
franja **20–35 literalmente vacía** (0 muestras). El umbral de 30 no está afinado al borde: está en
el medio de un hueco.
"""
from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")

REPO = Path(__file__).resolve().parents[3]
_S9 = REPO / "Documentacion/Screenshots_Triggers/Discos_Triggers/09_Inventario_discos_general"

# Etiquetado a ojo sobre el montaje de los recortes (scratchpad `s9_badges_montaje.png`).
_CON_DUENO = ["Ejemplo_1", "Ejemplo_3", "Ejemplo_7", "Ejemplo_9",
              "Ejemplo_11", "Ejemplo_13", "Ejemplo_14"]
_LIBRES = ["Ejemplo_2", "Ejemplo_8", "Ejemplo_10", "Ejemplo_12"]
# El tile seleccionado no se localiza (no hay recuadro resaltado visible en el recorte de grilla).
_SIN_TILE = ["Ejemplo_4", "Ejemplo_5", "Ejemplo_6"]


def _frame(stem: str):
    p = _S9 / f"{stem}.png"
    if not p.exists():
        pytest.skip(f"falta el fixture {p.name}")
    return cv2.imread(str(p))


def _leer(stem: str):
    from app.core.detector import read_s9_selected_badge
    return read_s9_selected_badge(_frame(stem))


# --- los tres estados -------------------------------------------------------------------------

@pytest.mark.parametrize("stem", _CON_DUENO)
def test_un_disco_equipado_reporta_dueno_y_trae_el_recorte(stem):
    from app.core.detector import BADGE_CON_DUENO
    b = _leer(stem)
    assert b.estado == BADGE_CON_DUENO
    assert b.crop is not None, "sin recorte no hay a quién nombrar"


@pytest.mark.parametrize("stem", _LIBRES)
def test_un_disco_libre_lo_dice_en_vez_de_callarse(stem):
    from app.core.detector import BADGE_LIBRE
    b = _leer(stem)
    assert b.estado == BADGE_LIBRE
    assert b.crop is None, "no hay cara que recortar; devolverla invitaría a nombrar el arte"


@pytest.mark.parametrize("stem", _SIN_TILE)
def test_sin_tile_localizado_NO_es_libre(stem):
    """El punto entero. `no_localizado` significa 'no pude leer'; `libre`, 'leí y no hay nadie'.
    Tratar al primero como el segundo es lo que dejaría un disco equipado registrado como suelto."""
    from app.core.detector import BADGE_NO_LOCALIZADO
    b = _leer(stem)
    assert b.estado == BADGE_NO_LOCALIZADO
    assert b.nitidez is None, "no se midió nada: no había dónde medir"


# --- por qué hizo falta una métrica nueva -----------------------------------------------------

@pytest.mark.parametrize("stem", _LIBRES)
def test_el_gate_VIEJO_daba_presencia_en_los_libres(stem):
    """Regresión documentada, no aspiracional: fija que el gate por saturación + Hough se equivoca
    en estos cuatro. Si algún día alguien propone volver a él, este test dice por qué no."""
    import numpy as np

    from app.core import detector as D
    f = _frame(stem)
    bb = D._selected_grid_tile_bbox(f, D._S9_GRID_REGION)
    assert bb is not None
    tx, ty, tw, th = bb
    cx, cy, r = int(tx + D._BADGE_CX_F * tw), int(ty + D._BADGE_CY_F * th), int(D._BADGE_R_F * tw)
    H, W = f.shape[:2]
    crop = f[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
    assert isinstance(crop, np.ndarray) and crop.size
    assert D._grid_badge_present(crop) is True, \
        "si esto pasa a False, el gate mejoró y este test pierde sentido — revisar, no borrar"


def test_la_nitidez_separa_las_dos_clases_con_margen():
    """La calibración, medida acá y no copiada de un comentario. El umbral tiene que caer en el
    hueco, no rozar ninguno de los dos extremos."""
    from app.core.detector import _S9_BADGE_NITIDEZ_MIN
    con = [_leer(s).nitidez for s in _CON_DUENO]
    libres = [_leer(s).nitidez for s in _LIBRES]
    assert max(libres) < _S9_BADGE_NITIDEZ_MIN < min(con)
    assert min(con) / max(libres) > 2.5, "el gap se achicó — recalibrar antes de confiar"


# --- el contrato viejo sigue en pie -----------------------------------------------------------

@pytest.mark.parametrize("stem", _LIBRES + _SIN_TILE)
def test_crop_s9_selected_badge_sigue_devolviendo_None_cuando_no_hay_dueno(stem):
    """La API vieja no cambia de forma: lo que cambia es que ahora, además, se puede preguntar
    POR QUÉ es None."""
    from app.core.detector import crop_s9_selected_badge
    assert crop_s9_selected_badge(_frame(stem)) is None


@pytest.mark.parametrize("stem", _CON_DUENO)
def test_crop_s9_selected_badge_sigue_recortando_a_los_equipados(stem):
    from app.core.detector import crop_s9_selected_badge
    assert crop_s9_selected_badge(_frame(stem)) is not None
