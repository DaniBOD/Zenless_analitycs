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


@dataclass
class DiscSetArchetype:
    set_id: int
    archetype_id: int
    archetype_code: str
    prioridad: int  # 1=primario, 2=secundario


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

        for r in self._con.execute("SELECT id, nombre, rol FROM agents"):
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
