"""Instrumental de latencia (QA-06 §2) — `app/core/metrics.py`.

Sin números registrados de p50/p99, "está rápido" es una opinión, y las opiniones no cumplen
RNF-06. Este módulo es el costo de admisión para poder optimizar algo con criterio.

**Las métricas viven en una DB APARTE** (`metrics.db`, al lado de la principal), y no en
`metrics_latency` dentro de `danibod_zzz_v2.db` como sugería el sketch de QA-06 §2.2. Tres razones,
y la primera es la que decidió:

1. La verificación de que un QA en readonly no escribió nada se hace comparando el **sha256 de la
   DB de dominio** — se usó dos veces el 2026-08-15. Si la telemetría escribiera ahí, esa prueba
   desaparece.
2. En readonly no se podría medir, y varios QA corren así: justo los que más interesa instrumentar.
3. RNF-01 protege la DB de dominio con backup + transacción + PRAGMA. Escrituras append-only de
   alta frecuencia no encajan con esa disciplina, y un flush que salga mal se lleva puestos datos
   del dominio.

Efecto colateral bueno: no hace falta migración ninguna.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

import pytest


@pytest.fixture
def met(tmp_path, monkeypatch):
    """El módulo con su DB redirigida a un tmp y el instrumental ENCENDIDO."""
    import app.core.metrics as m
    monkeypatch.setenv("DANIBOD_METRICS", "1")
    monkeypatch.setenv("DANIBOD_METRICS_DB", str(tmp_path / "metrics.db"))
    m.reset()
    return m


def _filas(path: Path, superficie: str | None = None) -> int:
    if not path.exists():
        return 0
    con = sqlite3.connect(str(path))
    try:
        if superficie:
            return con.execute("SELECT COUNT(*) FROM metrics_latency WHERE superficie=?",
                               (superficie,)).fetchone()[0]
        return con.execute("SELECT COUNT(*) FROM metrics_latency").fetchone()[0]
    finally:
        con.close()


# --- lo básico ---------------------------------------------------------------------------------

def test_el_decorator_mide_y_persiste(met, tmp_path):
    @met.measure_latency("prueba")
    def lenta():
        time.sleep(0.01)
        return "ok"

    for _ in range(3):
        assert lenta() == "ok"          # no altera el valor de retorno
    met.flush()
    assert _filas(tmp_path / "metrics.db", "prueba") == 3


def test_el_bloque_mide_lo_mismo_que_el_decorator(met, tmp_path):
    with met.measure_block("bloque"):
        time.sleep(0.01)
    met.flush()
    assert _filas(tmp_path / "metrics.db", "bloque") == 1


def test_mide_aunque_la_funcion_reviente(met, tmp_path):
    """Una excepción no puede tragarse la medición ni cambiar de tipo: el caso lento suele ser
    justamente el que falla, y perderlo sesga el p99 hacia lo optimista."""
    @met.measure_latency("explota")
    def mala():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        mala()
    met.flush()
    assert _filas(tmp_path / "metrics.db", "explota") == 1


def test_flushea_solo_al_llenar_el_buffer(met, tmp_path):
    """El flush por lote es lo que mantiene la instrumentación fuera del camino caliente."""
    @met.measure_latency("lote")
    def f():
        return 1

    for _ in range(met._FLUSH_CADA - 1):
        f()
    assert _filas(tmp_path / "metrics.db", "lote") == 0, "escribió antes de llenar el buffer"
    f()
    assert _filas(tmp_path / "metrics.db", "lote") == met._FLUSH_CADA


# --- el gate ------------------------------------------------------------------------------------

def test_apagado_no_mide_ni_crea_el_archivo(tmp_path, monkeypatch):
    """Instrumentación env-gateada, como el resto del proyecto (`DANIBOD_ID_DIAG`,
    `DANIBOD_MEM_DIAG`). Apagado no debe dejar rastro NI archivo: un usuario que nunca la enciende
    no tiene por qué encontrarse una DB extra."""
    import app.core.metrics as m
    monkeypatch.delenv("DANIBOD_METRICS", raising=False)
    monkeypatch.setenv("DANIBOD_METRICS_DB", str(tmp_path / "metrics.db"))
    m.reset()

    @m.measure_latency("apagado")
    def f():
        return 42

    assert f() == 42
    m.flush()
    assert not (tmp_path / "metrics.db").exists()


# --- la razón por la que la DB está aparte -------------------------------------------------------

def test_la_db_de_dominio_no_se_toca(met, tmp_path, monkeypatch):
    """**El test que justifica la decisión de diseño.**

    Si esto cae, se perdió la propiedad que hace verificable cualquier QA en readonly: que el
    sha256 de `danibod_zzz_v2.db` sea idéntico antes y después de una corrida.
    """
    dominio = tmp_path / "danibod_zzz_v2.db"
    con = sqlite3.connect(str(dominio))
    con.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT)")
    con.execute("INSERT INTO agents (nombre) VALUES ('Ellen')")
    con.commit()
    con.close()
    monkeypatch.setenv("DANIBOD_DB_PATH", str(dominio))
    antes = hashlib.sha256(dominio.read_bytes()).hexdigest()

    @met.measure_latency("no_toca")
    def f():
        return 1

    for _ in range(met._FLUSH_CADA + 5):
        f()
    met.flush()

    assert hashlib.sha256(dominio.read_bytes()).hexdigest() == antes
    assert _filas(tmp_path / "metrics.db", "no_toca") > 0     # y sí midió


def test_por_defecto_la_db_de_metricas_va_al_lado_de_la_principal(tmp_path, monkeypatch):
    """Sin override explícito, `metrics.db` vive junto a la DB de dominio — así una instalación
    empaquetada la deja en el directorio de usuario y no en el cwd."""
    import app.core.metrics as m
    monkeypatch.delenv("DANIBOD_METRICS_DB", raising=False)
    monkeypatch.setenv("DANIBOD_DB_PATH", str(tmp_path / "sub" / "danibod_zzz_v2.db"))
    m.reset()
    assert m.db_path() == tmp_path / "sub" / "metrics.db"


# --- lectura ------------------------------------------------------------------------------------

def test_percentil_sobre_una_muestra_conocida(met):
    vals = [float(x) for x in range(1, 101)]        # 1..100
    assert met.percentile(vals, 50) == 50.0
    assert met.percentile(vals, 99) == 99.0
    assert met.percentile(vals, 100) == 100.0      # no se sale del rango
    assert met.percentile([], 50) is None          # sin datos no se inventa un número


def test_resumen_devuelve_p50_y_p99_por_superficie(met):
    for i in range(100):
        met.registrar("a", float(i))
    for i in range(10):
        met.registrar("b", 1000.0 + i)
    met.flush()
    r = {x["superficie"]: x for x in met.resumen()}
    assert r["a"]["n"] == 100 and r["b"]["n"] == 10
    assert r["a"]["p50"] < r["a"]["p99"] < r["b"]["p50"]


def test_resumen_sin_datos_no_revienta(met):
    assert met.resumen() == []


# --- no puede romper la app ---------------------------------------------------------------------

def test_un_fallo_de_persistencia_no_propaga(met, monkeypatch, tmp_path):
    """La instrumentación es un observador: si no puede escribir, se calla y la app sigue. Medir no
    es una funcionalidad por la que valga la pena tirar abajo una captura."""
    monkeypatch.setenv("DANIBOD_METRICS_DB", str(tmp_path / "no" / "existe" / "x.db"))
    met.reset()

    @met.measure_latency("roto")
    def f():
        return "sigue andando"

    for _ in range(met._FLUSH_CADA + 1):
        assert f() == "sigue andando"
    met.flush()          # tampoco acá
