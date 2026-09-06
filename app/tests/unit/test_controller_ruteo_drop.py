"""El drop de S3 se PERSISTE y además sigue emitiendo su toast.

Hasta el 2026-09-05 `_on_disc_from_monitor` persistía sólo con `state.code in ("S17","S9")`, y esa
rama hace `return` antes de `_build_payload`. Rutear S3 ahí sin más habría guardado el disco y
apagado el toast del farmeo — que es justamente lo que el usuario mira mientras farmea.

Estos tests fijan las dos mitades a la vez, porque el riesgo es hacer una y romper la otra.
"""
from __future__ import annotations

import sys

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


def _drop():
    """El `DiscParsed` de un drop tal como lo emite `_emit_s3_disc`: sin dueño y AFIRMADO libre."""
    from app.core.parser_disc import DiscParsed, SubstatParsed
    d = DiscParsed(
        set_name_raw="Jazz caótico", set_name_canon="Jazz caótico", slot=1,
        main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad="flat",
        nivel=0, rareza="S", confianza_global=0.95,
        subs=[SubstatParsed("ATK", "ATK", 38.0, "flat", 0, 0.95)],
    )
    d.equip_libre = True
    return d


def _controller_con_repos():
    """Controller con los repos de LECTURA reales, que es lo que `_build_payload` necesita.

    No se llama a `start()` a propósito: eso levantaría el monitor y el OCR. Se arma sólo la parte
    de lectura, igual que hace `_init_dependencies` (controller.py:357-361)."""
    from pathlib import Path
    from app.db.connection import get_connection
    from app.db.repositories import AgentRepo, ArchetypeRepo, DiscSetRepo
    from app.core.score_normalizer import ScoringContext
    from app.ui.controller import MonitorController
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    if not db.exists():
        pytest.skip("DB de dominio no presente")
    ctrl = MonitorController()
    con = get_connection(db, check_same_thread=False)
    ctrl._con = con
    ctrl._agent_repo = AgentRepo(con)
    ctrl._archetype_repo = ArchetypeRepo(con)
    ctrl._disc_set_repo = DiscSetRepo(con)
    ctrl._scoring_ctx = ScoringContext()
    return ctrl


class _SyncerEspia:
    """Registra cómo lo llamaron, sin tocar ninguna DB."""
    def __init__(self):
        self.llamadas = []

    def persist_s17_disc(self, parsed, *, es_drop=False):
        self.llamadas.append(es_drop)
        return None            # None ⇒ el ruteo no puede depender de que haya escrito


def test_el_drop_se_persiste_como_drop(qapp):
    from app.core.detector import ScreenState
    from app.ui.controller import MonitorController
    ctrl = _controller_con_repos()
    espia = _SyncerEspia()
    ctrl._disc_syncer = espia

    ctrl._on_disc_from_monitor(_drop(), ScreenState("S3", 1.0, "s3_drop"))

    assert espia.llamadas == [True], "S3 tiene que persistir, y marcado como drop"


def test_el_drop_sigue_emitiendo_su_toast(qapp):
    """La otra mitad: persistir no puede costar el toast del farmeo."""
    from app.core.detector import ScreenState
    from app.ui.controller import MonitorController
    ctrl = _controller_con_repos()
    ctrl._disc_syncer = _SyncerEspia()
    payloads: list[dict] = []
    ctrl.disc_detected.connect(payloads.append)

    ctrl._on_disc_from_monitor(_drop(), ScreenState("S3", 1.0, "s3_drop"))

    assert len(payloads) == 1, "el drop dejó de avisar por toast"


def test_sin_syncer_el_toast_sale_igual(qapp):
    """El toast afirma lo que se VIO; no puede colgar de que la persistencia exista o funcione.

    Mismo contrato que el toast de reemplazo (rediseño 2026-07-20): en read-only, o con la DB
    caída, el usuario tiene que seguir viendo su drop."""
    from app.core.detector import ScreenState
    from app.ui.controller import MonitorController
    ctrl = _controller_con_repos()
    ctrl._disc_syncer = None
    payloads: list[dict] = []
    ctrl.disc_detected.connect(payloads.append)

    ctrl._on_disc_from_monitor(_drop(), ScreenState("S3", 1.0, "s3_drop"))

    assert len(payloads) == 1


def test_s17_no_se_marca_como_drop(qapp):
    """Lo que NO cambia: S17/S9 siguen persistiendo por su camino, sin `es_drop`."""
    from app.core.detector import ScreenState
    from app.ui.controller import MonitorController
    ctrl = _controller_con_repos()
    espia = _SyncerEspia()
    ctrl._disc_syncer = espia

    d = _drop()
    d.equip_libre = False
    ctrl._on_disc_from_monitor(d, ScreenState("S17", 1.0, "s17"))

    assert espia.llamadas == [False]
