"""
Repositorios read-only para el scoring engine (Hito 2.1.3).
Los writes los hacen sync_equip.py / sync_upgrade.py con sus propias transacciones.
"""
import json
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.parser_disc import DiscParsed


# ---------------------------------------------------------------------------
# Dataclasses de dominio
# ---------------------------------------------------------------------------

@dataclass
class Archetype:
    id: int
    code: str
    substats_positivos: dict[str, float]
    substats_perjudiciales: dict[str, float]
    threshold_stock: float
    mains_4: list[str] = field(default_factory=list)
    mains_5: list[str] = field(default_factory=list)
    mains_6: list[str] = field(default_factory=list)


@dataclass
class Agent:
    id: int
    nombre: str
    arquetipo_primario_id: int
    arquetipo_primario_code: str
    threshold_equip: float
    threshold_upgrade: float
    substat_preferences: dict[str, float]
    set_4p_id: int | None = None
    set_2p_id: int | None = None
    protected_build: bool = False


@dataclass
class DiscSetArchetype:
    set_id: int
    archetype_id: int
    archetype_code: str
    prioridad: int  # 1=primario, 2=secundario


@dataclass
class DiscSetEntry:
    """Representación liviana de una fila de disc_sets para resolvers de UI/assets."""
    id: int
    nombre: str
    nombre_en: str | None = None


@dataclass
class Disc:
    id: int
    set_id: int
    slot: int
    main_stat: str | None
    main_valor: float | None
    main_unidad: str | None
    subs: list[tuple[str, float | None, str | None, int]]  # (canon, val, unidad, rolls)
    nivel: int
    equipado: int
    agente_asignado: int | None
    # Por qué la fila está sin dueño, cuando lo está. Dos filas con `agente_asignado` NULL se ven
    # idénticas en la tabla, y esta nota es lo ÚNICO que separa "no lo tiene nadie" de "alguien lo
    # tiene y no se pudo leer quién" — distinción que `sync_equip._persist_disco_libre` necesita
    # para no dejar que un libre genuino pise a un incierto.
    notas: str | None = None


# ---------------------------------------------------------------------------
# Repositorios
# ---------------------------------------------------------------------------

class ArchetypeRepo:
    def __init__(self, con: sqlite3.Connection):
        self._con = con
        self._cache: dict[int, Archetype] | None = None

    def _load(self):
        if self._cache is not None:
            return
        self._cache = {}
        for r in self._con.execute("SELECT * FROM disc_archetypes"):
            pos = json.loads(r["substats_positivos"] or "{}")
            neg = json.loads(r["substats_perjudiciales"] or "{}")
            self._cache[r["id"]] = Archetype(
                id=r["id"],
                code=r["code"],
                substats_positivos=pos,
                substats_perjudiciales=neg,
                threshold_stock=r["threshold_stock"] or 0.50,
                mains_4=json.loads(r["mains_4"] or "[]"),
                mains_5=json.loads(r["mains_5"] or "[]"),
                mains_6=json.loads(r["mains_6"] or "[]"),
            )

    def get_all(self) -> list[Archetype]:
        self._load()
        return list(self._cache.values())  # type: ignore[union-attr]

    def get_by_id(self, arch_id: int) -> Archetype | None:
        self._load()
        return self._cache.get(arch_id)  # type: ignore[union-attr]

    def get_by_code(self, code: str) -> Archetype | None:
        self._load()
        for a in self._cache.values():  # type: ignore[union-attr]
            if a.code == code:
                return a
        return None


class DiscSetRepo:
    def __init__(self, con: sqlite3.Connection):
        self._con = con
        self._cache: dict[int, list[DiscSetArchetype]] | None = None

    def _load(self):
        if self._cache is not None:
            return
        self._cache = {}
        for r in self._con.execute(
            "SELECT dsa.set_id, dsa.archetype_id, da.code, dsa.prioridad "
            "FROM disc_set_archetype dsa JOIN disc_archetypes da ON da.id=dsa.archetype_id"
        ):
            entry = DiscSetArchetype(
                set_id=r["set_id"],
                archetype_id=r["archetype_id"],
                archetype_code=r["code"],
                prioridad=r["prioridad"],
            )
            self._cache.setdefault(r["set_id"], []).append(entry)

    def get_archetypes_for_set(self, set_id: int) -> list[DiscSetArchetype]:
        self._load()
        return self._cache.get(set_id, [])  # type: ignore[union-attr]

    def get_id_by_name(self, nombre: str) -> int | None:
        """Resuelve nombre del set (OCR) → set_id. Matching case-insensitive."""
        r = self._con.execute(
            "SELECT id FROM disc_sets WHERE lower(nombre)=lower(?) LIMIT 1", (nombre,)
        ).fetchone()
        return r["id"] if r else None

    def get_all_names(self) -> dict[str, int]:
        """Devuelve {nombre_lower: id} para fuzzy matching desde el parser."""
        return {
            r["nombre"].lower(): r["id"]
            for r in self._con.execute("SELECT id, nombre FROM disc_sets")
        }

    # Regla de MARGEN (calibrada 2026-09-01, ver `tools/measure_set_resolver.py`).
    #
    # El cutoff absoluto de 0.86 tiraba lecturas INEQUÍVOCAS: `Melodia Faett` sale 0.8148 y su
    # segundo candidato está a 0.36 de distancia. Es el mismo error estructural que el guard de
    # identidad — un piso sobre el primer candidato mide otra cosa que la ambigüedad.
    #
    # Barrido sobre dos corpus (89 lecturas reales del censo del 2026-08-30 + 3789 corrupciones
    # sintéticas de los 30 nombres del catálogo): `MAL = 0` en TODAS las combinaciones, el
    # rescate viene entero de bajar el cutoff (1803 → 1822 detecciones) y el margen sólo se paga
    # en abstenciones. 0.70/0.75/0.80 dan idéntico resultado ⇒ 0.75 es el medio de la meseta, no
    # su borde (la lectura genuina más floja está en 0.8148 y la basura más alta en 0.4615).
    # El margen queda en 0.12 y no en 0.15 porque `metal caótico` compite con `metal eléctrico`
    # —el par más parecido del catálogo, 0.7692 entre sí— a 0.1474.
    SET_FUZZY_CUTOFF = 0.75
    SET_FUZZY_MARGIN = 0.12

    def resolve_id(self, name: str, cutoff: float = SET_FUZZY_CUTOFF,
                   margin: float = SET_FUZZY_MARGIN) -> int | None:
        """Resuelve un nombre de set (posible ruido OCR) → set_id: exact → fuzzy sin acentos
        (substring sobre `_norm_key`: NFD + quita Mn + minúscula + sin espacios) → difflib con
        guarda de ambigüedad (abstiene si dos sets DISTINTOS empatan dentro del margen; RNF-02:
        no adivinar). Fuente única para el resolvedor de sets (S4 tienda música + sync_equip).

        El ranking se calcula sobre el catálogo ENTERO. La versión anterior pedía candidatos con
        `get_close_matches(n=3, cutoff=...)` y evaluaba la ambigüedad sólo dentro de esa lista,
        así que un rival a distancia de margen que quedara 4º —o por debajo del cutoff— no se
        veía: la guarda dependía de quién hubiera entrado al recorte.
        """
        if not name:
            return None
        # 1. Exact case-insensitive.
        sid = self.get_id_by_name(name)
        if sid:
            return sid
        # 2/3. Fuzzy insensible a acentos.
        import difflib
        from app.core.stats_vocab import _norm_key
        name_n = _norm_key(name)
        if not name_n:
            return None
        norm_to: dict[str, tuple[str, int]] = {}
        for sname, s_id in self.get_all_names().items():
            sname_n = _norm_key(sname)
            if not sname_n:
                continue
            norm_to.setdefault(sname_n, (sname, s_id))
            if sname_n == name_n or sname_n in name_n or name_n in sname_n:
                return s_id
        # Ranking completo: 30 nombres cortos, y esto corre una vez por disco persistido (no por
        # frame), así que el costo es irrelevante frente a poder ver al rival real.
        ranked = sorted(
            ((difflib.SequenceMatcher(None, name_n, k).ratio(), k) for k in norm_to),
            key=lambda t: t[0], reverse=True,
        )
        if not ranked:
            return None
        r_best, k_best = ranked[0]
        best_sid = norm_to[k_best][1]
        if r_best < cutoff:
            return None
        # Margen al mejor candidato de OTRO set (los alias del mismo set no son ambigüedad).
        rival = next((t for t in ranked[1:] if norm_to[t[1]][1] != best_sid), None)
        if rival is not None and (r_best - rival[0]) < margin:
            return None   # ambiguo → abstenerse
        return best_sid

    def get_bonus(self, set_id: int) -> tuple[str | None, str | None, str | None]:
        """
        Bono de conjunto curado del set: (bonus_2p_stat, bonus_2p_valor,
        bonus_4p_desc). Es la fuente de verdad del item #3 (no se re-OCRiza —
        disc_sets está 100% curado). Devuelve (None, None, None) si no existe.
        """
        r = self._con.execute(
            "SELECT bonus_2p_stat, bonus_2p_valor, bonus_4p_desc FROM disc_sets WHERE id=?",
            (set_id,),
        ).fetchone()
        if not r:
            return (None, None, None)
        return (r["bonus_2p_stat"], r["bonus_2p_valor"], r["bonus_4p_desc"])

    def get_all(self) -> list[DiscSetEntry]:
        """Devuelve todas las filas de disc_sets con id, nombre y nombre_en."""
        return [
            DiscSetEntry(id=r["id"], nombre=r["nombre"], nombre_en=r["nombre_en"])
            for r in self._con.execute(
                "SELECT id, nombre, nombre_en FROM disc_sets ORDER BY id"
            )
        ]


class AgentRepo:
    def __init__(self, con: sqlite3.Connection):
        self._con = con
        self._cache: dict[int, Agent] | None = None

    def _load(self):
        if self._cache is not None:
            return
        self._cache = {}

        archetypes_by_role = {
            "Ataque":        "ATK_DPS",
            "Anomalía":      "ANOMALY",
            "Aturdimiento":  "STUN",
            "Soporte":       "SUPPORT_ER",
            "Defensa":       "DEFENSE",
            "Disruptivos":   "HP_DISRUPT",
        }

        arch_rows = {
            r["code"]: r["id"]
            for r in self._con.execute("SELECT id, code FROM disc_archetypes")
        }

        thresholds = {}
        for r in self._con.execute(
            "SELECT agente_id, threshold_equip, threshold_upgrade FROM agent_score_thresholds"
        ):
            thresholds[r["agente_id"]] = (r["threshold_equip"], r["threshold_upgrade"])

        prefs: dict[int, dict[str, float]] = {}
        for r in self._con.execute(
            "SELECT agente_id, substat, peso FROM agent_substat_preferences"
        ):
            prefs.setdefault(r["agente_id"], {})[r["substat"]] = r["peso"]

        for r in self._con.execute(
            "SELECT id, nombre, rol, set_4p_id, set_2p_id, protected_build FROM agents"
        ):
            arch_code = archetypes_by_role.get(r["rol"], "ATK_DPS")
            arch_id = arch_rows.get(arch_code, 1)
            t_equip, t_upgrade = thresholds.get(r["id"], (0.75, 0.50))
            self._cache[r["id"]] = Agent(
                id=r["id"],
                nombre=r["nombre"],
                arquetipo_primario_id=arch_id,
                arquetipo_primario_code=arch_code,
                threshold_equip=t_equip,
                threshold_upgrade=t_upgrade,
                substat_preferences=prefs.get(r["id"], {}),
                set_4p_id=r["set_4p_id"],
                set_2p_id=r["set_2p_id"],
                protected_build=bool(r["protected_build"]),
            )

    def get_all(self) -> list[Agent]:
        self._load()
        return list(self._cache.values())  # type: ignore[union-attr]

    def get_by_id(self, agent_id: int) -> Agent | None:
        self._load()
        return self._cache.get(agent_id)  # type: ignore[union-attr]

    def get_by_nombre(self, nombre: str) -> Agent | None:
        self._load()
        for a in self._cache.values():  # type: ignore[union-attr]
            if a.nombre == nombre:
                return a
        return None


class InventoryDiscRepo:
    def __init__(self, con: sqlite3.Connection):
        self._con = con

    def get_all_active(self) -> list[Disc]:
        rows = self._con.execute(
            "SELECT * FROM inventory_discs WHERE descartado = 0 OR descartado IS NULL"
        )
        return [self._row_to_disc(r) for r in rows]

    def get_by_id(self, disc_id: int) -> Disc | None:
        r = self._con.execute(
            "SELECT * FROM inventory_discs WHERE id = ?", (disc_id,)
        ).fetchone()
        return self._row_to_disc(r) if r else None

    def update_score(self, disc_id: int, score: float, agentes_json: str, notas: str | None):
        self._con.execute(
            "UPDATE inventory_discs SET score_evaluacion=?, agentes_compatibles=?, notas=? WHERE id=?",
            (score, agentes_json, notas, disc_id),
        )

    def find_by_hash(self, set_id: int, slot: int, main_stat: str | None, main_valor: float | None) -> "Disc | None":
        """Busca un disco existente por (set_id, slot, main_stat, main_valor) — hash de deduplicación."""
        r = self._con.execute(
            "SELECT * FROM inventory_discs WHERE set_id=? AND slot=? AND main_stat=? AND main_valor=? AND descartado=0 LIMIT 1",
            (set_id, slot, main_stat, main_valor),
        ).fetchone()
        return self._row_to_disc(r) if r else None

    def find_all_by_identity(self, p: "DiscParsed", set_id: int) -> list["Disc"]:
        """TODAS las filas que son el mismo disco que `p` por identidad COMPLETA
        (set, slot, nivel, main, {substat normalizado + rolls}) — misma definición que
        `row_matches_parsed_identity`, sin el filtro de dueño de `find_swap_candidates_by_identity`.

        Es la clave de dedup correcta para el upsert de captura, donde no hay `(PJ, slot)` que
        usar. `find_by_hash` no sirve ahí: compara `(set, slot, main, main_valor)`, y en los slots
        1/2/3 el main es FIJO, así que a un mismo nivel todos los discos de un set son iguales para
        esa firma. Medido sobre el inventario real de 367: la firma gruesa deja **177 filas**, la
        identidad completa **345**.

        Devuelve una lista y no un `Disc` a propósito: **≥2 significa ambigüedad real** (discos
        indistinguibles, 22 pares en el inventario medido) y el caller tiene que poder avisarla en
        vez de quedarse callado con el primero que salga (RNF-02).
        """
        rows = self._con.execute(
            "SELECT * FROM inventory_discs WHERE set_id=? AND slot=? AND nivel=? AND descartado=0",
            (set_id, p.slot, p.nivel),
        ).fetchall()
        out: list[Disc] = []
        for r in rows:
            d = self._row_to_disc(r)
            if self.row_matches_parsed_identity(d, p, set_id):
                out.append(d)
        return out

    def find_equipped_by_agent_slot(self, agente_id: int, slot: int) -> "Disc | None":
        """
        Disco equipado de un PJ en un slot dado. Clave NATURAL del equipamiento:
        un PJ tiene exactamente un disco equipado por slot. A diferencia de
        `find_by_hash` (set+slot+main+mainval, que COLISIONA entre PJs que comparten
        la misma firma), esto nunca devuelve el disco de otro PJ.
        """
        r = self._con.execute(
            "SELECT * FROM inventory_discs WHERE agente_asignado=? AND slot=? "
            "AND equipado=1 AND descartado=0 LIMIT 1",
            (agente_id, slot),
        ).fetchone()
        return self._row_to_disc(r) if r else None

    def find_swap_candidates_by_identity(
        self, p: "DiscParsed", set_id: int, dest_agent_id: int | None,
        exclude_disc_id: int | None = None,
    ) -> list["Disc"]:
        """Filas EXISTENTES candidatas a mover/re-equipar al destino (evitar duplicar), cuya
        identidad COMPLETA coincide con el parseado. DOS orígenes válidos (targeted, RNF-02):
          - EQUIPADO por OTRO PJ  → swap entre PJs (el otro lo pierde).
          - DESEQUIPADO del DESTINO → re-equipar su propio disco desplazado.
        Deliberadamente NO incluye discos sueltos de otros dueños ni sin dueño (evita robar por
        colisión de firma). Identidad = (set_id, slot, main, nivel, {substat normalizado + rolls}):
        incluye NIVEL (entero limpio) y omite VALORES (ruidosos por OCR). Match GRUESO (set+slot+
        nivel) en SQL; fino (main+substats) en Python. El caller mueve solo si hay EXACTAMENTE UNO
        (0 → nuevo; ≥2 → ambiguo → no tocar)."""
        from app.core.stats_vocab import _norm_key
        main_canon = p.main_stat_canon or p.main_stat_raw
        want = self._identity_subs(
            (s.nombre_canon or s.nombre_raw, s.rolls) for s in (p.subs or [])
        )
        rows = self._con.execute(
            "SELECT * FROM inventory_discs WHERE set_id=? AND slot=? AND nivel=? AND descartado=0 "
            "AND (? IS NULL OR id<>?) AND ("
            "  (equipado=1 AND agente_asignado IS NOT NULL AND (? IS NULL OR agente_asignado<>?)) "
            "  OR (equipado=0 AND agente_asignado IS NOT NULL AND agente_asignado=?)"
            ")",
            (set_id, p.slot, p.nivel, exclude_disc_id, exclude_disc_id,
             dest_agent_id, dest_agent_id, dest_agent_id),
        ).fetchall()
        out: list["Disc"] = []
        for r in rows:
            d = self._row_to_disc(r)
            if _norm_key(d.main_stat or "") != _norm_key(main_canon or ""):
                continue
            have = self._identity_subs((name, rolls) for name, _v, _u, rolls in d.subs)
            if have == want:
                out.append(d)
        return out

    def row_matches_parsed_identity(self, d: "Disc", p: "DiscParsed", set_id: int) -> bool:
        """True si la fila `d` es EL MISMO disco que el parseado `p`, por identidad COMPLETA
        (set, slot, nivel, main, {substat normalizado + rolls}) — misma definición que
        `find_swap_candidates_by_identity`, extraída para poder validar también el hint del
        diálogo S23. RNF-02: sin esto, un hint viejo podía mover la fila del origen solo por
        compartir el set, aunque el disco que estamos viendo fuera otro."""
        from app.core.stats_vocab import _norm_key
        if d.set_id != set_id or d.slot != p.slot or d.nivel != p.nivel:
            return False
        main_canon = p.main_stat_canon or p.main_stat_raw
        if _norm_key(d.main_stat or "") != _norm_key(main_canon or ""):
            return False
        want = self._identity_subs(
            (s.nombre_canon or s.nombre_raw, s.rolls) for s in (p.subs or [])
        )
        have = self._identity_subs((name, rolls) for name, _v, _u, rolls in d.subs)
        return have == want

    @staticmethod
    def _identity_subs(pairs) -> tuple:
        """Firma de substats para identidad: {(nombre normalizado, rolls)} ordenada."""
        from app.core.stats_vocab import _norm_key
        return tuple(sorted((_norm_key(n or ""), rolls or 0) for n, rolls in pairs))

    def set_unequipped(self, disc_id: int) -> None:
        """Marca un disco como NO equipado (swap-out). Conserva agente_asignado y data."""
        self._con.execute(
            "UPDATE inventory_discs SET equipado=0 WHERE id=?", (disc_id,)
        )

    def insert_from_parsed(
        self,
        p: "DiscParsed",
        set_id: int,
        agente_asignado: int | None = None,
        equipado: int = 0,
        notas: str | None = None,
    ) -> int:
        """
        Inserta un disco nuevo desde DiscParsed. Devuelve el id insertado.
        `agente_asignado`/`equipado` solo se setean cuando el caller tiene una
        asignación confiable (S17 latch+avatar); por defecto None/0.

        `notas` deja marcada la fila con el MOTIVO de una escritura parcial —hoy sólo
        `dueno_no_identificado_<fecha>`, misma convención que `no_visto_en_censo_<fecha>` de
        `census_store`—. No es documentación: `_persist_disco_libre` lee esa marca para NO meter
        la fila en el bucket de libres, porque una fila que en realidad está equipada no puede ser
        pisada por el próximo libre con la misma identidad.
        """
        subs = p.subs
        def _sub(i: int):
            if i < len(subs):
                s = subs[i]
                return s.nombre_canon or s.nombre_raw, s.valor, s.rolls, s.unidad
            return None, None, 0, None

        s1 = _sub(0); s2 = _sub(1); s3 = _sub(2); s4 = _sub(3)
        cur = self._con.execute(
            """INSERT INTO inventory_discs
               (set_id, slot, main_stat, main_valor, unidad_main,
                sub1, val1, rolls1, unidad1,
                sub2, val2, rolls2, unidad2,
                sub3, val3, rolls3, unidad3,
                sub4, val4, rolls4, unidad4,
                nivel, equipado, agente_asignado, descartado, notas)
               VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?,?)""",
            (
                set_id, p.slot, p.main_stat_canon or p.main_stat_raw, p.main_valor, p.main_unidad,
                s1[0], s1[1], s1[2], s1[3],
                s2[0], s2[1], s2[2], s2[3],
                s3[0], s3[1], s3[2], s3[3],
                s4[0], s4[1], s4[2], s4[3],
                p.nivel, (1 if agente_asignado is not None else equipado),
                agente_asignado, 0, notas,
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def update_assignment(self, disc_id: int, agente_id: int, equipado: int = 1) -> None:
        """
        Actualiza SOLO la asignación de un disco existente (PJ + equipado). Se
        llama únicamente con asignación confiable (S17 latch+avatar); nunca con
        valores nulos/inciertos — así no se pisa lo curado (RNF-02).
        """
        self._con.execute(
            "UPDATE inventory_discs SET agente_asignado=?, equipado=? WHERE id=?",
            (agente_id, equipado, disc_id),
        )

    def update_from_parsed(self, disc_id: int, p: "DiscParsed") -> None:
        """Actualiza nivel y substats de un disco existente (re-captura post-upgrade)."""
        subs = p.subs
        def _sub(i: int):
            if i < len(subs):
                s = subs[i]
                return s.nombre_canon or s.nombre_raw, s.valor, s.rolls, s.unidad
            return None, None, 0, None

        s1 = _sub(0); s2 = _sub(1); s3 = _sub(2); s4 = _sub(3)
        self._con.execute(
            """UPDATE inventory_discs SET
               nivel=?,
               sub1=?, val1=?, rolls1=?, unidad1=?,
               sub2=?, val2=?, rolls2=?, unidad2=?,
               sub3=?, val3=?, rolls3=?, unidad3=?,
               sub4=?, val4=?, rolls4=?, unidad4=?
               WHERE id=?""",
            (
                p.nivel,
                s1[0], s1[1], s1[2], s1[3],
                s2[0], s2[1], s2[2], s2[3],
                s3[0], s3[1], s3[2], s3[3],
                s4[0], s4[1], s4[2], s4[3],
                disc_id,
            ),
        )

    @staticmethod
    def _row_to_disc(r: sqlite3.Row) -> "Disc":
        from app.core.stats_vocab import normalize_stat_name, parse_value

        def sub(i: int) -> tuple[str, float | None, str | None, int]:
            name = r[f"sub{i}"]
            canon = normalize_stat_name(name) if name else None
            raw_val = r[f"val{i}"]
            parsed = parse_value(raw_val)
            rolls = r[f"rolls{i}"] or 0
            if parsed:
                return (canon or name or "", parsed[0], parsed[1], rolls)
            return (canon or name or "", None, None, rolls)

        main_canon = normalize_stat_name(r["main_stat"])
        main_parsed = parse_value(r["main_valor"])

        return Disc(
            id=r["id"],
            set_id=r["set_id"],
            slot=r["slot"],
            main_stat=main_canon or r["main_stat"],
            main_valor=main_parsed[0] if main_parsed else None,
            main_unidad=main_parsed[1] if main_parsed else None,
            subs=[sub(i) for i in (1, 2, 3, 4) if r[f"sub{i}"]],
            nivel=r["nivel"] or 0,
            equipado=r["equipado"] or 0,
            agente_asignado=r["agente_asignado"],
            # `.keys()` es a propósito y NO es el SIM118 que ruff cree: `r` es un
            # `sqlite3.Row`, donde `in` itera VALORES, no columnas. Y el guard existe
            # porque varios esquemas de test no declaran `notas`.
            notas=(r["notas"] if "notas" in r.keys() else None),  # noqa: SIM118
        )


class EvaluationRepo:
    """Write-only repo para inventory_disc_evaluations."""

    def __init__(self, con: sqlite3.Connection):
        self._con = con

    def insert(
        self,
        disc_id: int,
        trigger: str,
        recomendacion: str,
        score: float,
        detalle_json: str,
    ) -> int:
        from datetime import date
        cur = self._con.execute(
            """INSERT INTO inventory_disc_evaluations
               (inventory_disc_id, fecha, trigger_evento, recomendacion, score, detalle_json)
               VALUES (?,?,?,?,?,?)""",
            (disc_id, date.today().isoformat(), trigger, recomendacion, round(score, 6), detalle_json),
        )
        return cur.lastrowid  # type: ignore[return-value]


class AgentDiscRepo:
    """Lee agent_discs (build actual de cada PJ) como lista de Disc."""

    def __init__(self, con: sqlite3.Connection):
        self._con = con

    def get_by_agent(self, agente_id: int) -> list["Disc"]:
        rows = self._con.execute(
            "SELECT * FROM agent_discs WHERE agente_id = ?", (agente_id,)
        )
        return [self._row_to_disc(r, agente_id) for r in rows]

    @staticmethod
    def _row_to_disc(r: sqlite3.Row, agente_id: int) -> "Disc":
        from app.core.stats_vocab import normalize_stat_name, parse_value

        def sub(i: int) -> "tuple[str, float | None, str | None, int]":
            name = r[f"sub{i}"]
            canon = normalize_stat_name(name) if name else None
            raw_val = r[f"val{i}"]
            parsed = parse_value(raw_val) if raw_val else None
            rolls = r[f"sub{i}_up"] or 0
            if parsed:
                return (canon or name or "", parsed[0], parsed[1], rolls)
            return (canon or name or "", None, None, rolls)

        main_canon = normalize_stat_name(r["main_stat"]) if r["main_stat"] else None
        main_parsed = parse_value(r["main_valor"]) if r["main_valor"] else None

        return Disc(
            id=r["id"],
            set_id=r["set_id"],
            slot=r["slot"],
            main_stat=main_canon or r["main_stat"],
            main_valor=main_parsed[0] if main_parsed else None,
            main_unidad=main_parsed[1] if main_parsed else None,
            subs=[sub(i) for i in (1, 2, 3, 4) if r[f"sub{i}"]],
            nivel=r["nivel"] or 0,
            equipado=1,
            agente_asignado=agente_id,
        )


class OptimizerRepo:
    """Lee y escribe optimizer_pending_actions."""

    def __init__(self, con: sqlite3.Connection):
        self._con = con

    def upsert_build(
        self,
        agente_id: int,
        rank: int,
        score_estimado: float,
        score_actual: float,
        delta: float,
        build_json: str,
        set_bonus: str,
        requiere_swaps: str,
        fuente_trigger: str = "manual",
    ) -> int:
        from datetime import datetime
        # fuente_trigger must match the DB CHECK constraint
        trigger_map = {"manual": "manual", "auto_post_captura": "auto_post_captura", "recalc_inventario": "recalc_inventario"}
        fuente = trigger_map.get(fuente_trigger, "manual")
        self._con.execute(
            "UPDATE optimizer_pending_actions SET estado='OBSOLETO', fecha_obsoleto=? "
            "WHERE agente_id=? AND estado='TODO'",
            (datetime.now().isoformat(), agente_id),
        )
        cur = self._con.execute(
            """INSERT INTO optimizer_pending_actions
               (agente_id, rank, score_estimado, score_actual, delta,
                build_json, set_bonus, requiere_swaps, estado, fuente_trigger, fecha_calculado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                agente_id, rank, round(score_estimado, 6), round(score_actual, 6),
                round(delta, 6), build_json, set_bonus, requiere_swaps,
                "TODO", fuente, datetime.now().isoformat(),
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def get_latest_pending(self, agente_id: int) -> "sqlite3.Row | None":
        return self._con.execute(
            "SELECT * FROM optimizer_pending_actions WHERE agente_id=? AND estado='TODO' "
            "ORDER BY fecha_calculado DESC LIMIT 1",
            (agente_id,),
        ).fetchone()
