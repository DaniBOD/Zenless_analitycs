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


# --- La baja por desmontaje se dispara desde el controller (2026-09-06) ------------------------
#
# Mismo contrato que el drop y que el toast de reemplazo: el aviso al usuario afirma lo que se VIO
# en pantalla y no puede colgar de que la DB haya escrito. La baja corre después y aparte.

class _SyncerBaja:
    def __init__(self, resultado=None):
        self.registros = []
        self._resultado = resultado

    def dar_de_baja_desmontados(self, registro):
        self.registros.append(registro)
        return self._resultado


def _ev_desmontaje():
    return {
        "total": 2, "con_datos": 1, "faltantes": 1, "modo": "manual",
        "registro": {"conteo": {"declarado": 2, "capturados": 1, "faltantes": 1},
                     "discos": [{"set_id": 1, "slot": 1, "nivel": 0,
                                 "main": {"canon": "HP", "valor": 2200.0}, "subs": []}]},
    }


def test_el_desmontaje_da_de_baja_las_filas(qapp):
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    espia = _SyncerBaja({"dados_de_baja": 1, "ambiguos": 0, "no_encontrados": 0, "faltantes": 1})
    ctrl._disc_syncer = espia

    ctrl._on_teardown_from_monitor(_ev_desmontaje())

    assert len(espia.registros) == 1
    assert espia.registros[0]["conteo"]["declarado"] == 2


def test_el_toast_del_desmontaje_sale_aunque_la_baja_falle(qapp):
    """Si la baja revienta, el usuario tiene que ver igual que su tanda se desmontó."""
    from app.ui.controller import MonitorController

    class _Explota:
        def dar_de_baja_desmontados(self, registro):
            raise RuntimeError("DB caída")

    ctrl = MonitorController()
    ctrl._disc_syncer = _Explota()
    toasts: list[dict] = []
    ctrl.discs_dismantled.connect(toasts.append)

    ctrl._on_teardown_from_monitor(_ev_desmontaje())

    assert len(toasts) == 1 and toasts[0]["total"] == 2


def test_sin_registro_no_se_llama_a_la_baja(qapp):
    """Un evento viejo (sin `registro`) no debe hacer nada raro: sólo toast."""
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    espia = _SyncerBaja()
    ctrl._disc_syncer = espia
    toasts: list[dict] = []
    ctrl.discs_dismantled.connect(toasts.append)

    ev = _ev_desmontaje(); ev.pop("registro")
    ctrl._on_teardown_from_monitor(ev)

    assert espia.registros == [] and len(toasts) == 1


# --- verbo 2: la mejora del disco libre (2026-09-06) ---------------------------------------
#
# El `UpgradeSyncer` no tiene DB propia: le pide al `DiscSyncer` que migre la fila. El cable que
# los une es UNA línea en `start()`, y si falta, todo lo demás sigue verde mientras el verbo 2
# nunca corre en la app real — exactamente la forma de fallo que describe la práctica A2 (el
# silencio no es un aprobado: puede ser que ese código nunca haya corrido).

class _MonitorMudo:
    def __init__(self, **kw):
        self.kw = kw

    def start(self):
        pass


def test_el_upgrade_syncer_recibe_el_disc_syncer(qapp, monkeypatch):
    """`start()` tiene que pasarle el `disc_syncer` al `UpgradeSyncer`. Sin eso el tracking de
    mejora vuelve a ser display-only en producción, sin que ningún test lo note."""
    from app.ui.controller import MonitorController

    creado = {}

    class _UpgradeEspia:
        def __init__(self, **kw):
            creado.update(kw)

    def _init_fake(self):
        self._ocr = object()
        self._detector = object()
        self._disc_set_repo = object()
        self._disc_syncer = object()

    monkeypatch.setattr(MonitorController, "_init_dependencies", _init_fake)
    monkeypatch.setattr("app.core.sync_upgrade.UpgradeSyncer", _UpgradeEspia)
    monkeypatch.setattr("app.core.monitor.Monitor", _MonitorMudo)

    ctrl = MonitorController()
    ctrl.start()

    assert "disc_syncer" in creado, "start() no le pasó el disc_syncer al UpgradeSyncer"
    assert creado["disc_syncer"] is ctrl._disc_syncer
    assert creado["disc_syncer"] is not None
