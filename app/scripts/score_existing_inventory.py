"""
Hito 2.3 — Scoring batch de los 334 discos del inventario.
- Evalúa cada disco contra los 46 agentes del roster.
- Inserta/actualiza inventory_disc_evaluations (1 fila por disco, mejor candidato).
- Actualiza inventory_discs.score_evaluacion con el score normalizado.
- Idempotente: DELETE+INSERT por disco en cada ejecucion.
- Genera audit/batch_score_<YYYYMMDD>.md.

Uso:
    python app/scripts/score_existing_inventory.py [--dry-run] [--verbose]
"""
import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db.connection import get_connection, respaldar_db
from app.db.repositories import AgentRepo, ArchetypeRepo, DiscSetRepo, InventoryDiscRepo
from app.core.score_normalizer import ScoringContext
from app.core.recommender import recomendar, recommendation_to_json

DB_PATH = Path("db/danibod_zzz_v2.db")
AUDIT_DIR = Path("audit")
TRIGGER = "batch_score_2.3"


def run_batch(dry_run: bool = False, verbose: bool = False) -> dict:
    t0 = time.perf_counter()

    # Repos use a read connection (no write)
    con_r = get_connection()
    agent_repo  = AgentRepo(con_r)
    arch_repo   = ArchetypeRepo(con_r)
    set_repo    = DiscSetRepo(con_r)
    disc_repo   = InventoryDiscRepo(con_r)
    ctx         = ScoringContext()

    discs = disc_repo.get_all_active()
    if verbose:
        print(f"Evaluando {len(discs)} discos contra {len(agent_repo.get_all())} agentes...")

    results: list[dict] = []
    for disc in discs:
        rec = recomendar(disc, agent_repo, arch_repo, set_repo, ctx)
        results.append({
            "disc_id":    disc.id,
            "score_norm": rec.score_norm,
            "tipo":       rec.tipo,
            "agente_id":  rec.agente_id,
            "detalle":    recommendation_to_json(rec),
        })
        if verbose:
            print(f"  disc {disc.id:4d}  score={rec.score_norm:.3f}  {rec.tipo:8s}  {rec.agente_nombre or '-'}")

    elapsed = time.perf_counter() - t0

    stats = {
        "total":    len(discs),
        "equipar":  sum(1 for r in results if r["tipo"] == "equipar"),
        "mejorar":  sum(1 for r in results if r["tipo"] == "mejorar"),
        "reserva":  sum(1 for r in results if r["tipo"] == "reserva"),
        "descartar":sum(1 for r in results if r["tipo"] == "descartar"),
        "score_max":max((r["score_norm"] for r in results), default=0.0),
        "score_avg":sum(r["score_norm"] for r in results) / max(len(results), 1),
        "elapsed_s":elapsed,
    }
    con_r.close()

    if dry_run:
        return stats

    # --- Write ---
    respaldar_db(DB_PATH, "premig")   # nombre reservado, no colgado del reloj

    con_w = sqlite3.connect(str(DB_PATH))
    fecha = date.today().isoformat()

    with con_w:
        disc_ids = [r["disc_id"] for r in results]
        placeholders = ",".join("?" * len(disc_ids))

        # Idempotent: delete existing batch evaluations for these discs
        con_w.execute(
            f"DELETE FROM inventory_disc_evaluations WHERE inventory_disc_id IN ({placeholders}) AND trigger_evento=?",
            disc_ids + [TRIGGER],
        )

        # Insert new evaluations
        con_w.executemany(
            """INSERT INTO inventory_disc_evaluations
               (inventory_disc_id, fecha, trigger_evento, recomendacion, score, detalle_json)
               VALUES (?,?,?,?,?,?)""",
            [
                (r["disc_id"], fecha, TRIGGER, r["tipo"], round(r["score_norm"], 6), r["detalle"])
                for r in results
            ],
        )

        # Update score_evaluacion in inventory_discs
        con_w.executemany(
            "UPDATE inventory_discs SET score_evaluacion=? WHERE id=?",
            [(round(r["score_norm"], 6), r["disc_id"]) for r in results],
        )

    fk = list(con_w.execute("PRAGMA foreign_key_check"))
    ic = [r[0] for r in con_w.execute("PRAGMA integrity_check")]
    stats["fk_violations"] = len(fk)
    stats["integrity"] = ic
    con_w.close()

    return stats


def write_report(stats: dict, dry_run: bool):
    today = date.today().strftime("%Y%m%d")
    path = AUDIT_DIR / f"batch_score_{today}.md"
    lines = [
        f"# Batch scoring inventory_discs — {date.today()}",
        "",
        f"**Modo:** {'DRY-RUN (sin cambios)' if dry_run else 'APLICADO'}",
        "",
        "## Resumen",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| Total discos evaluados | {stats['total']} |",
        f"| Equipar | {stats['equipar']} |",
        f"| Mejorar | {stats['mejorar']} |",
        f"| Reserva | {stats['reserva']} |",
        f"| Descartar | {stats['descartar']} |",
        f"| Score máximo | {stats['score_max']:.4f} |",
        f"| Score promedio | {stats['score_avg']:.4f} |",
        f"| Tiempo total | {stats['elapsed_s']:.2f}s |",
    ]
    if not dry_run:
        lines += [
            f"| FK violations | {stats.get('fk_violations', 'N/A')} |",
            f"| Integrity check | {stats.get('integrity', 'N/A')} |",
        ]
    lines += [
        "",
        "---",
        f"*Trigger: `{TRIGGER}` · Script: `app/scripts/score_existing_inventory.py`*",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print(f"Batch scoring {'[DRY-RUN] ' if args.dry_run else ''}...")
    stats = run_batch(dry_run=args.dry_run, verbose=args.verbose)

    print(f"  Total: {stats['total']}")
    print(f"  equipar={stats['equipar']}  mejorar={stats['mejorar']}  reserva={stats['reserva']}  descartar={stats['descartar']}")
    print(f"  score_max={stats['score_max']:.4f}  score_avg={stats['score_avg']:.4f}")
    print(f"  Tiempo: {stats['elapsed_s']:.2f}s")

    if not args.dry_run:
        print(f"  FK violations: {stats.get('fk_violations')}")
        print(f"  Integrity: {stats.get('integrity')}")

    report_path = write_report(stats, args.dry_run)
    print(f"  Reporte: {report_path}")

    if stats.get("fk_violations", 0) > 0:
        print("[FAIL] FK violations.")
        sys.exit(1)
    else:
        print("[OK] Batch scoring completado.")


if __name__ == "__main__":
    main()
