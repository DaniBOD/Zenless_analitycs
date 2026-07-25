"""Resolución de la carpeta `audit/` para artefactos escritos en RUNTIME.

Espejo de `app/db/connection.py::_resolve_db_path`, y por el mismo motivo: hoy el único
precedente de escritura a `audit/` desde la app (`monitor._dump_s23_fallo`) usa `Path("audit")`
relativo al CWD. En desarrollo eso funciona porque se lanza desde la raíz del repo, pero en el
`.exe` el CWD es el del acceso directo — el archivo cae en cualquier parte, o no cae.

Prioridad:

1. `DANIBOD_AUDIT_DIR` — gana sobre todo (también lo usan los tests).
2. Empaquetado (`sys.frozen`) → `%LOCALAPPDATA%/DaniBOD_ZZZ_Analytics/audit`, junto a la DB de
   usuario y al `app.log`.
3. Desarrollo → el `audit/` del repo, que es donde ya viven los reportes versionados.

NO escribe nada: solo resuelve. Crear la carpeta es del que escribe.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIRNAME = "DaniBOD_ZZZ_Analytics"
_AUDIT_DIRNAME = "audit"


def _user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / _APP_DIRNAME


def resolve_audit_dir() -> Path:
    """Carpeta donde dejar artefactos de runtime (bitácoras, dumps de diagnóstico)."""
    override = os.environ.get("DANIBOD_AUDIT_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return _user_data_dir() / _AUDIT_DIRNAME
    return Path(_AUDIT_DIRNAME)
