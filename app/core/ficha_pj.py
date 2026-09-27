"""La ficha del PJ: leer lo que dice la guía y lo que eligió el usuario (SPEC 2026-09-27) — sin Qt.

La pantalla (brief `BRIEF_ficha_sets_y_stats.md`) pinta lo que arma este módulo y guarda por él;
el motor no pasa por acá: lee la mezcla en `AgentRepo` (`app.db.repositories`).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.coherencia import EleccionPJ, GuiaPJ
from app.db.repositories import (AgentRepo, BuildObjetivoRepo, CondicionSet, _tabla_existe,
                                 agentes_cambiaron, principales_de_la_guia)

log = logging.getLogger(__name__)


def leer_guia_pj(con: sqlite3.Connection, agente_id: int) -> GuiaPJ:
    """La guía del PJ (mig 43), con la PRIMERA variante como el motor (`pesos_de_la_guia`)."""
    if not _tabla_existe(con, "pj_stats_recomendados"):
        return GuiaPJ()
    niveles: dict[str, int] = {}
    primera = None
    for variante, nivel, stat in con.execute(
            "SELECT variante, nivel, stat FROM pj_stats_recomendados "
            "WHERE agente_id = ? AND linea = 'substat' ORDER BY rowid", (agente_id,)):
        primera = primera or variante
        if variante == primera:
            niveles[stat] = nivel
    principales = principales_de_la_guia(con.execute(
        "SELECT agente_id, variante, linea, stat FROM pj_stats_recomendados "
        "WHERE agente_id = ? AND linea LIKE 'principal_%' ORDER BY rowid", (agente_id,))).get(agente_id, {})
    sets_4pc = tuple(r[0] for r in con.execute(
        "SELECT set_id FROM pj_sets_4pc WHERE agente_id = ? ORDER BY orden", (agente_id,)))
    dos: dict[int, set[int]] = {}
    for s4, s2 in con.execute("SELECT set_4p_id, set_id FROM pj_sets_2pc WHERE agente_id = ?", (agente_id,)):
        dos.setdefault(s4, set()).add(s2)
    return GuiaPJ(niveles=niveles, principales=principales, sets_4pc=sets_4pc, dos_por_4pc=dos)


def leer_eleccion_pj(con: sqlite3.Connection, agente_id: int) -> EleccionPJ:
    """Sólo lo que el usuario tocó (mig 43 y 46): sin filas, una elección vacía."""
    e = EleccionPJ()
    if _tabla_existe(con, "ajustes_usuario_substats"):
        e.niveles = {s: n for s, n in con.execute(
            "SELECT substat, nivel FROM ajustes_usuario_substats WHERE agente_id = ?", (agente_id,))}
    if _tabla_existe(con, "ajustes_usuario_principales"):
        e.principales = {slot: tuple(sorted(json.loads(v))) for slot, v in con.execute(
            "SELECT slot, valor_json FROM ajustes_usuario_principales WHERE agente_id = ?", (agente_id,))}
    if _tabla_existe(con, "ajustes_usuario_build"):
        fila = con.execute("SELECT set_4p_id, set_2p_id FROM ajustes_usuario_build WHERE agente_id = ?",
                           (agente_id,)).fetchone()
        if fila:
            e.set_4p_id, e.set_2p_id = fila[0], fila[1]
    return e


def leer_condiciones(con: sqlite3.Connection) -> list[CondicionSet]:
    if not _tabla_existe(con, "set_condiciones_4pc"):
        return []
    return [CondicionSet(*r) for r in con.execute(
        "SELECT set_id, tipo, stat, umbral, rol, elemento, alcance, texto FROM set_condiciones_4pc")]


def avisos_de(con: sqlite3.Connection, agent) -> list:
    """Los avisos del asesor para un PJ ya cargado por `AgentRepo` (la mezcla que usa el motor)."""
    from app.core.coherencia import avisos
    sets = {r[0]: r[1] for r in con.execute("SELECT id, nombre FROM disc_sets")}
    return avisos(agent.nombre, leer_guia_pj(con, agent.id), leer_eleccion_pj(con, agent.id),
                  rol=agent.rol, elemento=agent.elemento, set_4p_id=agent.set_4p_id,
                  set_2p_id=agent.set_2p_id, condiciones=leer_condiciones(con),
                  stats=agent.stats, stats_fijos=agent.stats_fijos, sets=sets)


# ---------------------------------------------------------------------------
# Escribir lo que el usuario elige (mig 43 y 46) — la ceremonia de `app.core.build_objetivo`
# ---------------------------------------------------------------------------


#: Los niveles que el usuario elige, como los lee la ficha (0 = "No sirve").
NIVELES = {1: "Imprescindible", 2: "Muy bueno", 3: "Bueno", 4: "Sirve", 0: "No sirve"}
_TABLAS_DEL_USUARIO = ("ajustes_usuario_substats", "ajustes_usuario_principales",
                       "ajustes_usuario_fijos", "ajustes_usuario_build")


@dataclass
class ResultadoFicha:
    escribio: bool = False
    motivo_no_escribio: str | None = None
    backup: Path | None = None


class EditorFichaPJ:
    """Una sesión de edición de la ficha. `db_path=None` = la DB activa de la app.

    Cada operación con valor `None` vuelve a la guía (borra el ajuste). Las reglas de los valores
    (substat conocido, nivel 0-4, slot 4-6, stat de fijo) las hace cumplir la DB con sus CHECK:
    un valor inválido levanta `sqlite3.IntegrityError` y no queda nada escrito."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = Path(db_path) if db_path else None
        self.backup: Path | None = None

    # --- substats ---
    def nivel_substat(self, agente_id: int, substat: str, nivel: int | None) -> ResultadoFicha:
        if nivel is None:
            return self._escribir(lambda c: c.execute(
                "DELETE FROM ajustes_usuario_substats WHERE agente_id = ? AND substat = ?",
                (agente_id, substat)), f"PJ {agente_id} · {substat} → guía")
        return self._escribir(lambda c: c.execute(
            "INSERT INTO ajustes_usuario_substats (agente_id, substat, nivel) VALUES (?, ?, ?) "
            "ON CONFLICT (agente_id, substat) DO UPDATE SET nivel = excluded.nivel, "
            "actualizado = CURRENT_TIMESTAMP", (agente_id, substat, nivel)),
            f"PJ {agente_id} · {substat} → {NIVELES.get(nivel, nivel)}")

    # --- principales ---
    def principales(self, agente_id: int, slot: int, stats: "list[str] | None") -> ResultadoFicha:
        if stats is None:
            return self._escribir(lambda c: c.execute(
                "DELETE FROM ajustes_usuario_principales WHERE agente_id = ? AND slot = ?",
                (agente_id, slot)), f"PJ {agente_id} · slot {slot} → guía")
        if not stats:
            raise ValueError("una lista vacía de principales no restringiría nada: usá None (guía)")
        valor = json.dumps(sorted(stats), ensure_ascii=False)
        return self._escribir(lambda c: c.execute(
            "INSERT INTO ajustes_usuario_principales (agente_id, slot, valor_json) VALUES (?, ?, ?) "
            "ON CONFLICT (agente_id, slot) DO UPDATE SET valor_json = excluded.valor_json, "
            "actualizado = CURRENT_TIMESTAMP", (agente_id, slot, valor)),
            f"PJ {agente_id} · slot {slot} → {valor}")

    # --- stats fijos ---
    def fijo(self, agente_id: int, stat: str, objetivo: float) -> ResultadoFicha:
        return self._fijo(agente_id, stat, objetivo, f"PJ {agente_id} · fijo {stat} → {objetivo:g}")

    def desactivar_fijo(self, agente_id: int, stat: str) -> ResultadoFicha:
        return self._fijo(agente_id, stat, None, f"PJ {agente_id} · fijo {stat} → desactivado")

    def fijo_de_la_guia(self, agente_id: int, stat: str) -> ResultadoFicha:
        return self._escribir(lambda c: c.execute(
            "DELETE FROM ajustes_usuario_fijos WHERE agente_id = ? AND stat = ?", (agente_id, stat)),
            f"PJ {agente_id} · fijo {stat} → guía")

    def _fijo(self, agente_id, stat, objetivo, descripcion):
        return self._escribir(lambda c: c.execute(
            "INSERT INTO ajustes_usuario_fijos (agente_id, stat, objetivo) VALUES (?, ?, ?) "
            "ON CONFLICT (agente_id, stat) DO UPDATE SET objetivo = excluded.objetivo, "
            "actualizado = CURRENT_TIMESTAMP", (agente_id, stat, objetivo)), descripcion)

    # --- sets ---
    def build(self, agente_id: int, set_4p_id: int | None, set_2p_id: int | None = None) -> ResultadoFicha:
        if set_4p_id is None:
            return self._escribir(lambda c: BuildObjetivoRepo(c).borrar(agente_id),
                                  f"PJ {agente_id} · build → automático")
        if set_2p_id is not None and set_2p_id == set_4p_id:
            raise ValueError("el 2pc no puede ser el mismo set que el 4pc")
        return self._escribir(lambda c: BuildObjetivoRepo(c).guardar(agente_id, set_4p_id, set_2p_id),
                              f"PJ {agente_id} · build → 4pc {set_4p_id} + 2pc {set_2p_id}")

    # --- todo ---
    def volver_a_la_guia(self, agente_id: int) -> ResultadoFicha:
        """Borra TODOS los ajustes de la ficha de un PJ (substats, principales, fijos y build)."""
        def borrar(c):
            for t in _TABLAS_DEL_USUARIO:
                if _tabla_existe(c, t):
                    c.execute(f"DELETE FROM {t} WHERE agente_id = ?", (agente_id,))
        return self._escribir(borrar, f"PJ {agente_id} → todo a la guía")

    def _escribir(self, cambio, descripcion: str) -> ResultadoFicha:
        res = ResultadoFicha()
        from app.db.connection import get_db_path, is_readonly, respaldar_db
        if is_readonly():
            res.motivo_no_escribio = "la app está en modo solo lectura (DANIBOD_READONLY)"
            log.info("[ficha] readonly: no se guarda %s", descripcion)
            return res
        destino = self._db_path or get_db_path()
        if not destino.exists():
            res.motivo_no_escribio = f"no existe la DB de dominio ({destino})"
            log.warning("[ficha] %s", res.motivo_no_escribio)
            return res
        if self.backup is None:
            self.backup = respaldar_db(destino, "preficha")
        res.backup = self.backup

        con = sqlite3.connect(destino, isolation_level=None)
        # Con la FK activa, un PJ o un set inexistente falla ANTES del commit (rollback).
        con.execute("PRAGMA foreign_keys = ON")
        try:
            con.execute("BEGIN")
            cambio(con)
            con.execute("COMMIT")
            res.escribio = True
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
            if fk or integridad != "ok":
                log.error("[ficha] validación FALLÓ tras guardar (fk=%s integrity=%s). Backup: %s",
                          fk, integridad, self.backup)
        except sqlite3.Error:
            con.execute("ROLLBACK")
            log.exception("[ficha] falló %s — restaurá con %s", descripcion, self.backup)
            raise
        finally:
            con.close()
        agentes_cambiaron()         # el motor ve el cambio sin reiniciar
        log.info("[ficha] %s", descripcion)
        return res


# ---------------------------------------------------------------------------
# La foto que pinta la ficha
# ---------------------------------------------------------------------------

@dataclass
class FotoFicha:
    """Todo lo que la sección de la ficha necesita, sin consultar nada más."""
    agente_id: int
    nombre: str
    guia: GuiaPJ
    eleccion: EleccionPJ
    #: Lo que USA el motor, como NIVELES (nunca como pesos): substat → 0..4.
    niveles: dict[str, int] = field(default_factory=dict)
    principales: dict[int, tuple[str, ...]] = field(default_factory=dict)
    fijos: dict[str, float] = field(default_factory=dict)
    set_4p_id: int | None = None
    set_2p_id: int | None = None
    origen_build: str | None = None
    avisos: list = field(default_factory=list)


def foto(con: sqlite3.Connection, agente_id: int) -> FotoFicha:
    """La ficha de un PJ. El nivel que se muestra es el del usuario si lo eligió; si no, el de la
    guía; si la guía no lo nombra, "No sirve" (0): la misma regla con la que el motor arma los pesos."""
    agentes_cambiaron()
    agent = AgentRepo(con).get_by_id(agente_id)
    if agent is None:
        raise KeyError(f"no existe el PJ {agente_id}")
    guia, eleccion = leer_guia_pj(con, agente_id), leer_eleccion_pj(con, agente_id)
    from app.core.stats_vocab import CANONICAL_SUBSTATS
    niveles = {s: eleccion.niveles.get(s, guia.niveles.get(s, 0)) for s in sorted(CANONICAL_SUBSTATS)}
    return FotoFicha(agente_id=agent.id, nombre=agent.nombre, guia=guia, eleccion=eleccion,
                     niveles=niveles, principales=dict(agent.mains), fijos=dict(agent.stats_fijos),
                     set_4p_id=agent.set_4p_id, set_2p_id=agent.set_2p_id,
                     origen_build=agent.origen_build, avisos=avisos_de(con, agent))
