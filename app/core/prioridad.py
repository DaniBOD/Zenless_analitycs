"""Escribir la prioridad de buildeo que Daniel declara en la app (mig 42) — sin Qt.

La pantalla (Roster en modo edición, modal de PJ) llama a `EditorPrioridades.guardar` en cada
click. Es una escritura al dominio y lleva la ceremonia del proyecto (RNF-01), la misma de
`roster_declaration.declarar`: gate `is_readonly()`, backup previo, transacción, los dos PRAGMA.

**Un backup por sesión de edición, no por click.** Declarar ~15 prioridades de una sentada con un
backup por click dejaría 15 copias de la DB de ~700 KB; el estado previo que importa es el de
ANTES de empezar a editar. Cada click sigue siendo su propia transacción con sus PRAGMA. Una
sesión nueva (otra instancia del editor) hace su propio backup.

Después de cada commit se avisa a los `AgentRepo` del proceso (`prioridades_cambiaron`): si no, el
motor seguía con la prioridad vieja hasta reiniciar, y la pantalla diría "sugerencias
recalculadas" sin que fuera cierto.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.db.repositories import PRIORIDADES, PrioridadRepo, prioridades_cambiaron

log = logging.getLogger(__name__)


@dataclass
class ResultadoPrioridad:
    escribio: bool = False
    motivo_no_escribio: str | None = None
    backup: Path | None = None


class EditorPrioridades:
    """Una sesión de edición de prioridades. `db_path=None` = la DB activa de la app."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = Path(db_path) if db_path else None
        self.backup: Path | None = None

    def guardar(self, agente_id: int, prioridad: str, nombre: str | None = None) -> ResultadoPrioridad:
        res = ResultadoPrioridad()
        if prioridad not in PRIORIDADES:
            raise ValueError(f"prioridad desconocida: {prioridad!r} (válidas: {PRIORIDADES})")

        from app.db.connection import get_db_path, is_readonly, respaldar_db
        if is_readonly():
            res.motivo_no_escribio = "la app está en modo solo lectura (DANIBOD_READONLY)"
            log.info("[prioridad] readonly: no se guarda %s → %s", nombre or agente_id, prioridad)
            return res
        destino = self._db_path or get_db_path()
        if not destino.exists():
            res.motivo_no_escribio = f"no existe la DB de dominio ({destino})"
            log.warning("[prioridad] %s", res.motivo_no_escribio)
            return res

        if self.backup is None:
            self.backup = respaldar_db(destino, "preprioridad")
        res.backup = self.backup

        con = sqlite3.connect(destino, isolation_level=None)
        # Con la FK activa, un PJ inexistente falla ANTES del commit (rollback), en vez de quedar
        # escrito y recién aparecer en el `foreign_key_check` de después.
        con.execute("PRAGMA foreign_keys = ON")
        try:
            con.execute("BEGIN")
            PrioridadRepo(con).guardar(agente_id, prioridad)
            con.execute("COMMIT")
            res.escribio = True
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
            if fk or integridad != "ok":
                log.error("[prioridad] validación FALLÓ tras guardar (fk=%s integrity=%s). Backup: %s",
                          fk, integridad, self.backup)
        except sqlite3.Error:
            con.execute("ROLLBACK")
            log.exception("[prioridad] falló guardar %s → %s — restaurá con %s",
                          nombre or agente_id, prioridad, self.backup)
            raise
        finally:
            con.close()

        prioridades_cambiaron()
        log.info("[prioridad] %s → %s", nombre or f"PJ {agente_id}", prioridad)
        return res
