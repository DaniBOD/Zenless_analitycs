"""Persistencia del censo — multi-sesión, historial, y la frontera con la DB de dominio.

El estado del censo vive en `census.db`, **aparte** de `danibod_zzz_v2.db`. No es una preferencia
de orden: es lo que vuelve ESTRUCTURAL —y no disciplinar— que observar no contamine el dominio.
El censo es justo el flujo que más conviene ejercitar en readonly (mirar el menú y moverse no
arriesga nada), y con el estado adentro habría que elegir entre no poder correrlo así o perder la
prueba del sha256.

Por eso el test que cierra este archivo es el que más importa: **una corrida completa deja la DB
de dominio byte por byte igual.**
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from app.core.census import MenuSighting
from app.core.census_store import CensusStore, abrir_o_reanudar

_ROSTER = [(1, "Ellen"), (2, "Astra Yao"), (3, "Nicole"), (4, "Aria")]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_CENSUS_DB", str(tmp_path / "census.db"))
    return CensusStore()


def _ok(nombre: str) -> MenuSighting:
    return MenuSighting(nombre, nombre, 0.97, nombre, 0.95, "ok")


def _sha(p) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- esquema y apertura ---------------------------------------------------------------------

def test_el_esquema_se_crea_solo_sin_migracion(store, tmp_path):
    """`census.db` no necesita migración: no es dato de dominio, es evidencia SOBRE el dominio."""
    c = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    assert c.run_id is not None
    con = sqlite3.connect(tmp_path / "census.db")
    tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"census_runs", "census_coverage", "census_observations"} <= tablas


def test_abrir_siembra_el_roster_como_pendiente(store):
    c = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    assert len(c.pendientes) == 4


# --- multi-sesión: lo que Daniel pidió ------------------------------------------------------

def test_una_pasada_sobrevive_a_cerrar_la_app(store):
    """Censar 367 discos (o 51 PJs) en una sentada es mucho pedir. Reabrir la app tiene que
    retomar la MISMA corrida, no empezar de cero."""
    c1 = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    c1.observe(_ok("Ellen"), ts=101.0)
    c1.observe(_ok("Nicole"), ts=102.0)
    run_id = c1.run_id

    c2 = abrir_o_reanudar(CensusStore(), _ROSTER, ts=200.0)   # "reinicio"
    assert c2.run_id == run_id, "tiene que retomar la misma corrida, no abrir otra"
    assert {r.clave for r in c2.vistos} == {"Ellen", "Nicole"}
    assert {r.clave for r in c2.pendientes} == {"Astra Yao", "Aria"}


def test_lo_observado_despues_de_reanudar_se_acumula_sobre_lo_anterior(store):
    c1 = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    c1.observe(_ok("Ellen"), ts=101.0)
    c2 = abrir_o_reanudar(CensusStore(), _ROSTER, ts=200.0)
    c2.observe(_ok("Aria"), ts=201.0)
    c3 = abrir_o_reanudar(CensusStore(), _ROSTER, ts=300.0)
    assert {r.clave for r in c3.vistos} == {"Ellen", "Aria"}


def test_una_corrida_vencida_se_abandona_y_no_produce_huerfanos(store):
    """Vencerse no es terminar. Si se reanudara una pasada de hace semanas, su cobertura vieja
    mentiría sobre la cuenta de hoy; si se CERRARA sola, inventaría huérfanos."""
    c1 = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    c1.observe(_ok("Ellen"), ts=101.0)
    viejo = c1.run_id

    c2 = abrir_o_reanudar(CensusStore(), _ROSTER, ts=100.0 + 100 * 3600, ventana_h=72.0)
    assert c2.run_id != viejo
    assert len(c2.pendientes) == 4, "la corrida nueva arranca limpia"
    prev = next(r for r in store.historial() if r["id"] == viejo)
    assert prev["estado"] == "abandonada" and prev["cierre_motivo"] == "expirada"


def test_no_reanuda_una_corrida_contabilizada_contra_otra_db(store, tmp_path):
    """QA suele apuntar `DANIBOD_DB_PATH` a una copia. Reanudar a través de ese cambio mezclaría
    dos cuentas en una sola foto."""
    c1 = abrir_o_reanudar(store, _ROSTER, ts=100.0, db_path=tmp_path / "cuenta_a.db")
    c1.observe(_ok("Ellen"), ts=101.0)

    c2 = abrir_o_reanudar(CensusStore(), _ROSTER, ts=110.0, db_path=tmp_path / "cuenta_b.db")
    assert c2.run_id != c1.run_id
    assert c2.vistos == []
    prev = next(r for r in store.historial() if r["id"] == c1.run_id)
    assert prev["cierre_motivo"] == "db_distinta"


def test_una_corrida_cerrada_no_se_reabre(store):
    """Censar de nuevo es una corrida NUEVA. Eso es lo que vuelve el historial una auditoría de
    sincronía y no un flag de 'ya se hizo'."""
    c1 = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    c1.observe(_ok("Ellen"), ts=101.0)
    c1.cerrar(ts=102.0)

    c2 = abrir_o_reanudar(CensusStore(), _ROSTER, ts=103.0)
    assert c2.run_id != c1.run_id
    assert c2.vistos == [] and len(c2.pendientes) == 4


# --- cierre y historial ---------------------------------------------------------------------

def test_cerrar_persiste_estado_huerfanos_y_fecha(store):
    c = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    c.observe(_ok("Ellen"), ts=101.0)
    c.cerrar(ts=102.0)
    fila = store.historial()[0]
    assert fila["estado"] == "cerrada" and fila["ts_cierre"] == 102.0
    assert fila["cierre_motivo"] == "declarado_por_usuario"
    guardadas = store.cargar_cobertura(c.run_id)
    assert {r.clave for r in guardadas if r.estado == "huerfano"} == {"Astra Yao", "Nicole", "Aria"}


def test_el_historial_viene_de_la_mas_nueva_a_la_mas_vieja(store):
    for ts in (100.0, 200.0, 300.0):
        c = abrir_o_reanudar(CensusStore(), _ROSTER, ts=ts)
        c.observe(_ok("Ellen"), ts=ts + 1)
        c.cerrar(ts=ts + 2)
    ids = [r["id"] for r in store.historial()]
    assert ids == sorted(ids, reverse=True)


def test_cada_avistamiento_deja_rastro_para_poder_auditar_un_dudoso(store, tmp_path):
    """Sin el rastro, un DUDOSO dice que algo salió mal pero no qué."""
    c = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    c.observe(MenuSighting("Ellen", "Ellen", 0.31, "Ellen", 0.95, "ok"), ts=101.0)
    con = sqlite3.connect(tmp_path / "census.db")
    filas = con.execute("SELECT clave, conf, veredicto FROM census_observations").fetchall()
    con.close()
    assert filas == [("Ellen", 0.31, "dudoso")]


# --- drift del roster -----------------------------------------------------------------------

def test_un_pj_onboardeado_a_mitad_de_pasada_entra_como_pendiente(store):
    """Pasa de verdad: Aria se onboardeó el mismo día que se censaba."""
    c1 = abrir_o_reanudar(store, _ROSTER[:3], ts=100.0)
    c1.observe(_ok("Ellen"), ts=101.0)
    c2 = abrir_o_reanudar(CensusStore(), _ROSTER, ts=200.0)
    assert "Aria" in {r.clave for r in c2.pendientes}
    assert {r.clave for r in c2.vistos} == {"Ellen"}


def test_un_pj_que_desaparecio_del_roster_no_borra_lo_ya_observado(store):
    c1 = abrir_o_reanudar(store, _ROSTER, ts=100.0)
    c1.observe(_ok("Aria"), ts=101.0)
    c2 = abrir_o_reanudar(CensusStore(), _ROSTER[:3], ts=200.0)
    assert "Aria" in {r.clave for r in c2.filas()}


# --- el catálogo de personajes que EXISTEN ---------------------------------------------------

def test_el_catalogo_toma_tambien_los_splash_arts():
    """QA en vivo 2026-08-17: Norma es un PJ que Daniel no posee y que **no tiene** arte en
    `avatar_refs/`, así que el censo la reportaba como "no reconocida" en vez de "no poseída".
    Al agregarle el splash art —el paso 7 del onboarding, que Daniel ya hace— la esperada es que
    el catálogo se entere sola.

    Por eso el catálogo es la UNIÓN de las dos carpetas: `avatar_refs/` (semilla de badges) y
    `splash_arts/`. Cuál de las dos se actualice primero no debería importar."""
    from app.core.census_store import roster_y_catalogo
    roster, catalogo = roster_y_catalogo()
    if not roster:
        pytest.skip("roster DB no disponible")
    from app.core.asset_resolver import SPLASH_ARTS_DIR
    if not (SPLASH_ARTS_DIR / "Norma-ico.webp").exists():
        pytest.skip("falta el splash art de Norma")
    assert "Norma" in catalogo


def test_el_catalogo_no_confunde_las_variantes_de_archivo_con_personajes():
    """Cada PJ tiene `-ico` y `-extend`; son dos archivos del MISMO personaje."""
    from app.core.census_store import roster_y_catalogo
    roster, catalogo = roster_y_catalogo()
    if not roster:
        pytest.skip("roster DB no disponible")
    assert not [c for c in catalogo if c.endswith(("-ico", "-extend", "_ico", "_extend"))]


# --- la frontera con el dominio -------------------------------------------------------------

def test_readonly_queda_registrado_en_la_corrida(store, monkeypatch):
    monkeypatch.setenv("DANIBOD_READONLY", "1")
    c = abrir_o_reanudar(CensusStore(), _ROSTER, ts=100.0)
    c.observe(_ok("Ellen"), ts=101.0)
    assert store.historial()[0]["readonly"] == 1


def test_una_corrida_completa_deja_la_db_de_dominio_byte_por_byte_igual(tmp_path, monkeypatch):
    """**El test que justifica la DB aparte.** Si esto cae, se perdió la propiedad que hace
    verificable cualquier QA en readonly: que el sha256 del dominio pruebe que no se escribió."""
    dominio = tmp_path / "danibod_zzz_v2.db"
    con = sqlite3.connect(dominio)
    con.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, nombre TEXT)")
    con.executemany("INSERT INTO agents VALUES (?, ?)", _ROSTER)
    con.commit()
    con.close()
    monkeypatch.setenv("DANIBOD_DB_PATH", str(dominio))
    monkeypatch.delenv("DANIBOD_CENSUS_DB", raising=False)

    antes = _sha(dominio)
    c = abrir_o_reanudar(CensusStore(), _ROSTER, ts=100.0)
    for i, (_, n) in enumerate(_ROSTER):
        c.observe(_ok(n), ts=101.0 + i)
    c.cerrar(ts=200.0)

    assert (tmp_path / "census.db").exists(), "el censo tiene que haber escrito en SU archivo"
    assert _sha(dominio) == antes
