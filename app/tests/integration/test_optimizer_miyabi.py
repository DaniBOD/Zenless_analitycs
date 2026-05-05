"""
Hito 2.6.5 — Test canónico del optimizador: Miyabi (agente_id=2).
Usa la DB real (no fixture en memoria) para validar que el optimizador
produce builds coherentes con el inventario actual.

Propiedades verificadas:
- Devuelve exactamente 3 builds.
- Cada build tiene exactamente 6 discos (uno por slot).
- No hay discos duplicados dentro de una build.
- El score total de la mejor build es mayor que el baseline actual.
- Todos los swaps propuestos tienen neto > 0.
- El delta_vs_actual coincide con score_total - score_actual.
- La latencia es < 1000 ms (RF-06 §2.2).
- El build #1 persiste en optimizer_pending_actions con estado='TODO'.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path("db/danibod_zzz_v2.db")
MIYABI_ID = 2


@pytest.fixture(scope="module")
def optimizer():
    if not DB_PATH.exists():
        pytest.skip("DB no disponible — ejecutar desde la raíz del repo.")
    from app.core.optimizer import BuildOptimizer
    opt = BuildOptimizer(DB_PATH)
    yield opt
    opt.close()


@pytest.fixture(scope="module")
def result(optimizer):
    return optimizer.best_builds(MIYABI_ID, top_n=3, persist=True)


class TestOptimizerMiyabi:
    def test_returns_three_builds(self, result):
        assert len(result.builds) == 3

    def test_ranks_are_sequential(self, result):
        for i, b in enumerate(result.builds, 1):
            assert b.rank == i

    def test_each_build_has_six_discos(self, result):
        for b in result.builds:
            assert len(b.discos) == 6, f"Build #{b.rank} tiene {len(b.discos)} discos"

    def test_no_duplicate_discos_in_build(self, result):
        for b in result.builds:
            disc_ids = [d.disc_id for d in b.discos]
            assert len(disc_ids) == len(set(disc_ids)), f"Build #{b.rank} tiene discos duplicados"

    def test_one_disco_per_slot(self, result):
        for b in result.builds:
            slots = [d.slot for d in b.discos]
            assert sorted(slots) == [1, 2, 3, 4, 5, 6], f"Build #{b.rank} slots: {slots}"

    def test_best_build_beats_baseline(self, result):
        assert result.builds[0].score_total > result.score_actual, (
            f"Mejor build ({result.builds[0].score_total:.3f}) no supera baseline ({result.score_actual:.3f})"
        )

    def test_delta_consistency(self, result):
        for b in result.builds:
            expected_delta = b.score_total - result.score_actual
            assert abs(b.delta_vs_actual - expected_delta) < 1e-3, (
                f"Build #{b.rank}: delta={b.delta_vs_actual} esperado={expected_delta:.4f}"
            )

    def test_builds_ordered_by_score(self, result):
        scores = [b.score_total for b in result.builds]
        assert scores == sorted(scores, reverse=True), f"Builds no ordenados: {scores}"

    def test_swaps_have_positive_neto(self, result):
        for b in result.builds:
            for sw in b.swaps_requeridos:
                assert sw["neto"] > 0, (
                    f"Build #{b.rank}: swap disc={sw['disc_id']} neto={sw['neto']:.4f} ≤ 0"
                )

    def test_latency_under_1000ms(self, result):
        assert result.latency_ms < 1000, f"Latencia {result.latency_ms:.0f}ms supera 1000ms"

    def test_build_id_is_uuid(self, result):
        import uuid
        for b in result.builds:
            uuid.UUID(b.build_id)  # raises ValueError si no es UUID válido

    def test_persisted_in_db(self):
        if not DB_PATH.exists():
            pytest.skip("DB no disponible.")
        con = sqlite3.connect(str(DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            rows = list(con.execute(
                "SELECT * FROM optimizer_pending_actions WHERE agente_id=? AND estado='TODO' "
                "ORDER BY fecha_calculado DESC LIMIT 3",
                (MIYABI_ID,),
            ))
            assert len(rows) >= 1, "No hay ninguna entrada TODO para Miyabi en optimizer_pending_actions"
            assert rows[0]["score_estimado"] > 0
            assert rows[0]["build_json"] is not None
        finally:
            con.close()

    def test_score_norm_in_range(self, result):
        for b in result.builds:
            assert 0.0 <= b.score_norm <= 1.0, f"Build #{b.rank}: score_norm={b.score_norm} fuera de [0,1]"

    def test_set_bonus_non_negative(self, result):
        for b in result.builds:
            assert b.set_bonus >= 0.0, f"Build #{b.rank}: set_bonus={b.set_bonus} negativo"

    def test_agente_nombre(self, result):
        assert result.agente_nombre == "Miyabi"

    def test_no_protected_build_swaps(self, result):
        if not DB_PATH.exists():
            pytest.skip("DB no disponible.")
        con = sqlite3.connect(str(DB_PATH))
        con.row_factory = sqlite3.Row
        try:
            protected_ids = {
                r["id"] for r in con.execute(
                    "SELECT id FROM agents WHERE protected_build=1"
                )
            }
        finally:
            con.close()
        for b in result.builds:
            for sw in b.swaps_requeridos:
                assert sw["pj_origen_id"] not in protected_ids, (
                    f"Swap propuesto desde PJ protegido id={sw['pj_origen_id']}"
                )
