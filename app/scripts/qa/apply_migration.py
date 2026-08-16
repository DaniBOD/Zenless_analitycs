"""
Runner de migraciones SQL — reemplaza al CLI `sqlite3` (que no está instalado
en la máquina de DaniBOD; ver CLAUDE.md §3.1, que lo asumía disponible).

Hace cumplir RNF-01 por construcción:
  1. Backup automático a db/danibod_zzz_v2.backup_premig_<TS>.db ANTES de tocar nada.
  2. Ejecuta el .sql sentencia por sentencia, imprimiendo el resultado de las que
     devuelven filas (los smoke checks `expected_N` y los PRAGMA de validación).
  3. Si algo revienta, aborta y te dice con qué comando restaurar.

Uso (desde la raíz del repo):

    python app/scripts/qa/apply_migration.py db/migrations/2026-07-28_14_....sql
    python app/scripts/qa/apply_migration.py <sql> --db db/otra.db --no-backup

`--dry-run` corre todo dentro de una transacción que se revierte al final: sirve
para ver los smoke checks sin persistir. Ojo: no sirve para migraciones que
hacen DDL con su propio BEGIN/COMMIT (como los rebuilds de tabla), porque el
COMMIT interno ya persiste — para esas confiá en el backup.

Tampoco sirve si el .sql abre su PROPIO `BEGIN TRANSACTION`, que es como están
escritas casi todas las de onboarding: revienta en la sentencia 01 con "cannot
start a transaction within a transaction". Para esas, el ensayo es contra una
COPIA de la DB, que además prueba más que el dry-run (los smoke checks corren
sobre datos ya commiteados, igual que en la corrida real):

    cp db/danibod_zzz_v2.db /tmp/ensayo.db
    python app/scripts/qa/apply_migration.py <sql> --db /tmp/ensayo.db --no-backup
    # revisar los expected_N; recién ahí, la corrida real sobre la DB buena

`PRAGMA foreign_keys` se deja en OFF durante la ejecución: los rebuilds de tabla
(DROP + RENAME) lo requieren, si no SQLite reescribe las FK de las tablas que
apuntan a la que se renombra. Al terminar se corre `foreign_key_check` igual.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path("db/danibod_zzz_v2.db")


def split_statements(sql: str) -> list[str]:
    """Parte un script SQL en sentencias completas usando el parser de SQLite."""
    sentencias: list[str] = []
    buffer = ""
    for linea in sql.splitlines(keepends=True):
        buffer += linea
        if sqlite3.complete_statement(buffer):
            texto = buffer.strip()
            if texto:
                sentencias.append(texto)
            buffer = ""
    if buffer.strip():
        sentencias.append(buffer.strip())
    return sentencias


def _resumen(sentencia: str, ancho: int = 70) -> str:
    """Primera línea no-comentaria de la sentencia, recortada."""
    for linea in sentencia.splitlines():
        limpia = linea.strip()
        if limpia and not limpia.startswith("--"):
            return limpia[:ancho]
    return sentencia[:ancho]


def aplicar(sql_path: Path, db_path: Path, *, hacer_backup: bool, dry_run: bool) -> int:
    sql = sql_path.read_text(encoding="utf-8")
    sentencias = split_statements(sql)

    print(f"DB       : {db_path}")
    print(f"Migración: {sql_path}")
    print(f"Sentencias: {len(sentencias)}")

    backup: Path | None = None
    if hacer_backup and not dry_run:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path.with_name(f"{db_path.stem}.backup_premig_{ts}.db")
        shutil.copy2(db_path, backup)
        print(f"Backup   : {backup}")
    print("-" * 78)

    con = sqlite3.connect(db_path, isolation_level=None)
    con.execute("PRAGMA foreign_keys=OFF")
    if dry_run:
        con.execute("BEGIN")

    try:
        for i, sentencia in enumerate(sentencias, 1):
            cur = con.execute(sentencia)
            filas = cur.fetchall() if cur.description else []
            if filas:
                cols = [d[0] for d in cur.description]
                print(f"[{i:02d}] {_resumen(sentencia)}")
                for fila in filas:
                    print("     " + " | ".join(f"{c}={v}" for c, v in zip(cols, fila)))
            else:
                print(f"[{i:02d}] {_resumen(sentencia)}  -> ok")
    except sqlite3.Error as exc:
        print("-" * 78)
        print(f"FALLÓ en la sentencia [{i:02d}]: {exc}", file=sys.stderr)
        print(f"  {sentencia[:400]}", file=sys.stderr)
        try:
            con.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        con.close()
        if backup:
            print(f"\nRestaurar con:\n  cp {backup} {db_path}", file=sys.stderr)
        return 1

    if dry_run:
        con.execute("ROLLBACK")
        print("-" * 78)
        print("DRY-RUN: revertido (lo que ya commiteó la propia migración persiste).")

    con.execute("PRAGMA foreign_keys=ON")
    con.close()
    print("-" * 78)
    print("OK — revisá arriba que cada `expected_N` valga exactamente N.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Aplica un .sql de migración con backup previo (RNF-01).")
    ap.add_argument("sql", type=Path, help="ruta al archivo .sql de migración")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="ruta a la DB SQLite")
    ap.add_argument("--no-backup", action="store_true", help="saltear el backup (desaconsejado)")
    ap.add_argument("--dry-run", action="store_true", help="ejecutar y revertir al final")
    args = ap.parse_args()

    for p in (args.sql, args.db):
        if not p.exists():
            print(f"ERROR: no existe {p}", file=sys.stderr)
            return 1

    return aplicar(args.sql, args.db, hacer_backup=not args.no_backup, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
