"""Aplica migración 08 (corrige mains_5/6 en disc_archetypes)."""
import sqlite3, shutil
from datetime import datetime
from pathlib import Path

DB = Path("db/danibod_zzz_v2.db")
SQL = Path("db/migrations/2026-05-04_08_fix_archetypes_mains.sql")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = DB.parent / f"danibod_zzz_v2.backup_premig_{ts}.db"
shutil.copy(DB, backup)
print(f"Backup: {backup}")

sql = SQL.read_text(encoding="utf-8")
parts = sql.split("COMMIT;", 1)
txn = parts[0] + "COMMIT;"

con = sqlite3.connect(str(DB))
con.executescript(txn)
print("Transaccion OK")

fk = list(con.execute("PRAGMA foreign_key_check"))
ic = [r[0] for r in con.execute("PRAGMA integrity_check")]
print(f"FK violations: {len(fk)}, Integrity: {ic}")

rows = list(con.execute("SELECT code, mains_5, mains_6 FROM disc_archetypes"))
for r in rows:
    print(f"  {r[0]}: mains_5={r[1][:50]}... mains_6={r[2]}")

con.close()
print("[OK] Migracion 08 aplicada.")
