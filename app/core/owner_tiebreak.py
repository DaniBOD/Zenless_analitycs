"""
Desempate de dueño por CONTEXTO (RF-04 / Fase 5R) — para discos S9/S17.

Cuando el matcher de badges se ABSTIENE por margen chico entre look-alikes (el top-1
y el top-2 quedan visualmente pegados a 60px, p.ej. Velina vs César, Ye Shunguang vs
Zhu Yuan), el badge solo no alcanza para asignar dueño sin riesgo. Este desempate usa
una señal de la DB que CORROBORA al top-1 VISUAL, sin inventar:

  - Señal de BUILD: el set del disco coincide con el set firma (4pc/2pc) del top-1 en
    la DB, y NO con el del top-2. Como el set distingue únicamente al top-1 entre los
    dos candidatos que el matcher ya rankeó arriba, se confirma el top-1.

Reglas RNF-02 (cero asignaciones MAL):
  - Solo CONFIRMA el top-1 visual; NUNCA promueve el top-2 por encima del top-1, ni
    asigna un PJ que el matcher no haya rankeado #1.
  - Solo dispara con corroboración EXCLUSIVA (top-1 corre el set, top-2 no). Si ambos
    (o ninguno) corren el set → abstención.
  - Si el set del disco no resuelve a un id → abstención.

LIMITACIÓN conocida (validada 2026-06-23): no rescata PJs recién onboardeados sin build
(Velina/Pyrois) ni sets filler compartidos por muchos PJs (Monarca del Pináculo). Esos
casos se resuelven capturando al PJ en S17 (badge más grande + detail-badge). Sirve para
el GRUESO del inventario = PJs establecidos con set firma.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from app.core.stats_vocab import _norm_key

if TYPE_CHECKING:
    from app.core.parser_disc_s17 import DiscParsed

log = logging.getLogger(__name__)


class OwnerTiebreaker:
    """Confirma el top-1 visual de un badge ambiguo usando el build (set firma) de la DB.

    `resolve_set_id`: callable `(DiscParsed) -> int | None` que resuelve el set del disco
    a su id (se reusa `DiscSyncer._resolve_set_id`, con su fuzzy sin acentos + difflib).
    """

    def __init__(self, db_path: Path | str, resolve_set_id: Callable[["DiscParsed"], int | None]):
        self._resolve_set_id = resolve_set_id
        # build_map: nombre_normalizado -> {set_id, ...}  (4pc + 2pc, no-NULL)
        self._build_map: dict[str, set[int]] = {}
        self._load_build_map(Path(db_path))

    def _load_build_map(self, db_path: Path) -> None:
        try:
            con = sqlite3.connect(str(db_path))
            con.row_factory = sqlite3.Row
            try:
                for r in con.execute("SELECT nombre, set_4p_id, set_2p_id FROM agents"):
                    sets = {r["set_4p_id"], r["set_2p_id"]} - {None}
                    if not sets:
                        continue
                    key = _norm_key(r["nombre"] or "")
                    if key:
                        self._build_map[key] = {int(s) for s in sets}
            finally:
                con.close()
        except Exception:
            log.exception("[owner_tiebreak] no se pudo cargar el build_map")

    def resolve(self, disc: "DiscParsed", top: list[tuple[str, float]]) -> tuple[str, str] | None:
        """Devuelve (nombre, razon) si el contexto confirma el top-1; si no, None.

        `top`: candidatos del matcher best-first `[(nombre, distancia), ...]` (MatchResult.top).
        """
        if not top or len(top) < 2 or not self._build_map:
            return None
        top1 = top[0][0]
        top2 = top[1][0]
        if not top1 or not top2:
            return None
        set_id = self._resolve_set_id(disc)
        if set_id is None:
            return None
        t1_sets = self._build_map.get(_norm_key(top1), set())
        t2_sets = self._build_map.get(_norm_key(top2), set())
        # Corroboración EXCLUSIVA: el set distingue al top-1 del top-2.
        if set_id in t1_sets and set_id not in t2_sets:
            return top1, "build"
        return None
