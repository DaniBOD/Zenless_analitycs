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

Resolver NO escribe nada. La excepción es `reservar_rutas`, que sí toca el disco: reservar
un nombre es crearlo (ver `app.core.unique_paths`).
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from datetime import datetime
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


def reservar_rutas(carpeta: Path, etiqueta: str,
                   extensiones: Sequence[str] = ("json",)) -> list[Path]:
    """Reserva un juego de rutas hermanas libres en `carpeta`, y las devuelve en orden.

    Nombre: `<AAAAMMDD_HHMMSS_ffffff>_<etiqueta>.<ext>`, con `_2`, `_3`… si ese está tomado. El
    sello queda para que un humano ubique la corrida en su día; **la unicidad no cuelga de él** —
    el porqué está en `app.core.unique_paths`, que es la autoridad de esto.

    Es la única función de este módulo que toca el disco: reservar es crear.

    **Política de esta carpeta:** si el llamador muere entre la reserva y su `os.replace`, el
    archivo de 0 bytes **se queda**. Es ruido visible, y estrictamente mejor que el modo de falla
    que reemplaza — una tanda de auditoría pisada en silencio. (En los respaldos de DB la decisión
    es la contraria: ver `db.connection.respaldar_db`.)
    """
    from app.core.unique_paths import candidatos_numerados, reservar
    sello = f"{datetime.now():%Y%m%d_%H%M%S_%f}"                            # noqa: DTZ005
    return reservar(candidatos_numerados(carpeta, f"{sello}_{etiqueta}", extensiones))
