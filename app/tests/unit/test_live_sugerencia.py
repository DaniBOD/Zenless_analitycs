"""Paso 8 (SPEC 2026-10-01): la sugerencia del motor en la vista en vivo.

La card muestra la etiqueta con el color de la columna de Discos y la región derecha el detalle.
Los payloads viejos (sin `sugerencia`) no rompen y dejan la región vacía.
"""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from app.ui import tokens as T                     # noqa: E402
from app.ui.live.view import drop_como_observacion  # noqa: E402

EQUIPAR = {"texto": "EQUIPAR → Anby +0,57", "tipo": "equipar", "conflicto": None,
           "detalle": ["Hoy Anby lleva en el slot 4: #00301 Monarca del Pináculo · …"],
           "destino": "Anby", "destino_id": 15, "mejora": 0.57, "toast": True, "error": False}
NADA = {"texto": "Nada que hacer", "tipo": None, "conflicto": None, "detalle": [], "destino": None,
        "destino_id": None, "mejora": None, "toast": False, "error": False}
ERROR = dict(NADA, texto="sin sugerencia: falló el cálculo (ver log)", error=True)
DESCARTAR = dict(NADA, texto="DESCARTAR", tipo="descartar",
                 detalle=["No le sirve a ningún PJ de tu cuenta y no es el único de su tipo."])


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    inst = QCoreApplication.instance()
    if inst is not None and not isinstance(inst, QApplication):
        pytest.skip("ya existe una QCoreApplication en el proceso → no se puede crear QApplication de widgets")
    yield inst or QApplication(sys.argv)


def _drop(sug=None) -> dict:
    p = {"set": "Monarca del Pináculo", "slot": 4, "rarity": "S", "main": "Daño Crítico",
         "main_valor": 48.0, "main_unidad": "%", "nivel": 15, "subs_detail": ["ATK% 3% (+1)"],
         "variant": "equipar", "target": "Anby", "score": 80.0, "threshold": 0.75, "urgency": 0.9}
    if sug is not None:
        p["sugerencia"] = sug
    return p


def _vista():
    from app.ui.live.view import LiveView
    return LiveView(build_fn=lambda _n: {})


def test_la_card_y_la_region_con_un_equipar(qapp):
    v = _vista()
    v.on_disc_detected(_drop(EQUIPAR))
    assert v.item_card._d_sug.text() == "EQUIPAR → Anby +0,57"
    assert T.SUGERENCIA["equipar"][1] in v.item_card._d_sug.styleSheet()
    r = v.recuadro_sugerencia
    assert not r.isHidden()
    assert r.textos_visibles()[:3] == ["SUGERENCIA DEL MOTOR", "EQUIPAR → Anby +0,57", EQUIPAR["detalle"][0]]


def test_nada_que_hacer_y_el_error(qapp):
    v = _vista()
    v.on_disc_observed(dict(_drop(NADA), dueno="Anby", tenencia="equipada"))
    assert v.item_card._d_sug.text() == "Nada que hacer"
    assert v.recuadro_sugerencia.textos_visibles() == ["SUGERENCIA DEL MOTOR", "Nada que hacer"]
    v.on_disc_detected(_drop(ERROR))
    assert v.item_card._d_sug.text().startswith("sin sugerencia")
    assert T.WARNING in v.item_card._d_sug.styleSheet()


def test_el_disco_siguiente_reemplaza_la_region(qapp):
    v = _vista()
    v.on_disc_detected(_drop(EQUIPAR))
    v.on_disc_detected(_drop(DESCARTAR))
    textos = v.recuadro_sugerencia.textos_visibles()
    assert "DESCARTAR" in textos and not any(t.startswith("EQUIPAR") for t in textos)
    assert T.SUGERENCIA["descartar"][1] in v.item_card._d_sug.styleSheet()


def test_un_payload_viejo_no_rompe_y_deja_la_region_vacia(qapp):
    v = _vista()
    v.on_disc_detected(_drop(EQUIPAR))
    v.on_disc_detected(_drop())
    assert v.recuadro_sugerencia.isHidden() and v.item_card._d_sug.isHidden()


def test_drop_como_observacion_deja_pasar_la_sugerencia_y_no_el_scoring():
    o = drop_como_observacion(_drop(EQUIPAR))
    assert o["sugerencia"] == EQUIPAR
    assert not {"score", "threshold", "urgency", "target", "variant"} & set(o)
