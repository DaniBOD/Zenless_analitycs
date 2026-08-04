"""Inventario de amplificadores (S30): el panel derecho, con el parser de S26 reusado.

Las dos pantallas describen un arma con las MISMAS secciones ("Atributo principal", "Atributos
avanzados", "Efecto de amplificador"), así que compartir parser no es un atajo: es la misma
gramática. Lo que cambia son dos parámetros:

| | S26 (detalle) | S30 (inventario) |
|---|---|---|
| banda del panel | centro, `_S26_LAYOUT` | derecha, `_S9_LAYOUT` |
| badge de rareza | `pill.x1 − 64`, separado | `pill.x1 − 26`, pegado |
| fila de estrellas | caja **debajo** del pill | **a la derecha**, misma fila |

Los pills miden casi lo mismo (190×28 vs 194×31): **no es escala, es otra disposición**. Por eso
la geometría se pasa como `PillGeometry` en vez de derivarse de un factor.

Medido sobre los 6 fixtures: los seis campos salen 6/6 y la canonización contra `weapons` acierta
6/6, incluidos los que el OCR maltrata más que en el detalle.

Los fixtures de `Engines_Triggers/` son locales (gitignoreados) ⇒ skip-if-absent.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_weapon_s26 import (
    _S26_PILL,
    _S30_PILL,
    PillGeometry,
    parse_weapon_s30,
    weapon_panel_signature,
    weapon_panel_signature_s30,
)

_FX = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
       / "Engines_Triggers" / "Inventario_general_engines")
_FIXTURES = sorted(_FX.glob("Ejemplo_*.png"))

# Verdad de tierra leída de los screenshots. `nombre` es un substring del CANÓNICO (el crudo trae
# ruido de OCR distinto en cada corrida de Paddle; lo que se fija es el resultado canonizado).
_TRUTH = {
    "Ejemplo_1.png": ("Engranaje infernal", "S", 60, 60, 2, 684),
    "Ejemplo_2.png": ("Florescencia", "A", 60, 60, 5, 594),
    "Ejemplo_3.png": ("Última cena", "A", 60, 60, 5, 594),
    "Ejemplo_4.png": ("Llanto mielgo", "A", 60, 60, 5, 594),
    "Ejemplo_5.png": ("Modelo II", "B", 0, 10, 1, 32),
    "Ejemplo_6.png": ("Caldero de la claridad", "A", 60, 60, 5, 594),
}


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@lru_cache(maxsize=1)
def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:  # pragma: no cover - depende del entorno
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@lru_cache(maxsize=1)
def _catalogo() -> tuple[str, ...]:
    """Nombres españoles de `weapons`. Read-only (un SELECT)."""
    import sqlite3
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    if not db.exists():
        pytest.skip("DB no presente")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return tuple(r[0] for r in con.execute("select nombre from weapons"))
    finally:
        con.close()


# --- La geometría, que es lo único nuevo ------------------------------------------------------

def test_las_dos_geometrias_son_distintas_y_no_por_escala():
    """Si algún día alguien intenta unificarlas con un factor, este test explica por qué no."""
    assert _S26_PILL.stars_y_from == "y2" and _S30_PILL.stars_y_from == "y1"
    assert _S26_PILL.stars_x_from == "x1" and _S30_PILL.stars_x_from == "x2"
    assert _S26_PILL.badge_dx != _S30_PILL.badge_dx


def test_el_default_de_lectura_sigue_siendo_el_de_s26():
    """`read_rareza`/`read_refinamiento` toman la geometría con default, así que el camino de S26
    no cambia ni una línea. Si el default se moviera, S26 se rompería en silencio."""
    from app.core.parser_weapon_s26 import read_rareza, read_refinamiento
    import inspect
    for fn in (read_rareza, read_refinamiento):
        assert inspect.signature(fn).parameters["geom"].default is _S26_PILL


def test_pillgeometry_es_inmutable():
    with pytest.raises(AttributeError):
        PillGeometry(-26, "x2", (60, 290), "y1", (-8, 45)).badge_dx = 0


# --- Los seis campos --------------------------------------------------------------------------

@pytest.mark.skipif(not _FIXTURES, reason="capturas del inventario de armas no presentes")
@pytest.mark.parametrize("name", sorted(_TRUTH))
def test_parsea_los_seis_campos(name):
    p = _FX / name
    if not p.exists():
        pytest.skip(f"falta {name}")
    nombre_sub, rareza, nivel, nivel_max, refin, atk = _TRUTH[name]
    d = parse_weapon_s30(_load(p), _paddle(), catalogo=list(_catalogo()))
    assert d.nombre_canon and nombre_sub.lower() in d.nombre_canon.lower(), \
        f"{name}: canon={d.nombre_canon!r} crudo={d.nombre_raw!r}"
    assert d.rareza == rareza, f"{name}: rareza {d.rareza}"
    assert (d.nivel, d.nivel_max) == (nivel, nivel_max), f"{name}: nivel {d.nivel}/{d.nivel_max}"
    assert d.refinamiento == refin, f"{name}: refinamiento {d.refinamiento}"
    assert d.atk_base == atk, f"{name}: atk {d.atk_base}"
    assert d.stat_avanzado_canon and d.stat_avanzado_valor is not None, f"{name}: sin stat avanzado"


@pytest.mark.skipif(not _FIXTURES, reason="capturas del inventario de armas no presentes")
def test_ningun_fixture_deja_notas():
    """Las notas son el canal de "esto no se pudo leer". Con la geometría correcta no debe quedar
    ninguna — y en particular ninguna `rareza_discrepa_atk`, que sería el badge contradiciendo al
    ATK base (las dos señales son independientes)."""
    ocr, cat = _paddle(), list(_catalogo())
    con_notas = {p.name: parse_weapon_s30(_load(p), ocr, catalogo=cat).notas for p in _FIXTURES}
    assert not any(con_notas.values()), con_notas


@pytest.mark.skipif(not _FIXTURES, reason="capturas del inventario de armas no presentes")
def test_la_canonizacion_arregla_lo_que_el_ocr_rompe():
    """El OCR maltrata más los nombres acá que en el detalle, así que la canonización no es un
    lujo. Se afirma que el CRUDO viene sucio y el canónico sale limpio: si algún día el crudo
    saliera perfecto, este test avisa que la verdad de tierra cambió (no que algo se rompió)."""
    d = parse_weapon_s30(_load(_FX / "Ejemplo_3.png"), _paddle(), catalogo=list(_catalogo()))
    assert d.nombre_canon == "Última cena"
    assert d.nombre_raw != d.nombre_canon, "el crudo dejó de venir sucio — revisar la verdad de tierra"


# --- Gate de rendimiento (RNF-06) -------------------------------------------------------------

@pytest.mark.skipif(len(_FIXTURES) < 2, reason="hacen falta 2 capturas")
def test_la_firma_distingue_armas_y_es_estable():
    """Sin el gate, mirar la grilla quieta serían N OCRs idénticos por minuto."""
    a, b = _load(_FIXTURES[0]), _load(_FIXTURES[1])
    assert weapon_panel_signature_s30(a) == weapon_panel_signature_s30(a)
    assert weapon_panel_signature_s30(a) != weapon_panel_signature_s30(b)


@pytest.mark.skipif(not _FIXTURES, reason="capturas del inventario de armas no presentes")
def test_la_firma_de_s30_mira_otro_panel_que_la_de_s26():
    """Usar la firma de S26 acá dejaría el gate mirando una columna donde no pasa nada."""
    fr = _load(_FIXTURES[0])
    assert weapon_panel_signature(fr) != weapon_panel_signature_s30(fr)


# --- El campo que faltaba en el dataclass -----------------------------------------------------

def test_rareza_y_refinamiento_son_none_sin_frame():
    """Estaban asignados al vuelo y sin `frame` no existían ⇒ AttributeError en cualquier
    consumidor. El contrato del módulo es "campo no leído ⇒ None"."""
    from app.core.parser_weapon_s26 import parse_weapon_s26_from_lines
    d = parse_weapon_s26_from_lines([], 2559, 1439)
    assert d.rareza is None and d.refinamiento is None
