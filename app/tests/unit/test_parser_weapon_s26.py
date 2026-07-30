"""Parser del panel de detalle de W-Engine (S26).

Verdad de tierra de los 40 fixtures, campo por campo. Los valores salen de leer las capturas
del propio juego, no de la DB: el catálogo `weapons` venía con rareza, tipo y `atk_base`
heredados de otra arma en varias filas (ver `audit/weapons_catalog_20260728.md`), así que usarlo
como verdad sería circular.

El catálogo que se le pasa al parser es la lista de los 40 nombres esperados, no el catálogo
completo. Es a propósito y es **más exigente**: incluye los pares confundibles
(*Modelo II* / *Modelo III*, *Motor estelar* / *Réplica motor estelar*, *Turbulencia - Flecha* /
*- Hacha*), que son justo donde un fuzzy demasiado laxo se equivoca.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_weapon_s26 import (
    WeaponParsed,
    match_catalogo,
    parse_weapon_s26,
    parse_weapon_s26_from_lines,
)

_DIR = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
        / "Engines_Triggers" / "Engine_vista_detallada_pj")

# fixture → (nombre en el catálogo, nivel, nivel_max, atk_base, stat canon, valor, unidad)
_GT: dict[str, tuple] = {
    "Ejemplo_1":  ("Ecos bulliciosos", 60, 60, 594, "Maestría de Anomalía", 75.0, "flat"),
    "Ejemplo_2":  ("Fósil preciado", 60, 60, 594, "Impacto", 15.0, "%"),
    "Ejemplo_3":  ("Cañón bombástica", 60, 60, 624, "Recarga de Energía", 50.0, "%"),
    "Ejemplo_4":  ("Repercusión - Modelo III", 0, 10, 32, "HP%", 8.0, "%"),
    "Ejemplo_5":  ("Cámara acorazada", 0, 10, 42, "Recarga de Energía", 20.0, "%"),
    "Ejemplo_6":  ("Sol exuvia", 60, 60, 713, "ATK%", 30.0, "%"),
    "Ejemplo_7":  ("Templo a la granizada estelífera", 60, 60, 743, "Prob. Crítica", 24.0, "%"),
    "Ejemplo_8":  ("Coctelera incandescente", 60, 60, 713, "ATK%", 30.0, "%"),
    "Ejemplo_9":  ("Compilador quimérico", 60, 60, 684, "Tasa de Perforación", 24.0, "%"),
    "Ejemplo_10": ("Aguijón agudo", 60, 60, 713, "Maestría de Anomalía", 90.0, "flat"),
    "Ejemplo_11": ("Gastrónomo selvático", 60, 60, 594, "Maestría de Anomalía", 75.0, "flat"),
    "Ejemplo_12": ("Llanto mielgo", 60, 60, 594, "ATK%", 25.0, "%"),
    "Ejemplo_13": ("Viaje estruendoso", 60, 60, 624, "ATK%", 25.0, "%"),
    "Ejemplo_14": ("Tormenta magnética - Charlie", 0, 10, 32, "Tasa de Perforación", 6.4, "%"),
    "Ejemplo_15": ("Engranaje infernal", 60, 60, 684, "Impacto", 18.0, "%"),
    "Ejemplo_16": ("Almohadillas férreas", 60, 60, 684, "Prob. Crítica", 24.0, "%"),
    "Ejemplo_17": ("Petrazufre", 60, 60, 684, "ATK%", 30.0, "%"),
    "Ejemplo_18": ("Visitante de altamar", 60, 60, 713, "Prob. Crítica", 24.0, "%"),
    "Ejemplo_19": ("Esplendor surcanimbos", 60, 60, 743, "Daño Crítico", 48.0, "%"),
    "Ejemplo_20": ("Estrella callejera", 60, 60, 594, "ATK%", 25.0, "%"),
    "Ejemplo_21": ("Motor estelar", 60, 60, 594, "ATK%", 25.0, "%"),
    "Ejemplo_22": ("Florescencia aurífera", 60, 60, 594, "ATK%", 25.0, "%"),
    "Ejemplo_23": ("Anhelo marcato", 60, 60, 594, "Prob. Crítica", 20.0, "%"),
    "Ejemplo_24": ("Amo de llaves", 60, 60, 624, "ATK%", 25.0, "%"),
    "Ejemplo_25": ("Réplica motor estelar", 60, 60, 624, "ATK%", 25.0, "%"),
    "Ejemplo_26": ("Taladradora giratoria - Eje rojo", 60, 60, 624, "Recarga de Energía", 50.0, "%"),
    "Ejemplo_27": ("Rotor de cañón", 60, 60, 594, "Prob. Crítica", 20.0, "%"),
    "Ejemplo_28": ("Fase lunar - Plenilunio", 0, 10, 32, "ATK%", 8.0, "%"),
    "Ejemplo_29": ("Última cena", 60, 60, 594, "Recarga de Energía", 50.0, "%"),
    "Ejemplo_30": ("Caldero ardiente", 60, 60, 594, "Impacto", 15.0, "%"),
    "Ejemplo_31": ("Cúter", 60, 60, 624, "Impacto", 15.0, "%"),
    "Ejemplo_32": ("Turbulencia - Flecha", 0, 10, 32, "Impacto", 4.8, "%"),
    "Ejemplo_33": ("Turbulencia - Hacha", 0, 10, 32, "Recarga de Energía", 16.0, "%"),
    "Ejemplo_34": ("Lapso de tiempo", 60, 60, 594, "Tasa de Perforación", 20.0, "%"),
    "Ejemplo_35": ("Repercusión - Modelo II", 0, 10, 32, "Recarga de Energía", 16.0, "%"),
    "Ejemplo_36": ("Repercusión - Modelo III", 0, 10, 32, "HP%", 8.0, "%"),
    "Ejemplo_37": ("Proyector de celuloide", 60, 60, 594, "Impacto", 15.0, "%"),
    "Ejemplo_38": ("Transmorfer original", 60, 60, 594, "HP%", 25.0, "%"),
    "Ejemplo_39": ("Pacificador especializado", 60, 60, 624, "ATK%", 25.0, "%"),
    "Ejemplo_40": ("Primavera termal", 60, 60, 594, "ATK%", 25.0, "%"),
}

_CATALOGO = sorted({v[0] for v in _GT.values()})


def _present(stem: str) -> bool:
    return (_DIR / f"{stem}.png").exists()


def _load(stem: str) -> np.ndarray:
    p = _DIR / f"{stem}.png"
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@lru_cache(maxsize=1)
def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:  # pragma: no cover
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@lru_cache(maxsize=64)
def _parsed(stem: str) -> WeaponParsed:
    """Una pasada de OCR por fixture, compartida entre los tests de campo."""
    return parse_weapon_s26(_load(stem), _paddle(), catalogo=_CATALOGO)


# --- Campo por campo ------------------------------------------------------------------------


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
@pytest.mark.parametrize("stem", list(_GT), ids=lambda s: s)
def test_nivel_y_maximo(stem):
    """El denominador importa: 60/60 y 0/10 son los dos regímenes, y el segundo es el que
    invalida usar el ATK como señal de rareza."""
    if not _present(stem):
        pytest.skip("fixture no presente")
    _, nivel, nivel_max, *_ = _GT[stem]
    d = _parsed(stem)
    assert (d.nivel, d.nivel_max) == (nivel, nivel_max)


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
@pytest.mark.parametrize("stem", list(_GT), ids=lambda s: s)
def test_atk_base(stem):
    if not _present(stem):
        pytest.skip("fixture no presente")
    atk = _GT[stem][3]
    assert _parsed(stem).atk_base == atk


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
@pytest.mark.parametrize("stem", list(_GT), ids=lambda s: s)
def test_stat_avanzado(stem):
    """Nombre canónico + valor + unidad. La unidad no es decorativa: es lo que distingue
    'Ataque 30 %' (ATK%) de un ATK plano, vía `_canon_with_unit`."""
    if not _present(stem):
        pytest.skip("fixture no presente")
    _, _, _, _, canon, valor, unidad = _GT[stem]
    d = _parsed(stem)
    assert (d.stat_avanzado_canon, d.stat_avanzado_valor, d.stat_avanzado_unidad) == (
        canon, valor, unidad)


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
@pytest.mark.parametrize("stem", list(_GT), ids=lambda s: s)
def test_nombre_canonico(stem):
    """El OCR mutila sistemáticamente ('Última cena' → 'Uitima cena', 'Cañón' → 'Canon'), así
    que el fuzzy tiene que aguantar eso SIN cruzarse entre los pares confundibles."""
    if not _present(stem):
        pytest.skip("fixture no presente")
    esperado = _GT[stem][0]
    d = _parsed(stem)
    assert d.nombre_canon == esperado, f"raw={d.nombre_raw!r} → {d.nombre_canon!r}"


# --- Abstención y pureza --------------------------------------------------------------------


def test_sin_catalogo_no_inventa_nombre():
    """Sin catálogo no hay canonización posible: se devuelve el crudo y `nombre_canon` queda
    en None. Es el caso normal en la app hasta que el llamador inyecte el catálogo."""
    lines = [("Petrazufre", 0.99, (800, 200, 1100, 240)),
             ("Nivel 60/60", 0.99, (800, 260, 1100, 300)),
             ("Atributo principal", 0.99, (800, 420, 1100, 450)),
             ("Ataque Base 684", 0.99, (800, 460, 1300, 495)),
             ("Atributos avanzados", 0.99, (800, 520, 1100, 550)),
             ("Ataque", 0.99, (800, 570, 950, 600)),
             ("30 %", 0.99, (1250, 570, 1350, 600))]
    d = parse_weapon_s26_from_lines(lines, W=2559, H=1439)
    assert d.nombre_raw == "Petrazufre"
    assert d.nombre_canon is None
    assert (d.nivel, d.nivel_max, d.atk_base) == (60, 60, 684)
    assert (d.stat_avanzado_canon, d.stat_avanzado_valor) == ("ATK%", 30.0)


def test_arma_fuera_del_catalogo_se_declara():
    """Decisión de Daniel: el arma desconocida se MUESTRA, no se registra ni se acumula. El
    parser lo deja explícito en `notas` para que el log pueda decirlo sin adivinar."""
    assert match_catalogo("Arma Que No Existe", ["Petrazufre", "Sol exuvia"]) is None
    lines = [("Arma Inexistente", 0.99, (800, 200, 1100, 240)),
             ("Nivel 1/10", 0.99, (800, 260, 1100, 300))]
    d = parse_weapon_s26_from_lines(lines, W=2559, H=1439, catalogo=["Petrazufre"])
    assert d.nombre_canon is None
    assert "nombre_fuera_del_catalogo" in d.notas


def test_panel_vacio_no_revienta():
    d = parse_weapon_s26_from_lines([], W=2559, H=1439)
    assert d.notas == ["panel_vacio"]
    assert d.nivel is None and d.atk_base is None


def test_al_maximo_distingue_los_dos_regimenes():
    """`al_maximo` gobierna si el ATK base sirve como corroboración de la rareza (S ∈
    {684,713,743}, A ∈ {594,624}). A nivel 0 el ATK no dice nada y hay que saberlo."""
    assert WeaponParsed(nivel=60, nivel_max=60).al_maximo is True
    assert WeaponParsed(nivel=0, nivel_max=10).al_maximo is False
    assert WeaponParsed(nivel=None, nivel_max=None).al_maximo is False


def test_el_fuzzy_no_cruza_los_modelos_de_repercusion():
    """El caso más filoso del catálogo: 'Modelo II' y 'Modelo III' difieren en una letra, y el
    OCR devuelve 'll' y 'lll'. Si el corte fuera más laxo, se cruzarían — y serían dos armas
    distintas reportadas como la misma."""
    cat = ["Repercusión - Modelo I", "Repercusión - Modelo II", "Repercusión - Modelo III"]
    assert match_catalogo("Repercusion - Modelo ll", cat) == "Repercusión - Modelo II"
    assert match_catalogo("Repercusión- Modelo lll", cat) == "Repercusión - Modelo III"
