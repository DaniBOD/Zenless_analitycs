"""
Conexión SQLite con foreign_keys ON y row_factory por defecto.
"""
import sqlite3
from pathlib import Path

_DEFAULT_DB = Path("db/danibod_zzz_v2.db")


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _DEFAULT_DB
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con
