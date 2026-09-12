"""El baseline del optimizador (`score_actual`) es la build que el PJ TIENE equipada.

Hallazgo 2026-09-12: `BuildOptimizer` leía la build actual de `agent_discs`, una tabla que quedó en
0 filas con la reconstrucción de la DB (2026-08-17) y que nada vuelve a llenar. La autoridad de "qué
tiene equipado un PJ" es `inventory_discs` (`agente_asignado=? AND equipado=1 AND descartado=0`).
Medido sobre una copia de la DB real: `score_actual == 0` para los 51 PJs con discos equipados, y
todo delta salía inflado (Miyabi: 23.25 contra 14.55 real).

El test no depende del inventario real (que se vacía y se re-censa): usa el esquema y el catálogo de
una COPIA de la DB de dominio y le pone un inventario controlado. Con un inventario donde los únicos
discos son los que el PJ ya lleva, la mejor build ES la actual — el optimizador no puede proponer
una mejora. Con el baseline en 0, proponía una por el total de la build.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

REAL_DB_PATH = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
MIYABI_ID = 2

# Build fija de Miyabi (forma tomada de su build real al 2026-09-12; valores CONSTANTES del test,
# no leídos de la DB, para que el test no cambie cuando se re-censa el inventario).
# (slot, set_id, main, main_valor, [(sub, val, rolls) x4])
_BUILD = [
    (1, 48, "HP", 2200.0, [("Perforación", 9.0, 0), ("Prob. Crítica", 7.2, 2),
                           ("Maestría de Anomalía", 27.0, 2), ("ATK", 19.0, 0)]),
    (2, 48, "ATK", 316.0, [("Prob. Crítica", 7.2, 2), ("ATK%", 3.0, 0),
                           ("Daño Crítico", 14.4, 2), ("DEF", 15.0, 0)]),
    (3, 25, "DEF", 184.0, [("Maestría de Anomalía", 9.0, 0), ("Daño Crítico", 14.4, 2),
                           ("Perforación", 9.0, 0), ("ATK%", 9.0, 2)]),
    # Slot 4: su disco real tiene main "Daño Crítico", que el arquetipo ANOMALY NO admite en slot 4
    # (mains_4 = Maestría de Anomalía / ATK%), y el optimizador filtra candidatos por esa lista. Acá
    # va ATK% para que el test mida SOLO el baseline; lo del filtro es otra discusión.
    (4, 25, "ATK%", 30.0, [("DEF%", 9.6, 1), ("ATK%", 12.0, 3),
                                   ("HP%", 6.0, 1), ("Perforación", 9.0, 0)]),
    (5, 25, "Bono Daño Hielo", 30.0, [("Perforación", 36.0, 3), ("Daño Crítico", 4.8, 0),
                                      ("HP%", 6.0, 1), ("HP", 112.0, 0)]),
    (6, 25, "ATK%", 30.0, [("DEF", 15.0, 0), ("Maestría de Anomalía", 18.0, 1),
                           ("Daño Crítico", 14.4, 2), ("Perforación", 18.0, 1)]),
]


def _insert_disc(con, slot, set_id, main, main_valor, subs, *, agente, equipado, descartado=0):
    cols = {"set_id": set_id, "slot": slot, "main_stat": main, "main_valor": main_valor,
            "nivel": 15, "agente_asignado": agente, "equipado": equipado,
            "descartado": descartado}
    for i, (name, val, rolls) in enumerate(subs, 1):
        cols[f"sub{i}"], cols[f"val{i}"], cols[f"rolls{i}"] = name, val, rolls
    cur = con.execute(
        f"INSERT INTO inventory_discs ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    return cur.lastrowid


@pytest.fixture
def db_con_build_equipada(tmp_path):
    """Copia de la DB de dominio con inventario controlado: SOLO la build equipada de Miyabi."""
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    copia = tmp_path / "danibod_zzz_v2.db"
    shutil.copy2(REAL_DB_PATH, copia)
    con = sqlite3.connect(copia)
    try:
        if con.execute("SELECT 1 FROM agents WHERE id=?", (MIYABI_ID,)).fetchone() is None:
            pytest.skip("Miyabi no está en agents")
        with con:
            con.execute("DELETE FROM optimizer_pending_actions")
            con.execute("DELETE FROM inventory_disc_evaluations")
            con.execute("DELETE FROM inventory_discs")
            ids = [
                _insert_disc(con, *d, agente=MIYABI_ID, equipado=1) for d in _BUILD
            ]
            # Ruido que NO es la build actual y NO puede entrar al baseline. Tiene que PUNTUAR
            # DISTINTO que el disco real del slot 1: con clones idénticos, un baseline que se
            # colara el ruido daba el mismo número y el test no lo veía (se probó rompiendo el
            # filtro `equipado=1`: pasaba en verde).
            #  - desequipado pero de Miyabi, y PEOR (así tampoco es una mejora para el test 2);
            _insert_disc(con, 1, 48, "HP", 2200.0,
                         [("DEF", 15.0, 0), ("HP", 112.0, 0), ("DEF%", 4.8, 0), ("HP%", 3.0, 0)],
                         agente=MIYABI_ID, equipado=0)
            #  - "equipado" pero descartado, y MEJOR (descartado no entra al inventario activo).
            _insert_disc(con, 1, 48, "HP", 2200.0,
                         [("Prob. Crítica", 12.0, 2), ("Daño Crítico", 24.0, 2),
                          ("ATK%", 6.0, 1), ("Perforación", 18.0, 0)],
                         agente=MIYABI_ID, equipado=1, descartado=1)
    finally:
        con.close()
    return copia, ids


def _score_de(opt, disc_ids):
    """Score de un conjunto de discos con la MISMA función que usa el optimizador."""
    agent = opt._agent_repo.get_by_id(MIYABI_ID)
    arch = opt._arch_repo.get_by_id(agent.arquetipo_primario_id)
    discs = [opt._inv_disc_repo.get_by_id(i) for i in disc_ids]
    return opt._build_total_score(discs, agent, arch)


def test_score_actual_es_el_de_la_build_equipada_en_inventory_discs(db_con_build_equipada):
    from app.core.optimizer import BuildOptimizer
    db, ids = db_con_build_equipada
    opt = BuildOptimizer(db)
    try:
        esperado = _score_de(opt, ids)
        result = opt.best_builds(MIYABI_ID, persist=False)
    finally:
        opt.close()
    assert esperado > 0
    assert result.score_actual == pytest.approx(esperado, abs=1e-3), (
        f"score_actual={result.score_actual} — el baseline no es la build equipada ({esperado:.4f})"
    )


def test_sin_otros_discos_no_hay_mejora_que_proponer(db_con_build_equipada):
    """La única build posible es la equipada ⇒ delta 0, y así queda PERSISTIDO (la fila, no el
    objeto: `optimizer_pending_actions` es lo que lee quien decide mostrar una sugerencia)."""
    from app.core.optimizer import BuildOptimizer
    db, ids = db_con_build_equipada
    opt = BuildOptimizer(db)
    try:
        result = opt.best_builds(MIYABI_ID, top_n=1, persist=True)
    finally:
        opt.close()
    assert sorted(d.disc_id for d in result.builds[0].discos) == sorted(ids)
    assert result.builds[0].delta_vs_actual == pytest.approx(0.0, abs=1e-3)

    con = sqlite3.connect(db)
    try:
        filas = con.execute(
            "SELECT score_actual, score_estimado, delta FROM optimizer_pending_actions "
            "WHERE agente_id=?", (MIYABI_ID,)
        ).fetchall()
    finally:
        con.close()
    assert len(filas) == 1
    score_actual, score_estimado, delta = filas[0]
    assert score_actual > 0
    assert score_actual == pytest.approx(score_estimado, abs=1e-3)
    assert delta == pytest.approx(0.0, abs=1e-3)
