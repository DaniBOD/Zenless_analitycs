"""Las pantallas de W-Engine NO deben producir datos de disco.

La pantalla de detalle de un arma es, para el detector, **indistinguible** de la de un disco:
matchea el mismo template `s17_personalizacion_pistas.png` a 1.000. Lo mismo pasa con el
inventario de armas (S9) y con el diálogo de reemplazo de arma (S23 a 0.999, y **pasando**
`_verify_s23`).

Hoy nada se rompe, pero por **accidente**, no por diseño:

  · `parse_disc_s17` / `parse_disc_s9` se abstienen porque `disc_is_mature()` exige
    `slot ∈ 1..6` y los substats esperados, y el panel de un arma no tiene ninguna de las dos
    cosas (`slot=0`, `subs=[]`).

    Ojo con las condiciones que NO protegen, para no confiarse:
      - el nombre: el gate acepta `set_name_raw`, y el arma lo llena ('Petrazufre Nivel 60/60').
        Los discos reales maduran con `set_name_canon=None`, así que canonizar no es requisito.
      - `main_valor`: el arma lo llena con el "Ataque Base" (684).
      - la confianza: `confianza_global` da 0.97-0.99 sobre frames de arma.
    O sea que de las cuatro condiciones del gate, dos ya las cumple un arma.

  · `parse_sustitucion` se abstiene porque `_RE_SUSTITUCION` exige el `(N)` del slot:
    el diálogo de disco dice "... equipa actualmente Jazz caótico (2). ¿Deseas sustituirlo?"
    y el de arma "... equipa actualmente Rotor de cañón. ¿Deseas sustituirlo?" — sin slot.

Por qué importa: **S23 escribe la DB** (mueve un disco entre PJs) y S17 es donde se confirma
ese swap. Aflojar el gate de madurez o volver opcional el slot en la regex —dos cambios que
parecen inocentes— abriría una escritura mala sin que nada avise.

Estos tests fijan esa abstención como CONTRATO. Si alguno cae, el cambio que lo hizo caer
necesita antes un discriminador arma/disco explícito (RF-15 H1: el estado S26).

Los fixtures de `Engines_Triggers/` son locales (gitignoreados, ~150 MB), así que todo es
skip-if-absent — la convención del repo para verdad de tierra pesada.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_disc_s17 import disc_is_mature, parse_disc_s17, parse_disc_s9
from app.core.parser_sustitucion import parse_sustitucion

_ROOT = Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
_ENG = _ROOT / "Engines_Triggers"

_DETALLE = sorted((_ENG / "Engine_vista_detallada_pj").glob("Ejemplo_*.png"))
_INVENTARIO = sorted((_ENG / "Inventario_general_engines").glob("Ejemplo_*.png"))
_REEMPLAZO = sorted((_ENG / "Reemplazo_engine").glob("Ejemplo_*.png"))
# Control positivo: el diálogo de DISCO, que sí debe parsear.
_SWAP_DISCO = sorted((_ROOT / "Discos_Triggers" / "15_sustitucion_disco_confirmacion")
                     .glob("Ejemplo_*.png"))[:3]


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@lru_cache(maxsize=1)
def _paddle():
    """Un solo backend para todo el módulo: instanciarlo por test cargaría los modelos
    ~50 veces."""
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:  # pragma: no cover - depende del entorno
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


# --- Detalle de arma vs. parser de disco equipado (S17) -----------------------------------


@pytest.mark.skipif(not _DETALLE, reason="capturas de W-Engine no presentes")
@pytest.mark.parametrize("fx", _DETALLE, ids=lambda p: p.stem)
def test_detalle_de_arma_no_produce_disco_maduro(fx):
    """Ninguno de los 40 frames de detalle de arma puede madurar como disco.

    Es el cruce más peligroso: S17 es donde se CONFIRMA el swap pendiente de S23 y se
    escribe la DB. La abstención hoy la sostiene `disc_is_mature`, no el detector.
    """
    d = parse_disc_s17(_load(fx), _paddle())
    assert not disc_is_mature(d), (
        f"{fx.name} maduró como disco: set={d.set_name_canon!r} slot={d.slot} "
        f"nivel={d.nivel} subs={len(d.subs or [])}"
    )


@pytest.mark.skipif(not _DETALLE, reason="capturas de W-Engine no presentes")
def test_las_dos_condiciones_que_sostienen_la_abstencion():
    """Las condiciones LOAD-BEARING, afirmadas aparte y por separado.

    `disc_is_mature` pide cuatro cosas y un arma ya cumple dos (nombre crudo y `main_valor`).
    Lo único que la frena es que el panel de un arma **no tiene slot ni substats**. Si el
    test de arriba cae algún día, este dice cuál de las dos se perdió — y si alguien agrega
    un fallback de slot para S17, cae este primero, que es el que explica el riesgo.
    """
    ocr = _paddle()
    con_slot = []
    con_subs = []
    for p in _DETALLE:
        d = parse_disc_s17(_load(p), ocr)
        if 1 <= d.slot <= 6:
            con_slot.append((p.name, d.slot))
        if d.subs:
            con_subs.append((p.name, len(d.subs)))
    assert not con_slot, f"frames de arma con slot de disco válido: {con_slot}"
    assert not con_subs, f"frames de arma con substats de disco: {con_subs}"


# --- Inventario de armas vs. parser del inventario de discos (S9) --------------------------


@pytest.mark.skipif(not _INVENTARIO, reason="capturas del inventario de armas no presentes")
@pytest.mark.parametrize("fx", _INVENTARIO, ids=lambda p: p.stem)
def test_inventario_de_armas_no_produce_disco_maduro(fx):
    """El inventario de armas clasifica S9 (0.855-0.864) igual que el de discos; el parser
    del panel derecho debe abstenerse."""
    d = parse_disc_s9(_load(fx), _paddle())
    assert not disc_is_mature(d), (
        f"{fx.name} maduró como disco: set={d.set_name_canon!r} raw={d.set_name_raw!r}"
    )


# --- Diálogo de reemplazo de arma vs. parser de sustitución (S23) ---------------------------


@pytest.mark.skipif(not _REEMPLAZO, reason="capturas del reemplazo de arma no presentes")
@pytest.mark.parametrize("fx", _REEMPLAZO, ids=lambda p: p.stem)
def test_dialogo_de_arma_no_parsea_como_sustitucion_de_disco(fx):
    """El diálogo de reemplazo de ARMA pasa `_verify_s23` (texto "sustituir") y llega al
    handler que escribe la DB. Lo único que lo frena es que la regex exige el `(N)` del slot.

    Si alguna vez el slot se vuelve opcional para tolerar OCR malo, esto se rompe y el
    sistema movería un disco inexistente entre PJs.
    """
    assert parse_sustitucion(_load(fx), _paddle()) is None, (
        f"{fx.name} parseó como sustitución de disco"
    )


@pytest.mark.skipif(not _SWAP_DISCO, reason="capturas del swap de disco no presentes")
@pytest.mark.parametrize("fx", _SWAP_DISCO, ids=lambda p: p.stem)
def test_control_el_dialogo_de_disco_si_parsea(fx):
    """Control positivo. Sin esto, los tests de arriba pasarían igual con el parser roto."""
    d = parse_sustitucion(_load(fx), _paddle())
    assert d is not None, f"{fx.name} NO parseó — el parser está roto, no abstiéndose"
    assert 1 <= d.slot <= 6
