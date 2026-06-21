"""
Sync RF-04 — stats base de agente capturados en S18 (Atributos base) → DB EN VIVO.

Cuando el monitor produce una lectura S18 madura e identificada, persiste los stats
base en la fila de `agents`. Es la propuesta de valor del hito de captura en vivo:
subís de nivel / cambiás discos → la DB queda al día sola (alimenta el seguimiento
de thresholds y el scoring).

Mirror de `sync_equip.DiscSyncer`:
  - Transacción propia por evento (atómica, rollback ante error), thread-safe (lock).
  - Guard `is_readonly()` → en QA NO toca la DB.
  - Backup de sesión RNF-01: lo hace el controller 1× al arrancar (`_backup_db_session`).

Reglas (RNF-01/02):
  - Identidad CIERTA: persiste solo si `agente_nombre` resuelve a una fila de `agents`
    y no está marcado `nombre_fuera_de_roster`. Si no → abstención (no escribe).
  - Ancla de madurez: requiere PV o Ataque (un frame de transición trae todo None).
  - Update PARCIAL: escribe SOLO los campos LEÍDOS (no-None) que CAMBIARON vs la DB
    (dedup con tolerancia anti-jitter). Un campo que el OCR dropea NO se toca → no
    NULL-ea lo que ya había (p.ej. ER de Pyrois Nv1, que el full-frame pierde).
  - Decisión del usuario (2026-06-21): actualiza a TODOS los PJs, incluso
    `protected_build=1` (los stats varían al mejorar discos → sirve para tracking).

Unidades (clave para no corromper la escala): la DB guarda prob_critico / dano_critico
/ tasa_perforacion como PORCENTAJE (27.8) pero el parser los entrega como FRACCIÓN
(0.278, vía `_normalize_percent`) → se multiplican ×100. `rec_energia` es multiplicador
crudo (1.2), sin conversión. El resto son enteros directos.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from app.core.parser_agent_stats import AgentStatsParsed
from app.db.connection import is_readonly

log = logging.getLogger(__name__)

# (atributo del parser, columna en `agents`, tipo) — tipo: 'int' | 'pct' | 'float'.
#   'pct'   = el parser da fracción → DB guarda porcentaje → ×100.
#   'float' = multiplicador crudo (rec_energia).
# NO se incluyen fuerza_bruta/acumulacion_adrenalina (no hay columna en `agents`;
# son display-only de Disruptivos) ni perforacion plana / bono_dano_elemento (no los
# parsea S18) ni mindscape (no está en AgentStatsParsed).
_STAT_MAP: tuple[tuple[str, str, str], ...] = (
    ("nivel",                "nivel",             "int"),
    ("pv",                   "pv",                "int"),
    ("ataque",               "ataque",            "int"),
    ("defensa",              "defensa",           "int"),
    ("impacto",              "impacto",           "int"),
    ("prob_crit",            "prob_critico",      "pct"),
    ("dano_crit",            "dano_critico",      "pct"),
    ("tasa_anomalia",        "tasa_anomalia",     "int"),
    ("maestria_anomalia",    "maestria_anomalia", "int"),
    ("tasa_perforacion",     "tasa_perforacion",  "pct"),
    ("recuperacion_energia", "rec_energia",       "float"),
)
# Tolerancias del dedup (evitan churn por jitter del OCR; los cambios reales de
# subir nivel / cambiar discos son >> esto).
_PCT_TOL = 0.1
_FLOAT_TOL = 0.01


def _db_value(attr_value: float, kind: str) -> int | float:
    """Convierte el valor del parser a la unidad/tipo de la columna de `agents`."""
    if kind == "int":
        return int(round(attr_value))
    if kind == "pct":
        return round(float(attr_value) * 100.0, 1)
    return round(float(attr_value), 2)


def _tol(kind: str) -> float:
    return 0.0 if kind == "int" else (_PCT_TOL if kind == "pct" else _FLOAT_TOL)


class AgentStatsSyncer:
    """Persiste en vivo los stats base de S18 a la fila de `agents` (RF-04)."""

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._lock = threading.Lock()

    def sync(self, stats: AgentStatsParsed) -> int | None:
        """Persiste los stats base de `stats` en `agents`.

        Devuelve la cantidad de campos actualizados, o None si NO escribió
        (readonly, identidad incierta, agente fuera de la DB, o sin cambios).
        """
        nombre = (stats.agente_nombre or "").strip()
        if not nombre or "nombre_fuera_de_roster" in (stats.notas or []):
            return None
        # Ancla de madurez: un frame de transición trae todo None (RNF-02).
        if stats.pv is None and stats.ataque is None:
            return None
        if is_readonly():
            return None

        with self._lock:
            con = sqlite3.connect(str(self._db_path))
            con.row_factory = sqlite3.Row
            try:
                cols = ", ".join(col for _, col, _ in _STAT_MAP)
                row = con.execute(
                    f"SELECT id, {cols} FROM agents WHERE nombre = ?", (nombre,)
                ).fetchone()
                if row is None:
                    # OCR resolvió a un nombre que no está en `agents` → no inventar.
                    log.debug("[agent_sync] '%s' no esta en agents — sin persistir.", nombre)
                    return None

                updates: dict[str, int | float] = {}
                for attr, col, kind in _STAT_MAP:
                    val = getattr(stats, attr, None)
                    if val is None:
                        continue                       # el OCR no leyó este campo → no tocar
                    new = _db_value(val, kind)
                    cur = row[col]
                    if cur is None or abs(float(new) - float(cur)) > _tol(kind):
                        updates[col] = new
                if not updates:
                    return None                        # nada cambió → no escribir (RNF-06)

                set_clause = ", ".join(f"{c} = ?" for c in updates)
                params = list(updates.values()) + [row["id"]]
                with con:                              # transacción atómica (RNF-01)
                    con.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", params)
                log.info(
                    "[agent_sync] %s (id=%d) ← %d campo(s): %s",
                    nombre, row["id"], len(updates),
                    ", ".join(f"{c}={v}" for c, v in updates.items()),
                )
                return len(updates)
            except Exception:
                log.exception("[agent_sync] error persistiendo stats de '%s'", nombre)
                return None
            finally:
                con.close()
