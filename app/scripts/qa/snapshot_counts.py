"""
QA-07 Fase A/G — snapshot de conteos de filas de toda la DB.

Emite JSON por stdout con `COUNT(*)` de cada tabla de usuario, para poder
diffear el estado pre-patch contra el post-patch y entender cada cambio.

Uso (desde la raíz del repo):

    python app/scripts/qa/snapshot_counts.py > Documentacion/QA/evidencia/baseline_prepatch_<TS>.json
    python app/scripts/qa/snapshot_counts.py --db db/otra.db

Read-only: abre la DB en modo `ro` vía URI, así no puede escribir ni siquiera
por accidente (RNF-01).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path("db/danibod_zzz_v2.db")


def snapshot(db_path: Path) -> dict:
    """Devuelve {tabla: n_filas} + metadata, leyendo la DB en modo read-only."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        tablas = [
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tablas}
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rotas = len(con.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        con.close()

    return {
        "db": str(db_path),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "n_tablas": len(counts),
        "integrity_check": integrity,
        "foreign_key_check_rows": fk_rotas,
        "counts": counts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="ruta a la DB SQLite")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"ERROR: no existe {args.db}", file=sys.stderr)
        return 1

    json.dump(snapshot(args.db), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
