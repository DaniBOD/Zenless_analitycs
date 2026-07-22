"""El toast de REEMPLAZO no depende de la DB — sale igual en read-only.

Rediseño 2026-07-20. Antes el toast colgaba de `SyncResult.moved and .swap_fresh`, o sea de que
una transacción SQL hubiera encontrado y movido una fila. Dos consecuencias que el QA en vivo
destapó: (a) en read-only era IMPOSIBLE de validar, porque `persist_s17_disc` corta antes de
escribir y devuelve `moved=False`; y (b) cualquier desincronización DB↔juego se comía un swap
real que había ocurrido a la vista.

El toast es una afirmación sobre lo que se VIO en pantalla, así que ahora lo dispara el monitor
al observar el cambio de dueño (`_check_swap_owner` → `on_replacement`), y el controller solo
arma el payload con lecturas. Estos tests fijan ese contrato: sin ellos nada impide volver a
acoplarlo sin darse cuenta.
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


@pytest.fixture
def readonly(monkeypatch):
    """Modo read-only: la app no escribe la DB."""
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    from app.db.connection import is_readonly
    assert is_readonly(), "el fixture no logró activar el modo read-only"


def _disc_swap():
    """DiscParsed de un disco cuyo swap el monitor ya confirmó por observación."""
    from app.core.parser_disc import DiscParsed
    d = DiscParsed(
        set_name_raw="Jazz caótico", set_name_canon="Jazz caótico", slot=1,
        main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad="flat",
        nivel=15, rareza="S", agente_asignado_nombre="Velina", confianza_global=0.95,
    )
    d.agente_asignado_conf = 0.95      # PJ confiable: pasa los gates previos al de read-only
    d.swap_origin_hint = "Jane"
    d.swap_fresh = True
    return d


def test_el_toast_de_reemplazo_sale_en_readonly(qapp, readonly):
    """EL test del rediseño: con la DB intocable, el toast igual se emite."""
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    recibidos: list[dict] = []
    ctrl.disc_replaced.connect(recibidos.append)

    ctrl._on_replacement_from_monitor({
        "set_name": "Jazz caótico", "slot": 1, "from_name": "Jane", "to_name": "Velina",
    })

    assert len(recibidos) == 1, "el toast no salió en read-only"
    p = recibidos[0]
    assert p["from_agent"] == "Jane" and p["to_agent"] == "Velina"
    assert p["slot"] == 1 and "Jazz" in p["set"]


def test_la_persistencia_en_readonly_no_reporta_movimiento(qapp, readonly, tmp_path):
    """Contraparte: en read-only `persist_s17_disc` NUNCA dice que movió algo.

    Es exactamente por esto que el toast no puede depender de su resultado."""
    import sqlite3
    from app.core.sync_equip import DiscSyncer
    from app.tests.unit.test_sync_swap import _SCHEMA
    db = tmp_path / "minima.db"
    con = sqlite3.connect(str(db))
    con.executescript(_SCHEMA)      # el set debe resolverse ANTES del corte de read-only
    con.commit()
    con.close()

    s = DiscSyncer(db_path=str(db))
    try:
        result = s.persist_s17_disc(_disc_swap())
    finally:
        s.close()
    assert result is not None and result.trigger == "readonly"
    assert result.moved is False and result.swap_fresh is False


def test_el_toast_de_equipado_sale_en_readonly(qapp, readonly):
    """Mismo contrato para el disco LIBRE equipado (2026-07-22): también es observacional.

    Y va por OTRA señal: `kind` enruta el mismo callback a `disc_equipped`, no a
    `disc_replaced` — si se mezclaran, un equipamiento saldría como reemplazo."""
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    equipados: list[dict] = []
    reemplazos: list[dict] = []
    ctrl.disc_equipped.connect(equipados.append)
    ctrl.disc_replaced.connect(reemplazos.append)

    ctrl._on_replacement_from_monitor({
        "kind": "equipado", "set_name": "Jazz caótico", "slot": 1,
        "from_name": None, "to_name": "Velina",
    })

    assert len(equipados) == 1, "el toast de equipado no salió en read-only"
    assert reemplazos == [], "un equipamiento no debe salir como reemplazo"
    p = equipados[0]
    assert p["to_agent"] == "Velina" and p["slot"] == 1 and "Jazz" in p["set"]


def test_un_reemplazo_no_sale_como_equipado(qapp, readonly):
    """La otra dirección del ruteo: sin `kind` (o con 'reemplazo') va a `disc_replaced`."""
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    equipados: list[dict] = []
    reemplazos: list[dict] = []
    ctrl.disc_equipped.connect(equipados.append)
    ctrl.disc_replaced.connect(reemplazos.append)

    ctrl._on_replacement_from_monitor({
        "kind": "reemplazo", "set_name": "Jazz caótico", "slot": 1,
        "from_name": "Jane", "to_name": "Velina",
    })

    assert len(reemplazos) == 1 and equipados == []


def test_el_disco_emitido_ya_no_dispara_el_toast(qapp):
    """Anti-doble-toast: la vía de emisión del disco no debe emitir `disc_replaced`.

    El toast tiene UN solo origen (el callback de observación). Si `_on_disc_from_monitor`
    volviera a emitirlo, saldrían dos toasts por swap."""
    from app.core.detector import ScreenState
    from app.ui.controller import MonitorController
    ctrl = MonitorController()
    recibidos: list[dict] = []
    ctrl.disc_replaced.connect(recibidos.append)
    ctrl._disc_syncer = None            # sin persistencia: el toast no debe depender de ella

    ctrl._on_disc_from_monitor(_disc_swap(), ScreenState("S17", 1.0, "s17"))

    assert recibidos == [], "el toast debe venir solo del check observacional"
