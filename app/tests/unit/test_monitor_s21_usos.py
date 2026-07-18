"""Handler del modal de USOS de batería (S21) en el monitor (`_process_s21_usos`).

S21 es la previa del farmeo por baterías: el usuario elige cuántas corridas (`Cantidad
consumida × N`) va a lanzar con el auto-combate. El handler OCRea ese N, lo guarda en
`FarmSession` (el "Obtenido" lo usa después como denominador de "uso 2/4") y emite un
diagnóstico display-only con el nodo predicho en S13. No persiste ni puntúa.

OCR falso para testear la lógica de forma determinista (el OCR real sobre los screenshots
está cubierto por `test_s21_lee_los_screenshots_reales`).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from app.core.detector import ScreenState
from app.core.farm_nodes import FarmNodeCatalog

_TOML = Path(__file__).resolve().parents[2] / "resources" / "farm_nodes.toml"
_FX = (Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
       / "Discos_Triggers" / "20_Extraccion_Baterias")


def _catalog() -> FarmNodeCatalog:
    import tomllib
    with open(_TOML, "rb") as f:
        nodes = tomllib.load(f)["nodes"]
    ens: list[str] = []
    for n in nodes:
        ens.extend(n["sets_en"])
    ids = {en: i + 1 for i, en in enumerate(dict.fromkeys(ens))}
    return FarmNodeCatalog.from_toml(_TOML, ids)


class _RoiOcr:
    """OCR falso: devuelve un texto distinto según el ALTO del crop, que es lo que separa al
    ROI de usos (0.042) del de stock (0.045). Permite testear ambas lecturas en un solo frame."""
    def __init__(self, usos: str, stock: str = "Bateria eterea x8"):
        self.usos, self.stock = usos, stock

    def text(self, img, psm: int = 6, lang: str = "spa"):
        h = img.shape[0]
        return (self.usos if h < 63 else self.stock), 0.99


class _SeqOcr:
    """OCR falso que va devolviendo textos de usos en secuencia (simula mover el slider)."""
    def __init__(self, usos_seq):
        self.seq = list(usos_seq)
        self.i = 0

    def text(self, img, psm: int = 6, lang: str = "spa"):
        if img.shape[0] >= 63:
            return "Bateria eterea x8", 0.99
        t = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return t, 0.99


def _monitor(ocr, diags):
    import app.core.monitor as mon
    from app.core.farm_session import FarmSession
    return mon.Monitor(ocr=ocr, detector=None, on_diagnostic=diags.append,
                       farm_session=FarmSession(), farm_node_catalog=_catalog())


def _frame(fill: int = 0):
    # `fill` distinto → firma del ROI distinta (pasa el gate de re-OCR RNF-06).
    return np.full((1439, 2559, 3), fill, dtype=np.uint8)


_ST21 = ScreenState("S21", 1.0, "s21_seleccion_usos.png")


def test_s21_lee_los_usos_y_los_guarda_en_farm_session():
    diags: list[str] = []
    m = _monitor(_RoiOcr("Cantidad consumida x 3"), diags)
    m._dispatch_state(_frame(), _ST21)

    linea = [d for d in diags if d.startswith("[extracción]")]
    assert linea, f"esperaba una línea de extracción, diags={diags}"
    assert "3 uso(s)" in linea[-1]
    assert m._farm_session.usos(time.monotonic()) == 3


def test_s21_incluye_el_nodo_predicho_en_s13():
    """El valor de la previa es cruzar el nº de corridas con los sets que dropea el nodo."""
    diags: list[str] = []
    m = _monitor(_RoiOcr("Cantidad consumida x 4"), diags)
    m._farm_session.set_prediction(
        "El piloto y el meca rebelde",
        [(1, "Wuthering Salon"), (2, "The Sky Ablaze")], time.monotonic())
    m._dispatch_state(_frame(), _ST21)

    linea = [d for d in diags if d.startswith("[extracción]")][-1]
    assert "4 uso(s)" in linea
    assert "El piloto y el meca rebelde" in linea
    assert "Wuthering Salon" in linea and "The Sky Ablaze" in linea


def test_s21_sin_prediccion_degrada_pero_emite():
    """N es un dato LEÍDO, no inferido → se reporta aunque no haya nodo predicho (RNF-02:
    la abstención es para lo no confirmado, no para lo que se ve en pantalla)."""
    diags: list[str] = []
    m = _monitor(_RoiOcr("Cantidad consumida x 2"), diags)
    m._dispatch_state(_frame(), _ST21)

    linea = [d for d in diags if d.startswith("[extracción]")][-1]
    assert "2 uso(s)" in linea
    assert "sin nodo predicho" in linea


def test_s21_ocr_ilegible_no_inventa():
    diags: list[str] = []
    m = _monitor(_RoiOcr("gvfd ###"), diags)
    m._dispatch_state(_frame(), _ST21)
    assert [d for d in diags if d.startswith("[extracción]")] == []
    assert m._farm_session.usos(time.monotonic()) is None


def test_s21_stock_ilegible_se_omite_del_log():
    """Si el stock no se lee, se OMITE del mensaje — no se inventa ni se pone '?'."""
    diags: list[str] = []
    m = _monitor(_RoiOcr("Cantidad consumida x 1", stock="!!!"), diags)
    m._dispatch_state(_frame(), _ST21)
    linea = [d for d in diags if d.startswith("[extracción]")][-1]
    assert "1 uso(s)" in linea
    assert "stock" not in linea


def test_s21_reporta_una_sola_vez_por_valor():
    diags: list[str] = []
    m = _monitor(_RoiOcr("Cantidad consumida x 2"), diags)
    for _ in range(3):
        m._dispatch_state(_frame(), _ST21)
    assert len([d for d in diags if d.startswith("[extracción]")]) == 1


def test_s21_reemite_al_mover_el_slider():
    """Mover el slider cambia N sin salir de S21 → re-emitir por cada valor distinto."""
    diags: list[str] = []
    m = _monitor(_SeqOcr(["Cantidad consumida x 1",
                          "Cantidad consumida x 2",
                          "Cantidad consumida x 4"]), diags)
    for i in range(3):
        m._dispatch_state(_frame(fill=20 + i * 40), _ST21)   # frames distintos → gate pasa
    lineas = [d for d in diags if d.startswith("[extracción]")]
    assert len(lineas) == 3, f"esperaba 3, hubo {len(lineas)}: {lineas}"
    assert "1 uso(s)" in lineas[0] and "2 uso(s)" in lineas[1] and "4 uso(s)" in lineas[2]
    assert m._farm_session.usos(time.monotonic()) == 4


def test_s21_mismo_valor_no_reemite_aunque_cambie_el_frame():
    """La perilla del slider se anima; si N no cambió, no re-loguear."""
    diags: list[str] = []
    m = _monitor(_SeqOcr(["Cantidad consumida x 3"] * 3), diags)
    for i in range(3):
        m._dispatch_state(_frame(fill=30 + i * 50), _ST21)
    assert len([d for d in diags if d.startswith("[extracción]")]) == 1


def test_s21_reset_al_salir_permite_reemitir():
    diags: list[str] = []
    m = _monitor(_RoiOcr("Cantidad consumida x 2"), diags)
    m._dispatch_state(_frame(), _ST21)
    m._dispatch_state(_frame(), ScreenState("S13", 1.0, "s13_set"))   # cerrar el modal
    m._dispatch_state(_frame(), _ST21)                                # re-abrirlo
    assert len([d for d in diags if d.startswith("[extracción]")]) == 2


def test_s21_arma_el_gate_de_farmeo():
    """Con baterías no hay S14: S21 tiene que sostener la ventana sobre el auto-combate."""
    diags: list[str] = []
    m = _monitor(_RoiOcr("Cantidad consumida x 4"), diags)
    m._dispatch_state(_frame(), _ST21)
    assert m._farm_session.is_armed(time.monotonic())


def test_s21_lee_los_screenshots_reales():
    """OCR real contra los 4 fixtures: cada uno declara su N en el nombre del archivo."""
    import cv2
    import pytest
    esperado = {
        "Seleccion_baterias_uso.png": 1,
        "Seleccion_nodo_2.png": 2,
        "Seleccion_nodo_3.png": 3,
        "Seleccion_nodo_4.png": 4,
    }
    files = {n: _FX / n for n in esperado}
    if not all(p.exists() for p in files.values()):
        pytest.skip("screenshots S21 no presentes")
    try:
        from app.core.ocr_tesseract import TesseractBackend
        ocr = TesseractBackend()
    except Exception:
        pytest.skip("Tesseract no disponible")

    for name, n in esperado.items():
        diags: list[str] = []
        m = _monitor(ocr, diags)
        frame = cv2.imdecode(np.fromfile(str(files[name]), np.uint8), cv2.IMREAD_COLOR)
        m._dispatch_state(frame, _ST21)
        linea = [d for d in diags if d.startswith("[extracción]")]
        assert linea, f"{name}: no emitió, diags={diags}"
        assert f"{n} uso(s)" in linea[-1], f"{name}: esperaba {n}, salió {linea[-1]!r}"
        assert "stock 8" in linea[-1], f"{name}: esperaba stock 8, salió {linea[-1]!r}"


def test_s21_reemite_al_cambiar_el_slider_con_frames_reales():
    """Regresión del bug del `/N` (QA en vivo 2026-07-18): tras leer ×1, mover el slider a ×4
    debía re-leer. El gate de firma lo bloqueaba (el cambio visual del slider es < umbral, medido
    ~3 sobre los fixtures reales) → el 'Obtenido' quedaba en `uso 4/1`. Sin gate, OCReando cada
    ciclo y dedupeando por valor, el 2º frame (×4) se re-lee. Frames y OCR REALES."""
    import cv2
    import pytest
    x1, x4 = _FX / "Seleccion_baterias_uso.png", _FX / "Seleccion_nodo_4.png"
    if not (x1.exists() and x4.exists()):
        pytest.skip("screenshots S21 no presentes")
    try:
        from app.core.ocr_tesseract import TesseractBackend
        ocr = TesseractBackend()
    except Exception:
        pytest.skip("Tesseract no disponible")

    diags: list[str] = []
    m = _monitor(ocr, diags)
    m._dispatch_state(cv2.imdecode(np.fromfile(str(x1), np.uint8), cv2.IMREAD_COLOR), _ST21)
    m._dispatch_state(cv2.imdecode(np.fromfile(str(x4), np.uint8), cv2.IMREAD_COLOR), _ST21)

    lineas = [d for d in diags if d.startswith("[extracción]")]
    assert len(lineas) == 2, f"esperaba re-emitir al cambiar el slider, hubo {lineas}"
    assert "1 uso(s)" in lineas[0] and "4 uso(s)" in lineas[1]
    assert m._farm_session.usos(time.monotonic()) == 4   # el denominador queda en 4, no en 1
