"""
Hito 2.0.4 — Re-estandarización de inventory_discs.
Idempotente: correr varias veces no rompe nada.
- Normaliza main_stat, sub1-4 al canónico (stats_vocab.ALIASES).
- Convierte val1-4 a REAL y puebla unidad1-4 ('flat' o '%').
- Corrige main_valor + unidad_main.
- Genera reporte audit/restandarization_report_YYYYMMDD.md.

Uso:
    python app/scripts/restandarize_inventory_discs.py [--dry-run]
"""
import argparse
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.stats_vocab import normalize_stat_name, parse_value

DB_PATH = Path("db/danibod_zzz_v2.db")
AUDIT_DIR = Path("audit")


def restandarize(dry_run: bool = False) -> dict:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    rows = list(con.execute("SELECT * FROM inventory_discs"))

    stats = {
        "total": len(rows),
        "updated": 0,
        "rejected": [],
        "already_canon": 0,
    }

    updates = []

    for r in rows:
        payload: dict = {"id": r["id"]}
        had_change = False
        rejected_fields = []

        # --- main_stat + main_valor + unidad_main ---
        if r["main_stat"]:
            canon = normalize_stat_name(r["main_stat"])
            if canon is None:
                rejected_fields.append(("main_stat", r["main_stat"]))
            else:
                if canon != r["main_stat"]:
                    payload["main_stat"] = canon
                    had_change = True
                # Normalizar main_valor
                raw_mv = r["main_valor"]
                parsed = parse_value(raw_mv)
                if parsed:
                    val, unit = parsed
                    if r["main_valor"] != val or r["unidad_main"] != unit:
                        payload["main_valor"] = val
                        payload["unidad_main"] = unit
                        had_change = True

        # --- sub1-4 + val1-4 + unidad1-4 ---
        for i in (1, 2, 3, 4):
            sub_raw = r[f"sub{i}"]
            val_raw = r[f"val{i}"]
            if not sub_raw:
                continue
            canon = normalize_stat_name(sub_raw)
            if canon is None:
                rejected_fields.append((f"sub{i}", sub_raw))
                continue
            if canon != sub_raw:
                payload[f"sub{i}"] = canon
                had_change = True
            parsed = parse_value(val_raw)
            if parsed:
                val, unit = parsed
                current_val = r[f"val{i}"]
                current_unit = r[f"unidad{i}"]
                if current_val != val or current_unit != unit:
                    payload[f"val{i}"] = val
                    payload[f"unidad{i}"] = unit
                    had_change = True

        if rejected_fields:
            stats["rejected"].append({"id": r["id"], "fields": rejected_fields})
            continue

        if had_change:
            updates.append(payload)
            stats["updated"] += 1
        else:
            stats["already_canon"] += 1

    # --- Aplicar updates ---
    if not dry_run and updates:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(str(DB_PATH), str(DB_PATH.parent / f"danibod_zzz_v2.backup_premig_{ts}.db"))

        con2 = sqlite3.connect(str(DB_PATH))
        with con2:
            for payload in updates:
                cols = [k for k in payload if k != "id"]
                sql = f"UPDATE inventory_discs SET {', '.join(c+'=?' for c in cols)} WHERE id=?"
                con2.execute(sql, [payload[c] for c in cols] + [payload["id"]])

        fk = list(con2.execute("PRAGMA foreign_key_check"))
        ic = [r[0] for r in con2.execute("PRAGMA integrity_check")]
        stats["fk_violations"] = len(fk)
        stats["integrity"] = ic
        con2.close()

    con.close()
    return stats


def write_report(stats: dict, dry_run: bool):
    today = date.today().strftime("%Y%m%d")
    path = AUDIT_DIR / f"restandarization_report_{today}.md"
    lines = [
        f"# Re-estandarización inventory_discs — {date.today()}",
        "",
        f"**Modo:** {'DRY-RUN (sin cambios)' if dry_run else 'APLICADO'}",
        "",
        "## Resumen",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| Total discos | {stats['total']} |",
        f"| Actualizados | {stats['updated']} |",
        f"| Ya canónicos (sin cambio) | {stats['already_canon']} |",
        f"| Rechazados (stat desconocido) | {len(stats['rejected'])} |",
    ]
    if not dry_run:
        lines += [
            f"| FK violations post-update | {stats.get('fk_violations', 'N/A')} |",
            f"| Integrity check | {stats.get('integrity', 'N/A')} |",
        ]
    if stats["rejected"]:
        lines += [
            "",
            "## Stats rechazados (requieren revision manual)",
            "",
            "| disc_id | campo | valor |",
            "|---------|-------|-------|",
        ]
        for r in stats["rejected"]:
            for field, val in r["fields"]:
                lines.append(f"| {r['id']} | {field} | `{val}` |")
    else:
        lines += ["", "> Todos los stats mapearon al canon. 0 rechazados."]

    lines += ["", "---", f"*Generado por `app/scripts/restandarize_inventory_discs.py`*"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Analizar sin modificar la DB")
    args = parser.parse_args()

    print(f"Re-estandarizando {DB_PATH} {'[DRY-RUN]' if args.dry_run else ''}...")
    stats = restandarize(dry_run=args.dry_run)

    print(f"  Total: {stats['total']}")
    print(f"  Actualizados: {stats['updated']}")
    print(f"  Ya canonicos: {stats['already_canon']}")
    print(f"  Rechazados: {len(stats['rejected'])}")
    if not args.dry_run:
        print(f"  FK violations: {stats.get('fk_violations')}")
        print(f"  Integrity: {stats.get('integrity')}")

    report_path = write_report(stats, args.dry_run)
    print(f"Reporte: {report_path}")

    if stats["rejected"]:
        print("[!!] HAY STATS RECHAZADOS — revisar el reporte antes de continuar.")
        sys.exit(1)
    else:
        print("[OK] Re-estandarizacion completada sin rechazados.")


if __name__ == "__main__":
    main()
