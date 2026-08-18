"""Reconstruye `danibod_zzz_v2.db` desde cero — conservando lo que el censo NO puede recuperar.

Los 367 discos y los stats de los 51 PJs se transcribieron a mano hace meses, que es justo el dato
que la tesis del proyecto dice que diverge. La decisión (2026-08-17) fue re-censar la cuenta
observando, y para eso hace falta una DB vacía de estado de cuenta.

**Pero "desde cero" tiene un límite duro, y es el que define este script:**

    se vacía lo que el sistema sabe volver a observar; se conserva lo que no.

Las 516 filas de `agent_thresholds` / `agent_score_thresholds` / `agent_substat_preferences` /
`pj_weapon_synergy` tienen `fuente='Prydwen'` o `'manual'`: son investigación, no observación.
Ningún censo las devuelve. Lo mismo con tres columnas de `agents` que son stats pero que S18 no
parsea — ver `AGENTS_ARRASTRADAS`.

El script **no toca la DB de origen**: construye la nueva aparte y recién al final, con los dos
PRAGMA en verde, hace el swap. El origen queda archivado en `audit/` como respaldo permanente.

Uso (desde la raíz del repo):

    python app/scripts/rebuild_account_db.py --dry-run    # solo el reporte, no toca nada
    python app/scripts/rebuild_account_db.py              # reconstruye y hace el swap
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# --- clasificación de las 31 tablas -----------------------------------------------------------
# Toda tabla de la DB tiene que estar en exactamente uno de estos grupos. Si mañana una migración
# agrega una y nadie la clasifica, `rebuild` falla a propósito en vez de decidir por su cuenta:
# vaciar por defecto es como se pierden datos que nadie sabía que eran irrecuperables.

#: Propiedades del JUEGO, no de la cuenta. Se copian enteras.
CATALOGO: tuple[str, ...] = (
    "disc_sets", "disc_archetypes", "disc_set_archetype", "weapons",
    "enemies", "enemy_resistances", "content_profiles", "weapon_passives_structured",
)

#: Trabajo de investigación (Prydwen/Fandom/matrices de rol). **El censo NO las recupera.**
INVESTIGACION: tuple[str, ...] = (
    "agent_thresholds", "agent_score_thresholds", "agent_substat_preferences",
    "pj_weapon_synergy", "agent_awakenings",
)

#: Declaraciones del usuario. **No son observación**: son lo que el usuario afirma sobre su propia
#: cuenta, y ningún censo las reproduce. Se conservan enteras — incluido el historial, que es lo que
#: vuelve la tabla una auditoría de sincronía y no un flag de "ya se hizo".
DECLARADO: tuple[str, ...] = (
    "roster_declarations",
)

#: Estado de cuenta observable. Se re-censa.
VACIAR: tuple[str, ...] = (
    "inventory_discs", "inventory_disc_evaluations", "agent_discs",
    "inventory_weapons", "optimizer_pending_actions",
)

#: Ya estaban vacías (features de fases posteriores). Se crean y quedan vacías.
DERIVADAS_VACIAS: tuple[str, ...] = (
    "ai_catalog_runs", "da_cycles", "lategame_run_damage", "lategame_runs",
    "prydwen_tier_snapshots", "prydwen_weapon_recommendations_snapshots", "shiyu_cycles",
    "team_compositions", "team_synergies", "team_synergy_adjustments",
    "tier_list_personal", "weapon_evaluations",
)

#: `agents` va aparte: se conservan las filas y el `id` (las FK cuelgan de él), se NULLean columnas.
TABLA_AGENTS = "agents"

#: Exactamente lo que `sync_agent_stats._STAT_MAP` sabe re-leer de pantalla, más la build que se
#: reconstruye desde los discos una vez recensados.
AGENTS_NULL: tuple[str, ...] = (
    "nivel", "pv", "ataque", "defensa", "impacto", "prob_critico", "dano_critico",
    "tasa_anomalia", "maestria_anomalia", "tasa_perforacion", "rec_energia",
    "weapon_id", "weapon_nivel", "weapon_rango", "set_4p_id", "set_2p_id", "disco6_main",
)

#: Son stats, pero el pipeline NO las lee: el comentario de `sync_agent_stats._STAT_MAP` es
#: explícito ("no los parsea S18 ... ni mindscape"). Vaciarlas sería perder dato irrecuperable, así
#: que se arrastran — y el reporte lo dice, porque un dato conservado que el usuario cree recién
#: censado es peor que uno faltante: se ve igual de confiable y no lo es.
AGENTS_ARRASTRADAS: tuple[str, ...] = ("mindscape", "perforacion", "bono_dano_elemento")


def clasificar_tablas(reales: set[str]) -> tuple[list[str], list[str]]:
    """Compara las tablas de una DB contra la clasificación del módulo.

    Devuelve `(faltan, sobran)`: las que están en la DB y nadie clasificó, y las clasificadas que
    ya no existen. Ambas listas vacías = la clasificación está al día.
    """
    clasificadas = (set(CATALOGO) | set(INVESTIGACION) | set(DECLARADO)
                    | set(VACIAR) | set(DERIVADAS_VACIAS))
    clasificadas.add(TABLA_AGENTS)
    return sorted(reales - clasificadas), sorted(clasificadas - reales)


# --- reporte ----------------------------------------------------------------------------------

@dataclass
class Reporte:
    origen: Path
    destino: Path
    conteos: dict[str, tuple[int, int]] = field(default_factory=dict)   # tabla -> (antes, después)
    nulleadas: list[str] = field(default_factory=list)
    arrastradas: list[str] = field(default_factory=list)
    integridad: str = ""
    fk_rotas: list = field(default_factory=list)
    archivo_respaldo: Path | None = None

    def markdown(self) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")  # noqa: DTZ005
        out = [
            "# Reconstrucción de la DB de cuenta",
            "",
            f"- **fecha:** {ts}",
            f"- **origen:** `{self.origen}`",
            f"- **destino:** `{self.destino}`",
        ]
        if self.archivo_respaldo:
            out.append(f"- **respaldo permanente:** `{self.archivo_respaldo}`")
        out += [
            f"- **integrity_check:** `{self.integridad}`",
            f"- **foreign_key_check:** {'OK' if not self.fk_rotas else self.fk_rotas}",
            "",
            "## Filas por tabla",
            "",
            "| tabla | grupo | antes | después |",
            "|---|---|--:|--:|",
        ]
        grupo_de = {}
        for nombre, tablas in (("catálogo", CATALOGO), ("investigación", INVESTIGACION),
                               ("declarado", DECLARADO),
                               ("vaciada", VACIAR), ("ya vacía", DERIVADAS_VACIAS)):
            for t in tablas:
                grupo_de[t] = nombre
        grupo_de[TABLA_AGENTS] = "identidad"
        for tabla in sorted(self.conteos):
            antes, despues = self.conteos[tabla]
            marca = " ⚠️" if antes and not despues else ""
            out.append(f"| `{tabla}` | {grupo_de.get(tabla, '?')} | {antes} | {despues}{marca} |")

        out += [
            "",
            "## Columnas de `agents` puestas a NULL",
            "",
            "Es lo que `sync_agent_stats._STAT_MAP` sabe volver a leer de pantalla, más la build",
            "que se reconstruye desde los discos. El censo las repuebla.",
            "",
            "```",
            " · ".join(self.nulleadas) or "(ninguna)",
            "```",
            "",
            "## ⚠️ Columnas ARRASTRADAS — conservadas, NO reverificadas",
            "",
            "Son stats, pero el pipeline no las parsea (lo dice el comentario de",
            "`sync_agent_stats._STAT_MAP`). Se conservan porque vaciarlas sería perder dato que la",
            "observación no recupera — pero **su valor es el viejo**, no uno recién censado.",
            "",
            "```",
            " · ".join(self.arrastradas) or "(ninguna)",
            "```",
            "",
            "## Lo que esta reconstrucción NO hace",
            "",
            "- No verifica que los datos conservados sigan siendo correctos. Solo los mueve.",
            "- No borra nada del origen: queda intacto como respaldo.",
            "- `agents.notas` se conserva y por eso **queda vieja**: describe builds que acaban de",
            "  dejar de existir. Se prefirió eso a perder las decisiones y correcciones que también",
            "  guarda.",
        ]
        return "\n".join(out) + "\n"


# --- el rebuild -------------------------------------------------------------------------------

def _objetos_schema(con: sqlite3.Connection, tipo: str) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT sql FROM sqlite_master WHERE type=? AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'",
        (tipo,),
    )]


def _tablas(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def _columnas(con: sqlite3.Connection, tabla: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{tabla}")')]


def _contar(con: sqlite3.Connection, tabla: str) -> int:
    return con.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]


def rebuild(origen: Path | str, destino: Path | str) -> Reporte:
    """Construye `destino` a partir de `origen`. **No modifica `origen`.**

    Lanza `ValueError` si alguna tabla del origen no está clasificada: el script no puede decidir
    solo si una tabla desconocida es catálogo o estado de cuenta, y adivinar es como se pierden
    datos irrecuperables.
    """
    origen, destino = Path(origen), Path(destino)
    if destino.exists():
        destino.unlink()

    src = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    try:
        reales = _tablas(src)
        faltan, _sobran = clasificar_tablas(reales)
        if faltan:
            raise ValueError(
                f"tablas sin clasificar en {origen.name}: {faltan}. "
                "Agregalas a CATALOGO / INVESTIGACION / VACIAR / DERIVADAS_VACIAS antes de seguir."
            )

        dst = sqlite3.connect(destino)
        try:
            for sql in _objetos_schema(src, "table"):
                dst.execute(sql)
            for sql in _objetos_schema(src, "index"):
                dst.execute(sql)

            rep = Reporte(origen=origen, destino=destino)

            # 1. Catálogo + investigación: copia íntegra.
            for tabla in [t for t in (*CATALOGO, *INVESTIGACION, *DECLARADO) if t in reales]:
                cols = _columnas(src, tabla)
                lista = ", ".join(f'"{c}"' for c in cols)
                marcas = ", ".join("?" * len(cols))
                filas = src.execute(f'SELECT {lista} FROM "{tabla}"').fetchall()
                dst.executemany(f'INSERT INTO "{tabla}" ({lista}) VALUES ({marcas})', filas)
                rep.conteos[tabla] = (len(filas), len(filas))

            # 2. `agents`: filas e ids intactos, columnas observables a NULL.
            if TABLA_AGENTS in reales:
                cols = _columnas(src, TABLA_AGENTS)
                a_null = [c for c in AGENTS_NULL if c in cols]
                seleccion = ", ".join(
                    ("NULL" if c in a_null else f'"{c}"') for c in cols
                )
                lista = ", ".join(f'"{c}"' for c in cols)
                marcas = ", ".join("?" * len(cols))
                filas = src.execute(f'SELECT {seleccion} FROM "{TABLA_AGENTS}"').fetchall()
                dst.executemany(
                    f'INSERT INTO "{TABLA_AGENTS}" ({lista}) VALUES ({marcas})', filas)
                rep.conteos[TABLA_AGENTS] = (len(filas), len(filas))
                rep.nulleadas = a_null
                rep.arrastradas = [c for c in AGENTS_ARRASTRADAS if c in cols]

            # 3. Lo que se vacía: la tabla existe (el schema ya se clonó), sin filas.
            for tabla in [t for t in (*VACIAR, *DERIVADAS_VACIAS) if t in reales]:
                rep.conteos[tabla] = (_contar(src, tabla), 0)

            dst.commit()
            rep.fk_rotas = dst.execute("PRAGMA foreign_key_check").fetchall()
            rep.integridad = dst.execute("PRAGMA integrity_check").fetchone()[0]
            return rep
        finally:
            dst.close()
    finally:
        src.close()


# --- CLI --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=None,
                    help="DB de origen (default: la que resuelve app.db.connection)")
    ap.add_argument("--dry-run", action="store_true",
                    help="genera la nueva y el reporte, pero NO reemplaza la de origen")
    ap.add_argument("--snapshot", action="store_true", default=None,
                    help="fuerza el snapshot permanente en audit/ (default: solo para la DB real)")
    args = ap.parse_args(argv)

    from app.db.connection import get_db_path
    origen = args.db or get_db_path()
    if not origen.exists():
        print(f"[ERROR] no existe {origen}", file=sys.stderr)
        return 1

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
    nueva = origen.with_name(f"{origen.stem}.rebuild_{sello}.db")

    print(f"origen : {origen}")
    print(f"nueva  : {nueva}")
    rep = rebuild(origen, nueva)

    from app.core.audit_paths import resolve_audit_dir
    destino_rep = Path(resolve_audit_dir()) / f"rebuild_db_{sello}.md"
    destino_rep.parent.mkdir(parents=True, exist_ok=True)
    destino_rep.write_text(rep.markdown(), encoding="utf-8")
    print(f"reporte: {destino_rep}")

    if rep.integridad != "ok" or rep.fk_rotas:
        print(f"[ERROR] validación FALLÓ (integrity={rep.integridad} fk={rep.fk_rotas}) — "
              f"no se hace el swap. La nueva queda en {nueva} para inspección.", file=sys.stderr)
        return 2

    for tabla, (antes, despues) in sorted(rep.conteos.items()):
        if antes != despues:
            print(f"  {tabla:34s} {antes:6d} -> {despues}")

    if args.dry_run:
        print("\n--dry-run: NO se reemplazó la DB de origen. Revisá el reporte y volvé a correr "
              "sin el flag.")
        return 0

    # Respaldo permanente en audit/ (CLAUDE.md §3.1: los snapshots intencionales se versionan).
    # Solo para la DB real: con `--db` el origen YA es una copia (un ensayo), y archivar copias de
    # ensayo en `audit/` mete 1.6 MB por corrida en un directorio que se versiona.
    snapshot = args.snapshot if args.snapshot is not None else (args.db is None)
    if snapshot:
        respaldo = Path("audit") / f"{origen.stem}.pre_censo_{sello}.db"
        respaldo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, respaldo)
        rep.archivo_respaldo = respaldo
        destino_rep.write_text(rep.markdown(), encoding="utf-8")
        print(f"\nrespaldo permanente: {respaldo}")
    else:
        print("\n(sin snapshot en audit/: el origen ya es una copia — usá --snapshot para forzarlo)")

    shutil.move(str(nueva), str(origen))
    print(f"swap hecho: {origen} es ahora la DB reconstruida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
