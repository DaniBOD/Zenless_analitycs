"""Verifica que la re-estandarizacion quedo correcta en la DB."""
import sqlite3

con = sqlite3.connect("db/danibod_zzz_v2.db")
con.row_factory = sqlite3.Row

old_aliases = ["PV", "Ataque", "Defensa", "Prob Critico", "Maestria Anomalia", "Tasa Anomalia"]
all_ok = True
for alias in old_aliases:
    total = 0
    for field in ("main_stat", "sub1", "sub2", "sub3", "sub4"):
        total += con.execute(f"SELECT COUNT(*) FROM inventory_discs WHERE {field}=?", (alias,)).fetchone()[0]
    if total > 0:
        print(f"[FAIL] alias '{alias}' aun presente: {total} ocurrencias")
        all_ok = False

if all_ok:
    print("[OK] Ningun alias crudo en main_stat/sub1-4")

n_unidad = con.execute("SELECT COUNT(*) FROM inventory_discs WHERE unidad1 IS NOT NULL").fetchone()[0]
n_pct    = con.execute("SELECT COUNT(*) FROM inventory_discs WHERE unidad1='%'").fetchone()[0]
n_flat   = n_unidad - n_pct
print(f"[OK] unidad1 poblada: {n_unidad} discos ({n_pct} con '%', {n_flat} flat)")

r = con.execute("SELECT id, slot, main_stat, main_valor, unidad_main, sub1, val1, unidad1 FROM inventory_discs WHERE id=54").fetchone()
print(f"Disco 54 (era Tasa Anomalia slot6): main='{r['main_stat']}' ({r['unidad_main']}) sub1='{r['sub1']}' {r['unidad1']}={r['val1']}")

r2 = con.execute("SELECT id, slot, main_stat, main_valor, unidad_main, sub1, val1, unidad1 FROM inventory_discs WHERE id=1").fetchone()
print(f"Disco 1 (slot1 HP flat): main='{r2['main_stat']}' ({r2['unidad_main']}) sub1='{r2['sub1']}' {r2['unidad1']}={r2['val1']}")

# Tipos en val1 post-normalizacion
type_counts = {"REAL":0, "TEXT":0, "NULL":0, "INTEGER":0}
for row in con.execute("SELECT val1 FROM inventory_discs"):
    v = row[0]
    if v is None: type_counts["NULL"] += 1
    elif isinstance(v, float): type_counts["REAL"] += 1
    elif isinstance(v, int): type_counts["INTEGER"] += 1
    else: type_counts["TEXT"] += 1
print(f"val1 tipos post-normalizacion: {type_counts}")

con.close()
