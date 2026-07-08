"""Handler de SELECCIÓN de set a farmear (S13) en el monitor (`_process_s13_node_title`).

En S13 el juego muestra el título del nodo. El handler hace OCR del título → `FarmNodeCatalog`
→ predice los 2 sets del nodo, los guarda en `FarmSession` (para restringir el matcher de S2)
y emite un diagnóstico display-only. No persiste ni puntúa.

Se inyecta un OCR falso para testear la lógica de forma determinista (el OCR real sobre el
screenshot es parte de la QA en vivo, no del unit test).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from app.core.detector import ScreenState
from app.core.farm_nodes import FarmNodeCatalog

_TOML = Path(__file__).resolve().parents[2] / "resources" / "farm_nodes.toml"


def _catalog() -> FarmNodeCatalog:
    import tomllib
    with open(_TOML, "rb") as f:
        nodes = tomllib.load(f)["nodes"]
    ens: list[str] = []
    for n in nodes:
        ens.extend(n["sets_en"])
    ids = {en: i + 1 for i, en in enumerate(dict.fromkeys(ens))}
    return FarmNodeCatalog.from_toml(_TOML, ids)


class _FakeOcr:
    """OCR backend falso: devuelve un texto fijo (el 'título' leído en S13)."""
    def __init__(self, title: str):
        self.title = title

    def text(self, img, psm: int = 6, lang: str = "spa"):
        return self.title, 0.99


class _SeqOcr:
    """OCR falso que devuelve títulos en secuencia (simula cambiar de nodo en S13)."""
    def __init__(self, titles):
        self.titles = list(titles)
        self.i = 0

    def text(self, img, psm: int = 6, lang: str = "spa"):
        t = self.titles[min(self.i, len(self.titles) - 1)]
        self.i += 1
        return t, 0.99


def _monitor_ocr(ocr, on_diagnostic):
    import app.core.monitor as mon
    from app.core.farm_session import FarmSession
    return mon.Monitor(
        ocr=ocr, detector=None,
        on_diagnostic=on_diagnostic,
        farm_session=FarmSession(),
        farm_node_catalog=_catalog(),
    )


def _monitor(title: str, on_diagnostic):
    return _monitor_ocr(_FakeOcr(title), on_diagnostic)


def _frame(fill: int = 0):
    # `fill` distinto → firma del ROI del título distinta (pasa el gate de re-OCR RNF-06).
    return np.full((1439, 2559, 3), fill, dtype=np.uint8)


def test_s13_predice_y_guarda_en_farm_session():
    diags: list[str] = []
    m = _monitor("El piloto y el meca rebelde", on_diagnostic=diags.append)
    m._dispatch_state(_frame(), ScreenState("S13", 1.0, "s13_set"))

    # Diagnóstico display-only con el nodo y sus 2 sets.
    pred_diag = [d for d in diags if "piloto" in d.lower()]
    assert pred_diag, f"esperaba un diagnóstico de predicción, diags={diags}"
    assert "Wuthering Salon" in pred_diag[-1]
    assert "The Sky Ablaze" in pred_diag[-1]

    # Predicción guardada en FarmSession, legible por el futuro handler S2.
    pred = m._farm_session.predicted(time.monotonic())
    assert pred is not None
    node, sets = pred
    assert node == "El piloto y el meca rebelde"
    assert {en for _sid, en in sets} == {"Wuthering Salon", "The Sky Ablaze"}


def test_s13_titulo_desconocido_no_predice():
    diags: list[str] = []
    m = _monitor("Pantalla cualquiera sin nodo", on_diagnostic=diags.append)
    m._dispatch_state(_frame(), ScreenState("S13", 1.0, "s13_set"))
    assert m._farm_session.predicted(time.monotonic()) is None


def test_s13_reporta_una_sola_vez_por_entrada():
    diags: list[str] = []
    m = _monitor("Puños y balas", on_diagnostic=diags.append)
    st = ScreenState("S13", 1.0, "s13_set")
    m._dispatch_state(_frame(), st)
    m._dispatch_state(_frame(), st)
    m._dispatch_state(_frame(), st)
    pred_diag = [d for d in diags if "puños" in d.lower() or "punos" in d.lower()]
    assert len(pred_diag) == 1, f"esperaba 1 predicción, hubo {len(pred_diag)}: {pred_diag}"


def test_s13_reemite_al_cambiar_de_nodo_sin_salir():
    """Navegar entre nodos SIN salir de S13 re-emite por cada nodo distinto, incluido volver
    a uno ya visto (El piloto → Engaños → La ley → El piloto = 4 emisiones)."""
    diags: list[str] = []
    titles = [
        "El piloto y el meca rebelde",
        "Engaños y baluartes",
        "La ley de hierro y los rebeldes",
        "El piloto y el meca rebelde",
    ]
    m = _monitor_ocr(_SeqOcr(titles), on_diagnostic=diags.append)
    st = ScreenState("S13", 1.0, "s13_set")
    for i in range(len(titles)):
        m._dispatch_state(_frame(fill=20 + i * 40), st)   # frames distintos → gate pasa
    nodos = [d for d in diags if d.startswith("[farmeo] nodo:")]
    assert len(nodos) == 4, f"esperaba 4 emisiones (una por cambio), hubo {len(nodos)}: {nodos}"
    assert "El piloto y el meca rebelde" in nodos[0]
    assert "Engaños y baluartes" in nodos[1]
    assert "La ley de hierro y los rebeldes" in nodos[2]
    assert "El piloto y el meca rebelde" in nodos[3]   # re-captura el que ya había pasado


def test_s13_mismo_nodo_no_reemite_aunque_cambie_el_frame():
    """Si el frame cambia (animación del cursor) pero el nodo sigue siendo el mismo, no re-emite."""
    diags: list[str] = []
    m = _monitor_ocr(_SeqOcr(["Puños y balas", "Puños y balas", "Puños y balas"]),
                     on_diagnostic=diags.append)
    st = ScreenState("S13", 1.0, "s13_set")
    for i in range(3):
        m._dispatch_state(_frame(fill=30 + i * 50), st)
    nodos = [d for d in diags if d.startswith("[farmeo] nodo:")]
    assert len(nodos) == 1, f"esperaba 1 (mismo nodo), hubo {len(nodos)}: {nodos}"


def test_s13_flujo_entre_5_screenshots_reales():
    """Simula navegar entre los 5 nodos de los screenshots reales (OCR real) + volver al 1º:
    cada nodo distinto debe emitirse, incl. la re-captura del repetido. Un frame repetido
    consecutivo NO re-emite (gate de firma)."""
    import cv2
    _S13 = Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "13_Seleccion_set_farmeo"
    files = sorted(_S13.glob("Ejemplo_*.png"))
    if len(files) < 5:
        import pytest
        pytest.skip("screenshots S13 no presentes")
    try:
        from app.core.ocr_paddle import PaddleBackend
        ocr = PaddleBackend()
    except Exception:
        import pytest
        pytest.skip("PaddleOCR no disponible")

    import app.core.monitor as mon
    from app.core.farm_session import FarmSession
    diags: list[str] = []
    m = mon.Monitor(ocr=ocr, detector=None, on_diagnostic=diags.append,
                    farm_session=FarmSession(), farm_node_catalog=_catalog())
    frs = [cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR) for f in files]
    st = ScreenState("S13", 1.0, "s13_set")

    # Flujo: 1,2,3,4,5, luego repetir el 1 (vuelvo a un nodo ya visto).
    orden = [0, 1, 2, 3, 4, 0]
    for i in orden:
        m._dispatch_state(frs[i], st)
    # Un frame repetido consecutivo (mismo que el último) → gate de firma lo suprime.
    m._dispatch_state(frs[0], st)

    nodos = [d for d in diags if d.startswith("[farmeo] nodo:")]
    esperados = [
        "La ley de hierro y los rebeldes", "Colmillo y hacha", "El loco y el adepto",
        "El cazador y la bestia", "Engaños y baluartes", "La ley de hierro y los rebeldes",
    ]
    assert len(nodos) == len(esperados), f"esperaba {len(esperados)}, hubo {len(nodos)}: {nodos}"
    for got, exp in zip(nodos, esperados):
        assert exp in got, f"esperaba '{exp}' en '{got}'"


def test_s13_reset_al_salir_permite_reemitir():
    diags: list[str] = []
    m = _monitor("Colmillo y hacha", on_diagnostic=diags.append)
    st13 = ScreenState("S13", 1.0, "s13_set")
    m._dispatch_state(_frame(), st13)
    m._dispatch_state(_frame(), ScreenState("S1", 1.0, "combate"))   # salir de S13
    m._dispatch_state(_frame(), st13)                                # re-entrar
    pred_diag = [d for d in diags if "colmillo" in d.lower()]
    assert len(pred_diag) == 2, f"esperaba 2 (re-emite al re-entrar), hubo {len(pred_diag)}"
