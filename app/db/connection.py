"""
Conexión SQLite con foreign_keys ON y row_factory por defecto.

Resolución de path de la DB (en orden de prioridad):
- Override por env var `DANIBOD_DB_PATH`: si está seteada, se usa ESE path tal
  cual (sin copiar nada). Pensado para QA del `.exe`: apuntar la app a la DB del
  repo (`db/danibod_zzz_v2.db`) para que el agente pueda leer/arreglar/verificar
  la misma DB que usa la app sin pelear con el sandbox de %LOCALAPPDATA%.
- Modo dev (corriendo `python -m app.main`): usa `db/danibod_zzz_v2.db` relativo al cwd.
- Modo .exe (PyInstaller --onedir): copia la DB empaquetada a
  `%LOCALAPPDATA%/DaniBOD_ZZZ_Analytics/db/danibod_zzz_v2.db` en el primer
  arranque, y de ahí en adelante usa esa copia (writable, persistente entre
  ejecuciones, sobrevive a actualizaciones del .exe).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

_APP_DIRNAME = "DaniBOD_ZZZ_Analytics"
_DB_FILENAME = "danibod_zzz_v2.db"
_DB_PATH_ENV = "DANIBOD_DB_PATH"
_READONLY_ENV = "DANIBOD_READONLY"


def is_readonly() -> bool:
    """
    Modo offline/readonly (env `DANIBOD_READONLY`): la app detecta y loguea normal
    pero NO escribe nada persistente (DB ni librería de avatares). Para testear
    hipótesis sin riesgo de corromper datos. True si la var está seteada y no es
    una negación explícita ("", "0", "false", "no").
    """
    v = (os.environ.get(_READONLY_ENV) or "").strip().lower()
    return v not in ("", "0", "false", "no", "off")


def _user_data_dir() -> Path:
    """Directorio writable persistente para datos del usuario (Windows)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / _APP_DIRNAME


def _bundled_db_path() -> Path | None:
    """Path a la DB empaquetada en el bundle PyInstaller, o None si no es bundle."""
    if not getattr(sys, "frozen", False):
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    bundled = Path(meipass) / "db" / _DB_FILENAME
    return bundled if bundled.exists() else None


def _resolve_db_path() -> Path:
    """
    Determina dónde está la DB activa.
    - Override `DANIBOD_DB_PATH`: si está seteada (no vacía), gana sobre todo lo demás.
    - Si está corriendo desde el .exe (PyInstaller): usa %LOCALAPPDATA% writable.
      Copia desde el bundle en primer arranque.
    - Si está corriendo desde source: usa db/<file> relativo al cwd.
    """
    override = os.environ.get(_DB_PATH_ENV)
    if override and override.strip():
        # QA: la app (incluso el .exe) apunta a esta DB tal cual, sin copiar.
        return Path(override.strip()).expanduser()

    bundled = _bundled_db_path()
    if bundled is not None:
        # Estamos en el .exe. Asegurar copia writable.
        user_dir = _user_data_dir() / "db"
        user_dir.mkdir(parents=True, exist_ok=True)
        user_db = user_dir / _DB_FILENAME
        if not user_db.exists():
            shutil.copy2(bundled, user_db)
        return user_db

    # Modo dev: cwd-relative
    return Path("db") / _DB_FILENAME


def get_db_path() -> Path:
    """Devuelve el path actualmente resuelto (sin abrir conexión)."""
    return _resolve_db_path()


def get_connection(db_path: Path | str | None = None, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Abre una conexión SQLite.

    `check_same_thread=False` permite compartir la conexión entre threads (p.ej. una conexión
    de SOLO LECTURA de datos de referencia usada por la UI y por el thread del monitor para
    puntuar/recomendar). SQLite (modo serializado) serializa el acceso; es seguro mientras esa
    conexión no escriba (las escrituras usan su propia conexión, en su propio thread). NO usar
    para conexiones de escritura compartidas (riesgo de corrupción, RNF-01)."""
    path = Path(db_path) if db_path else _resolve_db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"DB no encontrada en {path}. "
            f"Si corres desde source, asegurate de estar en la raíz del repo."
        )
    con = sqlite3.connect(str(path), check_same_thread=check_same_thread)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con
