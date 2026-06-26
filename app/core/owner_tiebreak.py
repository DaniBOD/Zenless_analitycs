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
        # equip_index: (set_id, slot, main_norm) -> {nombre_normalizado, ...} — qué PJs
        # tienen YA un disco con ese fingerprint asignado en inventory_discs. Señal más
        # potente que el build (incluye filler reales, no solo el set firma). Para slots
        # 1/2/3 el main es fijo por slot (HP/ATK/DEF) → fingerprint preciso; para 4-6 solo
        # matchea si el string del main coincide normalizado (si no, no dispara → seguro).
        self._equip_index: dict[tuple[int, int, str], set[str]] = {}
        self._load_maps(Path(db_path))

    def _load_maps(self, db_path: Path) -> None:
        try:
            con = sqlite3.connect(str(db_path))
            con.row_factory = sqlite3.Row
            try:
                id_to_name: dict[int, str] = {}
                for r in con.execute("SELECT id, nombre, set_4p_id, set_2p_id FROM agents"):
                    key = _norm_key(r["nombre"] or "")
                    if key:
                        id_to_name[r["id"]] = key
                    sets = {r["set_4p_id"], r["set_2p_id"]} - {None}
                    if sets and key:
                        self._build_map[key] = {int(s) for s in sets}
                for r in con.execute(
                    "SELECT set_id, slot, main_stat, agente_asignado FROM inventory_discs "
                    "WHERE agente_asignado IS NOT NULL AND set_id IS NOT NULL AND slot IS NOT NULL"
                ):
                    owner = id_to_name.get(r["agente_asignado"])
                    if not owner:
                        continue
                    fp = (int(r["set_id"]), int(r["slot"]), _norm_key(r["main_stat"] or ""))
                    self._equip_index.setdefault(fp, set()).add(owner)
            finally:
                con.close()
        except Exception:
            log.exception("[owner_tiebreak] no se pudieron cargar los mapas de contexto")

    def resolve(self, disc: "DiscParsed", top: list[tuple[str, float]]) -> tuple[str, str] | None:
        """Devuelve (nombre, razon) si el contexto confirma el top-1; si no, None.

        `top`: candidatos del matcher best-first `[(nombre, distancia), ...]` (MatchResult.top).
        Solo CONFIRMA el top-1 visual cuando una señal lo distingue EXCLUSIVAMENTE del top-2
        (RNF-02: nunca promueve el top-2, nunca asigna un PJ que el matcher no rankeó #1).
        """
        if not top or len(top) < 2:
            return None
        top1 = top[0][0]
        top2 = top[1][0]
        if not top1 or not top2:
            return None
        set_id = self._resolve_set_id(disc)
        if set_id is None:
            return None
        n1, n2 = _norm_key(top1), _norm_key(top2)

        # Señal 1 — BUILD firma (set_4p/2p): el set del disco es el set firma del top-1
        # y no del top-2. Sirve para PJs establecidos con set distintivo.
        t1_sets = self._build_map.get(n1, set())
        t2_sets = self._build_map.get(n2, set())
        if set_id in t1_sets and set_id not in t2_sets:
            return top1, "build"

        # Señal 2 — ASIGNACIÓN existente: el top-1 YA tiene un disco con este fingerprint
        # (set, slot, main) asignado en inventory_discs y el top-2 no. Rescata filler/slots
        # 1-3 (Nana s1, Monarca s1) que el build no distingue (validado: Seth/Nana s1).
        slot = getattr(disc, "slot", None)
        main = getattr(disc, "main_stat_canon", None) or getattr(disc, "main_stat_raw", None) or ""
        if slot and 1 <= int(slot) <= 6:
            fp = (set_id, int(slot), _norm_key(main))
            owners = self._equip_index.get(fp, set())
            if n1 in owners and n2 not in owners:
                return top1, "equip"

        return None
