"""
Tests del parser espacial de S17 (disco equipado) — `parse_disc_s17`.

Corren sobre OCR cacheado (app/tests/fixtures/s17_ocr/*.json), generado con
PaddleOCR sobre 8 capturas reales 2559×1439. Esto los hace rápidos (sin
re-correr OCR) y deterministas.
"""
import json
from pathlib import Path

import pytest

from app.core.parser_disc_s17 import _parse_s17_from_lines, _coalesce_rolls_fragments, _Line

_FIX = Path(__file__).resolve().parent.parent / "fixtures" / "s17_ocr"

# Capturas S17 reales para el camino end-to-end (re-OCR de rescate con Paddle vivo).
_SLOT_IMGS = (
    Path(__file__).resolve().parents[3]
    / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "14_Slots_equipamiento"
)


def _load(name: str):
    d = json.loads((_FIX / name).read_text(encoding="utf-8"))
    lines = [(t, c, tuple(bb)) for t, c, bb in d["lines"]]
    return _parse_s17_from_lines(lines, d["W"], d["H"])


def _subs_map(parsed):
    """Mapa {canon: (valor, unidad, rolls)} de substats canonizados."""
    return {
        s.nombre_canon: (s.valor, s.unidad, s.rolls)
        for s in parsed.subs if s.nombre_canon
    }


def test_ejemplo1_jazz_slot1_hp():
    r = _load("Ejemplo_1.json")
    assert r.set_name_raw == "Jazz caótico"
    assert r.slot == 1
    assert r.nivel == 15
    assert r.main_stat_canon == "HP"
    assert r.main_valor == 2200.0
    m = _subs_map(r)
    # ATK% (3%, 0 rolls) y ATK flat (38, 1 roll) coexisten — desambiguados por unidad
    assert m["ATK%"] == (3.0, "%", 0)
    assert m["ATK"] == (38.0, "flat", 1)
    assert m["Daño Crítico"] == (9.6, "%", 1)
    assert m["Maestría de Anomalía"] == (27.0, "flat", 2)


def test_ejemplo8_slot6_tasa_anomalia():
    """Slot 6 main = 'Tasa de Anomalía' 30% (NO 'Maestría de Anomalía')."""
    r = _load("Ejemplo_8.json")
    assert r.slot == 6
    assert r.main_stat_canon == "Tasa de Anomalía"
    assert r.main_valor == 30.0
    assert r.main_unidad == "%"
    # y NO debe haber nota de main inválido para el slot
    assert not any("main_invalido" in n for n in r.notas), r.notas


def test_ejemplo9_slot4_maestria_flat():
    """Slot 4 main = 'Maestría de Anomalía' flat (distinta de Tasa)."""
    r = _load("Ejemplo_9.json")
    assert r.slot == 4
    assert r.main_stat_canon == "Maestría de Anomalía"
    assert r.main_valor == 92.0
    assert r.main_unidad == "flat"


def test_titulo_dos_lineas():
    """Sets de nombre largo parten el título en 2 líneas; el slot va al final."""
    r2 = _load("Ejemplo_2.json")
    assert r2.set_name_raw == "Nana a la luz cenicienta"
    assert r2.slot == 1
    r4 = _load("Ejemplo_4.json")
    assert r4.set_name_raw == "Monarca del Pináculo"
    assert r4.slot == 1
    r10 = _load("Ejemplo_10.json")
    assert r10.set_name_raw == "Melodia de Faetón"
    assert r10.slot == 2


@pytest.mark.parametrize("name", [
    "Ejemplo_1.json", "Ejemplo_2.json", "Ejemplo_3.json", "Ejemplo_4.json",
    "Ejemplo_5.json", "Ejemplo_8.json", "Ejemplo_9.json", "Ejemplo_10.json",
])
def test_estructura_basica(name):
    """Invariantes en todas las capturas: slot 1-6, nivel 15, 4 substats, rolls ≤ 5."""
    r = _load(name)
    assert 1 <= r.slot <= 6, f"slot={r.slot}"
    assert r.nivel == 15
    assert len(r.subs) == 4, f"{len(r.subs)} substats"
    assert sum(s.rolls for s in r.subs) <= 5
    assert r.main_stat_canon is not None
    # main válido para su slot (no debe emitir nota de invalidez)
    assert not any("main_invalido" in n for n in r.notas), r.notas


def test_rolls_badge_envuelto_se_fusiona():
    """
    Bug en vivo (2026-06-06, Melodía de Faetón slot 5): cuando el nombre del
    substat es largo ('Probabilidad de Crítico'), el juego parte el badge '+1' a
    una línea aparte. Antes se leía con rolls=0 y el '+1' quedaba fantasma.
    Reproduce las líneas OCR con bbox (W=2557) y verifica que el roll se fusiona.
    """
    W, H = 2557, 1439
    lines = [
        ("Melodia de Faeton (5)",        0.99, (812, 164, 1170, 222)),
        ("Nivel 15/15",                  0.99, (924, 249, 1103, 286)),
        ("Atributo principal",           0.99, (818, 317, 1058, 349)),
        ("Ataque",                       0.99, (836, 378, 950, 410)),
        ("30 %",                         0.99, (1201, 376, 1286, 413)),
        ("Atributos secundarios",        0.99, (818, 444, 1113, 476)),
        ("Dano Critico +1",              0.99, (839, 508, 1057, 537)),
        ("9.6 %",                        0.99, (1233, 508, 1284, 532)),
        ("Maestria de Anomalia +2",      0.99, (836, 577, 1164, 606)),
        ("27",                           0.99, (1241, 577, 1281, 606)),
        # nombre largo → el badge "+1" se envuelve a su propia línea debajo
        ("Probabilidad de Critico",      0.99, (839, 645, 1180, 675)),
        ("+1",                           0.95, (839, 682, 884, 710)),
        ("4.8 %",                        0.99, (1233, 660, 1284, 690)),
        ("Ataque",                       0.99, (839, 745, 951, 774)),
        ("19",                           0.99, (1241, 745, 1281, 774)),
        ("Efecto de conjunto",           0.99, (815, 815, 1073, 849)),
        ("Melodia de Faeton",            0.99, (839, 873, 1023, 899)),
        ("2 pistas: Tasa de Anomalia",   0.99, (818, 930, 1294, 964)),
    ]
    r = _parse_s17_from_lines(lines, W, H)
    assert len(r.subs) == 4, [s.nombre_raw for s in r.subs]
    m = {s.nombre_canon: (s.valor, s.unidad, s.rolls) for s in r.subs if s.nombre_canon}
    assert m["Prob. Crítica"] == (4.8, "%", 1), m
    # no debe quedar un substat fantasma sin canon (el '+1' huérfano)
    assert all(s.nombre_raw.strip() for s in r.subs)


def test_coalesce_no_toca_nombres_normales():
    """Sin badges envueltos, _coalesce_rolls_fragments es identidad."""
    names = [
        _Line("Dano Critico +1", 0.99, (839, 508, 1057, 537), 2557),
        _Line("Ataque +1", 0.99, (839, 577, 983, 606), 2557),
        _Line("Maestria de Anomalia +2", 0.99, (836, 645, 1164, 675), 2557),
    ]
    out = _coalesce_rolls_fragments(names)
    assert [l.txt for l in out] == [
        "Dano Critico +1", "Ataque +1", "Maestria de Anomalia +2",
    ]


@pytest.mark.parametrize("name", [
    "Ejemplo_1.json", "Ejemplo_3.json", "Ejemplo_4.json",
    "Ejemplo_5.json", "Ejemplo_8.json", "Ejemplo_9.json", "Ejemplo_10.json",
])
def test_substats_todas_canonizadas(name):
    """Todas las substats deben canonizar (tolera el caso OCR 'Dafo' de Ej.2 aparte)."""
    r = _load(name)
    sin_canon = [s.nombre_raw for s in r.subs if s.nombre_canon is None]
    assert not sin_canon, f"{name}: substats sin canon: {sin_canon}"


# ---------------------------------------------------------------------------
# End-to-end con Paddle vivo: rescate de badge "+N" envuelto y de valor dropeado
# (texto chico que el detector pierde a 960px; re-OCR upscaleado lo recupera).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def paddle_ocr():
    try:
        import cv2
        import numpy as np
        from app.core.ocr_paddle import PaddleBackend
        ocr = PaddleBackend(lang="es")
        sample = _SLOT_IMGS / "Ejemplo_Slot1_1.png"
        if not sample.exists():
            pytest.skip("Sin capturas S17 en el repo para el test e2e")
        frame = cv2.imdecode(np.fromfile(str(sample), dtype=np.uint8), cv2.IMREAD_COLOR)
        text, conf = ocr.text(frame)
        if conf == 0.0 and not text:
            raise RuntimeError("warmup Paddle vacío")
        return ocr
    except Exception as e:
        pytest.skip(f"PaddleOCR no disponible: {e}")


def _img(name):
    import cv2
    import numpy as np
    p = _SLOT_IMGS / name
    if not p.exists():
        pytest.skip(f"falta {name}")
    return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)


def test_e2e_rescata_badge_y_valor(paddle_ocr):
    """
    Slot1_1 (caso reportado en vivo 2026-06-06): 'Probabilidad de Crítico' parte el
    badge '+1' a 2ª línea (Paddle no lo ve) y el valor '9' de 'Maestría de Anomalía'
    se dropea por chico. El rescate por re-OCR upscaleado recupera ambos.
    """
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, _ = parse_disc_s17_full(_img("Ejemplo_Slot1_1.png"), paddle_ocr)
    m = {s.nombre_canon: s for s in parsed.subs if s.nombre_canon}
    assert m["Prob. Crítica"].rolls == 1, "badge +1 envuelto no rescatado"
    assert m["Maestría de Anomalía"].valor == 9.0, "valor dropeado no rescatado"
    assert all(s.valor is not None for s in parsed.subs), "quedó un valor None"


@pytest.mark.parametrize("name", [
    "Ejemplo_Slot1_1.png", "Ejemplo_Slot1_2.png", "Ejemplo_Slot3_2.png",
    "Ejemplo_Slot6_2.png",
])
def test_e2e_sin_substats_sin_valor_ni_desconocidos(paddle_ocr, name):
    """Invariantes e2e: 4 substats canonizados, con valor, rolls totales ≤ 5."""
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, _ = parse_disc_s17_full(_img(name), paddle_ocr)
    assert len(parsed.subs) == 4, name
    assert all(s.nombre_canon for s in parsed.subs), \
        [s.nombre_raw for s in parsed.subs if not s.nombre_canon]
    assert all(s.valor is not None for s in parsed.subs), name
    assert sum(s.rolls for s in parsed.subs) <= 5, name


def test_e2e_ene_tilde_dano_critico(paddle_ocr):
    """La 'ñ' mangleada de 'Daño Crítico' canoniza vía fallback difuso (Slot1_2)."""
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, _ = parse_disc_s17_full(_img("Ejemplo_Slot1_2.png"), paddle_ocr)
    canons = {s.nombre_canon for s in parsed.subs}
    assert "Daño Crítico" in canons, canons


# Grilla de visualización: detección equipado/no-equipado por densidad de bordes.
_INV_IMGS = (
    Path(__file__).resolve().parents[3]
    / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
    / "04_Inventario_Disco_Vista_Individual"
)


def _inv_img(name):
    import cv2
    import numpy as np
    p = _INV_IMGS / name
    if not p.exists():
        pytest.skip(f"falta {name}")
    return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)


def test_e2e_avatar_no_equipado(paddle_ocr):
    """
    Disco candidato SIN equipar (sin avatar a la derecha del set): el detector por
    densidad de bordes NO debe dar falso positivo, aunque el arte de fondo esté
    saturado (Ejemplo_11_nangong, 'Blues libre'). Regresión 2026-06-07.
    """
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, face = parse_disc_s17_full(_inv_img("Ejemplo_11_nangong.png"), paddle_ocr)
    assert parsed.set_name_raw.startswith("Blues"), parsed.set_name_raw
    assert face is None, "falso positivo: detectó avatar donde no hay (fondo saturado)"


def test_e2e_avatar_equipado_otro_pj(paddle_ocr):
    """Disco candidato equipado por otro PJ (avatar presente): se detecta (Ejemplo_12)."""
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, face = parse_disc_s17_full(_inv_img("Ejemplo_12_nangong.png"), paddle_ocr)
    assert parsed.set_name_raw.startswith("Voz"), parsed.set_name_raw
    assert face is not None, "no detectó el avatar del disco equipado"


# --- Fase 2: OCR sobre crop nativo del panel -------------------------------------

@pytest.mark.parametrize("name,slot", [
    ("Ejemplo_Slot1_1.png", 1), ("Ejemplo_Slot2_1.png", 2),
    ("Ejemplo_Slot3_1.png", 3), ("Ejemplo_Slot4_1.png", 4),
    ("Ejemplo_Slot5_1.png", 5), ("Ejemplo_Slot6_1.png", 6),
])
def test_e2e_crop_slot_correcto(paddle_ocr, name, slot):
    """
    El path de crop nativo (parse_disc_s17_full) extrae el slot 1-6 correcto en
    todas las capturas, incluido slot=1 (el '(1)' fino que el crop pierde y el
    rescate de título recupera). Regresión Fase 2.
    """
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, _ = parse_disc_s17_full(_img(name), paddle_ocr)
    assert parsed.slot == slot, f"{name}: slot={parsed.slot} (esperado {slot})"
    assert parsed.main_stat_canon is not None and parsed.main_valor is not None
    assert len(parsed.subs) == 4 and all(s.valor is not None for s in parsed.subs)


def test_rescue_slot_from_title_slot1(paddle_ocr):
    """El rescate de slot lee el '(1)' de una franja fina del título (Slot1_1)."""
    from app.core.parser_disc_s17 import _rescue_slot_from_title
    frame = _img("Ejemplo_Slot1_1.png")
    H, W = frame.shape[:2]
    assert _rescue_slot_from_title(frame, paddle_ocr, W, H) == 1


def test_e2e_crop_tier_detectado(paddle_ocr):
    """detect_active_set_tier sigue funcionando sobre el crop (la línea '4 pistas:'
    entra en el ROI del panel). Slot1_2 = build 4pc activo."""
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, _ = parse_disc_s17_full(_img("Ejemplo_Slot1_2.png"), paddle_ocr)
    assert parsed.set_active_tier == 4, parsed.set_active_tier


def test_e2e_no_substat_fantasma_numerico(paddle_ocr):
    """
    Regresión QA Burnice 2026-06-08 (Slot6): un fragmento numérico ('12') que cae en
    la columna de NOMBRE no debe generar un 5º substat fantasma con canon=None. Se
    filtran los nombres sin letras (los badges '+N' legítimos ya se fusionaron antes).
    """
    from app.core.parser_disc_s17 import parse_disc_s17_full
    parsed, _ = parse_disc_s17_full(_img("Ejemplo_Slot6_3.png"), paddle_ocr)
    assert len(parsed.subs) == 4, [s.nombre_raw for s in parsed.subs]
    assert all(s.nombre_canon for s in parsed.subs), \
        [s.nombre_raw for s in parsed.subs if not s.nombre_canon]


def test_ocr_detail_lines_offset_a_frame_completo(paddle_ocr):
    """`_ocr_detail_lines` re-offsetea las bboxes a coords de frame completo: las
    líneas del panel caen en la banda x∈[0.30,0.52] (no en [0,ancho_del_crop])."""
    from app.core.parser_disc_s17 import _ocr_detail_lines, _BAND_X_MIN, _BAND_X_MAX
    frame = _img("Ejemplo_Slot1_1.png")
    H, W = frame.shape[:2]
    lines = _ocr_detail_lines(frame, paddle_ocr)
    assert lines, "sin líneas"
    # alguna línea del panel debe caer dentro de la banda en coords de frame completo
    in_band = [l for l in lines if _BAND_X_MIN <= (l[2][0] / W) <= _BAND_X_MAX]
    assert in_band, "las bboxes no están en coords de frame completo (offset roto)"
    assert all(l[2][2] <= W and l[2][3] <= H for l in lines), "bbox fuera del frame"
