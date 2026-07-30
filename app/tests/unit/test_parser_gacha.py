"""Unit del parseo del gacha: canal seleccionado (S27) y grilla de recompensas (S28).

Fija las mediciones hechas al calibrar, para que un cambio futuro las rompa ruidosamente en vez
de degradar en silencio. Skip-if-absent: los fixtures son locales (gitignoreados).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from app.core.parser_gacha_banner import (
    CHANNEL_TYPES,
    pill_highlight_scores,
    selected_channel,
)
from app.core.parser_gacha_result import (
    count_rarity_badges,
    parse_grid,
    tile_boxes,
)

REPO = Path(__file__).resolve().parents[3]
GACHA = REPO / "Documentacion" / "Screenshots_Triggers" / "Gacha_Sintonizacion"
BANNERS = GACHA / "Banners"
GRIDS = GACHA / "Resultados_sintonizacion"

# Canal seleccionado esperado en cada banner de 3.1, leído a ojo del realce amarillo.
CANAL_ESPERADO = {
    "Remielle": 1,
    "Aria": 2,
    "W_engine_Remielle": 3,
    "W_engine_Aria": 4,
    "Permanente": 5,
    "Bangbus": 6,
}

# Rareza esperada de los 10 tiles, verificada contra la pantalla. `Ejemplo_4` es el fixture rico:
# trae el único S de la muestra (con etiqueta NEW!), un A agente duplicado (×20) y un A engine.
RAREZA_ESPERADA = {
    "Ejemplo_1.png": list("ABBBBBBBBB"),
    "Ejemplo_2.png": list("ABBBBBBBBB"),
    "Ejemplo_4.png": list("SAABBBBBBB"),
    "Ejemplo_5.png": list("ABBBBBBBBB"),
    "Ejemplo_7.png": list("AABBBBBBBB"),
    "Ejemplo_8.png": list("ABBBBBBBBB"),
    "Ejemplo_9.png": list("ABBBBBBBBB"),
}

pytestmark = pytest.mark.skipif(
    not BANNERS.is_dir() or not GRIDS.is_dir(),
    reason=f"fixtures de gacha ausentes (locales, gitignoreados): {GACHA}",
)


def _load(p: Path):
    img = cv2.imread(str(p))
    assert img is not None, f"no pude leer {p}"
    return img


# --- S27: canal seleccionado ------------------------------------------------------------

@pytest.mark.parametrize("stem,idx", sorted(CANAL_ESPERADO.items()))
def test_canal_seleccionado(stem: str, idx: int):
    path = BANNERS / f"{stem}.png"
    if not path.exists():
        pytest.skip(f"falta {path.name}")
    sel = selected_channel(_load(path))
    assert sel is not None, f"{stem}: no detectó ningún canal realzado"
    assert sel.idx == idx, f"{stem}: detectó #{sel.idx} ({sel.tipo}), esperaba #{idx}"
    assert sel.tipo == CHANNEL_TYPES[idx - 1]


def test_el_televisor_del_canal_estable_no_gana_por_ser_amarillo():
    """Trampa medida: el ícono del canal Estable (#5) es un televisor amarillo permanente. Con
    la máscara sobre la pastilla entera ganaba SIEMPRE; por eso se mira solo el marco."""
    path = BANNERS / "Remielle.png"
    if not path.exists():
        pytest.skip("falta Remielle.png")
    sel = selected_channel(_load(path))
    assert sel is not None and sel.idx == 1, "el televisor del #5 volvió a ganar"


def test_scores_del_riel_separan_seleccionado_de_resto():
    """El realce tiene que destacarse, no ganar por poco: seleccionado ≥0.03, resto ≤0.01."""
    path = BANNERS / "Aria.png"
    if not path.exists():
        pytest.skip("falta Aria.png")
    scores = pill_highlight_scores(_load(path))
    assert len(scores) == 6
    ganador = scores[1]                      # Aria es el canal #2
    resto = [s for i, s in enumerate(scores) if i != 1]
    assert ganador >= 0.03, f"realce débil: {ganador:.4f}"
    assert max(resto) <= 0.01, f"un no-seleccionado midió {max(resto):.4f}"


# --- S28: grilla de recompensas ---------------------------------------------------------

@pytest.mark.parametrize("nombre,esperado", sorted(RAREZA_ESPERADA.items()))
def test_rareza_de_los_10_tiles(nombre: str, esperado: list[str]):
    path = GRIDS / nombre
    if not path.exists():
        pytest.skip(f"falta {nombre}")
    tiles = parse_grid(_load(path))
    assert len(tiles) == 10
    assert [t.rarity for t in tiles] == esperado


def test_ningun_tile_se_abstiene_de_la_rareza():
    """70/70 al calibrar. Si esto baja, la geometría del badge se corrió."""
    total = abstenidos = 0
    for nombre in RAREZA_ESPERADA:
        path = GRIDS / nombre
        if not path.exists():
            continue
        for t in parse_grid(_load(path)):
            total += 1
            abstenidos += t.rarity is None
    assert total > 0
    assert abstenidos == 0, f"{abstenidos}/{total} tiles sin rareza legible"


def test_etiqueta_new_solo_en_el_tile_nuevo():
    """`Ejemplo_4` es el único fixture con un ítem nuevo, y es su tile 1 (el S)."""
    path = GRIDS / "Ejemplo_4.png"
    if not path.exists():
        pytest.skip("falta Ejemplo_4.png")
    nuevos = [t.idx for t in parse_grid(_load(path)) if t.is_new]
    assert nuevos == [1], f"NEW! detectado en {nuevos}"


def test_grilla_tiene_10_cajas_sin_solaparse():
    path = GRIDS / "Ejemplo_1.png"
    if not path.exists():
        pytest.skip("falta Ejemplo_1.png")
    boxes = tile_boxes(_load(path))
    assert len(boxes) == 10
    fila1 = boxes[:5]
    for a, b in zip(fila1, fila1[1:]):
        assert a.x1 <= b.x0, "las columnas se solapan"
    assert boxes[0].y1 <= boxes[5].y0, "las filas se solapan"


# --- handlers del monitor ---------------------------------------------------------------

def _monitor_pelado():
    """Monitor sin construir: los handlers del gacha solo tocan cuatro atributos, así que se
    los aísla en vez de levantar todo el pipeline (OCR, DB, capturador)."""
    from app.core.monitor import Monitor
    m = Monitor.__new__(Monitor)
    m._on_diagnostic = lambda msg: emitido.append(msg)
    m._s27_last_canal = None
    m._s28_last_sig = None
    m._gacha_identifier = None
    return m


emitido: list[str] = []


def test_handler_s27_emite_el_canal_y_no_repite():
    path = BANNERS / "Aria.png"
    if not path.exists():
        pytest.skip("falta Aria.png")
    emitido.clear()
    m = _monitor_pelado()
    frame = _load(path)
    m._process_s27_banner(frame, None)
    assert len(emitido) == 1 and "#2" in emitido[0], emitido
    # Mismo canal en pantalla ⇒ no se re-emite (edge-triggered por índice).
    m._process_s27_banner(frame, None)
    assert len(emitido) == 1, f"se repitió: {emitido}"


def test_handler_s28_resume_las_recompensas_y_no_repite():
    path = GRIDS / "Ejemplo_4.png"
    if not path.exists():
        pytest.skip("falta Ejemplo_4.png")
    emitido.clear()
    m = _monitor_pelado()
    frame = _load(path)
    m._process_s28_resultados(frame, None)
    assert len(emitido) == 1, emitido
    msg = emitido[0]
    assert "1 S" in msg and "2 A" in msg, msg
    assert "nuevo" in msg, msg          # Ejemplo_4 trae el tile con `NEW!`
    m._process_s28_resultados(frame, None)
    assert len(emitido) == 1, f"se repitió: {emitido}"


def test_handler_s28_nunca_nombra_un_tile_no_B():
    """Los tiles A y S se reportan por rareza, sin nombre: el matcher todavía no distingue
    agente de engine y nombrar un agente con nombre de arma sería mentir (RNF-02)."""
    from app.core.gacha_identity import GachaIdentifier
    path = GRIDS / "Ejemplo_4.png"
    if not path.exists():
        pytest.skip("falta Ejemplo_4.png")
    gi = GachaIdentifier()
    frame = _load(path)
    for t in parse_grid(frame):
        if t.rarity != "B":
            assert gi.identify(frame, t).name is None, f"tile {t.idx} ({t.rarity}) fue nombrado"


def test_conteo_de_badges_separa_grilla_de_animacion():
    """El gate de `_verify_s28`. Medido: grilla real 10, animación 6, splash 1. El umbral del
    detector es 9, o sea que hay hueco a ambos lados."""
    grilla = GRIDS / "Ejemplo_1.png"
    animacion = GRIDS / "Ejemplo_6.png"
    splash = GRIDS / "Ejemplo_3.png"
    if not (grilla.exists() and animacion.exists() and splash.exists()):
        pytest.skip("faltan fixtures")
    assert count_rarity_badges(_load(grilla)) == 10
    assert count_rarity_badges(_load(animacion)) <= 7
    assert count_rarity_badges(_load(splash)) <= 3
