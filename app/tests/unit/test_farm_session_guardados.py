"""La memoria de "ya guardado" vive en la tanda de farmeo (SPEC 2026-10-02 "El Obtenido guarda los
discos", punto 2): sobrevive a un "Ver", a una mejora y a los parpadeos de S22; se vacía con otra
tanda (S21) y, con breadcrumb, sobrevive a un reinicio (decisión de Daniel)."""
from __future__ import annotations

import json

from app.core.farm_session import FarmSession


def test_anota_y_devuelve_los_ids():
    fs = FarmSession()
    fs.anotar_guardado(408)
    fs.anotar_guardado(409)
    fs.anotar_guardado(408)
    assert fs.guardados() == [408, 409]


def test_otra_tanda_la_vacia():
    fs = FarmSession()
    fs.anotar_guardado(408)
    fs.set_usos(4, ts=0.0)                     # S21: otro "Obtenido"
    assert fs.guardados() == []


def test_los_estados_del_flujo_no_la_tocan():
    fs = FarmSession()
    fs.anotar_guardado(408)
    for code in ("S7", "S10", "S20", "S12", "S22", "S9"):
        fs.on_state(code, ts=1.0)
    assert fs.guardados() == [408]


def test_con_breadcrumb_sobrevive_al_reinicio(tmp_path):
    ruta = tmp_path / "farm.json"
    fs = FarmSession(state_path=ruta)
    fs.set_prediction("Espina veloz", [(54, "Feathered Fate"), (55, "Thorned Rose")], ts=0.0)
    fs.anotar_guardado(408)
    assert json.loads(ruta.read_text(encoding="utf-8"))["guardados"] == [408]
    otra = FarmSession(state_path=ruta)
    assert otra.restore(ts=0.0) is not None
    assert otra.guardados() == [408]


def test_el_breadcrumb_viejo_sin_la_clave_sigue_restaurando(tmp_path):
    ruta = tmp_path / "farm.json"
    ruta.write_text(json.dumps({"node": "Espina veloz", "sets": [[55, "Thorned Rose"]]}),
                    encoding="utf-8")
    fs = FarmSession(state_path=ruta)
    assert fs.restore(ts=0.0) is not None and fs.guardados() == []


def test_otra_tanda_tambien_vacia_el_breadcrumb(tmp_path):
    ruta = tmp_path / "farm.json"
    fs = FarmSession(state_path=ruta)
    fs.set_prediction("Espina veloz", [(55, "Thorned Rose")], ts=0.0)
    fs.anotar_guardado(408)
    fs.set_usos(2, ts=1.0)
    assert json.loads(ruta.read_text(encoding="utf-8"))["guardados"] == []
