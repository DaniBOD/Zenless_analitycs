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


def _monitor(title: str, on_diagnostic):
    import app.core.monitor as mon
    from app.core.farm_session import FarmSession
    return mon.Monitor(
        ocr=_FakeOcr(title),
        detector=None,
        on_diagnostic=on_diagnostic,
        farm_session=FarmSession(),
        farm_node_catalog=_catalog(),
    )


def _frame():
    return np.zeros((1439, 2559, 3), dtype=np.uint8)


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


def test_s13_reset_al_salir_permite_reemitir():
    diags: list[str] = []
    m = _monitor("Colmillo y hacha", on_diagnostic=diags.append)
    st13 = ScreenState("S13", 1.0, "s13_set")
    m._dispatch_state(_frame(), st13)
    m._dispatch_state(_frame(), ScreenState("S1", 1.0, "combate"))   # salir de S13
    m._dispatch_state(_frame(), st13)                                # re-entrar
    pred_diag = [d for d in diags if "colmillo" in d.lower()]
    assert len(pred_diag) == 2, f"esperaba 2 (re-emite al re-entrar), hubo {len(pred_diag)}"
