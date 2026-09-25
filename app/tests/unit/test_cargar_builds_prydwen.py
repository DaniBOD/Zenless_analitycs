"""El cargador de builds recomendados por PJ (mig 43), sobre la captura REAL de Prydwen.

Daniel, 2026-09-25 (SPEC, casos 12-13): "a Nangong no le sirve Balada porque las 2pc son para daño
crítico; ella es stunner/anómala". La guía lo confirma: ni un crítico en sus substats. Estos tests
fijan que el parser lee lo que la guía dice — incluidas las formas raras (dos 4pc con el mismo
número, dos builds sin rótulo, un 4pc sin 2pc) — y que la carga es RNF-01 sobre una COPIA.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.scripts.cargar_builds_prydwen import (
    AGENTE_POR_SLUG, armar_filas, canon_stat, cargar, niveles, parsear,
)

RAIZ = Path(__file__).resolve().parents[3]
DB_REAL = RAIZ / "db" / "danibod_zzz_v2.db"
CAPTURA = RAIZ / "audit" / "prydwen" / "2026-09-25_captura_prydwen.jsonl"


def _linea(slug: str) -> dict:
    for l in CAPTURA.read_text(encoding="utf-8").splitlines():
        d = json.loads(l)
        if d["u"] == slug:
            return d
    raise KeyError(slug)


@pytest.mark.parametrize("texto, canon", [
    ("CRIT Rate%", "Prob. Crítica"), ("CRIT RATE (Until 80%)", "Prob. Crítica"),
    ("Crit DMG%", "Daño Crítico"), ("ATK%", "ATK%"), ("ATK %", "ATK%"), ("Flat ATK", "ATK"),
    ("PEN", "Perforación"), ("Flat PEN", "Perforación"), ("PEN Ratio%", "Tasa de Perforación"),
    ("PEN Ratio", "Tasa de Perforación"), ("Anomaly Proficiency", "Maestría de Anomalía"),
    ("Anomaly Profiency", "Maestría de Anomalía"), ("Anomaly Mastery", "Tasa de Anomalía"),
    ("Ice DMG%", "Bono Daño Hielo"), ("Physical DMG %", "Bono Daño Físico"),
    ("Energy Regen", "Recarga de Energía"), ("Impact", "Impacto"), ("HP%", "HP%"),
    ("Flat HP", "HP"), ("DEF%", "DEF%"),
])
def test_canon_stat(texto, canon):
    assert canon_stat(texto) == canon


def test_un_rotulo_desconocido_no_se_adivina():
    assert canon_stat("Sheer Force") is None
    niv, desconocidos = niveles("ATK% > Sheer Force")
    assert [s for _, s, _ in niv] == ["ATK%"] and desconocidos == ["Sheer Force"]


def test_niveles_igual_comparte_y_mayor_baja():
    niv, _ = niveles("CRIT RATE (Until 80%) >= CRIT DMG = ATK% > Anomaly Proficiency = ATK = PEN")
    assert [(n, s) for n, s, _ in niv] == [
        (1, "Prob. Crítica"), (2, "Daño Crítico"), (2, "ATK%"),
        (3, "Maestría de Anomalía"), (3, "ATK"), (3, "Perforación")]


def test_niveles_barra_son_dos_del_mismo_nivel():
    niv, _ = niveles("ATK%/Flat ATK (until 3000 ATK) > CRIT Rate = CRIT DMG > PEN")
    assert [(n, s) for n, s, _ in niv] == [
        (1, "ATK%"), (1, "ATK"), (2, "Prob. Crítica"), (2, "Daño Crítico"), (3, "Perforación")]


def test_nangong_yu_la_guia_no_tiene_critico():
    """Caso 13: sus substats son Anomalía > ATK% > PEN > ATK. Ningún crítico en ninguna línea."""
    g = parsear(_linea("nangong-yu"))
    assert g.problemas == []
    assert [(o["set"], o["rango"]) for o in g.sets] == [("Phaethon's Melody", 1), ("Freedom Blues", 1)]
    rec = [gr for gr in g.sets[0]["dos"] if gr["rec"]]
    assert rec == [{"sets": ["Freedom Blues", "Chaos Jazz"], "rec": True}]   # un renglón, dos alternativas
    (v,) = g.variantes
    assert v["variante"] == "única"
    subs, _ = niveles(v["subs"])
    assert [s for _, s, _ in subs] == ["Maestría de Anomalía", "ATK%", "Perforación", "ATK"]
    todos = " ".join(v[k] for k in ("d4", "d5", "d6", "subs"))
    assert "CRIT" not in todos.upper()


def test_ye_shunguang_armonia_umbria_no_esta():
    """Caso 12: Shadow Harmony (Armonía umbría) no aparece ni como 4pc ni como 2pc."""
    g = parsear(_linea("ye-shunguang"))
    nombres = {o["set"] for o in g.sets} | {s for o in g.sets for gr in o["dos"] for s in gr["sets"]}
    assert "Shadow Harmony" not in nombres
    assert g.sets[0]["set"] == "White Water Ballad"
    assert "Puffer Electro" in nombres           # el 2pc que Daniel usa: es de la lista


def test_cesar_dos_builds_sin_rotulo_son_dos_variantes():
    g = parsear(_linea("caesar"))
    assert [v["variante"] for v in g.variantes] == ["variante 1", "variante 2"]
    assert niveles(g.variantes[1]["subs"])[0][0][1] == "Maestría de Anomalía"


def test_sunna_variantes_con_rotulo():
    g = parsear(_linea("sunna"))
    assert [v["variante"] for v in g.variantes] == ["Anomaly Build (for Aria Teams)", "CRIT Build"]


def test_evelyn_4pc_sin_2pc_y_zhao_sin_substats():
    ev = parsear(_linea("evelyn"))
    assert [o["set"] for o in ev.sets] == ["Hormone Punk", "Puffer Electro", "Astral Voice"]
    assert all(o["dos"] == [] for o in ev.sets)
    zh = parsear(_linea("zhao"))
    assert "subs" not in zh.variantes[0] and zh.problemas == []


def test_puntaje_de_la_guia_cuando_da_porcentaje():
    g = parsear(_linea("miyabi"))
    assert [(o["set"], o["puntaje"], o["rango"]) for o in g.sets][:2] == [
        ("Branch & Blade Song", 100.0, None), ("Woodpecker Electro", 95.22, None)]


def test_un_set_o_pj_desconocido_no_entra_y_se_reporta():
    g = parsear({"u": "nangong-yu", "s": "1|Set Inventado (4-PC)|2P|Freedom Blues"})
    f = armar_filas([g, parsear({"u": "nadie", "s": ""})], {"Nangong Yu": 26},
                    {"Freedom Blues": 31}, "2026-09-25")
    assert f.sets_4pc == [] and f.sets_2pc == []
    assert any("4pc desconocido 'Set Inventado'" in p for p in f.problemas)
    assert any(p.startswith("nadie:") for p in f.problemas)


def test_la_captura_cubre_los_52_pjs_de_la_db():
    if not DB_REAL.is_file():
        pytest.skip("sin la DB de dominio")
    con = sqlite3.connect(f"file:{DB_REAL}?mode=ro", uri=True)
    nombres = {r[0] for r in con.execute("SELECT nombre FROM agents")}
    con.close()
    slugs = {json.loads(l)["u"] for l in CAPTURA.read_text(encoding="utf-8").splitlines() if l.strip()}
    assert {AGENTE_POR_SLUG[s] for s in slugs} == nombres


@pytest.fixture
def copia(tmp_path):
    if not DB_REAL.is_file():
        pytest.skip("sin la DB de dominio")
    c = tmp_path / "copia.db"
    shutil.copy(DB_REAL, c)
    return c


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_carga_real_sobre_copia_idempotente_y_sin_tocar_el_dominio(copia):
    antes = _sha(DB_REAL)
    filas, backup = cargar(copia, CAPTURA, "2026-09-25")
    assert filas.problemas == []
    assert backup is not None and backup.is_file()
    con = sqlite3.connect(copia)
    cuenta = lambda: tuple(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                           for t in ("pj_sets_4pc", "pj_sets_2pc", "pj_stats_recomendados"))
    primera = cuenta()
    assert con.execute("SELECT COUNT(DISTINCT agente_id) FROM pj_sets_4pc").fetchone()[0] == 52
    assert primera == (len(filas.sets_4pc), len(filas.sets_2pc), len(filas.stats))
    con.close()
    cargar(copia, CAPTURA, "2026-09-25")                  # la segunda reemplaza, no duplica
    con = sqlite3.connect(copia)
    assert cuenta() == primera
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
    assert _sha(DB_REAL) == antes


def test_la_carga_no_toca_filas_de_otra_fuente(copia):
    con = sqlite3.connect(copia)
    # Shadow Harmony (41) no está en la guía de Nangong Yu (26): la PK (agente, set) no choca.
    con.execute("INSERT INTO pj_sets_4pc (agente_id, set_id, orden, fuente, url, capturado) "
                "VALUES (26, 41, 9, 'game8', 'https://game8', '2026-09-25')")
    con.commit()
    con.close()
    cargar(copia, CAPTURA, "2026-09-25")
    con = sqlite3.connect(copia)
    assert con.execute("SELECT COUNT(*) FROM pj_sets_4pc WHERE fuente = 'game8'").fetchone()[0] == 1
    con.close()


def test_dry_run_no_escribe(copia):
    antes = _sha(copia)
    filas, backup = cargar(copia, CAPTURA, "2026-09-25", dry_run=True)
    assert backup is None and filas.sets_4pc
    assert _sha(copia) == antes
