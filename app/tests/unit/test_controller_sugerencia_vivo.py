"""Paso 8 (SPEC 2026-10-01): el controlador pone en cada payload la sugerencia del motor de Discos.

- Discos nuevos (S3 desafío, S5 afinación, S22 baterías) y el "Ver" (S6/S7): toast sólo si la
  sugerencia es EQUIPAR o MEJORAR.
- El inventario (S9/S17): nunca toast, aunque mejore.
- Una observación se resuelve a su FILA real por identidad (el disco no queda gemelo de sí mismo);
  un evento se evalúa como disco nuevo.
- Si el cálculo falla, el payload sale igual con `error` y sin toast (A2).

Sobre una COPIA de la DB de dominio; el controlador se arma sólo con su parte de lectura, como
`test_controller_ruteo_drop._controller_con_repos`.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication      # noqa: E402

from app.core.detector import ScreenState         # noqa: E402
from app.core.parser_disc import DiscParsed, SubstatParsed  # noqa: E402
from app.core.sugerencias import contexto_motor, sugerir_un_disco  # noqa: E402
from app.db.repositories import agentes_cambiaron  # noqa: E402

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")


@pytest.fixture(scope="module")
def qapp():
    yield QCoreApplication.instance() or QCoreApplication(sys.argv)


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    p = tmp_path_factory.mktemp("vivo") / "copia.db"
    shutil.copy(DB_REAL, p)
    agentes_cambiaron()
    yield p
    agentes_cambiaron()


@pytest.fixture(scope="module")
def ctrl(qapp, db):
    from app.core.score_normalizer import ScoringContext
    from app.db.connection import get_connection
    from app.db.repositories import AgentRepo, ArchetypeRepo, DiscSetRepo
    from app.ui.controller import MonitorController
    c = MonitorController()
    c._con = get_connection(db, check_same_thread=False)
    c._agent_repo, c._archetype_repo = AgentRepo(c._con), ArchetypeRepo(c._con)
    c._disc_set_repo, c._scoring_ctx = DiscSetRepo(c._con), ScoringContext()
    c.logs = []
    c.log_message.connect(c.logs.append)
    yield c
    c._con.close()


@pytest.fixture(scope="module")
def casos(ctrl):
    """Un disco real por sugerencia que hace falta: libre a equipar, libre a descartar, equipado a mover."""
    c = contexto_motor(ctrl._con)
    out = {}
    for d in c.activos:
        s = sugerir_un_disco(ctrl._con, d, c).propia
        if s and s["tipo"] not in out and s["tipo"] in ("equipar", "descartar", "mover"):
            out[s["tipo"]] = (d, s)
    assert set(out) == {"equipar", "descartar", "mover"}, out.keys()
    return out


def _parseado(ctrl, d) -> DiscParsed:
    sets = {s.id: s.nombre for s in ctrl._disc_set_repo.get_all()}
    dueno = ctrl._agent_repo.get_by_id(d.agente_asignado).nombre if d.agente_asignado else None
    p = DiscParsed(set_name_raw=sets[d.set_id], set_name_canon=sets[d.set_id], slot=d.slot,
                   main_stat_raw=d.main_stat, main_stat_canon=d.main_stat, main_valor=d.main_valor,
                   main_unidad=d.main_unidad, nivel=d.nivel, rareza="S", confianza_global=0.95,
                   subs=[SubstatParsed(n, n, v, u, r, 0.95) for n, v, u, r in d.subs])
    if dueno and d.equipado:
        p.equip_pj_visual = dueno
    else:
        p.equip_libre = True
    return p


def _drop(ctrl, d, codigo="S3") -> dict:
    payloads = []
    ctrl.disc_detected.connect(payloads.append)
    try:
        ctrl._on_disc_from_monitor(_parseado(ctrl, d), ScreenState(codigo, 1.0, "prueba"))
    finally:
        ctrl.disc_detected.disconnect(payloads.append)
    assert len(payloads) == 1
    return payloads[0]


def test_un_drop_que_se_equipa_saca_toast_con_la_mejora(ctrl, casos):
    d, s = casos["equipar"]
    p = _drop(ctrl, d)
    sug = p["sugerencia"]
    assert sug["toast"] and sug["tipo"] == "equipar" and not sug["error"]
    assert sug["mejora"] == s["delta"] and sug["destino"] == s["destino"] == p["target"]
    assert sug["texto"].startswith("EQUIPAR → ")
    assert sug["detalle"] and sug["detalle"][0].startswith(f"Hoy {s['destino']} lleva en el slot")
    assert p["variant"] == "equipar"
    assert not {"score", "threshold", "urgency"} & set(p), "no viaja el scoring sin calibrar"


def test_un_drop_para_descartar_no_saca_toast(ctrl, casos):
    sug = _drop(ctrl, casos["descartar"][0])["sugerencia"]
    assert sug["tipo"] == "descartar" and not sug["toast"]


def test_el_ver_saca_toast_y_el_inventario_no(ctrl, casos):
    d, _s = casos["equipar"]
    assert _drop(ctrl, d, "S6")["sugerencia"]["toast"], "el Ver es abrir UN disco a propósito"
    payloads = []
    ctrl.disc_observed.connect(payloads.append)
    try:
        ctrl._on_disc_from_monitor(_parseado(ctrl, d), ScreenState("S9", 1.0, "prueba"))
    finally:
        ctrl.disc_observed.disconnect(payloads.append)
    sug = payloads[0]["sugerencia"]
    assert sug["tipo"] == "equipar" and not sug["toast"]


def test_una_observacion_se_resuelve_a_su_fila_real(ctrl, casos):
    d, s = casos["mover"]
    payloads = []
    ctrl.disc_observed.connect(payloads.append)
    ctrl.logs.clear()
    try:
        ctrl._on_disc_from_monitor(_parseado(ctrl, d), ScreenState("S9", 1.0, "prueba"))
    finally:
        ctrl.disc_observed.disconnect(payloads.append)
    sug = payloads[0]["sugerencia"]
    assert sug["tipo"] == "mover" and sug["destino"] == s["destino"] and not sug["toast"]
    assert f"[sugerencia] #{d.id} → MOVER → {s['destino']}" in " ".join(ctrl.logs)


def test_un_evento_se_evalua_como_disco_nuevo(ctrl, casos):
    ctrl.logs.clear()
    _drop(ctrl, casos["equipar"][0], "S22")
    assert any(l.startswith("[sugerencia] (nuevo) → EQUIPAR") for l in ctrl.logs), ctrl.logs


def test_si_el_calculo_falla_el_payload_sale_igual(ctrl, casos, monkeypatch, caplog):
    def rompe(*_a, **_k):
        raise RuntimeError("roto a propósito")
    monkeypatch.setattr("app.core.sugerencias.sugerir_un_disco", rompe)
    with caplog.at_level(logging.ERROR):
        p = _drop(ctrl, casos["equipar"][0])
    sug = p["sugerencia"]
    assert sug["error"] and not sug["toast"] and sug["texto"].startswith("sin sugerencia")
    assert "falló el cálculo en vivo" in caplog.text and p["slot"] == casos["equipar"][0].slot


def test_calcular_no_escribe(ctrl, casos, db):
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    _drop(ctrl, casos["equipar"][0], "S6")
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes
