"""Parser del modal "Obtenido" (S22): drops del farmeo por baterías.

Ground-truth de los 4 fixtures (leído a ojo de los screenshots; los 4 son la misma tanda de
4 corridas del nodo "El piloto y el meca rebelde", a distintas posiciones de scroll):

    uso 1 → slots 2, 6      uso 2 → slots 2, 3, 6
    uso 3 → slots 4, 4, 4   uso 4 → slots 2, 5, 5

Los fixtures se solapan (el scroll muestra secciones parciales), así que cada test declara qué
espera ver EN ESE frame, no la tanda entera.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core import parser_extraccion as pe

_FX = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
       / "Discos_Triggers" / "20_Extraccion_Baterias")
_NAMES = ("Resultados_discos.png", "Resultados_discos_2.png",
          "Resultados_discos_3.png", "Resultados_discos_4.png")
_FILES = [_FX / n for n in _NAMES]

pytestmark = pytest.mark.skipif(not all(p.exists() for p in _FILES),
                                reason="capturas del modal 'Obtenido' no presentes")


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def _ocr():
    try:
        from app.core.ocr_tesseract import TesseractBackend
        return TesseractBackend()
    except Exception:
        pytest.skip("Tesseract no disponible")


class _FakeMatcher:
    """Matcher de set falso: devuelve siempre el 1er candidato (la lógica del matcher real
    está cubierta por test_set_badge_matcher)."""
    def identify(self, bgr, cand_en):
        from app.core.avatar_descriptor import MatchResult
        return MatchResult(cand_en[0], 0.66, 0.2, False, [])


# --- geometría -----------------------------------------------------------------------------


@pytest.mark.parametrize("fx", _FILES, ids=lambda p: p.name)
def test_las_filas_se_detectan_con_paso_regular(fx):
    """El scroll corre el `y` de las filas, pero el paso es de solo dos tipos: 0.123 entre
    filas de la MISMA corrida, y 0.171 cuando en el medio va el header de la siguiente."""
    rows = pe.strip_rows(_load(fx))
    assert len(rows) >= 2, f"esperaba ≥2 filas, hubo {rows}"
    for p in (b - a for a, b in zip(rows, rows[1:])):
        assert abs(p - 0.123) < 0.005 or abs(p - 0.171) < 0.005, \
            f"paso {p:.4f} no es intra (0.123) ni inter-sección (0.171) — rows={rows}"


@pytest.mark.parametrize("fx", _FILES, ids=lambda p: p.name)
def test_ningun_tile_excede_el_viewport(fx):
    """Un tile clipeado perdería el badge de slot → slot inventado. Se descartan enteros."""
    frame = _load(fx)
    H = frame.shape[0]
    for cy in pe.strip_rows(frame):
        for box in pe.gold_boxes(frame, cy):
            assert box.y0 >= int(pe._VIEWPORT_Y[0] * H)
            assert box.y1 <= int(pe._VIEWPORT_Y[1] * H)


def test_localiza_los_discos_dorados():
    """Conteo de tiles S por frame (los fixtures se solapan por el scroll)."""
    esperado = {"Resultados_discos.png": 2,        # uso 1 (2 filas visibles, los S en la 1ª)
                "Resultados_discos_2.png": 3,      # uso 2
                "Resultados_discos_3.png": 3,      # uso 3
                "Resultados_discos_4.png": 3}      # uso 4
    for name, n in esperado.items():
        frame = _load(_FX / name)
        total = sum(len(pe.gold_boxes(frame, cy)) for cy in pe.strip_rows(frame))
        assert total == n, f"{name}: esperaba {n} discos S, hubo {total}"


# --- header de sección ---------------------------------------------------------------------


def test_regex_del_header_tolera_lo_que_el_ocr_hace_con_n_grado():
    """El OCR devuelve 'n.º' de mil formas; el nº de corrida tiene que sobrevivir a todas."""
    for txt, exp in [("Con el uso n.º 2 se obtiene:", 2),
                     ("Con el uso n.° 2 se obtiene:", 2),
                     ("Con el uso n.* 1 se obtiene:", 1),
                     ("Con el uso n.� 3 se obtiene:", 3),   # lo que devuelve Tesseract real
                     ("Con eluso n 4 se obtiene", 4)]:
        m = pe._RE_HEADER.search(txt)
        assert m and int(m.group(1)) == exp, f"{txt!r} → {m}"

    # Regresión: el OCR puede mutilar el "º" en un DÍGITO. Un patrón laxo (`n\D{0,4}(\d)`)
    # leía esto como corrida 9 en vez de 3 — un error silencioso, no una abstención.
    m = pe._RE_HEADER.search("Con el uso n.9 3 se obtiene:")
    assert m and int(m.group(1)) == 3, "el '9' del 'º' mutilado no debe ganarle al nº real"

    for txt in ["600 1 1", "", "basura sin nada", "Obtenido"]:
        assert pe._RE_HEADER.search(txt) is None, f"{txt!r} no debería matchear"


def test_lee_el_numero_de_corrida_de_cada_fixture():
    esperado = {"Resultados_discos.png": 1, "Resultados_discos_2.png": 2,
                "Resultados_discos_3.png": 3, "Resultados_discos_4.png": 4}
    ocr = _ocr()
    for name, n_uso in esperado.items():
        frame = _load(_FX / name)
        leidos = [pe.read_section_header(frame, cy, ocr) for cy in pe.strip_rows(frame)]
        assert n_uso in leidos, f"{name}: esperaba leer el uso {n_uso}, leyó {leidos}"


def test_una_fila_que_no_encabeza_seccion_no_inventa_header():
    """Sobre una fila interior, el ROI del header cae en los labels de cantidad de la fila de
    arriba ('600 1 1') → el regex los rechaza. Es lo que permite agrupar sin heurística de gap."""
    ocr = _ocr()
    frame = _load(_FX / "Resultados_discos.png")
    rows = pe.strip_rows(frame)
    assert pe.read_section_header(frame, rows[0], ocr) == 1     # 1ª fila: sí encabeza
    assert pe.read_section_header(frame, rows[1], ocr) is None   # 2ª fila: no


# --- scroll --------------------------------------------------------------------------------


def test_la_flecha_de_abajo_marca_el_fondo_de_la_lista():
    """`Resultados_discos_4` es la última corrida → sin ▼. Es lo que cierra la última sección."""
    for name in _NAMES[:3]:
        assert pe.has_more_below(_load(_FX / name)) is True, f"{name}: esperaba ▼"
    assert pe.has_more_below(_load(_FX / "Resultados_discos_4.png")) is False


def test_la_flecha_de_arriba_marca_el_tope():
    assert pe.has_more_above(_load(_FX / "Resultados_discos.png")) is False   # tope
    assert pe.has_more_above(_load(_FX / "Resultados_discos_3.png")) is True


# --- parse completo ------------------------------------------------------------------------


def test_parse_agrupa_por_corrida_y_lee_los_slots():
    """El caso feliz: uso 1 con sus 2 discos S (slots 2 y 6) y su set."""
    ocr = _ocr()
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), ocr,
                             _FakeMatcher(), ["Wuthering Salon", "The Sky Ablaze"])
    assert [s.n_uso for s in secs] == [1]
    assert [d.slot for d in secs[0].discos] == [2, 6]
    assert all(d.set_name == "Wuthering Salon" for d in secs[0].discos)


def test_parse_lee_los_slots_de_cada_corrida():
    """Slots por fixture. El uso 3 (tres '4') abstiene: el OCR del glifo estilizado falla
    crónicamente en el '4' y el matcher NCC está descartado acá (ver `_AlwaysAbstain`).
    Lo que NO puede pasar nunca es un slot EQUIVOCADO."""
    ocr = _ocr()
    esperado = {"Resultados_discos.png": [2, 6],
                "Resultados_discos_2.png": [2, 3, 6],
                "Resultados_discos_3.png": [None, None, None],   # '4' → abstiene, no yerra
                "Resultados_discos_4.png": [2, 5, 5]}
    for name, slots in esperado.items():
        secs = pe.parse_obtenido(_load(_FX / name), ocr)
        got = [d.slot for s in secs for d in s.discos]
        assert got == slots, f"{name}: esperaba {slots}, salió {got}"


def test_el_slot_nunca_sale_equivocado():
    """La garantía RNF-02: 8/11 exactos y 3 abstenciones, CERO errores."""
    ocr = _ocr()
    verdad = {"Resultados_discos.png": [2, 6], "Resultados_discos_2.png": [2, 3, 6],
              "Resultados_discos_3.png": [4, 4, 4], "Resultados_discos_4.png": [2, 5, 5]}
    ok = err = absn = 0
    for name, exp in verdad.items():
        secs = pe.parse_obtenido(_load(_FX / name), ocr)
        got = [d.slot for s in secs for d in s.discos]
        assert len(got) == len(exp), f"{name}: {len(got)} discos vs {len(exp)}"
        for g, e in zip(got, exp):
            ok, err, absn = (ok + 1, err, absn) if g == e else (
                (ok, err, absn + 1) if g is None else (ok, err + 1, absn))
    assert err == 0, f"{err} slot(s) EQUIVOCADOS — viola RNF-02"
    assert (ok, absn) == (8, 3), f"accuracy cambió: {ok} ok / {absn} abstenciones"


def test_seccion_incompleta_no_se_declara_completa():
    """`Resultados_discos` muestra el uso 1 con ▼ y sin el header del uso 2 todavía → no se
    puede afirmar que no haya más discos suyos abajo."""
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), _ocr())
    assert secs[0].completa is False


def test_el_fondo_de_la_lista_cierra_la_ultima_seccion():
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos_4.png"), _ocr())
    assert [s.n_uso for s in secs] == [4]
    assert secs[0].completa is True


def test_el_header_de_la_siguiente_corrida_cierra_la_actual():
    """`Resultados_discos_3` muestra el uso 3 y, debajo, ya asoma el header del uso 4 (su
    primera FILA todavía no). Ver ese header prueba que el uso 3 no tiene más filas → cierra.

    Sin este oráculo el uso 3 no cerraría NUNCA: al scrollear un poco más, sus filas pasan a
    ser huérfanas (su propio header sale de pantalla) y se descartan, así que la evidencia de
    cierre no vuelve a aparecer y quedaría en '≥3' para siempre."""
    frame = _load(_FX / "Resultados_discos_3.png")
    ocr = _ocr()
    assert pe.next_section_header(frame, pe.strip_rows(frame)[-1], ocr) == 4
    secs = pe.parse_obtenido(frame, ocr)
    assert [s.n_uso for s in secs] == [3]
    assert secs[0].completa is True


def test_sin_evidencia_de_cierre_no_se_declara_completa():
    """`Resultados_discos` muestra el uso 1 con ▼ y sin asomar el header del uso 2 → no se
    puede afirmar que no haya más discos suyos abajo."""
    frame = _load(_FX / "Resultados_discos.png")
    ocr = _ocr()
    assert pe.next_section_header(frame, pe.strip_rows(frame)[-1], ocr) is None
    assert pe.parse_obtenido(frame, ocr)[0].completa is False


def test_filas_huerfanas_se_descartan():
    """`Resultados_discos_2` arranca con la cola del uso 1 (su header quedó scrolleado fuera):
    esas filas no se pueden atribuir a ninguna corrida → se descartan, no se fusionan."""
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos_2.png"), _ocr())
    assert [s.n_uso for s in secs] == [2]


def test_sin_matcher_no_hay_set_pero_si_discos():
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), _ocr(), matcher=None)
    assert len(secs[0].discos) == 2
    assert all(d.set_name is None for d in secs[0].discos)


def test_sin_candidatos_no_se_afirma_set():
    """Sin predicción de nodo (S13), el matcher no tiene contra qué comparar → abstención."""
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), _ocr(),
                             _FakeMatcher(), cand_en=[])
    assert all(d.set_name is None for d in secs[0].discos)


def test_frame_vacio_no_rompe():
    assert pe.parse_obtenido(np.zeros((1439, 2559, 3), np.uint8), None) == []
    assert pe.strip_rows(None) == []
    assert pe.count_rarity_strips_viewport(None) == 0


# --- verificación anti-FP ------------------------------------------------------------------


@pytest.mark.parametrize("fx", _FILES, ids=lambda p: p.name)
def test_las_franjas_verifican_el_estado(fx):
    n = pe.count_rarity_strips_viewport(_load(fx))
    assert n >= pe._EXTRACCION_STRIP_MIN, f"{fx.name}: solo {n} franjas"
