"""Aplica migración 09 (ADD protected_build a agents)."""
import sqlite3, shutil
from datetime import datetime
from pathlib import Path

DB  = Path("db/danibod_zzz_v2.db")
SQL = Path("db/migrations/2026-05-05_09_add_protected_build.sql")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = DB.parent / f"danibod_zzz_v2.backup_premig_{ts}.db"
shutil.copy(DB, backup)
print(f"Backup: {backup}")

sql = SQL.read_text(encoding="utf-8")
txn = sql.split("COMMIT;", 1)[0] + "COMMIT;"

con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row
con.executescript(txn)
print("Transaccion OK")

fk = list(con.execute("PRAGMA foreign_key_check"))
ic = [r[0] for r in con.execute("PRAGMA integrity_check")]
print(f"FK violations: {len(fk)}, Integrity: {ic}")

row = con.execute("SELECT COUNT(*) total, SUM(protected_build) prot FROM agents").fetchone()
print(f"agents: {row['total']} totales, {row['prot'] or 0} con protected_build=1")

cols = [r[1] for r in con.execute("PRAGMA table_info(agents)")]
assert "protected_build" in cols, "protected_build no se agregó"
print("[OK] Migración 09 aplicada.")
con.close()
