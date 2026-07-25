"""Censo de tildes de la grilla de Desmontaje (S11) — geometría determinista, sin OCR.

La pantalla de desmontaje muestra una grilla de 9 columnas × 5 filas. Cada tile que el usuario
marcó para destruir lleva un **badge de tilde** (círculo amarillo relleno con un check) en su
esquina superior-derecha. Ese badge es la señal de "este disco se va a desmontar".

**Lo que hace difícil el problema** (y por qué este test es el que gobierna la calibración): el
tile ENFOCADO — el que se está mostrando en el panel DETAIL — lleva además un **aro de
selección** que pasa justo por esa misma esquina, y su color PULSA entre amarillo brillante,
lima y oliva según el frame. Verificado en los fixtures:

    Ejemplo_3 r3c5 → aro amarillo brillante + tilde
    Ejemplo_4 r3c2 → aro lima + tilde        ·  r3c5 → aro oliva + tilde
    Ejemplo_6 r0c0 → aro amarillo brillante y CERO tildes (contador 0/300)

Por eso el discriminante NO puede ser "hay amarillo en la esquina" sino la **fracción de
llenado**: el badge es un disco relleno, el aro es un trazo de pocos píxeles.

`Ejemplo_6` es el test BLOQUEANTE: si esa captura devuelve algún tilde, la calibración está mal
y todo lo que se construya encima (el conteo, la bitácora) miente.

Ground-truth corroborado de forma independiente por el contador `N/300` del header: en
Ejemplo_1/2/6 el nº de tildes visibles coincide exactamente con el contador. En Ejemplo_3/4 el
contador es mayor porque el resto de la selección quedó scrolleada fuera del viewport — que es
justamente el caso que obliga a que la autoridad del conteo sea el contador y no el censo.
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_desmontaje import (
    GRID_COLS,
    GRID_ROWS,
    scroll_pos,
    tilde_cells,
    tilde_fracs,
)

REPO = Path(__file__).resolve().parents[3]
_DIR = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "12_Desmontaje"

# Ground-truth leído a ojo de cada captura, con el contador del header como corroboración.
# (fila, col) 0-indexed, row-major desde arriba-izquierda.
_GT: dict[str, tuple[frozenset[tuple[int, int]], int]] = {
    # nombre                       tildes visibles                              contador
    "Ejemplo_1.png": (frozenset({(0, 0), (0, 1), (0, 2), (0, 3)}), 4),
    "Ejemplo_2.png": (frozenset({(0, 0), (0, 1), (0, 2), (0, 3), (0, 5), (2, 2)}), 6),
    "Ejemplo_3.png": (frozenset({(3, 5)}), 7),                    # 6 fuera del viewport
    "Ejemplo_4.png": (frozenset({(3, 2), (3, 5)}), 8),            # 6 fuera del viewport
    "Ejemplo_6.png": (frozenset(), 0),                            # ⚠ aro brillante, sin tilde
}

# Capturas de la carpeta que NO son la grilla (modales) → nunca deben dar tildes.
_NO_GRILLA = ("Ejemplo_5_(Post_demontaje).png", "Ejemplo_7_(Post_demontaje).png",
              "Ejemplo_8_(Confirmacion).png")


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def _present(name: str) -> bool:
    return (_DIR / name).exists()


@pytest.mark.skipif(not _present("Ejemplo_6.png"), reason="fixture no presente")
def test_el_aro_de_seleccion_no_es_un_tilde():
    """BLOQUEANTE. Ejemplo_6 = pantalla de entrada: contador 0/300, el primer tile con aro
    amarillo BRILLANTE (está en el DETAIL) y ningún disco marcado. Si acá aparece un tilde, el
    detector está leyendo el aro de foco y el conteo entero es mentira."""
    assert tilde_cells(_load(_DIR / "Ejemplo_6.png")) == frozenset()


@pytest.mark.skipif(not _present("Ejemplo_1.png"), reason="fixtures no presentes")
@pytest.mark.parametrize("name", list(_GT), ids=lambda n: n.replace(".png", ""))
def test_tildes_por_celda_ground_truth(name):
    esperado, contador = _GT[name]
    obtenido = tilde_cells(_load(_DIR / name))
    assert obtenido == esperado, f"{name}: sobran {obtenido - esperado}, faltan {esperado - obtenido}"
    # Corroboración independiente: sin scroll, el censo tiene que igualar al contador.
    if name in ("Ejemplo_1.png", "Ejemplo_2.png", "Ejemplo_6.png"):
        assert len(obtenido) == contador, f"{name}: censo {len(obtenido)} != contador {contador}"


@pytest.mark.skipif(not _present("Ejemplo_1.png"), reason="fixtures no presentes")
def test_las_225_celdas_se_clasifican_bien():
    """5 frames × 45 celdas: ninguna celda fuera del ground-truth puede dar tilde."""
    total = 0
    for name, (esperado, _) in _GT.items():
        fr = _load(_DIR / name)
        obtenido = tilde_cells(fr)
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                assert ((r, c) in obtenido) == ((r, c) in esperado), f"{name} celda ({r},{c})"
                total += 1
    assert total == 225, total


@pytest.mark.skipif(not _present("Ejemplo_1.png"), reason="fixtures no presentes")
def test_separacion_entre_tilde_y_no_tilde():
    """El margen tiene que ser ≥2×, no apenas separable. Si esto se acerca a 1×, la calibración
    es frágil y un frame de animación va a producir un falso tilde."""
    con: list[float] = []
    sin: list[float] = []
    for name, (esperado, _) in _GT.items():
        fracs = tilde_fracs(_load(_DIR / name))
        for celda, frac in fracs.items():
            (con if celda in esperado else sin).append(frac)
    assert con, "ningún tilde en el ground-truth"
    peor_con, peor_sin = min(con), max(sin)
    assert peor_con >= 2 * peor_sin, (
        f"separación insuficiente: tilde mínimo={peor_con:.4f} vs no-tilde máximo={peor_sin:.4f}"
    )


@pytest.mark.parametrize("name", _NO_GRILLA, ids=lambda n: n.split("_(")[0])
def test_no_dispara_en_los_modales(name):
    """Los modales de la misma carpeta (post-desmontaje, confirmación) tienen el fondo de la
    grilla atenuado detrás; el censo no debe inventar tildes ahí."""
    if not _present(name):
        pytest.skip("fixture no presente")
    assert tilde_cells(_load(_DIR / name)) == frozenset()


_FP_DIR = REPO / "Documentacion" / "Screenshots_Triggers" / "Triggers_Generales" / "Falsos_positivos"


@pytest.mark.skipif(not _FP_DIR.exists(), reason="corpus de falsos positivos no presente")
def test_no_dispara_en_los_negativos_de_qa():
    negativos = sorted(_FP_DIR.glob("*.png"))[:10]
    if not negativos:
        pytest.skip("sin negativos")
    for p in negativos:
        fr = _load(p)
        if fr is None:
            continue
        assert tilde_cells(fr) == frozenset(), p.name


@pytest.mark.skipif(not _present("Ejemplo_3.png"), reason="fixtures no presentes")
def test_scroll_pos_distingue_arriba_de_scrolleado():
    """La posición del thumb del scrollbar dice si el viewport se movió. Hace falta para poder
    etiquetar un hueco como "fuera_de_viewport" en vez de "click superpuesto", y para invalidar
    el mapa celda→disco (una celda NO es identidad estable si la grilla se corrió).

    Ejemplo_1/2/6 están al tope; Ejemplo_3 y 4 comparten la misma posición scrolleada (sus
    grillas son idénticas, es el mismo momento con un click de diferencia)."""
    arriba = scroll_pos(_load(_DIR / "Ejemplo_1.png"))
    e3 = scroll_pos(_load(_DIR / "Ejemplo_3.png"))
    e4 = scroll_pos(_load(_DIR / "Ejemplo_4.png"))
    assert arriba is not None and e3 is not None and e4 is not None
    assert arriba < e3, f"el tope ({arriba:.3f}) debería estar por encima del scrolleado ({e3:.3f})"
    assert abs(e3 - e4) < 0.02, f"E3 y E4 son el mismo scroll: {e3:.3f} vs {e4:.3f}"


def test_scroll_pos_devuelve_none_sin_grilla():
    assert scroll_pos(np.zeros((10, 10, 3), np.uint8)) is None


@pytest.mark.skipif(not _present("Ejemplo_2.png"), reason="fixture no presente")
def test_bench_censo_bajo_3ms():
    """Corre en el loop rápido a 10 fps ⇒ RNF-06. Sin OCR, solo máscaras HSV sobre 45 recortes."""
    fr = _load(_DIR / "Ejemplo_2.png")
    tilde_cells(fr)                      # warmup
    t0 = time.perf_counter()
    for _ in range(20):
        tilde_cells(fr)
    ms = (time.perf_counter() - t0) / 20 * 1000
    assert ms < 3.0, f"{ms:.2f} ms por censo"
