"""Escribir el build objetivo que Daniel declara para un PJ (mig 43) — sin Qt.

La ficha del PJ (selector del build, brief `BRIEF_build_objetivo.md`) llamará a
`EditorBuildObjetivo.guardar` / `.borrar` en cada elección. Es una escritura al dominio y lleva la
ceremonia del proyecto (RNF-01), la misma de `app.core.prioridad`: gate `is_readonly()`, un backup
por sesión de edición, una transacción por cambio con FK activas, y los dos PRAGMA.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.db.repositories import BuildObjetivoRepo

log = logging.getLogger(__name__)


@dataclass
class ResultadoBuild:
    escribio: bool = False
    motivo_no_escribio: str | None = None
    backup: Path | None = None


class EditorBuildObjetivo:
    """Una sesión de edición de builds objetivo. `db_path=None` = la DB activa de la app."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = Path(db_path) if db_path else None
        self.backup: Path | None = None

    def guardar(self, agente_id: int, set_4p_id: int, set_2p_id: int | None = None,
                nombre: str | None = None) -> ResultadoBuild:
        if set_2p_id is not None and set_2p_id == set_4p_id:
            raise ValueError("el 2pc no puede ser el mismo set que el 4pc")
        return self._escribir(lambda repo: repo.guardar(agente_id, set_4p_id, set_2p_id),
                              f"{nombre or f'PJ {agente_id}'} → 4pc {set_4p_id} + 2pc {set_2p_id}")

    def borrar(self, agente_id: int, nombre: str | None = None) -> ResultadoBuild:
        return self._escribir(lambda repo: repo.borrar(agente_id),
                              f"{nombre or f'PJ {agente_id}'} → automático")

    def _escribir(self, cambio, descripcion: str) -> ResultadoBuild:
        res = ResultadoBuild()
        from app.db.connection import get_db_path, is_readonly, respaldar_db
        if is_readonly():
            res.motivo_no_escribio = "la app está en modo solo lectura (DANIBOD_READONLY)"
            log.info("[build] readonly: no se guarda %s", descripcion)
            return res
        destino = self._db_path or get_db_path()
        if not destino.exists():
            res.motivo_no_escribio = f"no existe la DB de dominio ({destino})"
            log.warning("[build] %s", res.motivo_no_escribio)
            return res

        if self.backup is None:
            self.backup = respaldar_db(destino, "prebuild")
        res.backup = self.backup

        con = sqlite3.connect(destino, isolation_level=None)
        # Con la FK activa, un PJ o un set inexistente falla ANTES del commit (rollback).
        con.execute("PRAGMA foreign_keys = ON")
        try:
            con.execute("BEGIN")
            cambio(BuildObjetivoRepo(con))
            con.execute("COMMIT")
            res.escribio = True
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
            if fk or integridad != "ok":
                log.error("[build] validación FALLÓ tras guardar (fk=%s integrity=%s). Backup: %s",
                          fk, integridad, self.backup)
        except sqlite3.Error:
            con.execute("ROLLBACK")
            log.exception("[build] falló %s — restaurá con %s", descripcion, self.backup)
            raise
        finally:
            con.close()
        log.info("[build] %s", descripcion)
        return res
