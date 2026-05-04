"""Aplica migración 07 (columnas unidad* + índices)."""
import sqlite3
from pathlib import Path

sql = Path("db/migrations/2026-05-04_07_normalize_inventory_discs.sql").read_text(encoding="utf-8")
parts = sql.split("COMMIT;", 1)
txn = parts[0] + "COMMIT;"

con = sqlite3.connect("db/danibod_zzz_v2.db")
con.executescript(txn)
print("Transaccion OK")

fk = list(con.execute("PRAGMA foreign_key_check"))
ic = [r[0] for r in con.execute("PRAGMA integrity_check")]
print(f"FK violations: {len(fk)}, Integrity: {ic}")

cols = [r[1] for r in con.execute("PRAGMA table_info(inventory_discs)") if r[1].startswith("unidad")]
print(f"Columnas unidad agregadas ({len(cols)}): {cols}")
con.close()
print("[OK] Migracion 07 aplicada.")
