"""`get_connection(check_same_thread=False)` habilita compartir una conexión de solo-lectura
entre threads (UI + thread del monitor).

Regresión QA farmeo 2026-07-07: al abrir un disco (S3) el monitor (thread aparte) llamaba a
`_build_payload` → repos con la conexión creada en el thread principal → "SQLite objects
created in a thread can only be used in that same thread".
"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from app.db.connection import get_connection


def _make_db(tmp_path):
    p = tmp_path / "t.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE a(x INTEGER)")
    con.execute("INSERT INTO a VALUES (42)")
    con.commit()
    con.close()
    return p


def test_default_connection_falla_cross_thread(tmp_path):
    con = get_connection(_make_db(tmp_path))
    err = {}

    def worker():
        try:
            con.execute("SELECT x FROM a").fetchall()
        except Exception as e:  # noqa: BLE001
            err["e"] = e

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert isinstance(err.get("e"), sqlite3.ProgrammingError), "esperaba el error cross-thread por defecto"


def test_check_same_thread_false_ok_cross_thread(tmp_path):
    con = get_connection(_make_db(tmp_path), check_same_thread=False)
    out = {}

    def worker():
        out["rows"] = con.execute("SELECT x FROM a").fetchall()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert out["rows"][0][0] == 42
