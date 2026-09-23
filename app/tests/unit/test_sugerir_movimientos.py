"""El motor corrido sobre TODO el inventario (etapa 1, paso 7b).

Daniel: "la DB tiene más de 300 discos y si cargo mi roster ya podrías sugerir de un comienzo qué
disco puede ser bueno para mis personajes". Lo que se cuida acá: que sugiera lo que el motor
decide, que las sugerencias no se pisen entre sí, y que NO toque la DB de dominio (B3).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

from app.tests.unit.test_optimizer_build_actual import REAL_DB_PATH, _insert_disc

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "app" / "scripts"))
try:
    import sugerir_movimientos as sm
finally:
    sys.path.pop(0)

_BUENO = [("Prob. Crítica", 7.2, 2), ("Daño Crítico", 14.4, 2), ("ATK%", 6.0, 1), ("Perforación", 9.0, 0)]
_FLOJO = [("HP", 336.0, 2), ("DEF", 45.0, 2), ("ATK", 38.0, 1), ("HP%", 3.0, 0)]


@pytest.fixture
def db(tmp_path):
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    copia = tmp_path / "danibod_zzz_v2.db"
    shutil.copy2(REAL_DB_PATH, copia)
    con = sqlite3.connect(copia)
    con.row_factory = sqlite3.Row
    pj = con.execute(
        "SELECT a.id FROM agents a WHERE a.rol='Ataque' AND NOT EXISTS "
        "(SELECT 1 FROM agent_substat_preferences p WHERE p.agente_id=a.id) ORDER BY a.id LIMIT 1"
    ).fetchone()["id"]
    with con:
        con.execute("DELETE FROM inventory_disc_evaluations")
        con.execute("DELETE FROM optimizer_pending_actions")
        con.execute("DELETE FROM inventory_discs")
        flojo = _insert_disc(con, 1, 48, "HP", 2200.0, _FLOJO, agente=pj, equipado=1)
    con.close()
    return copia, pj, flojo


def _agregar(path, subs, **kw):
    con = sqlite3.connect(path)
    with con:
        i = _insert_disc(con, 1, 48, "HP", 2200.0, subs, **kw)
    con.close()
    return i


def test_un_libre_que_mejora_a_un_pj_se_sugiere_equipar(db):
    path, pj, _ = db
    bueno = _agregar(path, _BUENO, agente=None, equipado=0)
    rep = sm.generar(path)
    eq = rep["sugerencias"].get("equipar", [])
    assert any(s["disc_id"] == bueno and s["destino_id"] == pj for s in eq), eq


def test_dos_libres_para_el_mismo_slot_no_se_pisan(db):
    """Los dos le mejoran el slot 1 al mismo PJ: se toma el mejor y el otro queda EN CONFLICTO,
    no desaparece."""
    path, pj, _ = db
    mejor = _agregar(path, _BUENO, agente=None, equipado=0)
    menos = _agregar(path, [("Prob. Crítica", 4.8, 1), ("ATK%", 3.0, 0), ("Perforación", 9.0, 0),
                            ("ATK", 19.0, 0)], agente=None, equipado=0)
    eq = {s["disc_id"]: s for s in sm.generar(path)["sugerencias"].get("equipar", [])
          if s["destino_id"] == pj and s["slot"] == 1}
    assert mejor in eq and eq[mejor]["conflicto"] is None
    assert menos in eq and eq[menos]["conflicto"] is not None


def test_un_disco_sin_nivel_leido_no_se_sugiere(db):
    """Si el OCR se abstuvo del nivel (B2), no se sabe si está terminado: no se juzga, se cuenta
    aparte. (La DB real no tiene ninguno hoy —0 de 380—, así que sólo este test ejerce la rama.)"""
    path, _, _ = db
    sin_nivel = _agregar(path, _BUENO, agente=None, equipado=0)
    con = sqlite3.connect(path)
    with con:
        con.execute("UPDATE inventory_discs SET nivel = NULL WHERE id = ?", (sin_nivel,))
    con.close()
    rep = sm.generar(path)
    assert rep["totales"]["sin_nivel_leido"] == 1
    assert all(s["disc_id"] != sin_nivel for v in rep["sugerencias"].values() for s in v)


def test_no_toca_la_db_de_dominio(db, tmp_path, monkeypatch):
    path, _, _ = db
    _agregar(path, _BUENO, agente=None, equipado=0)
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "audit"))
    antes = hashlib.sha256(path.read_bytes()).hexdigest()
    assert sm.main(["--db", str(path)]) == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == antes
    md = list((tmp_path / "audit" / "sugerencias").glob("*.md"))
    js = list((tmp_path / "audit" / "sugerencias").glob("*.json"))
    assert len(md) == 1 and len(js) == 1
    assert json.loads(js[0].read_text(encoding="utf-8"))["schema"] == "sugerencias_discos/1"
    assert "Sugerencias del motor de discos" in md[0].read_text(encoding="utf-8")


def test_corre_sobre_la_db_real_sin_romperse(tmp_path):
    """El inventario de verdad (386 discos): no se exige un número de sugerencias, sí que no
    reviente con datos reales —niveles None, sets sin mapear, PJs sin stats— y que cuente todo.

    Sobre una COPIA: la primera versión corría sobre la DB de dominio, y un sabotaje que le sacaba
    el `mode=ro` al script le creó una tabla (2026-09-22; restaurada del commit, sha256 idéntico).
    Que el script sea de sólo lectura es justo lo que un test no puede dar por hecho."""
    if not REAL_DB_PATH.exists():
        pytest.skip("sin DB de dominio")
    copia = tmp_path / "danibod_zzz_v2.db"
    shutil.copy2(REAL_DB_PATH, copia)
    rep = sm.generar(copia)
    t = rep["totales"]
    contados = (t["equipados_sin_cambio"] + t["sin_nivel_leido"]
                + sum(len(v) for v in rep["sugerencias"].values()))
    assert contados == t["inventario_activo"], "algún disco quedó sin clasificar"
