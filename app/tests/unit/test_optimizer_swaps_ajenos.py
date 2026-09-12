"""Un disco que lleva OTRO PJ solo entra a la build si moverlo gana algo — y nunca sale rotulado libre.

Diagnóstico 2026-09-12 (`Dev_IA/.../2026-09-12_DIAG_Swaps_con_neto_negativo_entran_como_discos_libres.md`):
la fase 1 recibía todos los discos activos, ajenos incluidos, sin costo; `_compute_swaps` filtraba
la LISTA de swaps pero no la build. Resultado medido: 92 discos ajenos con neto ≤ 0 en las mejores
builds de 51 PJs, con `swap_origen=None` ("libre"). 72 de ellos con neto EXACTAMENTE 0: sin
preferencias por PJ el score depende solo del arquetipo, así que era un traslado entre compañeros.

Reglas (decididas por Daniel):
  B — un disco ajeno es candidato solo si su neto disco a disco es > 0 (y el origen no está
      protegido y se puede puntuar); se filtra ANTES del bonus pass.
  D — neto == 0 no es mejora: no se mueve.
  A — red: todo disco ajeno que igual termine en una build lleva `swap_origen`.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.tests.unit.test_optimizer_build_actual import REAL_DB_PATH, _insert_disc

_SUBS_CRIT = [("Prob. Crítica", 7.2, 2), ("Daño Crítico", 14.4, 2),
              ("ATK%", 9.0, 1), ("Perforación", 9.0, 0)]
_SUBS_FLOJOS = [("HP", 112.0, 0), ("DEF", 15.0, 0), ("HP%", 3.0, 0), ("DEF%", 4.8, 0)]


def _pjs_por_arquetipo(con):
    """{code: [agente_id, ...]} de los PJs SIN preferencias propias (su score es el del arquetipo)."""
    from app.db.repositories import AgentRepo, ArchetypeRepo
    con.row_factory = sqlite3.Row
    ar, rr = AgentRepo(con), ArchetypeRepo(con)
    out: dict[str, list[int]] = {}
    for (aid,) in con.execute("SELECT id FROM agents ORDER BY id").fetchall():
        a = ar.get_by_id(aid)
        if a is None or a.substat_preferences:
            continue
        arch = rr.get_by_id(a.arquetipo_primario_id)
        if arch is not None:
            out.setdefault(arch.code, []).append(aid)
    return out


@pytest.fixture
def db(tmp_path):
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    copia = tmp_path / "danibod_zzz_v2.db"
    shutil.copy2(REAL_DB_PATH, copia)
    con = sqlite3.connect(copia)
    try:
        por_arq = _pjs_por_arquetipo(con)
        if len(por_arq.get("ATK_DPS", [])) < 2 or not por_arq.get("DEFENSE"):
            pytest.skip("hacen falta 2 PJs ATK_DPS y 1 DEFENSE sin preferencias")
        con.row_factory = None
        with con:
            con.execute("DELETE FROM optimizer_pending_actions")
            con.execute("DELETE FROM inventory_disc_evaluations")
            con.execute("DELETE FROM inventory_discs")
            con.execute("UPDATE agents SET protected_build = 0")
    finally:
        con.close()
    dps, companero = por_arq["ATK_DPS"][:2]
    return copia, {"dps": dps, "companero": companero, "tanque": por_arq["DEFENSE"][0]}


def _run(db_path, agente_id, **kw):
    from app.core.optimizer import BuildOptimizer
    opt = BuildOptimizer(db_path)
    try:
        return opt.best_builds(agente_id, persist=False, **kw)
    finally:
        opt.close()


def _neto(db_path, disc_id, destino, origen):
    """Neto disco a disco con la función de score del optimizador (precondición de cada caso)."""
    from app.core.optimizer import BuildOptimizer, _disc_base_score
    opt = BuildOptimizer(db_path)
    try:
        d = opt._inv_disc_repo.get_by_id(disc_id)
        s = {}
        for aid in (destino, origen):
            a = opt._agent_repo.get_by_id(aid)
            s[aid] = _disc_base_score(d, a, opt._arch_repo.get_by_id(a.arquetipo_primario_id), opt._ctx)
        return s[destino] - s[origen]
    finally:
        opt.close()


def _con(db_path, fn):
    con = sqlite3.connect(db_path)
    try:
        with con:
            return fn(con)
    finally:
        con.close()


def _ids_en_builds(result):
    return {d.disc_id for b in result.builds for d in b.discos}


def test_D_companero_de_arquetipo_neto_cero_no_se_mueve(db):
    path, pj = db
    ajeno, libre = _con(path, lambda c: (
        _insert_disc(c, 1, 48, "HP", 2200.0, _SUBS_CRIT, agente=pj["companero"], equipado=1),
        _insert_disc(c, 1, 48, "HP", 2200.0, _SUBS_FLOJOS, agente=None, equipado=0),
    ))
    assert _neto(path, ajeno, pj["dps"], pj["companero"]) == pytest.approx(0.0, abs=1e-9)

    result = _run(path, pj["dps"])
    assert ajeno not in _ids_en_builds(result), "se llevó el disco del compañero con neto 0"
    assert [d.disc_id for d in result.builds[0].discos] == [libre]


def test_B_neto_negativo_no_es_candidato(db):
    path, pj = db
    # SIN alternativa libre: con un disco flojo al lado, el tanque ya lo prefería por score y el
    # test pasaba antes del arreglo (se verificó: verde sin B). Único candidato ⇒ lo toma o no.
    ajeno = _con(path, lambda c: _insert_disc(
        c, 1, 48, "HP", 2200.0, _SUBS_CRIT, agente=pj["dps"], equipado=1))
    assert _neto(path, ajeno, pj["tanque"], pj["dps"]) < 0

    result = _run(path, pj["tanque"])
    assert ajeno not in _ids_en_builds(result)


def test_B_neto_positivo_entra_y_lleva_el_swap(db):
    path, pj = db
    ajeno = _con(path, lambda c: _insert_disc(
        c, 1, 48, "HP", 2200.0, _SUBS_CRIT, agente=pj["tanque"], equipado=1))
    assert _neto(path, ajeno, pj["dps"], pj["tanque"]) > 0

    result = _run(path, pj["dps"], top_n=1)
    (disco,) = result.builds[0].discos
    assert disco.disc_id == ajeno
    assert disco.swap_origen is not None and disco.swap_origen["pj_id"] == pj["tanque"]
    (sw,) = result.builds[0].swaps_requeridos
    assert sw["disc_id"] == ajeno and sw["neto"] > 0


def test_B_origen_protegido_no_se_toca_aunque_gane(db):
    path, pj = db
    ajeno = _con(path, lambda c: _insert_disc(
        c, 1, 48, "HP", 2200.0, _SUBS_CRIT, agente=pj["tanque"], equipado=1))
    _con(path, lambda c: c.execute("UPDATE agents SET protected_build=1 WHERE id=?", (pj["tanque"],)))
    assert _neto(path, ajeno, pj["dps"], pj["tanque"]) > 0

    result = _run(path, pj["dps"])
    assert ajeno not in _ids_en_builds(result)


def test_A_red_un_disco_ajeno_nunca_sale_rotulado_libre(db, monkeypatch):
    """Si B fallara (acá se lo apaga a propósito), el disco ajeno igual tiene que decir de quién es."""
    import app.core.optimizer as optimizer
    path, pj = db
    ajeno = _con(path, lambda c: _insert_disc(
        c, 1, 48, "HP", 2200.0, _SUBS_CRIT, agente=pj["companero"], equipado=1))
    monkeypatch.setattr(optimizer, "_admite_disco_ajeno", lambda swap: True)

    result = _run(path, pj["dps"], top_n=1)
    (disco,) = result.builds[0].discos
    assert disco.disc_id == ajeno
    assert disco.swap_origen is not None, "disco de otro PJ rotulado como libre"
    assert disco.swap_origen["pj_id"] == pj["companero"]
    (sw,) = result.builds[0].swaps_requeridos
    assert sw["disc_id"] == ajeno and sw["neto"] == pytest.approx(0.0, abs=1e-9)
