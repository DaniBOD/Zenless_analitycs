"""Persistencia de la bitácora de desmontaje: resolución de ruta + escritura atómica.

La bitácora es lo único que el feature deja detrás, y **no toca la DB** (el proyecto está en
read-only). Por eso hay dos cosas que probar: que el archivo caiga donde corresponde también
cuando la app corre empaquetada, y que la DB quede con el mismo sha256 antes y después.

Hoy el único precedente de escritura a `audit/` en runtime (`_dump_s23_fallo`) usa `Path("audit")`
relativo al CWD, que en el `.exe` apunta a donde se lanzó el acceso directo. `resolve_audit_dir()`
es el espejo de `_resolve_db_path`: override por env → `%LOCALAPPDATA%` si está congelado → el
`audit/` del repo en desarrollo.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.core.audit_paths import resolve_audit_dir
from app.core.teardown_batch import TeardownBatch, write_teardown_record


def test_el_override_por_env_gana(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path / "mi_audit"))
    assert resolve_audit_dir() == tmp_path / "mi_audit"


def test_env_vacia_se_ignora(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", "")
    assert resolve_audit_dir().name == "audit"


def test_en_desarrollo_apunta_al_audit_del_repo(monkeypatch):
    monkeypatch.delenv("DANIBOD_AUDIT_DIR", raising=False)
    monkeypatch.setattr("sys.frozen", False, raising=False)
    assert resolve_audit_dir().name == "audit"


def test_congelado_usa_localappdata(tmp_path, monkeypatch):
    """En el `.exe` el CWD es el del acceso directo, así que `Path("audit")` sería impredecible."""
    monkeypatch.delenv("DANIBOD_AUDIT_DIR", raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    d = resolve_audit_dir()
    assert tmp_path in d.parents or d.parent == tmp_path, d
    assert d.name == "audit"


# --- Escritura -------------------------------------------------------------------------------

def _registro(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path))
    from types import SimpleNamespace
    sub = SimpleNamespace(nombre_canon="DEF%", nombre_raw="Defensa", valor=4.8,
                          unidad="%", rolls=0, confianza=1.0)
    disco = SimpleNamespace(set_name_raw="Firmamento llameante", set_name_canon=None, slot=2,
                            nivel=0, rareza="S", main_stat_canon="ATK", main_stat_raw="Ataque",
                            main_valor=79.0, main_unidad="flat", subs=[sub],
                            confianza_global=0.95, notas=[])
    b = TeardownBatch()
    b.ensure_open(ts=0.0)
    b.observe(tildes=frozenset({(0, 0)}), counter=1, scroll=0.1, ts=1.0)
    b.attach((0, 0), disco, set_id=12)
    return b.commit(materiales=[("Disco original", 1)], ts=2.0)


def test_escribe_json_valido_en_la_carpeta_resuelta(tmp_path, monkeypatch):
    reg = _registro(tmp_path, monkeypatch)
    p = write_teardown_record(reg)
    assert p is not None and p.exists()
    assert p.parent == tmp_path / "desmontajes"
    datos = json.loads(p.read_text(encoding="utf-8"))
    assert datos["schema"] == "desmontaje/1"
    assert datos["discos"][0]["set_raw"] == "Firmamento llameante"
    assert datos["discos"][0]["subs"][0]["valor"] == 4.8


def test_no_deja_archivo_temporal(tmp_path, monkeypatch):
    """Escritura atómica: `tmp` + `os.replace`, mismo patrón que `FarmSession._persist`. Un JSON
    a medio escribir sería peor que ninguno."""
    reg = _registro(tmp_path, monkeypatch)
    write_teardown_record(reg)
    assert list((tmp_path / "desmontajes").glob("*.tmp")) == []


def test_dos_tandas_no_se_pisan(tmp_path, monkeypatch):
    reg = _registro(tmp_path, monkeypatch)
    p1 = write_teardown_record(reg)
    p2 = write_teardown_record(reg)
    assert p1 != p2, "dos tandas cayeron en el mismo archivo"
    assert len(list((tmp_path / "desmontajes").glob("*.json"))) == 2


def test_registro_none_no_escribe_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("DANIBOD_AUDIT_DIR", str(tmp_path))
    assert write_teardown_record(None) is None
    assert not (tmp_path / "desmontajes").exists()


def test_la_db_no_se_toca(tmp_path, monkeypatch):
    """RNF-01. El feature es observacional: la bitácora va a un archivo, nunca a la DB."""
    db = Path(__file__).resolve().parents[3] / "db" / "danibod_zzz_v2.db"
    if not db.exists():
        pytest.skip("DB no presente")
    antes = hashlib.sha256(db.read_bytes()).hexdigest()
    write_teardown_record(_registro(tmp_path, monkeypatch))
    assert hashlib.sha256(db.read_bytes()).hexdigest() == antes
