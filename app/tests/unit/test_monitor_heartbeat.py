"""Prueba de vida del loop del monitor: que ningún tramo pueda pasar en silencio.

## Por qué existe

QA del 2026-07-25: el monitor estuvo **8 minutos sin escribir una sola línea** mientras la
pantalla del juego pasaba por tres estados distintos (diálogo → grilla → S17). Descartar causas
llevó media mañana —gate de foco, watchdog de RAM, pausa por hotkey, pérdida de ventana, y tres
reproducciones offline de los handlers— y aun así **el log no alcanzó para saber qué pasó**.

`_note_stall` ya cubre los returns tempranos de los *handlers*. Lo que faltaba es una capa más
abajo: la prueba de que el **loop** está girando y de que los frames están llegando. Sin eso, el
silencio es ambiguo — puede ser un loop muerto, un loop girando en vacío, o una pantalla que
simplemente no cambia — y las tres se ven exactamente igual desde afuera.

Este archivo también fija que **una excepción de un handler no puede matar el hilo**. Hoy el
cuerpo del loop no está protegido: cualquier `raise` en un `_process_*` termina el thread, y como
el traceback va a stderr (que en el .exe se bufferea y puede no vaciarse nunca), la app queda
viva y ciega sin dejar rastro.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.detector import ScreenState


@pytest.fixture
def mon(monkeypatch, tmp_path):
    import app.core.monitor as mon_mod
    from app.core.farm_session import FarmSession

    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path))
    diags: list[str] = []
    m = mon_mod.Monitor(ocr=object(), detector=None, on_diagnostic=diags.append,
                        farm_session=FarmSession())
    m._diags = diags
    return m


def _frame():
    return np.full((100, 100, 3), 40, dtype=np.uint8)


# --- El latido -------------------------------------------------------------------------------

def test_el_silencio_prolongado_produce_una_linea(mon, caplog):
    """Lo que faltó el 2026-07-25: saber si el loop seguía girando."""
    caplog.set_level("INFO")
    mon._hb_ticks = 600
    mon._hb_last_t = 0.0            # última señal: hace mucho
    mon._hb_last_log_t = 0.0
    mon._heartbeat(now=120.0, state_code="S17")

    latidos = [r.message for r in caplog.records if "[hb]" in r.message]
    assert len(latidos) == 1, caplog.text
    assert "600" in latidos[0], f"no dice cuántos ciclos giró: {latidos[0]}"
    assert "S17" in latidos[0], f"no dice en qué estado está: {latidos[0]}"


def test_no_late_si_el_log_tuvo_actividad_reciente(mon, caplog):
    """El latido es para el silencio. Si el monitor está logueando normalmente, ya hay prueba de
    vida y una línea por minuto sería ruido."""
    caplog.set_level("INFO")
    mon._hb_ticks = 600
    mon._hb_last_t = 100.0
    mon._hb_last_log_t = 118.0      # alguien logueó hace 2 s
    mon._heartbeat(now=120.0, state_code="S17")
    assert not [r for r in caplog.records if "[hb]" in r.message]


def test_late_igual_cada_tanto_aunque_haya_actividad(mon, caplog):
    """Una línea de base cada varios minutos: sirve de regla para medir el ritmo del loop
    (ciclos/segundo) cuando después hay que diagnosticar rendimiento."""
    caplog.set_level("INFO")
    mon._hb_ticks = 3000
    mon._hb_last_t = 0.0
    mon._hb_last_log_t = 599.0      # hay actividad, pero pasó el intervalo largo
    mon._heartbeat(now=600.0, state_code="S12")
    assert [r for r in caplog.records if "[hb]" in r.message], caplog.text


def test_el_latido_reporta_los_frames_nulos(mon, caplog):
    """Distingue "el loop gira pero no llegan frames" de "el loop gira y todo anda". Son causas
    completamente distintas y desde el log viejo se veían iguales."""
    caplog.set_level("INFO")
    mon._hb_ticks, mon._hb_nulls = 300, 297
    mon._hb_last_t = mon._hb_last_log_t = 0.0
    mon._heartbeat(now=120.0, state_code=None)
    latido = [r.message for r in caplog.records if "[hb]" in r.message][0]
    assert "297" in latido, latido


def test_los_contadores_se_reinician_en_cada_latido(mon):
    mon._hb_ticks, mon._hb_nulls = 300, 5
    mon._hb_last_t = mon._hb_last_log_t = 0.0
    mon._heartbeat(now=120.0, state_code="S1")
    assert mon._hb_ticks == 0 and mon._hb_nulls == 0


# --- Que una excepción no mate el hilo ---------------------------------------------------------

def test_una_excepcion_del_handler_no_propaga(mon, caplog):
    """Si esto propaga, el thread muere y la app queda viva y ciega — sin toast, sin log, sin
    forma de notarlo hasta que alguien mira py-spy."""
    caplog.set_level("ERROR")

    def explota(frame, state):
        raise RuntimeError("boom")

    mon._dispatch_state = explota
    mon._safe_dispatch(_frame(), ScreenState("S11", 1.0, "x"))   # no debe levantar

    errores = [r for r in caplog.records if r.levelname == "ERROR"]
    assert errores, "la excepción se tragó en silencio"
    assert "boom" in caplog.text


def test_la_excepcion_repetida_no_inunda_el_log(mon, caplog):
    """Una pantalla que rompe el handler se queda en pantalla: sin dedup, el log se llena de
    tracebacks idénticos y tapa lo que importa."""
    caplog.set_level("ERROR")

    def explota(frame, state):
        raise RuntimeError("boom")

    mon._dispatch_state = explota
    for _ in range(10):
        mon._safe_dispatch(_frame(), ScreenState("S11", 1.0, "x"))

    errores = [r for r in caplog.records if r.levelname == "ERROR"]
    assert 1 <= len(errores) <= 2, f"{len(errores)} tracebacks para el mismo fallo"


def test_el_latido_delata_las_excepciones_acumuladas(mon, caplog):
    """Aunque el traceback se logueé una sola vez, el latido tiene que seguir diciendo que el
    handler está roto — si no, el problema desaparece del log y parece resuelto."""
    def explota(frame, state):
        raise RuntimeError("boom")

    mon._dispatch_state = explota
    for _ in range(7):
        mon._safe_dispatch(_frame(), ScreenState("S11", 1.0, "x"))

    caplog.set_level("INFO")
    mon._hb_ticks = 100
    mon._hb_last_t = mon._hb_last_log_t = 0.0
    mon._heartbeat(now=120.0, state_code="S11")
    latido = [r.message for r in caplog.records if "[hb]" in r.message][0]
    assert "7" in latido, f"no reporta las 7 excepciones: {latido}"
