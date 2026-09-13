"""`disc_observed` — el disco cuyo dueño está ESCRITO EN LA PANTALLA llega a la UI.

Existe por un agujero que se descubrió al diseñar la pantalla en vivo: `_on_disc_from_monitor`
hacía `return` temprano para `S17`/`S9` —persistía, logueaba y cortaba— así que **el caso central
de esa pantalla nunca emitió una señal**. El disco equipado sólo aparecía como líneas de log.

La señal es OBSERVACIONAL y por eso es distinta de `disc_detected`:

| | `disc_detected` | `disc_observed` |
|---|---|---|
| cuándo | un drop nuevo o un disco suelto (S3/S6/S7) | un disco cuyo dueño se ve en pantalla (S17/S9) |
| qué afirma | una RECOMENDACIÓN (score, variante, PJ sugerido) | lo que se VIO, y nada más |
| dueño | el PJ que el scoring sugiere | el que dice el badge |

La distinción no es estética: el scoring todavía no está calibrado (los 51 thresholds están en el
default), y la pantalla en vivo dibuja el build del dueño REAL. Si las dos señales se mezclaran, un
disco de Yanagi podría dibujar el build del PJ que el scoring prefiere.

Y `tenencia` tiene cuatro valores a propósito: **"alguien la tiene y no sé quién" no es lo mismo
que "no pude ver el badge"**, y ninguno de los dos es "libre".
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


def _disco(**kw):
    """DiscParsed mínimo pero real (el dataclass, no un mock)."""
    from app.core.parser_disc import DiscParsed, SubstatParsed
    base = dict(
        set_name_raw="Fuego carmesí", set_name_canon="Fuego carmesí", slot=4,
        main_stat_raw="Ataque %", main_stat_canon="Ataque %", main_valor=30.0,
        main_unidad="%", nivel=15, rareza="S",
        subs=[SubstatParsed(nombre_raw="Daño Crítico", nombre_canon="Daño Crítico",
                            valor=9.6, unidad="%", rolls=3, confianza=0.93)],
        confianza_global=0.95,
    )
    base.update(kw)
    return DiscParsed(**base)


def _ctrl():
    from app.ui.controller import MonitorController
    c = MonitorController()
    c._disc_syncer = None          # sin persistencia: el test mira la señal, no la DB
    return c


def test_s17_emite_disc_observed(qapp):
    """Lo que hoy no pasa: el disco equipado llega a la vista."""
    recibidos = []
    c = _ctrl()
    c.disc_observed.connect(recibidos.append)
    c._on_disc_from_monitor(_disco(equip_detectado=True, equip_pj_visual="Yanagi"),
                            SimpleNamespace(code="S17"))
    assert len(recibidos) == 1, "S17 tiene que emitir disc_observed"
    p = recibidos[0]
    assert p["dueno"] == "Yanagi"
    assert p["tenencia"] == "equipada"
    assert p["slot"] == 4
    assert p["rareza"] == "S"
    assert p["nivel"] == 15


def test_s9_tambien_emite(qapp):
    """El inventario global comparte el camino con S17."""
    recibidos = []
    c = _ctrl()
    c.disc_observed.connect(recibidos.append)
    c._on_disc_from_monitor(_disco(equip_libre=True), SimpleNamespace(code="S9"))
    assert len(recibidos) == 1
    assert recibidos[0]["tenencia"] == "libre"
    assert recibidos[0]["dueno"] is None


def test_los_cuatro_estados_de_tenencia(qapp):
    """Cada desenlace del badge tiene su propio valor. Colapsarlos haría que la vista afirme
    algo que el sistema no sabe."""
    casos = [
        (dict(equip_detectado=True, equip_pj_visual="Ellen"),  "equipada", "Ellen"),
        (dict(equip_libre=True),                                "libre",    None),
        (dict(equip_detectado=True, equip_dueno_incierto=True), "incierto", None),
        (dict(equip_detectado=False),                           "sin_leer", None),
    ]
    for kw, tenencia, dueno in casos:
        recibidos = []
        c = _ctrl()
        c.disc_observed.connect(recibidos.append)
        c._on_disc_from_monitor(_disco(**kw), SimpleNamespace(code="S17"))
        assert recibidos[0]["tenencia"] == tenencia, f"{kw} → {recibidos[0]['tenencia']}"
        assert recibidos[0]["dueno"] == dueno


def test_no_trae_score_ni_recomendacion(qapp):
    """El contrato: esta señal reporta, no aconseja. Si algún día alguien le mete un score, la
    pantalla empezaría a mostrar un número que no está calibrado."""
    recibidos = []
    c = _ctrl()
    c.disc_observed.connect(recibidos.append)
    c._on_disc_from_monitor(_disco(equip_pj_visual="Yanagi", equip_detectado=True),
                            SimpleNamespace(code="S17"))
    for prohibida in ("score", "variant", "threshold", "urgency", "target"):
        assert prohibida not in recibidos[0], f"disc_observed no puede traer '{prohibida}'"


def test_el_log_sigue_saliendo(qapp):
    """La señal se suma al logging que ya existía, no lo reemplaza: el log es el registro de la
    pasada y hay QA que lo lee."""
    logs = []
    recibidos = []
    c = _ctrl()
    c.log_message.connect(logs.append)
    c.disc_observed.connect(recibidos.append)
    c._on_disc_from_monitor(_disco(equip_detectado=True, equip_pj_visual="Yanagi"),
                            SimpleNamespace(code="S17"))
    assert recibidos, "la señal"
    assert any("[reconocido]" in m for m in logs), "y el log de siempre"


def test_un_fallo_armando_el_payload_no_le_roba_la_identidad_al_censo(qapp, monkeypatch):
    """Lo que protege el `try` alrededor del emit NO es el log (ya salió antes) sino el `return`.

    `_on_disc_from_monitor` devuelve la fila que tocó la persistencia, y el censo de discos la usa
    como IDENTIDAD de lo que vio. Sin el `try` propio, una excepción armando el payload cae en el
    `except` de afuera, que devuelve None: el disco se persistió pero el censo no lo cuenta.

    Un test que sólo mirara el log pasaría igual sin el `try` — se comprobó sacándolo."""
    fila = SimpleNamespace(disc_id=123, trigger="s17_update", set_bonus_2p=None,
                           set_composition=None)
    c = _ctrl()
    c._disc_syncer = SimpleNamespace(persist_s17_disc=lambda d: fila)
    c._owner_tiebreaker = None
    monkeypatch.setattr(c, "_build_observed_payload",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    devuelto = c._on_disc_from_monitor(_disco(equip_detectado=True, equip_pj_visual="Yanagi"),
                                       SimpleNamespace(code="S17"))
    assert devuelto is fila, "el censo tiene que recibir la fila aunque la vista falle"
