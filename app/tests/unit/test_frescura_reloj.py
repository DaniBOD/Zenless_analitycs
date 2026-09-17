"""Frescura — que el cronómetro esté bien cerrado, y que una muestra absurda no pase por latencia.

Contexto, porque el bug que motiva este archivo es de los que no se ven: `frescura_estado_a_log`
abría el cronómetro con `time.monotonic()` (el reloj del loop rápido) y lo cerraba con
`time.time()` (tiempo de pared). La resta de dos relojes distintos no da un número *malo*, da el
**epoch entero**: ~1,789e12 ms. Se guardaron 14 muestras así durante un mes sin que nada se
quejara, porque **una métrica rota se ve igual que una métrica mala** — un número grande parece
"ah, estuvo lento".

Lo que se arregló no es la línea, es de quién es el reloj: `metrics.ahora()` + `registrar_desde()`
hacen la resta adentro del módulo, así que ningún llamador vuelve a elegir reloj (B1, una sola
autoridad por pregunta). Y como red, `registrar` descarta lo implausible y avisa.

Los tests de acá valen por lo que hacen FALLAR: si alguien vuelve a cerrar con `time.time()`, el
primero se pone rojo. Se verificó a mano revirtiendo el arreglo (A3 · verificar el efecto).
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import pytest

from app.core.detector import ScreenDetector, ScreenState
from app.core.monitor import Monitor
from app.core.parser_disc import DiscParsed, SubstatParsed

#: Techo de lo que puede tardar CUALQUIER frescura antes de ser un bug de medición y no una demora.
#: Generoso a propósito: el presupuesto real es 500 ms, así que un minuto no discute el rendimiento
#: —discute si el cronómetro cierra contra el reloj con el que abrió—. Con los relojes mezclados el
#: valor es ~1,789e12, o sea 3.000 millones de veces este techo: no hay zona gris.
_TECHO_PLAUSIBLE_MS = 60_000.0


class _DummyOcr:
    def text(self, *a, **kw):
        return "", 0.0

    def number(self, *a, **kw):
        return 0.0, 0.0


@pytest.fixture
def met(tmp_path, monkeypatch):
    """`metrics` con su DB en un tmp y la instrumentación encendida."""
    import app.core.metrics as m
    monkeypatch.setenv("DANIBOD_METRICS", "1")
    monkeypatch.setenv("DANIBOD_METRICS_DB", str(tmp_path / "metrics.db"))
    m.reset()
    yield m
    m.reset()


def _muestras(path: Path, superficie: str) -> list[float]:
    if not path.exists():
        return []
    con = sqlite3.connect(str(path))
    try:
        return [r[0] for r in con.execute(
            "SELECT duration_ms FROM metrics_latency WHERE superficie=?", (superficie,))]
    finally:
        con.close()


def _monitor():
    return Monitor(ocr=_DummyOcr(), detector=ScreenDetector())


def _sub(nombre, valor, rolls=0, unidad="flat"):
    return SubstatParsed(nombre, nombre, valor, unidad, rolls, 0.95)


def _disco_maduro():
    """Un disco que `disc_is_mature` acepta: set + slot + main con valor + 4 substats leídos."""
    return DiscParsed(
        set_name_raw="Jazz caótico", set_name_canon="Jazz caótico", slot=1,
        main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad="flat",
        nivel=15, rareza="S", confianza_global=0.95,
        subs=[_sub("ATK", 38.0, 1), _sub("Daño Crítico", 9.6, 1, "%"),
              _sub("Prob. Crítica", 4.8, 0, "%"), _sub("Maestría de Anomalía", 27.0, 2)],
    )


# --- el bug original ----------------------------------------------------------------------------

def test_la_frescura_de_estado_mide_un_numero_plausible(met, tmp_path):
    """**El test que pone rojo el bug.** Cierra un cronómetro abierto como lo abre el loop rápido
    (`time.monotonic()`) y exige que lo medido sea una latencia, no un epoch."""
    mon = _monitor()
    mon._frescura_estado_visto = "S9"
    mon._frescura_estado_t = time.monotonic()      # el reloj con el que abre el loop (línea del run)

    mon._notify_state_change(ScreenState("S9", 1.0, "prueba"))
    met.flush()

    vals = _muestras(tmp_path / "metrics.db", "frescura_estado_a_log")
    assert len(vals) == 1, "el cambio de estado tiene que dejar UNA muestra"
    assert 0.0 <= vals[0] < _TECHO_PLAUSIBLE_MS, (
        f"{vals[0]:.0f} ms no es una latencia: el cronómetro se cerró con otro reloj del que abrió")


def test_el_cronometro_solo_se_cierra_una_vez(met, tmp_path):
    """Dos cambios de estado con una sola apertura dejan una sola muestra. Sin esto, el segundo
    cierre mediría contra un `t0` viejo y el p99 se llenaría de demoras que nadie esperó."""
    mon = _monitor()
    mon._frescura_estado_visto = "S9"
    mon._frescura_estado_t = time.monotonic()

    mon._notify_state_change(ScreenState("S9", 1.0, "prueba"))
    mon._notify_state_change(ScreenState("S17", 1.0, "prueba"))
    met.flush()

    assert len(_muestras(tmp_path / "metrics.db", "frescura_estado_a_log")) == 1


# --- la red: una muestra absurda no se guarda ---------------------------------------------------

def test_una_muestra_implausible_se_descarta_y_avisa(met, tmp_path, caplog):
    """Lo que hubiera hecho visible el bug el primer día. El valor es el real que quedó en
    `metrics.db`: el epoch en milisegundos."""
    with caplog.at_level(logging.WARNING, logger="app.core.metrics"):
        met.registrar("frescura_estado_a_log", 1_789_152_796_830.0)
        met.registrar("negativa", -5.0)
    met.flush()

    assert _muestras(tmp_path / "metrics.db", "frescura_estado_a_log") == []
    assert _muestras(tmp_path / "metrics.db", "negativa") == []
    assert any("cronómetro" in r.getMessage() for r in caplog.records), (
        "descartar en silencio sería cambiar un percentil envenenado por un agujero invisible")


def test_avisa_una_vez_por_superficie_y_no_inunda(met, caplog):
    """El aviso vive en el camino caliente: si gritara en cada muestra, un reloj mal cerrado
    llenaría el log y taparía justamente las líneas de captura que Daniel usa como señal."""
    with caplog.at_level(logging.WARNING, logger="app.core.metrics"):
        for _ in range(50):
            met.registrar("repetida", 9e12)
    assert sum("repetida" in r.getMessage() for r in caplog.records) == 1


def test_lo_plausible_sigue_pasando(met, tmp_path):
    """La guarda no puede comerse una demora REAL: 4 segundos es exactamente el caso que se quiere
    poder ver (un disco que esperó el warmup), y tiene que quedar registrado."""
    met.registrar("lenta_pero_real", 4_000.0)
    met.flush()
    assert _muestras(tmp_path / "metrics.db", "lenta_pero_real") == [4_000.0]


# --- el reloj es uno solo -----------------------------------------------------------------------

def test_registrar_desde_acepta_el_reloj_del_loop(met, tmp_path):
    """`metrics.ahora()` y el `time.monotonic()` que toma el loop rápido tienen que ser el MISMO
    reloj. Si alguien cambia `ahora()` por `perf_counter` o `time.time()`, esto cae — y cae acá, no
    dentro de un percentil tres semanas después."""
    t0 = time.monotonic()
    met.registrar_desde("mixta", t0)
    met.flush()

    vals = _muestras(tmp_path / "metrics.db", "mixta")
    assert len(vals) == 1 and 0.0 <= vals[0] < 1_000.0, (
        "el t0 del loop no es compatible con el reloj de metrics")


def test_apagado_no_mide_la_frescura(tmp_path, monkeypatch):
    """Env-gateada como el resto: sin `DANIBOD_METRICS` no se escribe ni se crea el archivo."""
    import app.core.metrics as m
    monkeypatch.delenv("DANIBOD_METRICS", raising=False)
    monkeypatch.setenv("DANIBOD_METRICS_DB", str(tmp_path / "metrics.db"))
    m.reset()

    mon = _monitor()
    mon._frescura_estado_visto = "S9"
    mon._frescura_estado_t = m.ahora()
    mon._notify_state_change(ScreenState("S9", 1.0, "prueba"))
    m.flush()

    assert not (tmp_path / "metrics.db").exists()


# --- frescura del CONTENIDO (disco-a-log) -------------------------------------------------------

def test_la_frescura_del_disco_se_mide_aparte_de_la_pantalla(met, tmp_path):
    """La frescura de estado mide cambios de PANTALLA. En un censo la pantalla no cambia: cambia el
    disco mirado, y lo que se espera es su línea. QA-06 §10 dice que la de pantalla no cubre esto."""
    mon = _monitor()
    mon._abrir_frescura_disco()
    mon._cerrar_frescura_disco()
    met.flush()

    db = tmp_path / "metrics.db"
    assert len(_muestras(db, "frescura_disco_a_log")) == 1
    assert _muestras(db, "frescura_disco_warm") == [], "no pasó por warmup: no va al subconjunto"
    assert _muestras(db, "frescura_estado_a_log") == [], "son dos preguntas distintas"


def test_el_disco_que_esperó_el_warmup_queda_en_las_dos_superficies(met, tmp_path):
    """El warmup del dueño posterga la emisión de un disco YA leído. Marcarlo aparte es lo que
    permite atribuir la espera: si el p50 de `_warm` es mucho mayor que el general, la pone el
    warmup y no el cómputo. Sin esta separación habría que interpretar un solo número."""
    mon = _monitor()
    mon._abrir_frescura_disco()
    mon._frescura_disco_warm = True          # lo que hace el handler al entrar en warmup
    mon._cerrar_frescura_disco()
    met.flush()

    db = tmp_path / "metrics.db"
    assert len(_muestras(db, "frescura_disco_a_log")) == 1, "cuenta en el total"
    assert len(_muestras(db, "frescura_disco_warm")) == 1, "y también en el subconjunto"


def test_cerrar_sin_abrir_no_inventa_una_muestra(met, tmp_path):
    """Un disco que el dedup saltea no imprime línea, así que no hay evento que cronometrar. Y un
    `t0` viejo de otra pantalla no puede convertirse en una demora falsa."""
    mon = _monitor()
    mon._cerrar_frescura_disco()
    mon._cerrar_frescura_disco()
    met.flush()

    assert _muestras(tmp_path / "metrics.db", "frescura_disco_a_log") == []


def test_el_handler_REAL_de_s17_deja_la_muestra(met, tmp_path, monkeypatch):
    """**El test contra A2.** Los de arriba llaman a los helpers a mano, así que pasarían incluso
    si nadie los invocara nunca desde el pipeline. Éste maneja el handler de verdad
    (`_process_disc_s17_continuous`) y exige que la muestra aparezca sola."""
    import numpy as np
    mon = _monitor()
    mon._on_disc = lambda disc, st: None
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32),
           np.zeros((24, 24), np.float32))
    monkeypatch.setattr(mon, "_s17_disc_signature", lambda frame: sig)
    # Dueño RESUELTO (libre) → emite al madurar, sin pasar por el warmup.
    monkeypatch.setattr(mon, "_assign_s17_pj",
                        lambda disc, face: setattr(disc, "equip_libre", True))
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disco_maduro(), None))

    mon._process_disc_s17_continuous(None, ScreenState("S17", 1.0, "tmpl"))
    met.flush()

    db = tmp_path / "metrics.db"
    vals = _muestras(db, "frescura_disco_a_log")
    assert len(vals) == 1 and 0.0 <= vals[0] < _TECHO_PLAUSIBLE_MS
    assert _muestras(db, "frescura_disco_warm") == [], "no esperó al dueño: no es del subconjunto"


def test_el_handler_REAL_marca_el_disco_que_espero_al_dueno(met, tmp_path, monkeypatch):
    """Mismo handler, dueño INCIERTO: el disco madura pero la emisión se difiere hasta juntar
    pasadas del loop rápido. Cuando por fin sale, tiene que estar en las DOS superficies — eso es
    lo que después permite decir 'la espera la puso el warmup' con un número y no con una teoría."""
    import numpy as np
    import app.core.monitor as mon_mod
    mon = _monitor()
    mon._on_disc = lambda disc, st: None
    sig = (np.zeros((48, 24), np.float32), np.zeros((48, 48), np.float32),
           np.zeros((24, 24), np.float32))
    monkeypatch.setattr(mon, "_s17_disc_signature", lambda frame: sig)
    monkeypatch.setattr(mon, "_assign_s17_pj", lambda disc, face: None)   # nunca resuelve
    monkeypatch.setattr("app.core.monitor.parse_disc_s17_full",
                        lambda frame, ocr: (_disco_maduro(), None))
    st = ScreenState("S17", 1.0, "tmpl")

    mon._process_disc_s17_continuous(None, st)          # madura pero DIFIERE
    assert mon._s17_warming is True
    met.flush()
    assert _muestras(tmp_path / "metrics.db", "frescura_disco_a_log") == [], "todavía no hay línea"

    mon._s17_owner_passes = mon_mod._S17_OWNER_MIN_SAMPLES   # el loop rápido calentó el voto
    mon._process_disc_s17_continuous(None, st)          # ahora sí emite
    met.flush()

    db = tmp_path / "metrics.db"
    assert len(_muestras(db, "frescura_disco_a_log")) == 1
    assert len(_muestras(db, "frescura_disco_warm")) == 1, (
        "el disco esperó el warmup y eso tiene que quedar atribuido")


def test_abrir_de_nuevo_reinicia_la_marca_de_warmup(met, tmp_path):
    """Disco nuevo, cuenta limpia: el warmup del disco anterior no puede teñir al siguiente."""
    mon = _monitor()
    mon._abrir_frescura_disco()
    mon._frescura_disco_warm = True
    mon._cerrar_frescura_disco()

    mon._abrir_frescura_disco()              # otro disco, este no espera
    assert mon._frescura_disco_warm is False
    mon._cerrar_frescura_disco()
    met.flush()

    db = tmp_path / "metrics.db"
    assert len(_muestras(db, "frescura_disco_a_log")) == 2
    assert len(_muestras(db, "frescura_disco_warm")) == 1, "sólo el primero esperó"


# --- frescura CLICK→LOG en S9 (el punto ciego de la de despacho) ---------------------------------

def _firma(valor: float):
    """Firma de S9 sintética: título, bloque y posición. Dos valores muy distintos = dos discos."""
    import numpy as np
    return (np.full((24, 48), valor, np.float32), np.full((48, 48), valor, np.float32), None)


def _aislar_emision_s9(monkeypatch, mon):
    monkeypatch.setattr(mon, "_record_equip_map", lambda *a, **kw: None)
    monkeypatch.setattr(mon, "_censar_disco", lambda *a, **kw: None)


def test_click_a_log_se_abre_al_ver_el_disco_y_se_cierra_con_la_linea(met, tmp_path, monkeypatch):
    """La espera que Daniel vive: desde que el loop rápido ve el disco nuevo hasta la línea. La
    frescura de despacho no ve el tramo hasta el primer despacho, que en S9 llega a ~1,8 s."""
    mon = _monitor()
    _aislar_emision_s9(monkeypatch, mon)
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda frame: _firma(0.0))

    mon._vigilar_click_s9(None)
    assert mon._frescura_click_t is not None, "disco nuevo: el cronómetro tiene que abrirse"
    d = _disco_maduro()
    d.agente_asignado_nombre = "Corin"
    mon._emit_s9_disc(d, ScreenState("S9", 1.0, "t"))
    met.flush()

    vals = _muestras(tmp_path / "metrics.db", "frescura_disco_click_a_log")
    assert len(vals) == 1 and 0.0 <= vals[0] < _TECHO_PLAUSIBLE_MS
    assert mon._frescura_click_t is None


def test_click_a_log_no_se_reabre_mientras_el_panel_anima(met, monkeypatch):
    """Mientras el panel anima, la firma cambia varias veces. Re-abrir en cada cambio mediría desde
    el ÚLTIMO cuadro y la muestra saldría corta: sesgo optimista en justo lo que se quiere medir."""
    mon = _monitor()
    firmas = iter([_firma(0.0), _firma(255.0), _firma(120.0)])
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda frame: next(firmas))
    # Reloj CONTROLADO, y no es un detalle: `monotonic()` en Windows avanza de a 15,625 ms, así que
    # tres llamadas seguidas devuelven el mismo valor y "no se re-abrió" pasaba aunque se re-abriera.
    # Lo detectó el sabotaje del 2026-09-16 (práctica C2: un reloj declara unidad, no granularidad).
    instantes = iter([10.0, 20.0, 30.0])
    monkeypatch.setattr(met, "ahora", lambda: next(instantes))

    mon._vigilar_click_s9(None)
    t0 = mon._frescura_click_t
    assert t0 == 10.0
    mon._vigilar_click_s9(None)                 # la firma cambió (animación)
    mon._vigilar_click_s9(None)                 # y otra vez
    assert mon._frescura_click_t == t0, "se re-abrió: la muestra saldría corta"


def test_click_a_log_sin_firma_no_abre(met, monkeypatch):
    """Sin firma no hay evidencia de un disco nuevo (RNF-02): no se cronometra nada."""
    mon = _monitor()
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda frame: None)
    mon._vigilar_click_s9(None)
    assert mon._frescura_click_t is None


def test_click_a_log_con_metricas_apagadas_ni_calcula_la_firma(tmp_path, monkeypatch):
    """La firma cuesta ~15 ms por pasada. En uso normal (métricas apagadas) este vigilante no
    puede cobrar ese costo por una medición que nadie va a leer."""
    import app.core.metrics as m
    monkeypatch.delenv("DANIBOD_METRICS", raising=False)
    m.reset()
    mon = _monitor()
    llamadas = []
    monkeypatch.setattr(mon, "_s9_disc_signature", lambda frame: llamadas.append(1) or _firma(0.0))
    mon._vigilar_click_s9(None)
    assert llamadas == [] and mon._frescura_click_t is None


def test_click_a_log_un_disco_repetido_suelta_el_cronometro(met, tmp_path, monkeypatch):
    """Un disco repetido no imprime línea. Si el cronómetro quedara abierto, lo cerraría el disco
    SIGUIENTE y mediría las dos esperas juntas como si fueran una."""
    mon = _monitor()
    _aislar_emision_s9(monkeypatch, mon)
    d = _disco_maduro()
    d.agente_asignado_nombre = "Corin"
    st = ScreenState("S9", 1.0, "t")
    mon._emit_s9_disc(d, st)                     # primera vez: línea
    mon._frescura_click_t = met.ahora()          # cronómetro abierto para el repetido
    mon._emit_s9_disc(_disco_maduro_con("Corin"), st)        # mismo disco: dedup, sin línea
    met.flush()
    assert mon._frescura_click_t is None
    assert _muestras(tmp_path / "metrics.db", "frescura_disco_click_a_log") == []


def test_click_a_log_salir_de_S9_suelta_el_cronometro():
    """Un cronómetro abierto en S9 no lo puede cerrar la línea de un disco de otra pantalla."""
    mon = _monitor()
    mon._frescura_click_t = 1.0
    mon._s9_fast_sig = _firma(0.0)
    mon._reset_s9_disc_tracking()
    assert mon._frescura_click_t is None and mon._s9_fast_sig is None


def test_el_loop_rapido_realmente_vigila_S9():
    """**Contra A2.** Los tests de arriba llaman al vigilante a mano y pasarían aunque el loop no lo
    invocara. El loop no se puede correr en un test (captura pantalla), así que se verifica que lo
    llame en la rama de S9."""
    import inspect
    fuente = inspect.getsource(Monitor._run)
    rama = fuente.split('elif raw_state.code == "S9":', 1)
    assert len(rama) == 2 and "self._vigilar_click_s9(frame)" in rama[1].split("\n")[1]


def test_despacho_y_loop_rapido_usan_la_misma_comparacion():
    """B1: "¿es otro disco?" tiene UNA respuesta. Si el despacho y el loop rápido compararan con
    criterios distintos, la métrica mediría la diferencia entre dos umbrales, no la espera."""
    import inspect
    assert "_s9_firmas_distintas(" in inspect.getsource(Monitor._is_new_s9_disc)
    assert "_s9_firmas_distintas(" in inspect.getsource(Monitor._vigilar_click_s9)


def _disco_maduro_con(dueno):
    d = _disco_maduro()
    d.agente_asignado_nombre = dueno
    return d
