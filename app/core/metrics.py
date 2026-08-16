"""Instrumental de latencia — QA-06 §2.

*"Sin números registrados de p50/p99, cualquier afirmación sobre «está rápido» es opinión. Y las
opiniones no cumplen RNF-06."*

Mide cuánto tarda una superficie con presupuesto (QA-06 §1) y lo persiste para poder comparar
después. **No optimiza nada**: es lo que permite decidir QUÉ optimizar sin adivinar, que es el
primer paso que pide `Documentacion/2026-07-10_Futuro_Latencia_GPU_Distribucion.md` §9.

## Dos decisiones que se apartan del sketch de QA-06 §2, y por qué

**1. Las métricas viven en una DB APARTE** (`metrics.db`, al lado de la de dominio), no en una
tabla `metrics_latency` dentro de `danibod_zzz_v2.db`.

- La forma de verificar que un QA en readonly no escribió nada es comparar el **sha256 de la DB de
  dominio** — se usó dos veces el 2026-08-15, y es lo que dio confianza para tocar la ruta que
  alimenta `sync_equip`. Si la telemetría escribiera ahí, esa prueba desaparece.
- En readonly no se podría medir, y varios QA corren así: justamente los que más interesa medir.
- RNF-01 protege la DB de dominio con backup + transacción + PRAGMA. Escrituras append-only de alta
  frecuencia no encajan en esa disciplina, y un flush que salga mal se lleva datos del dominio.

Efecto colateral bueno: **no hace falta migración**. El esquema se crea solo, en su archivo.

**2. El reloj es `perf_counter`, y no es un detalle.** En Windows `thread_time` y `process_time`
avanzan de a **15.625 ms** (la tick del scheduler) aunque declaren `resolution=1e-07`: un bench de
pocos milisegundos devuelve un conteo de ticks disfrazado. Tres flakes seguidos del bench del censo
salieron de ahí (QA-06 §1.bis). Para presupuestos de 20-500 ms, `perf_counter` es el único que
sirve.

## Uso

    from app.core import metrics

    @metrics.measure_latency("ocr")
    def leer(...): ...

    with metrics.measure_block("detector"):
        ...

Está **apagado por defecto** y se enciende con `DANIBOD_METRICS=1`, igual que el resto de la
instrumentación del proyecto (`DANIBOD_ID_DIAG`, `DANIBOD_MEM_DIAG`). Apagado no escribe ni crea el
archivo: quien nunca la enciende no tiene por qué encontrarse una DB extra.

Para leer lo medido: `metrics.resumen()` → n/p50/p99/max por superficie.
"""
from __future__ import annotations

import functools
import logging
import math
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

_ENV_ON = "DANIBOD_METRICS"
_ENV_DB = "DANIBOD_METRICS_DB"

# Cuántas muestras se acumulan antes de tocar el disco. El flush por lote es lo que mantiene la
# instrumentación fuera del camino caliente: medir cuesta un `perf_counter` (~decenas de ns), y el
# costo real —abrir la DB y escribir— se paga una vez cada N.
_FLUSH_CADA = 100

_BUFFER: list[tuple[str, float, float]] = []      # (superficie, duration_ms, ts)
_LOCK = threading.Lock()                          # el monitor corre en su propio hilo
_ESQUEMA_LISTO = False

_DDL = """
CREATE TABLE IF NOT EXISTS metrics_latency (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    superficie  TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_superficie_ts
    ON metrics_latency(superficie, ts);
"""


def habilitado() -> bool:
    """¿Está encendida la instrumentación? Se lee del entorno en cada llamada a propósito: los
    tests la prenden y apagan con `monkeypatch`, y el costo es una consulta a un dict."""
    return os.environ.get(_ENV_ON, "").strip() not in ("", "0", "false", "no")


def db_path() -> Path:
    """Dónde se persiste. Por defecto, **al lado de la DB de dominio** — así una instalación
    empaquetada la deja en el directorio de usuario y no en el cwd desde donde se lanzó."""
    override = os.environ.get(_ENV_DB, "").strip()
    if override:
        return Path(override)
    from app.db.connection import get_db_path
    return get_db_path().with_name("metrics.db")


def reset() -> None:
    """Vacía el buffer y olvida que el esquema estaba creado. Para los tests, que redirigen la DB
    a un tmp distinto por caso."""
    global _ESQUEMA_LISTO
    with _LOCK:
        _BUFFER.clear()
        _ESQUEMA_LISTO = False


# --- registro ------------------------------------------------------------------------------------

def registrar(superficie: str, duration_ms: float) -> None:
    """Anota una medición ya tomada. Útil para tiempos que se obtienen de otra fuente."""
    if not habilitado():
        return
    with _LOCK:
        _BUFFER.append((superficie, float(duration_ms), time.time()))
        lleno = len(_BUFFER) >= _FLUSH_CADA
    if lleno:
        flush()


def measure_latency(superficie: str) -> Callable:
    """Decorator: mide la función y la registra bajo `superficie`.

    La medición va en un `finally`, así que **una excepción se mide igual** — y eso importa: el
    caso lento suele ser justamente el que falla, y perderlo sesga el p99 hacia lo optimista. La
    excepción se propaga intacta.
    """
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not habilitado():
                return fn(*a, **kw)       # camino sin instrumentar: una consulta al entorno
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                registrar(superficie, (time.perf_counter() - t0) * 1000.0)
        return wrapper
    return deco


@contextmanager
def measure_block(superficie: str):
    """Lo mismo que el decorator, para un tramo suelto que no es una función propia."""
    if not habilitado():
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        registrar(superficie, (time.perf_counter() - t0) * 1000.0)


def flush() -> int:
    """Vuelca lo acumulado. Devuelve cuántas filas escribió (0 si no había o si no pudo).

    **Nunca propaga.** La instrumentación es un observador: si no puede escribir, se calla y la app
    sigue. Medir no es una funcionalidad por la que valga la pena tirar abajo una captura.
    """
    global _ESQUEMA_LISTO
    with _LOCK:
        if not _BUFFER:
            return 0
        lote, _BUFFER[:] = list(_BUFFER), []
    try:
        con = sqlite3.connect(str(db_path()))
        try:
            if not _ESQUEMA_LISTO:
                con.executescript(_DDL)
                _ESQUEMA_LISTO = True
            con.executemany(
                "INSERT INTO metrics_latency (superficie, duration_ms, ts) VALUES (?,?,?)", lote)
            con.commit()
        finally:
            con.close()
        return len(lote)
    except Exception:
        log.debug("metrics: no se pudo persistir el lote (%d muestras)", len(lote), exc_info=True)
        return 0


# --- lectura -------------------------------------------------------------------------------------

def percentile(values: Iterable[float], p: float) -> float | None:
    """Percentil `p` (0-100) por **rango más cercano**. SQLite no trae `PERCENTILE_CONT`.

    Sin datos devuelve None en vez de 0.0: "no medí nada" y "medí 0 ms" son cosas distintas, y
    confundirlas arruina un baseline.

    ⚠ **Corrige un off-by-one del snippet de QA-06 §2.2**, que hacía `k = int(len(s) * p / 100)`.
    Con 100 muestras eso da `k=99` para p99 — o sea que **p99 siempre salía igual al máximo**, y un
    p99 que es el peor caso no sirve para lo único que se le pide: separar la cola de lo típico. El
    doc quedó actualizado.
    """
    s = sorted(values)
    if not s:
        return None
    k = max(0, math.ceil(len(s) * p / 100) - 1)
    return s[min(k, len(s) - 1)]


def resumen(dias: float = 7.0) -> list[dict]:
    """n / p50 / p99 / max por superficie sobre los últimos `dias`. Lista vacía si no hay nada."""
    path = db_path()
    if not path.exists():
        return []
    desde = time.time() - dias * 24 * 3600
    # `sqlite3.Error` cubre un archivo a medio escribir o sin la tabla todavía; `OSError`, un
    # permiso o una ruta que se fue. Leer métricas nunca puede tumbar a quien las consulta.
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except (sqlite3.Error, OSError):
        return []
    try:
        filas = con.execute(
            "SELECT superficie, duration_ms FROM metrics_latency WHERE ts >= ?", (desde,)
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    por: dict[str, list[float]] = {}
    for superficie, ms in filas:
        por.setdefault(superficie, []).append(float(ms))
    return [
        {
            "superficie": s,
            "n": len(v),
            "p50": percentile(v, 50),
            "p99": percentile(v, 99),
            "max": max(v),
        }
        for s, v in sorted(por.items())
    ]
