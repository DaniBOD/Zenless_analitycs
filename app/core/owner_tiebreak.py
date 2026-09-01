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

# Promoción del TOP-2: solo si el empate visual es ÍNFIMO (distancia top-2 − top-1 por
# debajo de esto) Y el contexto corrobora EXCLUSIVAMENTE al top-2. El matcher ya abstuvo
# por margen < 0.04; esto es más estricto aún (decisión DaniBOD 2026-06-26, "guardas
# estrictas"): rescata el caso "dueño real es el top-2 casi empatado" (César/Punk s4).
_TOP2_MARGIN_MAX = 0.03


class OwnerTiebreaker:
    """Confirma el top-1 visual de un badge ambiguo usando el build (set firma) de la DB.

    `resolve_set_id`: callable `(DiscParsed) -> int | None` que resuelve el set del disco
    a su id (se reusa `DiscSyncer._resolve_set_id`, con su fuzzy sin acentos + difflib).
    """

    def __init__(self, db_path: Path | str, resolve_set_id: Callable[["DiscParsed"], int | None]):
        self._resolve_set_id = resolve_set_id
        self._db_path = Path(db_path)
        # build_map: nombre_normalizado -> {set_id, ...}  (4pc + 2pc, no-NULL)
        self._build_map: dict[str, set[int]] = {}
        # equip_index: (set_id, slot, main_norm) -> {nombre_normalizado, ...} — qué PJs
        # tienen YA un disco con ese fingerprint asignado en inventory_discs. Señal más
        # potente que el build (incluye filler reales, no solo el set firma). Para slots
        # 1/2/3 el main es fijo por slot (HP/ATK/DEF) → fingerprint preciso; para 4-6 solo
        # matchea si el string del main coincide normalizado (si no, no dispara → seguro).
        self._equip_index: dict[tuple[int, int, str], set[str]] = {}
        # Los índices son una foto al cargar. `mark_dirty()` (que llama el controller tras
        # persistir un disco) fuerza una recarga LAZY en el próximo resolve() → mantiene el
        # desempate al día con cambios de build en vivo (p.ej. reasignar discos de Velina).
        self._dirty: bool = False
        self._load_maps(self._db_path)

    def mark_dirty(self) -> None:
        """Marca los índices como obsoletos → el próximo `resolve()` los recarga. Lo llama
        el controller tras persistir un disco (cambió `inventory_discs`/asignaciones)."""
        self._dirty = True

    def _load_maps(self, db_path: Path) -> None:
        self._build_map = {}
        self._equip_index = {}
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

    def _exclusive_signal(self, set_id, slot, main, a_key, b_key) -> str | None:
        """¿Alguna señal distingue EXCLUSIVAMENTE al candidato `a` del `b`? Devuelve la
        razón ('build' | 'equip') o None. `a`/`b` son nombres ya normalizados."""
        # BUILD firma (set_4p/2p): el set del disco es firma de `a` y no de `b`.
        a_sets = self._build_map.get(a_key, set())
        b_sets = self._build_map.get(b_key, set())
        if set_id in a_sets and set_id not in b_sets:
            return "build"
        # ASIGNACIÓN existente: `a` YA tiene un disco con este fingerprint (set, slot, main)
        # en inventory_discs y `b` no. Rescata filler/slots 1-3 (Nana s1) que el build no
        # distingue. Para slots 1-3 el main es fijo por slot → fingerprint preciso.
        if slot and 1 <= int(slot) <= 6:
            fp = (set_id, int(slot), _norm_key(main))
            owners = self._equip_index.get(fp, set())
            if a_key in owners and b_key not in owners:
                return "equip"
        return None

    def resolve(self, disc: "DiscParsed", top: list[tuple[str, float]],
                permitir_top2: bool = True) -> tuple[str, str] | None:
        """Devuelve (nombre, razon) si el contexto confirma un candidato; si no, None.

        `top`: candidatos del matcher best-first `[(nombre, distancia), ...]` (MatchResult.top).
        Confirma el TOP-1 cuando una señal lo distingue EXCLUSIVAMENTE del top-2. Si el top-1
        no se corrobora, promueve el TOP-2 SOLO si el empate visual es ínfimo (margen <
        _TOP2_MARGIN_MAX) y el contexto corrobora EXCLUSIVAMENTE al top-2 (caso "dueño real
        es el top-2 casi empatado"). RNF-02: corroboración siempre EXCLUSIVA.

        `permitir_top2=False` deja sólo la confirmación del top-1. Lo pone quien sabe que la
        DB está a medio llenar —hoy, una pasada de censo abierta—: ahí "el top-1 no corre este
        set" no es un hecho sino un "todavía no llegué a sus discos", y con esa evidencia se
        puede confirmar lo que la vista ya decidió, pero no darlo vuelta.
        """
        if not top or len(top) < 2:
            return None
        if self._dirty:                       # recarga lazy tras un persist (mark_dirty)
            self._load_maps(self._db_path)
            self._dirty = False
        top1, d1 = top[0]
        top2, d2 = top[1]
        if not top1 or not top2:
            return None
        set_id = self._resolve_set_id(disc)
        if set_id is None:
            return None
        n1, n2 = _norm_key(top1), _norm_key(top2)
        slot = getattr(disc, "slot", None)
        main = getattr(disc, "main_stat_canon", None) or getattr(disc, "main_stat_raw", None) or ""

        # TOP-1: corroboración exclusiva sobre el top-2.
        reason = self._exclusive_signal(set_id, slot, main, n1, n2)
        if reason:
            return top1, reason

        # TOP-2: solo con empate visual ÍNFIMO y corroboración exclusiva sobre el top-1.
        if permitir_top2 and (d2 - d1) <= _TOP2_MARGIN_MAX:
            reason = self._exclusive_signal(set_id, slot, main, n2, n1)
            if reason:
                return top2, f"{reason}_top2"

        return None
