"""Tests unitarios — stats_vocab.py (Hito 2.0.2)."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.stats_vocab import (
    ALIASES,
    ALL_CANONICAL,
    normalize_stat_name,
    parse_value,
    is_valid_main_for_slot,
)

DB_PATH = Path("db/danibod_zzz_v2.db")


# ---------------------------------------------------------------------------
# normalize_stat_name
# ---------------------------------------------------------------------------
class TestNormalizeStatName:
    def test_canonical_passthrough(self):
        for s in ("HP", "ATK%", "Prob. Crítica", "Daño Crítico", "Maestría de Anomalía"):
            assert normalize_stat_name(s) == s

    def test_alias_resolution(self):
        assert normalize_stat_name("PV") == "HP"
        assert normalize_stat_name("Ataque") == "ATK"
        assert normalize_stat_name("Defensa") == "DEF"
        assert normalize_stat_name("Ataque%") == "ATK%"
        assert normalize_stat_name("Ataque %") == "ATK%"
        assert normalize_stat_name("Defensa%") == "DEF%"
        assert normalize_stat_name("Defensa %") == "DEF%"
        assert normalize_stat_name("PV%") == "HP%"
        assert normalize_stat_name("PV %") == "HP%"
        assert normalize_stat_name("Prob Crítico") == "Prob. Crítica"
        assert normalize_stat_name("Maestría Anomalía") == "Maestría de Anomalía"
        # Tasa de Anomalía (Anomaly Mastery %) es una stat DISTINTA de Maestría
        # de Anomalía (flat) — corregido 2026-06-02 contra capturas reales.
        assert normalize_stat_name("Tasa Anomalía") == "Tasa de Anomalía"
        assert normalize_stat_name("Tasa de Anomalía") == "Tasa de Anomalía"
        # Insensible a acentos/mayúsculas (robustez OCR)
        assert normalize_stat_name("Dano Critico") == "Daño Crítico"
        assert normalize_stat_name("maestria de anomalia") == "Maestría de Anomalía"
        assert normalize_stat_name("Bono Daño Glacial") == "Bono Daño Hielo"
        assert normalize_stat_name("Bono Daño Ígneo") == "Bono Daño Fuego"
        assert normalize_stat_name("Rec Energía") == "Recarga de Energía"
        assert normalize_stat_name("Recuperación Energía") == "Recarga de Energía"
        assert normalize_stat_name("Tasa Perforación") == "Tasa de Perforación"

    def test_none_input(self):
        assert normalize_stat_name(None) is None

    def test_empty_string(self):
        assert normalize_stat_name("") is None

    def test_truly_unknown(self):
        assert normalize_stat_name("Fuerza Mística") is None


# ---------------------------------------------------------------------------
# parse_value
# ---------------------------------------------------------------------------
class TestParseValue:
    def test_percentage_string(self):
        assert parse_value("7.2%") == (7.2, "%")
        assert parse_value("24%") == (24.0, "%")

    def test_flat_float(self):
        assert parse_value(38.0) == (38.0, "flat")
        assert parse_value(0) == (0.0, "flat")

    def test_flat_string(self):
        assert parse_value("38") == (38.0, "flat")

    def test_none(self):
        assert parse_value(None) is None


# ---------------------------------------------------------------------------
# is_valid_main_for_slot
# ---------------------------------------------------------------------------
class TestIsValidMainForSlot:
    def test_fixed_slots(self):
        assert is_valid_main_for_slot(1, "HP") is True
        assert is_valid_main_for_slot(1, "ATK") is False
        assert is_valid_main_for_slot(2, "ATK") is True
        assert is_valid_main_for_slot(3, "DEF") is True
        assert is_valid_main_for_slot(3, "HP") is False

    def test_fixed_slot_via_alias(self):
        assert is_valid_main_for_slot(1, "PV") is True
        assert is_valid_main_for_slot(2, "Ataque") is True
        assert is_valid_main_for_slot(3, "Defensa") is True

    def test_slot4_valid(self):
        assert is_valid_main_for_slot(4, "Prob. Crítica") is True
        assert is_valid_main_for_slot(4, "Daño Crítico") is True
        assert is_valid_main_for_slot(4, "Maestría de Anomalía") is True
        assert is_valid_main_for_slot(4, "ATK%") is True
        assert is_valid_main_for_slot(4, "Tasa de Perforación") is True

    def test_slot4_invalid(self):
        assert is_valid_main_for_slot(4, "Bono Daño Físico") is False

    def test_slot5_valid(self):
        assert is_valid_main_for_slot(5, "Bono Daño Físico") is True
        assert is_valid_main_for_slot(5, "Bono Daño Hielo") is True
        assert is_valid_main_for_slot(5, "ATK%") is True

    def test_slot5_via_alias(self):
        assert is_valid_main_for_slot(5, "Bono Daño Glacial") is True
        assert is_valid_main_for_slot(5, "Bono Daño Ígneo") is True

    def test_slot6_valid(self):
        assert is_valid_main_for_slot(6, "HP%") is True
        # Slot VI lleva la variante % ("Tasa de Anomalía"), no la flat "Maestría".
        assert is_valid_main_for_slot(6, "Tasa de Anomalía") is True
        assert is_valid_main_for_slot(6, "Tasa Anomalía") is True   # alias OCR
        assert is_valid_main_for_slot(6, "Recarga de Energía") is True
        assert is_valid_main_for_slot(6, "Impacto") is True

    def test_slot6_invalid(self):
        # "Maestría de Anomalía" (flat) es main de slot IV, NO de slot VI.
        assert is_valid_main_for_slot(6, "Maestría de Anomalía") is False
        # Bono Daño solo es válido en slot 5
        assert is_valid_main_for_slot(6, "Bono Daño Fuego") is False
        # Prob. Crítica solo es válida en slot 4
        assert is_valid_main_for_slot(6, "Prob. Crítica") is False


# ---------------------------------------------------------------------------
# Test de cobertura total contra los 334 discos de la DB
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not DB_PATH.exists(), reason="DB no disponible")
def test_zero_unknowns_in_db():
    """Ningún stat en la DB debe quedar sin mapear a un canónico."""
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    rows = list(con.execute("SELECT * FROM inventory_discs"))
    con.close()

    unknowns = []
    for r in rows:
        for field in ("main_stat", "sub1", "sub2", "sub3", "sub4"):
            v = r[field]
            if v:
                canon = normalize_stat_name(v.strip())
                if canon is None:
                    unknowns.append((r["id"], field, v))

    assert unknowns == [], (
        f"{len(unknowns)} stats sin mapear:\n"
        + "\n".join(f"  id={rid} {field}={val}" for rid, field, val in unknowns[:20])
    )
