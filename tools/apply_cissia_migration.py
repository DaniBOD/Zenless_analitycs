"""
Aplica el SQL de onboarding de Cissia y muestra los smoke checks.
Uso: python tools/apply_cissia_migration.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("db/danibod_zzz_v2.db")
SQL_PATH = Path("db/migrations_pendientes/2026-05-04_onboarding_cissia.sql")


def run():
    sql = SQL_PATH.read_text(encoding="utf-8")

    # Separar la transaccion de los PRAGMAs/SELECTs de validacion
    parts = sql.split("COMMIT;", 1)
    transaccion = parts[0] + "COMMIT;"

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    print("Ejecutando transaccion principal...")
    con.executescript(transaccion)
    print("Transaccion completada.")

    print("\n--- PRAGMA foreign_key_check ---")
    fk_issues = list(con.execute("PRAGMA foreign_key_check"))
    if fk_issues:
        print(f"  [FAIL] {len(fk_issues)} FK violations:")
        for r in fk_issues:
            print(f"    {dict(r)}")
    else:
        print("  [OK] 0 FK violations")

    print("\n--- PRAGMA integrity_check ---")
    ic = [r[0] for r in con.execute("PRAGMA integrity_check")]
    if ic == ["ok"]:
        print("  [OK] integrity check passed")
    else:
        print(f"  [FAIL] Issues: {ic}")

    print("\n--- Smoke checks ---")
    checks = [
        ("agents Cissia",             "SELECT COUNT(*) FROM agents WHERE nombre='Cissia'", 1),
        ("thresholds (=5)",           "SELECT COUNT(*) FROM agent_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia')", 5),
        ("score_thresholds (=1)",     "SELECT COUNT(*) FROM agent_score_thresholds WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia')", 1),
        ("awakening placeholder (=1)","SELECT COUNT(*) FROM agent_awakenings WHERE agente_id=(SELECT id FROM agents WHERE nombre='Cissia')", 1),
        ("pj_weapon_synergy (=6)",    "SELECT COUNT(*) FROM pj_weapon_synergy WHERE pj_id=(SELECT id FROM agents WHERE nombre='Cissia')", 6),
        ("discos equipados (=6)",     "SELECT COUNT(*) FROM inventory_discs WHERE agente_asignado=(SELECT id FROM agents WHERE nombre='Cissia') AND equipado=1", 6),
        ("discos nuevos (=2)",        "SELECT COUNT(*) FROM inventory_discs WHERE agente_asignado=(SELECT id FROM agents WHERE nombre='Cissia') AND notas LIKE '%nuevo%'", 2),
        ("total agents (=46)",        "SELECT COUNT(*) FROM agents", 46),
        ("total inventory_discs (=334)", "SELECT COUNT(*) FROM inventory_discs", 334),
    ]

    all_ok = True
    for label, query, expected in checks:
        val = con.execute(query).fetchone()[0]
        status = "[OK]  " if val == expected else "[FAIL]"
        if val != expected:
            all_ok = False
        print(f"  {status} {label}: got {val} (expected {expected})")

    con.close()

    if not all_ok:
        print("\n[!!] Algunos checks fallaron. Revisar antes de continuar.")
        sys.exit(1)
    else:
        print("\n[OK] Todos los smoke checks pasaron.")


if __name__ == "__main__":
    run()
