"""
Tests del override de path de DB (`DANIBOD_DB_PATH`).

Motivación: el QA del `.exe` necesitaba apuntar la app a la DB del repo para que
el agente pueda leer/verificar la MISMA DB que usa la app (el sandbox bloquea
%LOCALAPPDATA%). Ver Dev_IA 2026-06-06 §4f.
"""
import sqlite3

from app.db import connection


def test_override_gana_sobre_resolucion_default(tmp_path, monkeypatch):
    """Con DANIBOD_DB_PATH seteada, _resolve_db_path devuelve ESE path tal cual."""
    target = tmp_path / "custom" / "mi.db"
    monkeypatch.setenv(connection._DB_PATH_ENV, str(target))

    assert connection._resolve_db_path() == target
    assert connection.get_db_path() == target


def test_override_vacio_se_ignora(tmp_path, monkeypatch):
    """Env var vacía o solo espacios no cuenta como override (cae al default dev)."""
    monkeypatch.setenv(connection._DB_PATH_ENV, "   ")
    # En modo source (no frozen) el default es db/<file> relativo al cwd.
    assert connection._resolve_db_path() == connection.Path("db") / connection._DB_FILENAME


def test_override_expande_tilde(monkeypatch):
    """Un path con ~ se expande al home del usuario."""
    monkeypatch.setenv(connection._DB_PATH_ENV, "~/zzz_qa.db")
    resolved = connection._resolve_db_path()
    assert "~" not in str(resolved)
    assert resolved.name == "zzz_qa.db"


def test_is_readonly_reconoce_valores(monkeypatch):
    """is_readonly() True salvo var ausente o negación explícita."""
    monkeypatch.delenv(connection._READONLY_ENV, raising=False)
    assert connection.is_readonly() is False
    for off in ("", "0", "false", "no", "off", "  "):
        monkeypatch.setenv(connection._READONLY_ENV, off)
        assert connection.is_readonly() is False, off
    for on in ("1", "true", "yes", "si"):
        monkeypatch.setenv(connection._READONLY_ENV, on)
        assert connection.is_readonly() is True, on


def test_get_connection_abre_la_db_del_override(tmp_path, monkeypatch):
    """get_connection() respeta el override y abre esa DB (extremo a extremo)."""
    target = tmp_path / "qa.db"
    # Crear una DB real mínima para que exista.
    seed = sqlite3.connect(str(target))
    seed.execute("CREATE TABLE marca (id INTEGER PRIMARY KEY)")
    seed.execute("INSERT INTO marca (id) VALUES (42)")
    seed.commit()
    seed.close()

    monkeypatch.setenv(connection._DB_PATH_ENV, str(target))
    con = connection.get_connection()
    try:
        row = con.execute("SELECT id FROM marca").fetchone()
        assert row["id"] == 42
        # foreign_keys debe quedar ON como en el resto del código.
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        con.close()
