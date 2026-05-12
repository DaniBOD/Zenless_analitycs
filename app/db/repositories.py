"""
Repositorios read-only para el scoring engine (Hito 2.1.3).
Los writes los hacen sync_equip.py / sync_upgrade.py con sus propias transacciones.
"""
import json
import sqlite3
from dataclasses import dataclass, field


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

    def insert_from_parsed(self, p: "DiscParsed", set_id: int) -> int:
        """Inserta un disco nuevo desde DiscParsed. Devuelve el id insertado."""
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
                nivel, equipado, descartado)
               VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?)""",
            (
                set_id, p.slot, p.main_stat_canon or p.main_stat_raw, p.main_valor, p.main_unidad,
                s1[0], s1[1], s1[2], s1[3],
                s2[0], s2[1], s2[2], s2[3],
                s3[0], s3[1], s3[2], s3[3],
                s4[0], s4[1], s4[2], s4[3],
                p.nivel, 0, 0,
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]

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
