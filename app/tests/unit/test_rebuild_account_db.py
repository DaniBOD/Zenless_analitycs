"""Reconstrucción de la DB de cuenta — qué se vacía y qué NO.

El rebuild existe porque los 367 discos y los stats de 51 PJs se transcribieron a mano hace meses,
que es justo el dato que la tesis del proyecto dice que diverge. Pero "empezar de cero" tiene un
límite duro: **solo se puede vaciar lo que el sistema sabe volver a observar.**

Las 516 filas de `agent_thresholds` / `agent_substat_preferences` / `pj_weapon_synergy` salen de
Prydwen y de las matrices de rol, no de la pantalla. Vaciarlas no sería empezar de cero: sería
perder trabajo que ningún censo devuelve. Lo mismo con `mindscape`, `perforacion` y
`bono_dano_elemento`, que S18 no parsea (ver `sync_agent_stats.py`).

Por eso el test que más importa acá no es el que verifica que algo se borró, sino los que verifican
que algo **sobrevivió**.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from app.scripts.rebuild_account_db import (
    AGENTS_ARRASTRADAS,
    AGENTS_NULL,
    CATALOGO,
    INVESTIGACION,
    VACIAR,
    clasificar_tablas,
    rebuild,
)

# --- una DB de juguete con la forma de la real ------------------------------------------------

_SCHEMA = """
CREATE TABLE agents (
    id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL,
    rango TEXT, elemento TEXT, rol TEXT, faccion TEXT,
    nivel INTEGER, mindscape INTEGER,
    pv INTEGER, ataque INTEGER, prob_critico REAL, rec_energia REAL,
    perforacion INTEGER, bono_dano_elemento REAL,
    weapon_id INTEGER, set_4p_id INTEGER, disco6_main TEXT,
    notas TEXT, protected_build INTEGER DEFAULT 0
);
CREATE TABLE disc_sets (id INTEGER PRIMARY KEY, nombre TEXT);
CREATE TABLE weapons (id INTEGER PRIMARY KEY, nombre TEXT);
CREATE TABLE agent_thresholds (
    id INTEGER PRIMARY KEY, agente_id INTEGER, stat TEXT, valor_minimo REAL, fuente TEXT
);
CREATE TABLE pj_weapon_synergy (id INTEGER PRIMARY KEY, pj_id INTEGER, bonus REAL);
CREATE TABLE inventory_discs (id INTEGER PRIMARY KEY, slot INTEGER, agente_asignado INTEGER);
CREATE TABLE agent_discs (id INTEGER PRIMARY KEY, agente_id INTEGER, disc_id INTEGER);
CREATE TABLE lategame_runs (id INTEGER PRIMARY KEY, ts TEXT);
CREATE INDEX ix_discs_slot ON inventory_discs(slot);
"""

# Mapeo de la DB de juguete a los grupos reales, para no depender de las constantes del modulo
# (que nombran las 31 tablas de verdad).
_GRUPOS_TOY = {
    "catalogo": ("disc_sets", "weapons"),
    "investigacion": ("agent_thresholds", "pj_weapon_synergy"),
    "vaciar": ("inventory_discs", "agent_discs"),
    "derivadas": ("lategame_runs",),
}


@pytest.fixture
def origen(tmp_path, monkeypatch):
    p = tmp_path / "danibod_zzz_v2.db"
    con = sqlite3.connect(p)
    con.executescript(_SCHEMA)
    con.execute(
        "INSERT INTO agents VALUES (1,'Ellen','S','Hielo','Ataque','Victoria',"
        "60, 2, 11248, 2667, 72.2, 1.2, 90, 30.0, 44, 12, 'Ataque 30%', 'nota vieja', 0)"
    )
    con.execute(
        "INSERT INTO agents VALUES (2,'Aria','S','Éter','Anomalía','Angels',"
        "40, 0, 8812, 1591, 12.2, 1.2, NULL, NULL, NULL, NULL, NULL, NULL, 0)"
    )
    con.execute("INSERT INTO disc_sets VALUES (1,'Puffer Electro')")
    con.execute("INSERT INTO weapons VALUES (1,'Caldero de claridad')")
    con.execute("INSERT INTO agent_thresholds VALUES (1,1,'maestria_anomalia',300.0,'Prydwen')")
    con.execute("INSERT INTO pj_weapon_synergy VALUES (1,1,0.7)")
    con.execute("INSERT INTO inventory_discs VALUES (1,4,1)")
    con.execute("INSERT INTO agent_discs VALUES (1,1,1)")
    con.commit()
    con.close()
    monkeypatch.setattr("app.scripts.rebuild_account_db.CATALOGO", _GRUPOS_TOY["catalogo"])
    monkeypatch.setattr("app.scripts.rebuild_account_db.INVESTIGACION", _GRUPOS_TOY["investigacion"])
    monkeypatch.setattr("app.scripts.rebuild_account_db.VACIAR", _GRUPOS_TOY["vaciar"])
    monkeypatch.setattr("app.scripts.rebuild_account_db.DERIVADAS_VACIAS", _GRUPOS_TOY["derivadas"])
    return p


def _fila(p, sql, *args):
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    try:
        r = con.execute(sql, args).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def _n(p, tabla) -> int:
    con = sqlite3.connect(p)
    try:
        return con.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]
    finally:
        con.close()


# --- lo que SOBREVIVE (los tests que justifican el diseño) ------------------------------------

def test_el_catalogo_del_juego_sobrevive(origen, tmp_path):
    """Los sets y las armas son del JUEGO, no de la cuenta. Vaciarlos no es empezar de cero:
    es romper el scoring y obligar a recargar a mano un catálogo que no cambió."""
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    assert _n(destino, "disc_sets") == 1
    assert _n(destino, "weapons") == 1


def test_la_investigacion_de_scoring_sobrevive(origen, tmp_path):
    """`fuente='Prydwen'`: esto no se observa, se investiga. Es el dato que el censo NO devuelve."""
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    assert _n(destino, "agent_thresholds") == 1
    assert _n(destino, "pj_weapon_synergy") == 1
    assert _fila(destino, "SELECT * FROM agent_thresholds")["fuente"] == "Prydwen"


def test_la_identidad_del_pj_y_su_id_sobreviven(origen, tmp_path):
    """El `id` no es cosmético: las FK de thresholds y synergy cuelgan de él. Y nombre/rango/
    elemento/rol/facción son propiedades del juego — Ellen es S/Hielo/Ataque tengas o no la cuenta."""
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    ellen = _fila(destino, "SELECT * FROM agents WHERE nombre='Ellen'")
    assert ellen["id"] == 1
    assert (ellen["rango"], ellen["elemento"], ellen["rol"]) == ("S", "Hielo", "Ataque")
    assert ellen["faccion"] == "Victoria"


def test_las_tres_columnas_que_S18_no_parsea_se_arrastran(origen, tmp_path):
    """`mindscape`, `perforacion` y `bono_dano_elemento` son stats, pero el pipeline NO las lee
    (lo dice el comentario de `sync_agent_stats._STAT_MAP`). Vaciarlas repetiría el error de vaciar
    los umbrales: dato perdido que la observación no recupera."""
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    ellen = _fila(destino, "SELECT * FROM agents WHERE nombre='Ellen'")
    assert ellen["mindscape"] == 2
    assert ellen["perforacion"] == 90
    assert ellen["bono_dano_elemento"] == 30.0


def test_las_notas_se_conservan_aunque_queden_viejas(origen, tmp_path):
    """Describen builds que dejan de existir, pero también guardan decisiones y correcciones
    históricas. Tenerlas viejas es menos malo que perderlas."""
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    assert _fila(destino, "SELECT * FROM agents WHERE nombre='Ellen'")["notas"] == "nota vieja"


# --- lo que se VACÍA --------------------------------------------------------------------------

def test_el_inventario_queda_vacio_pero_las_tablas_existen(origen, tmp_path):
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    for t in ("inventory_discs", "agent_discs"):
        assert _n(destino, t) == 0


def test_los_stats_observables_quedan_en_NULL(origen, tmp_path):
    """Todo lo que `sync_agent_stats` sabe re-leer: se vacía porque el censo lo repuebla."""
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    ellen = _fila(destino, "SELECT * FROM agents WHERE nombre='Ellen'")
    for col in ("nivel", "pv", "ataque", "prob_critico", "rec_energia",
                "weapon_id", "set_4p_id", "disco6_main"):
        assert ellen[col] is None, f"{col} tendría que haber quedado NULL"


# --- integridad y seguridad -------------------------------------------------------------------

def test_la_db_origen_no_se_toca(origen, tmp_path):
    """El respaldo tiene que seguir siendo el respaldo. Si el rebuild muta el origen, no hay
    marcha atrás — y el punto de todo esto es que la haya."""
    antes = hashlib.sha256(origen.read_bytes()).hexdigest()
    rebuild(origen, tmp_path / "nueva.db")
    assert hashlib.sha256(origen.read_bytes()).hexdigest() == antes


def test_el_schema_se_clona_entero_indices_incluidos(origen, tmp_path):
    destino = tmp_path / "nueva.db"
    rebuild(origen, destino)
    def objetos(p, tipo):
        con = sqlite3.connect(p)
        try:
            return {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type=? AND sql IS NOT NULL", (tipo,))}
        finally:
            con.close()
    assert objetos(destino, "table") == objetos(origen, "table")
    assert objetos(destino, "index") == objetos(origen, "index")


def test_la_nueva_pasa_los_dos_PRAGMA(origen, tmp_path):
    destino = tmp_path / "nueva.db"
    rep = rebuild(origen, destino)
    assert rep.integridad == "ok"
    assert rep.fk_rotas == []


def test_una_tabla_sin_clasificar_hace_fallar_el_rebuild(origen, tmp_path):
    """La guarda que importa a futuro: si mañana una migración agrega una tabla y nadie la
    clasifica, el rebuild NO puede decidir solo si vaciarla. Tiene que frenar y preguntar, no
    adivinar — vaciar por defecto es como perdimos los umbrales en la versión imaginaria de esto."""
    con = sqlite3.connect(origen)
    con.execute("CREATE TABLE tabla_nueva_sin_clasificar (id INTEGER PRIMARY KEY)")
    con.commit(); con.close()
    with pytest.raises(ValueError, match="sin clasificar"):
        rebuild(origen, tmp_path / "nueva.db")


def test_clasificar_tablas_cubre_las_31_de_la_db_real():
    """Las constantes del módulo tienen que nombrar TODAS las tablas reales. Si esto falla es que
    la DB cambió y el rebuild quedó desactualizado."""
    from app.db.connection import get_db_path
    db = get_db_path()
    if not db.exists():
        pytest.skip("DB de dominio no disponible")
    con = sqlite3.connect(db)
    reales = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    con.close()
    faltan, sobran = clasificar_tablas(reales)
    assert faltan == [], f"tablas de la DB sin clasificar: {faltan}"
    assert sobran == [], f"tablas clasificadas que ya no existen: {sobran}"


def test_las_listas_de_agents_no_se_pisan():
    """Una columna no puede estar a la vez en 'se vacía' y en 'se arrastra'."""
    assert set(AGENTS_NULL) & set(AGENTS_ARRASTRADAS) == set()


def test_las_constantes_no_se_solapan_entre_grupos():
    grupos = (CATALOGO, INVESTIGACION, VACIAR)
    todas = [t for g in grupos for t in g]
    assert len(todas) == len(set(todas)), "hay una tabla en dos grupos"


# --- el reporte -------------------------------------------------------------------------------

def test_el_reporte_dice_que_se_arrastro_sin_reverificar(origen, tmp_path):
    """Un dato conservado que el usuario cree recién censado es peor que uno faltante: se ve
    igual de confiable y no lo es."""
    rep = rebuild(origen, tmp_path / "nueva.db")
    texto = rep.markdown()
    assert "mindscape" in texto
    assert "arrastrad" in texto.lower()
    for t in ("disc_sets", "inventory_discs"):
        assert t in texto
