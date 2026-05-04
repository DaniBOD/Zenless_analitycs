"""Valida el estado post-onboarding Cissia sin re-aplicar SQL."""
import sqlite3
import sys
from pathlib import Path

con = sqlite3.connect("db/danibod_zzz_v2.db")
con.row_factory = sqlite3.Row

print("--- PRAGMA foreign_key_check ---")
fk = list(con.execute("PRAGMA foreign_key_check"))
print(f"  FK violations: {len(fk)} (esperado 0)")

print("--- PRAGMA integrity_check ---")
ic = [r[0] for r in con.execute("PRAGMA integrity_check")]
print(f"  Result: {ic}")

print("\n--- Smoke checks ---")
checks = [
    ("agents Cissia (=1)",            "SELECT COUNT(*) FROM agents WHERE nombre='Cissia'", 1),
    ("thresholds Cissia (=5)",        "SELECT COUNT(*) FROM agent_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia')", 5),
    ("score_thresholds Cissia (=1)",  "SELECT COUNT(*) FROM agent_score_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia')", 1),
    ("awakening placeholder (=1)",    "SELECT COUNT(*) FROM agent_awakenings WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia')", 1),
    ("pj_weapon_synergy Cissia (=6)", "SELECT COUNT(*) FROM pj_weapon_synergy WHERE pj_id=(SELECT id FROM agents WHERE nombre='Cissia')", 6),
    ("discos equipados Cissia (=6)",  "SELECT COUNT(*) FROM inventory_discs WHERE agente_asignado=(SELECT id FROM agents WHERE nombre='Cissia') AND equipado=1", 6),
    ("discos nuevos Cissia (=2)",     "SELECT COUNT(*) FROM inventory_discs WHERE agente_asignado=(SELECT id FROM agents WHERE nombre='Cissia') AND notas LIKE '%nuevo%'", 2),
    ("total agents (=46)",            "SELECT COUNT(*) FROM agents", 46),
    ("total inventory_discs (=334)",  "SELECT COUNT(*) FROM inventory_discs", 334),
    ("total agent_thresholds (=108)", "SELECT COUNT(*) FROM agent_thresholds", 108),
    ("total score_thresholds (=46)",  "SELECT COUNT(*) FROM agent_score_thresholds", 46),
    ("total awakenings (=6)",         "SELECT COUNT(*) FROM agent_awakenings", 6),
    ("total pj_weapon_synergy (=276)","SELECT COUNT(*) FROM pj_weapon_synergy", 276),
]

all_ok = True
for label, query, expected in checks:
    val = con.execute(query).fetchone()[0]
    ok = val == expected
    if not ok:
        all_ok = False
    status = "[OK]  " if ok else "[FAIL]"
    print(f"  {status} {label}: {val}")

con.close()
if all_ok:
    print("\n[OK] Onboarding Cissia validado correctamente.")
else:
    print("\n[!!] Revisar los checks fallidos.")
    sys.exit(1)
