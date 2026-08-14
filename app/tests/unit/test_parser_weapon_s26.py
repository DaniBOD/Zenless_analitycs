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

from app.core import parser_weapon_s26 as W
from app.core.parser_weapon_s26 import (
    WeaponParsed,
    match_catalogo,
    parse_weapon_s26,
    parse_weapon_s26_from_lines,
    read_rareza,
    read_refinamiento,
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

# --- Rareza y refinamiento (H3) --------------------------------------------------------------
# La rareza sale de dos señales independientes que coinciden en los 40: el hue del badge y, para
# las 32 que están a nivel máximo, el ATK base (S ∈ {684,713,743}, A ∈ {594,624}). Las 8 que están
# a 0/10 no tienen esa corroboración, así que se apoyan en el nombre: las Repercusión, Tormenta
# magnética, Fase lunar y Turbulencia son de rango B, y Cámara acorazada es A.
_GT_RAREZA = {
    "S": {"Ejemplo_6", "Ejemplo_7", "Ejemplo_8", "Ejemplo_9", "Ejemplo_10", "Ejemplo_15",
          "Ejemplo_16", "Ejemplo_17", "Ejemplo_18", "Ejemplo_19"},
    "B": {"Ejemplo_4", "Ejemplo_14", "Ejemplo_28", "Ejemplo_32", "Ejemplo_33", "Ejemplo_35",
          "Ejemplo_36"},
}
_GT_RAREZA["A"] = set(_GT) - _GT_RAREZA["S"] - _GT_RAREZA["B"]
_RAREZA_POR_FIXTURE = {st: r for r, ss in _GT_RAREZA.items() for st in ss}

# Refinamiento leído contando estrellas blancas contra grises, verificado a ojo en Ejemplo_17
# (Petrazufre, 1 blanca + 4 grises) y Ejemplo_31 (Cúter, 4 blancas + 1 gris).
_GT_REFIN = {
    1: {"Ejemplo_4", "Ejemplo_6", "Ejemplo_7", "Ejemplo_8", "Ejemplo_9", "Ejemplo_10",
        "Ejemplo_14", "Ejemplo_16", "Ejemplo_17", "Ejemplo_18", "Ejemplo_19", "Ejemplo_32",
        "Ejemplo_33", "Ejemplo_35", "Ejemplo_36"},
    2: {"Ejemplo_15", "Ejemplo_28", "Ejemplo_40"},
    4: {"Ejemplo_31"},
}
_GT_REFIN[5] = set(_GT) - _GT_REFIN[1] - _GT_REFIN[2] - _GT_REFIN[4]
_REFIN_POR_FIXTURE = {st: n for n, ss in _GT_REFIN.items() for st in ss}

_DISCOS = sorted((Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
                  / "Discos_Triggers" / "14_Slots_equipamiento").glob("Ejemplo_*.png"))


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


@lru_cache(maxsize=64)
def _pill_bbox(stem: str):
    """Bbox del pill "Nivel N/M" — el ancla de la rareza y del refinamiento."""
    for t, _c, bb in W._ocr_detail_lines(_load(stem), _paddle()):
        if W._RE_NIVEL_ARMA.search(t):
            return bb
    return None


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


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
@pytest.mark.parametrize("stem", list(_GT), ids=lambda s: s)
def test_rareza(stem):
    """La rareza sale de la PANTALLA, no del catálogo — decisión de Daniel: el catálogo tiene 42
    armas de menos y 5 sin mapeo, así que como fuente única fallaría en silencio."""
    if not _present(stem):
        pytest.skip("fixture no presente")
    assert _parsed(stem).rareza == _RAREZA_POR_FIXTURE[stem]


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
@pytest.mark.parametrize("stem", list(_GT), ids=lambda s: s)
def test_refinamiento(stem):
    if not _present(stem):
        pytest.skip("fixture no presente")
    assert _parsed(stem).refinamiento == _REFIN_POR_FIXTURE[stem]


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
def test_ninguna_rareza_discrepa_del_atk():
    """La verificación cruzada: en las 32 que están al máximo, el badge y el ATK base tienen que
    decir lo mismo. Si esto cae, una de las dos calibraciones se movió."""
    malos = [s for s in _GT if _present(s)
             for d in [_parsed(s)]
             if any(n.startswith("rareza_discrepa_atk") for n in d.notas)]
    assert not malos, malos


@pytest.mark.skipif(not _present("Ejemplo_1"), reason="capturas no presentes")
def test_tabla_de_separacion_de_las_estrellas():
    """Separación medida entre estrella llena y gris, que es lo que sostiene el conteo.

    La convención del proyecto pide ≥2×; acá es **absoluta**: las grises no tienen un solo píxel
    sobre V=200. Si el margen se degradara a algo finito, este test lo muestra antes de que se
    traduzca en un refinamiento equivocado.
    """
    llenas, vacias = [], []
    for stem in _GT:
        if not _present(stem):
            continue
        frame = _load(stem)
        d = _parsed(stem)
        bbox = _pill_bbox(stem)
        assert bbox is not None, f"{stem}: sin pill de nivel"
        x1, _, _, y2 = bbox
        band = frame[y2 + W._STARS_DY[0]:y2 + W._STARS_DY[1],
                     x1 + W._STARS_DX[0]:x1 + W._STARS_DX[1]]
        hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        poco_sat = hsv[:, :, 1] < 60
        runs = W._star_runs((hsv[:, :, 2] > 90) & poco_sat)
        assert len(runs) == 5, f"{stem}: {len(runs)} estrellas detectadas"
        blanco = (hsv[:, :, 2] > 200) & poco_sat
        fracs = [float(blanco[:, a:b].mean()) for a, b in runs]
        n = d.refinamiento
        llenas.extend(sorted(fracs, reverse=True)[:n])
        vacias.extend(sorted(fracs, reverse=True)[n:])
    assert llenas and vacias
    assert min(llenas) > W._STAR_LLENA_MIN > max(vacias), (
        f"llenas min={min(llenas):.4f} · umbral={W._STAR_LLENA_MIN} · vacías max={max(vacias):.4f}")
    assert min(llenas) / W._STAR_LLENA_MIN >= 2.0


@lru_cache(maxsize=16)
def _pill_bbox_disco(path_str: str):
    frame = cv2.imdecode(np.fromfile(path_str, np.uint8), cv2.IMREAD_COLOR)
    for t, _c, bb in W._ocr_detail_lines(frame, _paddle()):
        if W._RE_NIVEL_ARMA.search(t):
            return frame, bb
    return frame, None


@pytest.mark.skipif(not _DISCOS, reason="capturas de disco no presentes")
@pytest.mark.parametrize("p", _DISCOS[:8], ids=lambda p: p.stem)
def test_el_refinamiento_se_abstiene_sobre_un_disco(p):
    """Defensa en profundidad, y el lector que SÍ discrimina.

    El panel de un disco también dice "Nivel 15/15", así que el ancla existe y el recorte cae en
    algún lado — pero ahí no hay fila de estrellas. Tiene que devolver None, no un número.

    S26 nunca dispara sobre un disco (`test_detector_weapon_detail`), así que esto es una segunda
    línea: si alguien llamara al lector desde la ruta de discos, no inventa.
    """
    frame, bbox = _pill_bbox_disco(str(p))
    if bbox is None:
        pytest.skip("el disco no expuso un pill de nivel legible")
    assert read_refinamiento(frame, bbox) is None


@pytest.mark.skipif(not _DISCOS, reason="capturas de disco no presentes")
@pytest.mark.parametrize("p", _DISCOS[:8], ids=lambda p: p.stem)
def test_el_badge_de_rareza_es_un_widget_COMPARTIDO(p):
    """`read_rareza` NO se abstiene sobre un disco, y está bien que no lo haga.

    El badge circular a la izquierda del pill de nivel es el mismo widget en las dos pantallas,
    con el mismo código de color: en el detalle de un disco informa la rareza DEL DISCO. Leerlo
    correctamente ahí no es contaminación — no produce ningún dato de arma.

    Se afirma que devuelve una rareza VÁLIDA y no basura, que es lo verificable: no se fija el
    valor porque depende de qué disco esté seleccionado en cada captura.
    """
    frame, bbox = _pill_bbox_disco(str(p))
    if bbox is None:
        pytest.skip("el disco no expuso un pill de nivel legible")
    assert read_rareza(frame, bbox) in {"S", "A", "B"}


def test_los_lectores_no_revientan_con_un_bbox_absurdo():
    """Fuera de la imagen no hay que adivinar: None, sin excepción."""
    frame = np.zeros((100, 100, 3), np.uint8)
    assert read_refinamiento(frame, (5000, 5000, 5100, 5040)) is None
    assert read_rareza(frame, (5000, 5000, 5100, 5040)) is None


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


# --- Tenencia: ¿la lleva el PJ en pantalla, otro, o está libre? -------------------------------
#
# Verdad de tierra a ojo sobre los 40 fixtures (montaje de la ROI anclada, 2026-07-30). LIBRE es
# la lista corta a propósito: es el caso que el sistema NO podía ver y el que el feature agrega.
#
# Ojo con cuatro de ellas — Ejemplo_32/33/4/5 tienen un resplandor de color del ARTE DEL ARMA
# justo detrás del hueco del badge. Por brillo o por saturación pasan por avatar (blobs de hasta
# 8002 px², más que varios avatares reales); son el motivo de que la presencia se mida por
# nitidez y no por color.
_GT_LIBRES = {
    "Ejemplo_11", "Ejemplo_14", "Ejemplo_16", "Ejemplo_20", "Ejemplo_22", "Ejemplo_28",
    "Ejemplo_32", "Ejemplo_33", "Ejemplo_35", "Ejemplo_36", "Ejemplo_4", "Ejemplo_5",
}


@pytest.mark.parametrize("stem", sorted(_GT))
def test_presencia_del_badge_de_dueno(stem):
    """40/40. El caso que importa es el negativo: sin esta señal, un arma libre y una de otro PJ
    son indistinguibles, y son las dos que se comportan distinto al equiparlas."""
    if not _present(stem):
        pytest.skip("fixture ausente")
    b = W.read_weapon_owner_badge(_load(stem), _pill_bbox(stem))
    assert b is not None, "el pill está, así que el ancla tiene que resolver"
    assert b.present is (stem not in _GT_LIBRES), f"nitidez={b.nitidez:.1f}"


@pytest.mark.parametrize("stem", sorted(_GT))
def test_la_nitidez_separa_con_margen(stem):
    """No alcanza con acertar: el margen es lo que dice si aguanta un arma nueva.

    Medido: libres ≤ 4.75, con dueño ≥ 51.98 — 11× de separación. Se exige la mitad de ese
    margen para que el test avise si un fixture nuevo lo empieza a cerrar, en vez de esperar a
    que un día cruce el umbral y aparezca como un dueño inventado."""
    if not _present(stem):
        pytest.skip("fixture ausente")
    b = W.read_weapon_owner_badge(_load(stem), _pill_bbox(stem))
    if stem in _GT_LIBRES:
        assert b.nitidez < W._OWNER_NITIDEZ_MIN / 2, f"libre demasiado nítida: {b.nitidez:.1f}"
    else:
        assert b.nitidez > W._OWNER_NITIDEZ_MIN * 2, f"dueño demasiado liso: {b.nitidez:.1f}"


@pytest.mark.parametrize("stem", sorted(set(_GT) - _GT_LIBRES))
def test_con_dueno_siempre_hay_recorte_para_nombrar(stem):
    """28/28. La franja fija daba 26 y —peor— confundía "no encontré el círculo" con "no hay
    dueño". Acá son dos salidas distintas: `present` sin `crop` es "hay alguien, no sé quién"."""
    if not _present(stem):
        pytest.skip("fixture ausente")
    b = W.read_weapon_owner_badge(_load(stem), _pill_bbox(stem))
    assert b.crop is not None and b.crop.size > 0


def test_el_ancla_sobrevive_al_nombre_de_dos_lineas():
    """La regresión concreta que motivó el ancla.

    Ejemplo_34 y Ejemplo_39 TIENEN avatar y la franja fija de `crop_detail_badge` los daba por
    libres: el nombre del arma envuelve a dos líneas, empuja el panel hacia abajo y el círculo
    entra cortado por el borde del recuadro. Es la misma trampa de coordenadas fijas que ya había
    aparecido con la fila de estrellas."""
    from app.core.detector import crop_detail_badge
    for stem in ("Ejemplo_34", "Ejemplo_39"):
        if not _present(stem):
            pytest.skip("fixture ausente")
        assert crop_detail_badge(_load(stem)) is None, "cambió el comportamiento viejo"
        b = W.read_weapon_owner_badge(_load(stem), _pill_bbox(stem))
        assert b.present, f"{stem}: el avatar está y el ancla lo tiene que ver"


def test_sin_ancla_no_se_inventa_tenencia():
    """Sin pill no hay dónde mirar. Devolver None (y no `present=False`) es lo que evita que un
    panel ilegible se reporte como arma libre."""
    frame = np.zeros((1440, 2560, 3), np.uint8)
    assert W.read_weapon_owner_badge(frame, None) is None


def test_el_encuadre_del_dueno_lo_fija_el_frame_y_no_hough():
    """El encuadre no puede depender del radio que devuelva Hough — **esta es la ruta que cosecha**.

    Medido sobre los 30 badges localizados: los lados se partían en 48-52 (modal) y 60-62, y cuatro
    de los cinco de 62 px estaban entre los peores matches de toda la tanda. Un recorte flojo mete
    un anillo de fondo, la cara ocupa menos cuadro y el descriptor ve otra composición; cuando eso
    pasa mientras se COSECHA, la ref queda envenenada para siempre. Es lo que le pasó a Zhao, cuyas
    refs matchean mejor con encuadre ancho que ajustado.

    Con el radio de `_DET_CROP_R_F`: distancia media 0.199 → 0.169, bajo 0.15 de 11/30 a 17/30,
    nombrados 22 → 26, y **cero cambian de identificación** — que es lo que hacía falta verificar
    antes de tocar esto, porque el dueño alimenta `sync_equip` y eso escribe la DB.

    Lo que se afirma NO es "todos del mismo tamaño en píxeles": el radio es una FRACCIÓN del ancho
    del frame, y dos de estas capturas están a 2554 y 2555 px en vez de 2559, así que salen a 48 y
    no a 50. Eso es la fracción funcionando. Lo que se afirma es que el lado queda determinado por
    el frame y **nada más** — si volviera a depender del círculo detectado, dos capturas de la misma
    resolución darían lados distintos.
    """
    from app.core.detector import _DET_CROP_R_F
    vistos = 0
    for stem in sorted(_GT):
        if not _present(stem):
            continue
        frame = _load(stem)
        b = W.read_weapon_owner_badge(frame, _pill_bbox(stem))
        if b is None or b.crop is None:
            continue
        vistos += 1
        esperado = 2 * int(_DET_CROP_R_F * frame.shape[1])
        assert b.crop.shape[0] == esperado, (
            f"{stem}: lado {b.crop.shape[0]} para un frame de {frame.shape[1]} px "
            f"(esperado {esperado}) — el encuadre volvió a depender de Hough")
    if not vistos:
        pytest.skip("ningún badge localizado en las capturas presentes")
    assert W.clasificar_tenencia("reemplazar", None, None, "Velina") == ("incierto", None)


def test_desequipar_identifica_al_dueno_sin_libreria():
    """La vía de dueño CERTERO mientras `avatar_detbadge_v2` siga incompleta: si el juego ofrece
    'Desequipar', la lleva puesta el PJ que estás mirando. No hace falta reconocer la cara."""
    badge = W.OwnerBadge(present=True, nitidez=80.0)
    assert W.clasificar_tenencia("desequipar", badge, None, "Velina") == ("equipada", "Velina")


def test_desequipar_le_gana_a_un_badge_ausente():
    """Presencia gana a libre, la regla que ya rige en la ruta de discos. Un falso LIBRE del badge
    no debe poder contradecir al botón, que es la lectura más robusta del panel."""
    badge = W.OwnerBadge(present=False, nitidez=1.0)
    assert W.clasificar_tenencia("desequipar", badge, None, "Velina") == ("equipada", "Velina")


def test_libre_solo_cuando_el_boton_dice_que_no_es_de_este_pj():
    badge = W.OwnerBadge(present=False, nitidez=2.0)
    for boton in ("equipar", "reemplazar"):
        assert W.clasificar_tenencia(boton, badge, None, "Velina") == ("libre", None)


def test_otro_pj_sin_nombre_sigue_siendo_otro_pj():
    """Que la librería no sepa quién es no lo vuelve libre — es la distinción que decide si al
    equiparla salta el diálogo de confirmación."""
    badge = W.OwnerBadge(present=True, nitidez=70.0)
    assert W.clasificar_tenencia("reemplazar", badge, None, "Velina") == ("otro_pj", None)
    assert W.clasificar_tenencia("reemplazar", badge, "Lucia", "Velina") == ("otro_pj", "Lucia")


def test_sin_boton_no_se_afirma_de_quien_es():
    """Con badge presente y sin botón falta la segunda señal: hay dueño, pero no se puede saber
    si es el PJ en pantalla u otro. Se reporta incierto en vez de elegir."""
    badge = W.OwnerBadge(present=True, nitidez=70.0)
    assert W.clasificar_tenencia(None, badge, "Lucia", "Velina") == ("incierto", "Lucia")
