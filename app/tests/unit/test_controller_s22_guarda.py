"""El "Obtenido" de las baterías (S22) guarda el disco que se clickea (SPEC 2026-10-02, puntos 1 y 2).

- Primer clic → inserta (`s22_drop_insert`) y lo anota en la tanda de farmeo.
- El mismo disco otra vez, o ya mejorado (el Obtenido lo muestra mejorado al volver del "Ver",
  verificado en vivo), → no inserta: usa la fila de la tanda.
- Otra tanda → vuelve a insertar. Readonly → no escribe.

Sobre una COPIA de la DB de dominio, con el controlador armado como en
`test_controller_sugerencia_vivo`.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication      # noqa: E402

from app.core.detector import ScreenState         # noqa: E402
from app.core.parser_disc import DiscParsed, SubstatParsed  # noqa: E402
from app.db.repositories import agentes_cambiaron  # noqa: E402

DB_REAL = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
pytestmark = pytest.mark.skipif(not DB_REAL.is_file(), reason="sin la DB de dominio")
S22 = ScreenState("S22", 1.0, "s22")


@pytest.fixture(scope="module")
def qapp():
    yield QCoreApplication.instance() or QCoreApplication(sys.argv)


@pytest.fixture
def ctrl(qapp, tmp_path, monkeypatch):
    import app.core.sync_equip as se
    from app.core.farm_session import FarmSession
    from app.core.score_normalizer import ScoringContext
    from app.core.sync_equip import DiscSyncer
    from app.db.connection import get_connection
    from app.db.repositories import AgentRepo, ArchetypeRepo, DiscSetRepo
    from app.ui.controller import MonitorController
    monkeypatch.setattr(se, "is_readonly", lambda: False)
    sha0 = hashlib.sha256(DB_REAL.read_bytes()).hexdigest()
    copia = tmp_path / "copia.db"
    shutil.copy(DB_REAL, copia)
    agentes_cambiaron()
    c = MonitorController()
    c._con = get_connection(copia, check_same_thread=False)
    c._agent_repo, c._archetype_repo = AgentRepo(c._con), ArchetypeRepo(c._con)
    c._disc_set_repo, c._scoring_ctx = DiscSetRepo(c._con), ScoringContext()
    c._disc_syncer = DiscSyncer(db_path=copia)
    c._farm_session = FarmSession()
    c.copia = copia
    c.payloads = []
    c.disc_detected.connect(c.payloads.append)
    yield c
    c._disc_syncer.close()
    c._con.close()
    agentes_cambiaron()
    assert hashlib.sha256(DB_REAL.read_bytes()).hexdigest() == sha0, "la DB real no se toca"


def _hado1(nivel=0, subs=(("Perforación", 9.0, 0), ("Maestría de Anomalía", 9.0, 0),
                          ("Prob. Crítica", 2.4, 0))) -> DiscParsed:
    """El primer disco del QA: Hado emplumado slot 1, PV 550 (como lo arma el monitor en S22)."""
    d = DiscParsed(set_name_raw="Hado emplumado", set_name_canon="Hado emplumado", slot=1,
                   main_stat_raw="HP", main_stat_canon="HP", main_valor=550.0, main_unidad="flat",
                   nivel=nivel, rareza="S", confianza_global=0.95,
                   subs=[SubstatParsed(n, n, v, "%" if n.startswith("Prob") else "flat", r, 0.95)
                         for n, v, r in subs])
    d.equip_libre = True
    return d


def _filas(path):
    con = sqlite3.connect(str(path))
    n = con.execute("SELECT COUNT(*) FROM inventory_discs").fetchone()[0]
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    assert fk == [] and ok == "ok"
    return n


def test_el_primer_clic_inserta_y_lo_anota(ctrl, caplog):
    caplog.set_level(logging.INFO)
    n0 = _filas(ctrl.copia)
    ctrl._on_disc_from_monitor(_hado1(), S22)
    assert _filas(ctrl.copia) == n0 + 1
    assert len(ctrl._farm_session.guardados()) == 1
    assert "s22_drop_insert" in caplog.text
    assert ctrl.payloads[-1]["sugerencia"] is not None


def test_el_mismo_disco_otra_vez_no_reinserta(ctrl):
    ctrl._on_disc_from_monitor(_hado1(), S22)
    n1 = _filas(ctrl.copia)
    ctrl._on_disc_from_monitor(_hado1(), S22)       # volvió al Obtenido tras un "Ver"
    assert _filas(ctrl.copia) == n1


def test_el_mismo_disco_ya_mejorado_tampoco(ctrl):
    ctrl._on_disc_from_monitor(_hado1(), S22)
    n1 = _filas(ctrl.copia)
    mejorado = _hado1(nivel=15, subs=(("Perforación", 9.0, 0), ("Maestría de Anomalía", 36.0, 3),
                                      ("Prob. Crítica", 2.4, 0), ("ATK", 38.0, 1)))
    ctrl._on_disc_from_monitor(mejorado, S22)
    assert _filas(ctrl.copia) == n1


def test_otra_tanda_vuelve_a_insertar(ctrl):
    ctrl._on_disc_from_monitor(_hado1(), S22)
    n1 = _filas(ctrl.copia)
    ctrl._farm_session.set_usos(4, ts=0.0)
    ctrl._on_disc_from_monitor(_hado1(), S22)       # un gemelo de otra corrida
    assert _filas(ctrl.copia) == n1 + 1


def test_readonly_no_escribe_ni_anota(ctrl, monkeypatch):
    import app.core.sync_equip as se
    monkeypatch.setattr(se, "is_readonly", lambda: True)
    n0 = _filas(ctrl.copia)
    ctrl._on_disc_from_monitor(_hado1(), S22)
    assert _filas(ctrl.copia) == n0 and ctrl._farm_session.guardados() == []
    assert ctrl.payloads[-1]["sugerencia"] is not None, "la card y el toast salen igual"
