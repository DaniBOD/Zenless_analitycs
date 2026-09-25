"""Registrar en la DB un movimiento de disco que se hizo en el juego (mig 44) — sin Qt.

Daniel aplica sugerencias del motor en el juego y pide que la DB lo refleje con trazabilidad. Un
movimiento es "este disco pasa a este PJ": el disco ocupa su slot en el destino, el que estaba ahí
queda LIBRE (el juego no recuerda quién lo llevaba: invariante del 2026-07-22, el desplazado pierde
equipado Y dueño), y el origen, si lo tenía otro PJ, queda con ese slot vacío hasta que se registre
su reposición (otro movimiento de la misma tanda).

Escritura al dominio con la ceremonia RNF-01 de los otros editores: gate `is_readonly()`, un
backup por tanda, UNA transacción para toda la tanda (se aplica entera o nada), FK activas, los
dos PRAGMA, y el aviso a los `AgentRepo` (los discos equipados deciden el build objetivo, R19).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.db.repositories import agentes_cambiaron

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Movimiento:
    disc_id: int
    hacia_agente_id: int
    referencia: str | None = None


@dataclass
class ResultadoMovimientos:
    escribio: bool = False
    motivo_no_escribio: str | None = None
    backup: Path | None = None
    lote: str | None = None
    filas: list[tuple] = field(default_factory=list)   # (disc_id, slot, desde, hacia, motivo)


def aplicar(con: sqlite3.Connection, movimientos: list[Movimiento], lote: str,
            fuente: str) -> list[tuple]:
    """Aplica la tanda DENTRO de la transacción de quien llama. Devuelve lo registrado.

    Falla (ValueError) si un disco no existe, está descartado o si dos movimientos de la tanda
    ocupan el mismo slot del mismo PJ: la tanda no queda a medias porque es una transacción."""
    filas: list[tuple] = []
    ocupados: set[tuple[int, int]] = set()
    for m in movimientos:
        r = con.execute("SELECT slot, agente_asignado, equipado, descartado FROM inventory_discs "
                        "WHERE id = ?", (m.disc_id,)).fetchone()
        if r is None:
            raise ValueError(f"no existe el disco #{m.disc_id}")
        slot, dueno, equipado, descartado = r
        if descartado:
            raise ValueError(f"el disco #{m.disc_id} está descartado")
        if (m.hacia_agente_id, slot) in ocupados:
            raise ValueError(f"dos movimientos al slot {slot} del PJ {m.hacia_agente_id}")
        ocupados.add((m.hacia_agente_id, slot))
        desde = dueno if equipado else None
        if desde == m.hacia_agente_id:
            continue                                   # ya lo lleva: nada que registrar
        for (viejo,) in con.execute(
                "SELECT id FROM inventory_discs WHERE agente_asignado = ? AND slot = ? "
                "AND equipado = 1 AND id <> ?", (m.hacia_agente_id, slot, m.disc_id)).fetchall():
            con.execute("UPDATE inventory_discs SET equipado = 0, agente_asignado = NULL WHERE id = ?",
                        (viejo,))
            con.execute("INSERT INTO movimientos_discos (lote, disc_id, slot, desde_agente_id, "
                        "hacia_agente_id, motivo, fuente, referencia) VALUES (?, ?, ?, ?, NULL, "
                        "'desplazado', ?, ?)", (lote, viejo, slot, m.hacia_agente_id, fuente, m.referencia))
            filas.append((viejo, slot, m.hacia_agente_id, None, "desplazado"))
        con.execute("UPDATE inventory_discs SET equipado = 1, agente_asignado = ? WHERE id = ?",
                    (m.hacia_agente_id, m.disc_id))
        con.execute("INSERT INTO movimientos_discos (lote, disc_id, slot, desde_agente_id, "
                    "hacia_agente_id, motivo, fuente, referencia) VALUES (?, ?, ?, ?, ?, 'equipa', ?, ?)",
                    (lote, m.disc_id, slot, desde, m.hacia_agente_id, fuente, m.referencia))
        filas.append((m.disc_id, slot, desde, m.hacia_agente_id, "equipa"))
    return filas


class EditorMovimientos:
    """`db_path=None` = la DB activa de la app."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = Path(db_path) if db_path else None

    def registrar(self, movimientos: list[Movimiento], fuente: str = "declarado_usuario") -> ResultadoMovimientos:
        res = ResultadoMovimientos()
        from app.db.connection import get_db_path, is_readonly, respaldar_db
        if is_readonly():
            res.motivo_no_escribio = "la app está en modo solo lectura (DANIBOD_READONLY)"
            log.info("[movimientos] readonly: no se registran %d", len(movimientos))
            return res
        destino = self._db_path or get_db_path()
        if not destino.exists():
            res.motivo_no_escribio = f"no existe la DB de dominio ({destino})"
            return res
        res.lote = datetime.now().isoformat(timespec="seconds")   # noqa: DTZ005 — local
        res.backup = respaldar_db(destino, "premovimientos")
        con = sqlite3.connect(destino, isolation_level=None)
        con.execute("PRAGMA foreign_keys = ON")
        try:
            con.execute("BEGIN")
            res.filas = aplicar(con, movimientos, res.lote, fuente)
            if con.execute("PRAGMA foreign_key_check").fetchall():
                raise sqlite3.IntegrityError("FK rotas tras los movimientos")
            con.execute("COMMIT")
            res.escribio = True
        except BaseException:
            con.execute("ROLLBACK")
            log.exception("[movimientos] falló la tanda — no se escribió nada (backup %s)", res.backup)
            raise
        finally:
            integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
            con.close()
        if integridad != "ok":
            log.error("[movimientos] integrity_check: %s — backup %s", integridad, res.backup)
        agentes_cambiaron()
        for disc, slot, desde, hacia, motivo in res.filas:
            log.info("[movimientos] #%s slot %s: %s → %s (%s)", disc, slot, desde, hacia, motivo)
        return res
