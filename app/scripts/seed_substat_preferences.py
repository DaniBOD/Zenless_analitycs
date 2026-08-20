"""
Hito 2.0.5 — Seed agent_substat_preferences desde Prydwen.
Idempotente: DELETE + INSERT por agente en cada ejecucion.
- 5 PJs canonicos del brief de diseno: datos de Prydwen (fuente='prydwen').
- 4 PJs adicionales: Lycaon, Qingyi, Pulchra, Cissia (fuente='tentativo_prydwen').
- Genera audit/preferences_pendientes.md con los 37 PJs sin preferencias.

Uso:
    python app/scripts/seed_substat_preferences.py [--dry-run]
"""
import argparse
import sqlite3
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.connection import respaldar_db

DB_PATH = Path("db/danibod_zzz_v2.db")
AUDIT_DIR = Path("audit")

# Datos Prydwen verificados (fuente='prydwen')
PRYDWEN_VERIFIED: dict[str, dict[str, float]] = {
    "Yanagi": {
        "Maestría de Anomalía": 1.0,
        "ATK%":                 0.8,
        "Prob. Crítica":        0.5,
        "ATK":                  0.4,
        "Daño Crítico":        -0.3,
        "DEF%":                -0.6,
    },
    "Ellen": {
        "Prob. Crítica":  1.0,
        "Daño Crítico":   1.0,
        "ATK%":           0.8,
        "ATK":            0.4,
        "Perforación":    0.5,
        "HP%":           -0.4,
        "DEF%":          -0.6,
    },
    "Yixuan": {
        "Daño Crítico":  1.0,
        "Prob. Crítica": 1.0,
        "HP%":           0.8,
        "HP":            0.4,
        "ATK%":         -0.2,
        "DEF%":         -0.5,
    },
    "Burnice": {
        "Maestría de Anomalía": 1.0,
        "ATK%":                 0.7,
        "Recarga de Energía":   0.6,
        "ATK":                  0.4,
        "Prob. Crítica":       -0.2,
        "Daño Crítico":        -0.3,
        "DEF%":                -0.6,
    },
    # César = Caesar en la DB (id=5)
    "César": {
        "DEF%":                 1.0,
        "DEF":                  0.7,
        "HP%":                  0.6,
        "HP":                   0.3,
        "Impacto":              0.8,
        "Maestría de Anomalía":-0.5,
    },
}

# Datos aproximados basados en rol/kit (fuente='tentativo_prydwen', requieren verificacion)
PRYDWEN_TENTATIVO: dict[str, dict[str, float]] = {
    "Lycaon": {
        "Prob. Crítica": 1.0,
        "Daño Crítico":  1.0,
        "ATK%":          0.8,
        "ATK":           0.4,
        "Perforación":   0.5,
        "HP%":          -0.5,
        "DEF%":         -0.8,
    },
    "Qingyi": {
        "Prob. Crítica": 1.0,
        "Daño Crítico":  0.8,
        "ATK%":          0.8,
        "Impacto":       0.6,
        "ATK":           0.4,
        "HP%":          -0.5,
        "DEF%":         -0.8,
    },
    "Pulchra": {
        "Prob. Crítica": 1.0,
        "Daño Crítico":  1.0,
        "ATK%":          0.8,
        "ATK":           0.4,
        "Perforación":   0.5,
        "HP%":          -0.4,
        "DEF%":         -0.8,
    },
    "Cissia": {
        "Prob. Crítica": 1.0,
        "Daño Crítico":  1.0,
        "ATK%":          0.8,
        "ATK":           0.4,
        "Perforación":   0.5,
        "HP%":          -0.4,
        "DEF%":         -0.8,
    },
}


def seed(dry_run: bool = False) -> dict:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    # Fetch agent id map
    agent_map: dict[str, int] = {
        r["nombre"]: r["id"]
        for r in con.execute("SELECT id, nombre FROM agents")
    }
    all_agents = set(agent_map.keys())

    stats = {
        "seeded": [],
        "skipped": [],
        "total_rows": 0,
    }

    all_seed_data: list[tuple[int, str, float, str]] = []

    for nombre, prefs in PRYDWEN_VERIFIED.items():
        if nombre not in agent_map:
            stats["skipped"].append((nombre, "not found in DB"))
            continue
        fuente = "prydwen"
        for substat, peso in prefs.items():
            all_seed_data.append((agent_map[nombre], substat, peso, fuente))
        stats["seeded"].append((nombre, len(prefs), fuente))

    for nombre, prefs in PRYDWEN_TENTATIVO.items():
        if nombre not in agent_map:
            stats["skipped"].append((nombre, "not found in DB"))
            continue
        fuente = "tentativo_prydwen"
        for substat, peso in prefs.items():
            all_seed_data.append((agent_map[nombre], substat, peso, fuente))
        stats["seeded"].append((nombre, len(prefs), fuente))

    stats["total_rows"] = len(all_seed_data)

    # Agents covered
    seeded_names = {row[0] for row, *_ in [(s,) for s in stats["seeded"]]}
    seeded_ids = {agent_map[n] for n, *_ in stats["seeded"]}
    pending_agents = [n for n in sorted(all_agents) if agent_map[n] not in seeded_ids]
    stats["pending_agents"] = pending_agents

    if dry_run:
        print(f"[DRY-RUN] rows to insert: {len(all_seed_data)}")
        con.close()
        return stats

    # Backup
    respaldar_db(DB_PATH, "premig")   # nombre reservado, no colgado del reloj

    con2 = sqlite3.connect(str(DB_PATH))
    with con2:
        # Idempotent: delete existing seeded rows for these agents, then re-insert
        seeded_agent_ids = list(seeded_ids)
        placeholders = ",".join("?" * len(seeded_agent_ids))
        con2.execute(
            f"DELETE FROM agent_substat_preferences WHERE agente_id IN ({placeholders})",
            seeded_agent_ids,
        )
        con2.executemany(
            "INSERT INTO agent_substat_preferences (agente_id, substat, peso, fuente) VALUES (?,?,?,?)",
            all_seed_data,
        )

    fk = list(con2.execute("PRAGMA foreign_key_check"))
    ic = [r[0] for r in con2.execute("PRAGMA integrity_check")]
    stats["fk_violations"] = len(fk)
    stats["integrity"] = ic
    con2.close()
    con.close()
    return stats


def write_pending_report(pending_agents: list[str]):
    today = date.today().strftime("%Y%m%d")
    path = AUDIT_DIR / "preferences_pendientes.md"
    lines = [
        "# agent_substat_preferences — Agentes pendientes de seed",
        "",
        f"*Generado: {date.today()} — {len(pending_agents)} agentes sin preferencias Prydwen*",
        "",
        "Estos agentes caen al fallback de arquetipo en el scoring.",
        "Completar via `app/scripts/seed_substat_preferences.py` ampliado o scraper Prydwen (Hito 2.0.5b).",
        "",
        "| # | Agente |",
        "|---|--------|",
    ]
    for i, n in enumerate(pending_agents, 1):
        lines.append(f"| {i} | {n} |")
    lines += ["", "---", "*Ver Roadmap §2.0.5b para plan de scraping.*"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Seeding agent_substat_preferences {'[DRY-RUN]' if args.dry_run else ''}...")
    stats = seed(dry_run=args.dry_run)

    print(f"  Agentes seeded: {len(stats['seeded'])}")
    for nombre, n_rows, fuente in stats["seeded"]:
        print(f"    {nombre:15s} {n_rows} substats  fuente={fuente}")
    if stats["skipped"]:
        print(f"  SKIPPED: {stats['skipped']}")
    print(f"  Total filas: {stats['total_rows']}")

    if not args.dry_run:
        print(f"  FK violations: {stats.get('fk_violations')}")
        print(f"  Integrity: {stats.get('integrity')}")

    pending = stats.get("pending_agents", [])
    report = write_pending_report(pending)
    print(f"  Agentes pendientes (fallback arquetipo): {len(pending)}")
    print(f"  Reporte: {report}")

    if stats.get("fk_violations", 0) > 0:
        print("[FAIL] FK violations detectadas.")
        sys.exit(1)
    else:
        print("[OK] Seed completado.")


if __name__ == "__main__":
    main()
