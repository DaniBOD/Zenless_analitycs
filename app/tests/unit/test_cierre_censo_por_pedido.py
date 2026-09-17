"""Cerrar censo por PEDIDO: lo pide la UI, lo ejecuta el hilo del monitor (Fase 2B, 2026-09-17).

F8 se fue: ZZZ corre como administrador y Windows no le entrega las teclas a la app con el juego en
foco. El botón que la reemplaza corre en el hilo de la UI, y no hay locks en `Monitor` ni en los
censos — así que el botón no cierra: deja un pedido y el loop lo atiende al tope de cada pasada.

Lo que se prueba acá es lo que una lectura del código no garantiza:

- que pedir **no ejecute nada** en el hilo que pide, y que lo ejecute el `_run` VERDADERO (también
  pausado, que es un camino con `continue`);
- que el primer pedido **no cierre nada**, ni siquiera un inventario (un "Cancelar" que ya cerró el
  censo de discos sería peor que F8);
- que una confirmación sea un CONJUNTO: si lo abierto cambió desde que se mostró, no cierra.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.core.census import RosterCensus
from app.core.census_inventario import DiscCensus, InventoryCensus

from app.tests.unit.arnes_loop_monitor import correr_loop

_ROSTER = [(1, "Nangong Yu"), (2, "Jane"), (3, "Ellen")]


def _monitor(respuestas: list, **kw):
    import app.core.monitor as mon
    return mon.Monitor(ocr=None, detector=None, on_cierre_censo=respuestas.append, **kw)


def _discos_abierto():
    c = DiscCensus()
    c.ensure_open(ts=0.0)
    return c


def _armas_abierto():
    c = InventoryCensus(entidad="armas")
    c.ensure_open(ts=0.0)
    return c


def _roster_abierto():
    c = RosterCensus(_ROSTER)
    c.ensure_open(ts=0.0)
    return c


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    """Reportes a un directorio temporal y la DB de dominio en readonly: cerrar el roster escribe."""
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    return tmp_path


# --- quién ejecuta el pedido ------------------------------------------------------------------

def test_pedir_no_ejecuta_nada_en_el_hilo_que_pide():
    respuestas: list = []
    m = _monitor(respuestas)
    m._censo_discos = _discos_abierto()
    m.pedir_cierre_censo()
    m.pedir_cierre_censo(m._instantanea_cierre())
    assert respuestas == [], "pedir tiene que volver sin responder: responde el loop"
    assert m._censo_discos.abierta


def test_el_pedido_lo_ejecuta_el_hilo_del_loop_no_el_que_pide():
    """Con dos hilos de verdad: el `_run` corre en uno, el pedido sale del de este test."""
    respuestas: list = []
    hilos: list[str] = []
    import app.core.monitor as mon
    m = mon.Monitor(ocr=None, detector=None,
                    on_cierre_censo=lambda r: (hilos.append(threading.current_thread().name),
                                               respuestas.append(r)))
    m._censo_discos = _discos_abierto()

    def sin_frame():
        time.sleep(0.01)
        return None

    m._get_frame = sin_frame
    loop = threading.Thread(target=m._run, name="loop-de-test", daemon=True)
    loop.start()
    try:
        m.pedir_cierre_censo()
        limite = time.monotonic() + 5.0
        while not respuestas and time.monotonic() < limite:
            time.sleep(0.01)
    finally:
        m._stop.set()
        loop.join(timeout=5.0)
    assert hilos == ["loop-de-test"]
    assert respuestas[0]["accion"] == "confirmar"


def test_el_loop_atiende_el_pedido_en_una_pasada_normal(monkeypatch):
    respuestas: list = []
    m = _monitor(respuestas)
    m._censo_discos = _discos_abierto()
    m.pedir_cierre_censo()
    correr_loop(monkeypatch, m, [1.0], estado="S1")
    assert [r["accion"] for r in respuestas] == ["confirmar"]


def test_el_loop_atiende_el_pedido_tambien_PAUSADO(monkeypatch):
    """Pausado, el loop duerme y hace `continue` antes de capturar. Un cierre no tiene por qué
    esperar a que se reanude la captura."""
    respuestas: list = []
    m = _monitor(respuestas)
    m._censo_discos = _discos_abierto()
    frames: list[int] = []
    monkeypatch.setattr(m, "_get_frame", lambda: frames.append(1))
    monkeypatch.setattr("app.core.monitor.time.sleep", lambda s: m._stop.set())
    m._paused.clear()
    m.pedir_cierre_censo()
    m._run()
    assert frames == [], "el test tiene que haber corrido por el camino pausado"
    assert [r["accion"] for r in respuestas] == ["confirmar"]


def test_un_cierre_que_revienta_responde_error_y_el_loop_sigue(monkeypatch):
    respuestas: list = []
    m = _monitor(respuestas)

    def rompe(confirmado=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(m, "cerrar_censo", rompe)
    m.pedir_cierre_censo()
    reg = correr_loop(monkeypatch, m, [1.0, 1.0], estado="S1")
    assert respuestas == [{"accion": "error"}]
    assert reg.clasificados == [1, 2], "el loop siguió clasificando después del error"


# --- qué se cierra y cuándo --------------------------------------------------------------------

def test_sin_nada_abierto_responde_nada():
    assert _monitor([]).cerrar_censo() == {"accion": "nada"}


def test_el_primer_pedido_no_cierra_NI_el_inventario(aislado):
    """Con F8 el primer pedido cerraba los inventarios y recién después advertía por el roster. Con
    un diálogo, eso es un Cancelar que ya cerró el censo de discos — y ese censo no se reabre."""
    m = _monitor([])
    m._censo_discos = _discos_abierto()
    m._censo_armas = _armas_abierto()
    m._census = _roster_abierto()
    res = m.cerrar_censo()
    assert res["accion"] == "confirmar"
    assert m._censo_discos.abierta and m._censo_armas.abierta and m._census.abierta
    inst = res["instantanea"]
    assert inst["discos"] is not None and inst["armas"] is not None
    assert inst["roster"]["pendientes"] == ["Ellen", "Jane", "Nangong Yu"]


def test_confirmar_la_instantanea_mostrada_cierra_todo(aislado):
    m = _monitor([])
    m._censo_discos = _discos_abierto()
    m._censo_armas = _armas_abierto()
    m._census = _roster_abierto()
    inst = m.cerrar_censo()["instantanea"]
    res = m.cerrar_censo(inst)
    assert res["accion"] == "cerrado"
    assert not m._censo_discos.abierta and not m._censo_armas.abierta and not m._census.abierta
    assert res["discos"] is not None and res["armas"] is not None
    assert set(res["roster"]["huerfanos"]) == {"Nangong Yu", "Jane", "Ellen"}


def test_confirmar_OTROS_pendientes_no_cierra_y_vuelve_a_preguntar(aislado):
    """El caso del 2026-08-17 sin reloj: lo que se confirmó no es lo que se va a declarar."""
    m = _monitor([])
    m._census = _roster_abierto()
    inst = m.cerrar_censo()["instantanea"]
    otra = {**inst, "roster": {**inst["roster"], "pendientes": ["Ellen", "Jane"]}}
    res = m.cerrar_censo(otra)
    assert res["accion"] == "confirmar"
    assert m._census.abierta
    assert res["instantanea"]["roster"]["pendientes"] == ["Ellen", "Jane", "Nangong Yu"]


def test_un_censo_que_se_abrio_despues_de_confirmar_no_se_cierra(aislado):
    m = _monitor([])
    m._censo_discos = _discos_abierto()
    inst = m.cerrar_censo()["instantanea"]
    m._censo_armas = _armas_abierto()          # entró al inventario de armas con el diálogo abierto
    res = m.cerrar_censo(inst)
    assert res["accion"] == "confirmar"
    assert m._censo_discos.abierta and m._censo_armas.abierta


def test_seguir_recorriendo_con_el_dialogo_abierto_no_invalida_la_confirmacion(aislado):
    """El progreso del inventario no es parte de lo confirmado: se aceptó cerrar el censo de
    discos, no un número."""
    m = _monitor([])
    m._censo_discos = _discos_abierto()
    inst = m.cerrar_censo()["instantanea"]
    m._censo_discos.anclar_total(411, ts=1.0)
    res = m.cerrar_censo(inst)
    assert res["accion"] == "cerrado"
    assert not m._censo_discos.abierta
