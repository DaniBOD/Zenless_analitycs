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


# Cache por proceso: instanciar un backend (sobre todo PaddleOCR) cuesta segundos, y estos
# tests lo piden una vez por caso parametrizado.
_BACKENDS: dict[str, object] = {}


def _backend(name: str):
    if name not in _BACKENDS:
        try:
            if name == "tesseract":
                from app.core.ocr_tesseract import TesseractBackend
                _BACKENDS[name] = TesseractBackend()
            else:
                from app.core.ocr_paddle import PaddleBackend
                _BACKENDS[name] = PaddleBackend()
        except Exception:
            _BACKENDS[name] = None
    if _BACKENDS[name] is None:
        pytest.skip(f"{name} no disponible")
    return _BACKENDS[name]


@pytest.fixture(params=["tesseract", "paddle"], scope="session")
def ocr(request):
    """Los DOS backends. La app usa PaddleOCR de primario; testear solo con Tesseract dejó
    pasar DOS bugs que rompían el feature en producción (QA en vivo 2026-07-16): Paddle pega el
    número al texto ('n.*1se obtiene') donde Tesseract deja espacio, y su detección es marginal
    en la banda del header. Todo lo que dependa del OCR se testea contra los dos."""
    return _backend(request.param)


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
    """El OCR devuelve 'n.º' de mil formas; el nº de corrida tiene que sobrevivir a todas.
    Los marcados como REAL son salidas literales de los backends sobre los fixtures."""
    for txt, exp in [("Con el uso n.º 2 se obtiene:", 2),
                     ("Con el uso n.° 2 se obtiene:", 2),
                     ("Con el uso n.* 1 se obtiene:", 1),      # REAL — Tesseract
                     ("Con el uso n.� 3 se obtiene:", 3),      # REAL — Tesseract
                     ("Con el uso n.” 3 se obtiene:", 3),      # REAL — Tesseract
                     ("Con el uso n.*1se obtiene:", 1),        # REAL — PaddleOCR (sin espacios)
                     ("Con eluso n.° 3 se obtiene:", 3),       # REAL — PaddleOCR (se come el 'el')
                     ("Con eluso n 4 se obtiene", 4)]:
        m = pe._RE_HEADER.search(txt)
        assert m and int(m.group(1)) == exp, f"{txt!r} → {m}"

    # Regresión: el OCR puede mutilar el "º" en un DÍGITO. Un patrón laxo (`n\D{0,4}(\d)`)
    # leía esto como corrida 9 en vez de 3 — un error silencioso, no una abstención. Lo que lo
    # desambigua es el ancla de cola: solo el dígito seguido de "se obtiene" cuenta.
    m = pe._RE_HEADER.search("Con el uso n.9 3 se obtiene:")
    assert m and int(m.group(1)) == 3, "el '9' del 'º' mutilado no debe ganarle al nº real"

    for txt in ["600 1 1", "", "basura sin nada", "Obtenido", "Con el uso n.º 2"]:
        assert pe._RE_HEADER.search(txt) is None, f"{txt!r} no debería matchear"


def test_lee_el_numero_de_corrida_de_cada_fixture(ocr):
    esperado = {"Resultados_discos.png": 1, "Resultados_discos_2.png": 2,
                "Resultados_discos_3.png": 3, "Resultados_discos_4.png": 4}
    for name, n_uso in esperado.items():
        frame = _load(_FX / name)
        leidos = [pe.read_section_header(frame, cy, ocr) for cy in pe.strip_rows(frame)]
        assert n_uso in leidos, f"{name}: esperaba leer el uso {n_uso}, leyó {leidos}"


def test_una_fila_que_no_encabeza_seccion_no_inventa_header(ocr):
    """Sobre una fila interior, el ROI del header cae en los labels de cantidad de la fila de
    arriba ('600 1 1') → el regex los rechaza. Es lo que permite agrupar sin heurística de gap."""
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


def test_parse_agrupa_por_corrida_y_lee_los_slots(ocr):
    """El caso feliz: uso 1 con sus 2 discos S (slots 2 y 6) y su set."""
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), ocr,
                             _FakeMatcher(), ["Wuthering Salon", "The Sky Ablaze"])
    assert [s.n_uso for s in secs] == [1]
    assert [d.slot for d in secs[0].discos] == [2, 6]
    assert all(d.set_name == "Wuthering Salon" for d in secs[0].discos)


def test_parse_lee_los_slots_de_cada_corrida(ocr):
    """Slots por fixture. Depende del GATE del matcher (ver `_get_slot_matcher_extraccion`):

      * set de refs INCOMPLETO (hoy: falta el slot 1) → matcher apagado, manda el OCR, y el
        uso 3 (tres '4') ABSTIENE: Tesseract lee el '4' estilizado como 'a' siempre.
      * set COMPLETO → matcher activo y los tres '4' salen (medido: score 0.999).

    En los dos casos el invariante duro es el mismo: un slot puede faltar, NUNCA ser equivocado.

    Parametrizado por backend a propósito: el resultado debe ser IDÉNTICO con los dos, porque
    el slot NO usa el `ocr` que se pasa — usa Tesseract siempre (ver `_get_slot_ocr`)."""
    matcher_activo = pe._get_slot_matcher_extraccion().n_refs > 0
    cuatros = [4, 4, 4] if matcher_activo else [None, None, None]
    esperado = {"Resultados_discos.png": [2, 6],
                "Resultados_discos_2.png": [2, 3, 6],
                "Resultados_discos_3.png": cuatros,
                "Resultados_discos_4.png": [2, 5, 5]}
    for name, slots in esperado.items():
        secs = pe.parse_obtenido(_load(_FX / name), ocr)
        got = [d.slot for s in secs for d in s.discos]
        assert got == slots, f"{name}: esperaba {slots}, salió {got}"


def test_el_slot_nunca_sale_equivocado(ocr):
    """La garantía RNF-02: 8/11 exactos y 3 abstenciones, CERO errores — con CUALQUIER backend.

    Regresión del QA en vivo 2026-07-16: medido sobre estos mismos 11 tiles, PaddleOCR (el
    primario de la app) daba 7/11 con **4 errores y 0 abstenciones** — no sabe abstenerse en un
    glifo suelto y siempre devuelve su mejor conjetura. Por eso el slot fuerza Tesseract."""
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
    # El invariante DURO (RNF-02) no depende del gate: jamás un slot equivocado.
    assert err == 0, f"{err} slot(s) EQUIVOCADOS — viola RNF-02"
    # La accuracy sí depende del gate del matcher (ver `_get_slot_matcher_extraccion`): con el
    # set de refs completo (6 clases) lee los 11; sin él, solo OCR = 8/11 con 3 abstenciones
    # (los tres '4'). Cosechar Ejemplo_12 completó el set y encendió el matcher (2026-07-18).
    if pe._get_slot_matcher_extraccion().n_refs > 0:
        assert (ok, absn) == (11, 0), f"matcher activo: {ok} ok / {absn} abstenciones"
    else:
        assert (ok, absn) == (8, 3), f"solo OCR: {ok} ok / {absn} abstenciones"


def test_seccion_incompleta_no_se_declara_completa(ocr):
    """`Resultados_discos` muestra el uso 1 con ▼ y sin el header del uso 2 todavía → no se
    puede afirmar que no haya más discos suyos abajo."""
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), ocr)
    assert secs[0].completa is False


def test_el_fondo_de_la_lista_cierra_la_ultima_seccion(ocr):
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos_4.png"), ocr)
    assert [s.n_uso for s in secs] == [4]
    assert secs[0].completa is True


def test_el_header_de_la_siguiente_corrida_cierra_la_actual(ocr):
    """`Resultados_discos_3` muestra el uso 3 y, debajo, ya asoma el header del uso 4 (su
    primera FILA todavía no). Ver ese header prueba que el uso 3 no tiene más filas → cierra.

    Sin este oráculo el uso 3 no cerraría NUNCA: al scrollear un poco más, sus filas pasan a
    ser huérfanas (su propio header sale de pantalla) y se descartan, así que la evidencia de
    cierre no vuelve a aparecer y quedaría en '≥3' para siempre."""
    frame = _load(_FX / "Resultados_discos_3.png")
    assert pe.next_section_header(frame, pe.strip_rows(frame)[-1], ocr) == 4
    secs = pe.parse_obtenido(frame, ocr)
    assert [s.n_uso for s in secs] == [3]
    assert secs[0].completa is True


def test_sin_evidencia_de_cierre_no_se_declara_completa(ocr):
    """`Resultados_discos` muestra el uso 1 con ▼ y sin asomar el header del uso 2 → no se
    puede afirmar que no haya más discos suyos abajo."""
    frame = _load(_FX / "Resultados_discos.png")
    assert pe.next_section_header(frame, pe.strip_rows(frame)[-1], ocr) is None
    assert pe.parse_obtenido(frame, ocr)[0].completa is False


def test_filas_huerfanas_se_descartan(ocr):
    """`Resultados_discos_2` arranca con la cola del uso 1 (su header quedó scrolleado fuera):
    esas filas no se pueden atribuir a ninguna corrida → se descartan, no se fusionan."""
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos_2.png"), ocr)
    assert [s.n_uso for s in secs] == [2]


def test_sin_matcher_no_hay_set_pero_si_discos(ocr):
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), ocr, matcher=None)
    assert len(secs[0].discos) == 2
    assert all(d.set_name is None for d in secs[0].discos)


def test_sin_candidatos_no_se_afirma_set(ocr):
    """Sin predicción de nodo (S13), el matcher no tiene contra qué comparar → abstención."""
    secs = pe.parse_obtenido(_load(_FX / "Resultados_discos.png"), ocr,
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


# --- panel DETAIL (disco seleccionado) -----------------------------------------------------

_EJ = sorted(_FX.glob("Ejemplo_*.png"),
             key=lambda p: int("".join(c for c in p.name if c.isdigit())))

# Ground-truth de los 11 discos, leído del propio panel DETAIL de cada screenshot.
_EJ_TRUTH = {
    1: ("Salón huracanado", 2), 2: ("Firmamento llameante", 6), 3: ("Salón huracanado", 2),
    4: ("Salón huracanado", 3), 5: ("Firmamento llameante", 6), 6: ("Salón huracanado", 4),
    7: ("Firmamento llameante", 4), 8: ("Firmamento llameante", 4),
    9: ("Firmamento llameante", 2), 10: ("Firmamento llameante", 5),
    11: ("Firmamento llameante", 5),
    # Ejemplo_12 es una captura del "Obtenido" completa (grilla + panel DETAIL); su detalle es
    # un slot 1 — el único de todo el set, y el caso que destapó el bug del "(" comido por el OCR.
    12: ("Firmamento llameante", 1),
}


@pytest.mark.skipif(not _EJ, reason="ejemplos del panel DETAIL no presentes")
def test_el_detalle_lee_set_slot_y_stats_de_los_11_discos():
    """Los slots leídos del panel DETAIL coinciden con el ground-truth de la GRILLA — incluidos
    los tres '4' que la grilla no puede leer y el slot 1 de Ejemplo_12. El panel es la fuente
    autoritativa del slot: viene en texto, no como glifo."""
    from app.db.connection import get_connection
    from app.db.repositories import DiscSetRepo
    repo = DiscSetRepo(get_connection("db/danibod_zzz_v2.db"))
    ocr = _backend("paddle")
    for p in _EJ:
        n = int("".join(c for c in p.name if c.isdigit()))
        set_esp, slot = _EJ_TRUTH[n]
        d = pe.parse_detail_disc(_load(p), ocr)
        assert d is not None, f"{p.name}: no detectó disco"
        assert d.slot == slot, f"{p.name}: slot {d.slot} != {slot}"
        sid = repo.resolve_id(d.set_name_raw)
        canon = next((e.nombre for e in repo.get_all() if e.id == sid), None)
        assert canon == set_esp, f"{p.name}: set {canon!r} != {set_esp!r} (raw={d.set_name_raw!r})"
        assert d.main_stat_canon or d.main_stat_raw, f"{p.name}: sin atributo principal"
        assert len(d.subs) >= 3, f"{p.name}: solo {len(d.subs)} substats"
        assert all(s.valor is not None for s in d.subs), f"{p.name}: substat sin valor"


@pytest.mark.skipif(not _EJ, reason="ejemplos del panel DETAIL no presentes")
def test_el_titulo_de_dos_lineas_no_pierde_el_slot():
    """`Firmamento llameante (4)` envuelve: el '(4)' cae al segundo renglón. Con una franja de
    una sola línea el slot se perdía (aviso del usuario, confirmado en Ejemplo_7/11)."""
    ocr = _backend("paddle")
    for name, slot in [("Ejemplo_7.png", 4), ("Ejemplo_11.png", 5)]:
        nombre, got = pe._read_detail_title(_load(_FX / name), ocr)
        assert got == slot, f"{name}: slot {got} != {slot}"
        assert nombre and "lameante" in nombre, f"{name}: nombre {nombre!r}"


@pytest.mark.skipif(not _EJ, reason="ejemplos del panel DETAIL no presentes")
def test_sin_disco_seleccionado_el_detalle_se_abstiene():
    """El modal abre con "Crédito proxy" en el panel: no es un disco → no se parsea nada.
    La firma es el "(N)" del título; ningún otro ítem lo tiene."""
    ocr = _backend("paddle")
    for name in ("Resultados_discos.png", "Resultados_discos_3.png"):
        frame = _load(_FX / name)
        assert pe.detail_has_disc(frame, ocr) is False, f"{name}: creyó ver un disco"
        assert pe.parse_detail_disc(frame, ocr) is None


# --- Gate del matcher de dígito de slot ---------------------------------------------------
# El matcher NCC resuelve este badge mucho mejor que el OCR (leave-one-sample-out: 9/9, con los
# tres '4' en 0.999), pero SOLO si su set de refs cubre las 6 clases: con clases faltantes no
# abstiene, INVENTA (leave-one-class-out: 6/11 equivocados con score hasta 0.799, solapado con
# los aciertos ≥0.755 → no hay umbral que los separe). De ahí el gate. Ver
# `tools/harvest_extraccion_slot_digits.py` para el detalle de la medición.

def _reset_slot_matcher():
    pe._slot_matcher_extraccion = None
    pe._slot_matcher_loaded = False


def _fake_refs(tmp_path, clases):
    """Set de refs de juguete: un badge por clase (contenido irrelevante, solo el prefijo)."""
    import cv2
    import numpy as np
    for d in clases:
        img = np.full((30, 30, 3), 10 * d, dtype=np.uint8)
        img[10:20, 10:20] = 255 - 10 * d          # que no sean todas iguales
        cv2.imwrite(str(tmp_path / f"{d}_fake_0.png"), img)
    return tmp_path


def test_gate_apaga_el_matcher_si_falta_alguna_clase(tmp_path, monkeypatch):
    """Falta el slot 1 → matcher apagado (RNF-02: mejor abstenerse que inventar)."""
    monkeypatch.setattr(pe, "_EXTRACCION_REFS_DIR", _fake_refs(tmp_path, [2, 3, 4, 5, 6]))
    _reset_slot_matcher()
    try:
        assert pe._get_slot_matcher_extraccion().n_refs == 0
    finally:
        _reset_slot_matcher()


def test_gate_enciende_el_matcher_con_las_6_clases(tmp_path, monkeypatch):
    monkeypatch.setattr(pe, "_EXTRACCION_REFS_DIR", _fake_refs(tmp_path, [1, 2, 3, 4, 5, 6]))
    _reset_slot_matcher()
    try:
        m = pe._get_slot_matcher_extraccion()
        assert m.n_refs == 6 and set(m._refs) == {1, 2, 3, 4, 5, 6}
    finally:
        _reset_slot_matcher()


def test_gate_no_explota_sin_carpeta_de_refs(tmp_path, monkeypatch):
    monkeypatch.setattr(pe, "_EXTRACCION_REFS_DIR", tmp_path / "no_existe")
    _reset_slot_matcher()
    try:
        assert pe._get_slot_matcher_extraccion().n_refs == 0
    finally:
        _reset_slot_matcher()


def test_las_refs_cosechadas_cubren_las_6_clases_y_encienden_el_matcher():
    """Las refs versionadas se leen por el prefijo `<digito>_`. El set se completó con las 6
    clases al cosechar el slot 1 de Ejemplo_12 (2026-07-18) → el matcher queda ACTIVO. Este
    test es la guarda de que no se pierda ninguna clase (volvería a apagarse en silencio)."""
    if not pe._EXTRACCION_REFS_DIR.exists():
        pytest.skip("no hay refs cosechadas")
    clases = {int(p.name[0]) for p in pe._EXTRACCION_REFS_DIR.glob("*.png")}
    assert clases <= set(range(1, 7)), f"prefijo fuera de rango: {clases}"
    assert clases == set(range(1, 7)), f"faltan clases (matcher se apagaría): {sorted(clases)}"
    assert pe._get_slot_matcher_extraccion().n_refs > 0, "el matcher debería estar activo"
