"""Contrato: los mains que admite un arquetipo son mains que EXISTEN en ese slot.

`stats_vocab.CANONICAL_MAINS_VARIABLE` es la única autoridad de qué main puede tener cada slot
(B1). `disc_archetypes.mains_N` decide cuáles de esos le sirven a cada arquetipo — eso es diseño —,
pero no puede nombrar uno que no existe: una entrada así es letra muerta que ningún disco cumple.

Incidente (2026-09-12, `Dev_IA/.../2026-09-12_DIAG_El_filtro_de_mains_excluye_el_30_por_ciento_de_lo_equipado.md`):
la migración 09 (2026-06-03) separó "Maestría de Anomalía" (flat, slot 4) de "Tasa de Anomalía"
(%, slot 6) en los discos y en `stats_vocab`, y dejó ESCRITO como pendiente corregir los
arquetipos. No se hizo: ANOMALY siguió pidiendo "Maestría de Anomalía" en slot 6, así que para todo
PJ de anomalía el slot 6 solo admitía ATK%, y su disco correcto no sumaba el bono de main. Este
test lo habría atrapado el mismo día.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.core.stats_vocab import CANONICAL_MAINS_VARIABLE

DB = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"


@pytest.fixture(scope="module")
def arquetipos() -> dict[str, dict[int, list[str]]]:
    if not DB.exists():
        pytest.skip("sin DB de dominio")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT code, mains_4, mains_5, mains_6 FROM disc_archetypes").fetchall()
    finally:
        con.close()
    assert rows, "disc_archetypes vacía"
    return {code: {4: json.loads(m4 or "[]"), 5: json.loads(m5 or "[]"), 6: json.loads(m6 or "[]")}
            for code, m4, m5, m6 in rows}


def test_todo_main_de_un_arquetipo_existe_en_su_slot(arquetipos):
    muertos = [
        (code, slot, main)
        for code, por_slot in sorted(arquetipos.items())
        for slot, mains in por_slot.items()
        for main in mains
        if main not in CANONICAL_MAINS_VARIABLE[slot]
    ]
    assert not muertos, (
        f"mains que no existen en su slot según stats_vocab (ningún disco puede cumplirlos): {muertos}"
    )


def test_un_arquetipo_elemental_admite_todos_los_elementos(arquetipos):
    """Qué mains le sirven a un arquetipo es diseño; admitir el bono de daño de CUATRO elementos y
    no del quinto no lo es — es una lista que no siguió al juego. Pasó con Viento: entró con
    Velina y ningún arquetipo lo admitía (su disco de slot 5 no era candidato para ella misma)."""
    bonos = {m for m in CANONICAL_MAINS_VARIABLE[5] if m.startswith("Bono Daño")}
    incompletos = {
        code: sorted(bonos - set(por_slot[5]))
        for code, por_slot in sorted(arquetipos.items())
        if bonos & set(por_slot[5]) and not bonos <= set(por_slot[5])
    }
    assert not incompletos, f"arquetipos con bonos elementales incompletos en slot 5: {incompletos}"
