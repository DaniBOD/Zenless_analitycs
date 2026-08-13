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
    _counter_from_text,
    parse_header_counter,
    parse_obtenido_materiales,
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


# --- Contador del header: la ÚNICA autoridad del conteo -----------------------------------
# El censo de tildes solo ve el viewport; el contador es global. Ejemplo_3 (7) y Ejemplo_4 (8)
# lo prueban: declaran más de lo que se ve porque el resto quedó scrolleado.


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@pytest.mark.skipif(not _present("Ejemplo_1.png"), reason="fixtures no presentes")
@pytest.mark.parametrize("name", list(_GT), ids=lambda n: n.replace(".png", ""))
def test_contador_del_header(name):
    _, esperado = _GT[name]
    assert parse_header_counter(_load(_DIR / name), _paddle()) == esperado


@pytest.mark.parametrize("name", _NO_GRILLA, ids=lambda n: n.split("_(")[0])
def test_contador_devuelve_none_sin_header(name):
    """RNF-02: sin header legible se declara desconocido, nunca un número inventado. En los
    modales el header queda atenuado detrás del overlay."""
    if not _present(name):
        pytest.skip("fixture no presente")
    assert parse_header_counter(_load(_DIR / name), _paddle()) is None


def test_contador_exige_el_ancla_del_denominador():
    """El rescate de dígitos solo puede correr anclado en `/300`. Sin esa ancla, un `8` suelto
    en cualquier pantalla se leería como una selección de 8 discos."""
    assert _counter_from_text("Desmontaje de pistas de disco 8/300") == 8
    assert _counter_from_text("Nivel 8 / 15") is None
    assert _counter_from_text("300") is None
    assert _counter_from_text("") is None


def test_contador_rescata_digitos_mal_leidos():
    """El OCR confunde O/0, S/5, l/1 en la fuente estilizada del header. El rescate se permite
    solo con el ancla presente."""
    assert _counter_from_text("Desmontaje de pistas de disco S/300") == 5
    assert _counter_from_text("Desmontaje de pistas de disco lO/300") == 10
    assert _counter_from_text("desmontaje O/300") == 0


# --- Materiales del modal "Obtenido": oráculo SECUNDARIO ------------------------------------
# La cantidad del primer material se registra para CORROBORAR el contador, nunca para
# reemplazarlo — y menos después de ver que la evidencia es contradictoria: la previsualización
# de Ejemplo_3 muestra 7 y el "Obtenido" de Ejemplo_7 muestra 1.
#
# Los NOMBRES se leen bien; las CANTIDADES chicas (1 dígito) las dropea el downscale de Paddle y
# el rescate con upscale no las recupera (la banda es muy fina y el detector se pierde). Por eso
# el contrato es explícito: cantidad ilegible ⇒ `None`, jamás un número adivinado (RNF-02).


@pytest.mark.skipif(not _present("Ejemplo_7_(Post_demontaje).png"), reason="fixture no presente")
def test_materiales_lee_los_nombres_del_obtenido():
    mats = parse_obtenido_materiales(_load(_DIR / "Ejemplo_7_(Post_demontaje).png"), _paddle())
    nombres = [n for n, _q in mats]
    assert len(mats) == 5, mats
    assert nombres[0].lower().startswith("disco original"), nombres
    assert any("cristalizado" in n.lower() for n in nombres), nombres


@pytest.mark.skipif(not _present("Ejemplo_5_(Post_demontaje).png"), reason="fixture no presente")
def test_materiales_dos_items():
    mats = parse_obtenido_materiales(_load(_DIR / "Ejemplo_5_(Post_demontaje).png"), _paddle())
    assert len(mats) == 2, mats
    assert mats[0][0].lower().startswith("disco original"), mats


@pytest.mark.skipif(not _present("Ejemplo_7_(Post_demontaje).png"), reason="fixture no presente")
def test_materiales_cantidad_ilegible_es_none_no_un_numero_de_otra_columna():
    """El riesgo real: si una cantidad no se lee y se toma la del vecino, la corroboración
    afirmaría algo falso. Cada cantidad tiene que venir de SU columna o ser None."""
    mats = parse_obtenido_materiales(_load(_DIR / "Ejemplo_7_(Post_demontaje).png"), _paddle())
    cantidades = [q for _n, q in mats]
    assert all(q is None or isinstance(q, int) for q in cantidades), mats
    # 19 y 57600 son las dos que el OCR sí lee; ninguna puede aparecer duplicada en otra columna.
    leidas = [q for q in cantidades if q is not None]
    assert len(leidas) == len(set(leidas)), f"cantidad repetida entre columnas: {mats}"


def test_materiales_sin_ocr_devuelve_lista_vacia():
    assert parse_obtenido_materiales(np.zeros((10, 10, 3), np.uint8), None) == []


# --- Presupuesto del loop rápido (RNF-06) --------------------------------------------------
# Se vigila con DOS tests, porque son dos preguntas distintas y solo una necesita cronómetro:
#   · cuánto cuesta de verdad          → `test_bench_censo_bajo_3ms` (medido, con las cautelas
#                                         que documenta su docstring)
#   · sigue costando O(1) llamadas     → `test_el_censo_no_escala_con_las_45_celdas`
#                                         (estructural, determinista, no puede parpadear)

# Lote CORTO a propósito: tiene que caber entero en un quantum del scheduler para que exista
# alguna muestra sin desalojar. Medido dentro de la suite completa, el mínimo baja al acortarlo
# (lote de 20 → 1.83 ms, de 5 → 1.63, de 3 → 1.52), que es la firma de que el lote largo siempre
# come un cambio de contexto. Ver el docstring del bench.
_LOTE, _REPS = 3, 60


def _ms_por_censo(fr) -> float:
    """Costo propio de un censo, en ms: mínimo de `_REPS` lotes cortos medidos con `perf_counter`.

    El mínimo es el estimador robusto acá porque la contención solo puede SUMAR tiempo: ningún
    desalojo hace que el trabajo salga más barato de lo que es."""
    tilde_cells(fr)                      # warmup (cachea la máscara del annulus)
    lotes = []
    for _ in range(_REPS):
        t0 = time.perf_counter()
        for _ in range(_LOTE):
            tilde_cells(fr)
        lotes.append((time.perf_counter() - t0) / _LOTE * 1000)
    return min(lotes)


@pytest.mark.skipif(not _present("Ejemplo_2.png"), reason="fixture no presente")
def test_bench_censo_bajo_3ms():
    """Corre en el loop rápido a 10 fps ⇒ RNF-06. Sin OCR, solo máscaras HSV.

    **Tercer intento de instrumentar esto; los dos anteriores midieron el reloj, no el censo.**

    El intento #1 usó `perf_counter` sobre un lote de 20 y falló en la suite completa. Se
    diagnosticó "el reloj de pared incluye el tiempo desalojado" y se pasó a `thread_time`, que
    falló igual. El diagnóstico #2 fue "`thread_time` cuenta ciclos y la presión de caché de los
    otros tests los infla". También era falso. Lo medido el 2026-08-12:

        `time.thread_time()` en esta máquina avanza SOLO de a 15.625 ms exactos
        — 64 cambios por segundo, cero valores intermedios: es la tick del scheduler.

    `GetThreadTimes()` no cuenta ciclos ni tiempo real: es contabilidad **muestreada por tick**, y
    Windows le carga la tick entera al hilo que esté corriendo cuando salta. El `resolution=1e-07`
    que declara `get_clock_info` es la unidad de la API, no su granularidad. Sobre un lote de 20
    este test no medía milisegundos: contaba ticks, y `assert ms < 3.0` era `assert ticks <= 3`.
    Por eso TODAS las muestras históricas son múltiplos de 15.625/20 = 0.78125 ms:

        0.78 = 1 tick · 1.56 = 2 ticks · 2.34 = 3 ticks · 3.125 = 4 ticks ← el "fallo"

    Así de roto: con la máquina ociosa el instrumento también reportó 0.000 ms, o sea cero CPU
    para trabajo real. La "dispersión de 3×" entre 0.78 y 2.34 era la cuantización, no el censo.

    **Pero la sospecha de que los otros tests encarecen el censo no era falsa** — solo estaba mal
    dimensionada. Medido con QPC: en un proceso limpio el censo cuesta 0.82 ms y dispersa 1.12×;
    DENTRO de la suite cuesta ~1.6 ms, 2.5× más, y eso es real. No es el GC (con `gc.disable()`
    da igual: 1.654 vs 1.625 ms) ni contención de hilos (hay uno solo): es el estado de memoria
    de un proceso que arrastra 357k objetos vivos después de 1516 tests. O sea que el censo se
    encarece a 1.6 ms, no a 3.125; el resto lo puso el reloj. Contra el presupuesto de 3 ms
    quedan ~1.9× de margen medidos donde el test corre de verdad — así que no hay nada que
    arreglar en el código ni umbral que subir, y el 3.0 recién ahora significa algo.

    **Cómo se mide ahora**, con la misma convención que `test_parser_disc_s11.py`: `perf_counter`
    (sub-µs de verdad) y el MÍNIMO de muchos lotes; la contención solo puede sumar tiempo. La
    clave que faltaba es que el lote sea CORTO: para que exista una muestra sin desalojar tiene
    que caber entera en un quantum del scheduler (~15-30 ms en Windows). El lote de 20 del intento
    #1 duraba ~16 ms, o sea que casi siempre se comía un cambio de contexto — por eso "tomar el
    mínimo" no alcanzó entonces, no porque el mínimo sea mal estimador. Se ve en la suite
    completa: el mínimo baja de 1.83 ms (lote 20) a 1.63 (lote 5) a 1.52 (lote 3). Con lote de 3
    ni el PEOR de 60 lotes llegó al umbral (2.77 ms), y es el mínimo lo que se asegura. Medido
    aparte con los 12 cores saturados, el mínimo se sostuvo en 1.03 ms mientras el peor lote se
    iba a 4.45."""
    ms = _ms_por_censo(_load(_DIR / "Ejemplo_2.png"))
    assert ms < 3.0, f"{ms:.3f} ms por censo (mínimo de {_REPS} lotes de {_LOTE})"


@pytest.mark.skipif(not _present("Ejemplo_1.png"), reason="fixtures no presentes")
@pytest.mark.parametrize("name", list(_GT), ids=lambda n: n.replace(".png", ""))
def test_el_censo_no_escala_con_las_45_celdas(name, monkeypatch):
    """La otra mitad del presupuesto, sin cronómetro: cuántas llamadas a OpenCV cuesta un censo.

    Lo que hay que impedir es volver a la versión ingenua (un `cvtColor` + un `inRange` por
    celda). Eso es una propiedad ESTRUCTURAL y se puede afirmar sin medir tiempo, así que este
    test no puede parpadear por la carga de la máquina — que es justamente lo que arruinó tres
    veces al bench de arriba.

    La ley es exacta: **2 llamadas** para el lote vectorizado de las 45 celdas (constante — no
    escala con la grilla) **+ 4 por cada tilde**, que es lo que cuesta comprobarle la franja de
    rareza (1 `cvtColor` + 3 `inRange`, una por banda). Con la grilla vacía el censo cuesta 2
    llamadas y nada más."""
    esperado, _ = _GT[name]
    n = 0

    def contar(f):
        def envuelta(*a, **k):
            nonlocal n
            n += 1
            return f(*a, **k)
        return envuelta

    for fn in ("cvtColor", "inRange"):
        monkeypatch.setattr(cv2, fn, contar(getattr(cv2, fn)))

    obtenido = tilde_cells(_load(_DIR / name))
    # `tilde_cells` se traga las excepciones: sin esto, un wrapper roto pasaría como "2 llamadas".
    assert obtenido == esperado, f"{name}: el censo instrumentado ya no da el ground-truth"
    assert n == 2 + 4 * len(esperado), (
        f"{name}: {n} llamadas a OpenCV para {len(esperado)} tildes; se esperaban "
        f"{2 + 4 * len(esperado)}. Si subió con las celdas, el censo volvió a ser por-celda."
    )
