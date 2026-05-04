"""
Hito 2.0.1 — Auditoría completa de inventory_discs.
Read-only. No modifica la DB.

Uso:
    python app/scripts/audit_inventory_discs.py
    python app/scripts/audit_inventory_discs.py --db path/to/other.db

Output: audit/inventory_discs_audit_YYYYMMDD.md
"""
import argparse
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DB_DEFAULT = Path("db/danibod_zzz_v2.db")
AUDIT_DIR = Path("audit")

# ---------------------------------------------------------------------------
# Tablas canónicas (RF-04 §7.2.1)
# ---------------------------------------------------------------------------
MAINS_FIXED = {1: "HP", 2: "ATK", 3: "DEF"}

MAINS_SLOT4 = {
    "Prob. Crítica", "Probabilidad de Crítico",
    "Daño Crítico",
    "Maestría de Anomalía",
    "HP%", "ATK%", "DEF%",
    "Tasa de Perforación",
}
MAINS_SLOT5 = {
    "Bono Daño Físico", "Bono Daño Fuego", "Bono Daño Hielo",
    "Bono Daño Eléctrico", "Bono Daño Éter",
    "HP%", "ATK%", "DEF%",
    "Tasa de Perforación",
}
MAINS_SLOT6 = {
    "HP%", "ATK%", "DEF%",
    "Maestría de Anomalía",
    "Impacto", "Impacto (%)",
    "Recarga de Energía", "Recuperación de Energía",
}

VALID_MAINS_VARIABLE = {4: MAINS_SLOT4, 5: MAINS_SLOT5, 6: MAINS_SLOT6}

VALID_SUBSTATS = {
    "HP", "HP%", "ATK", "ATK%", "DEF", "DEF%",
    "Prob. Crítica", "Probabilidad de Crítico",
    "Daño Crítico",
    "Perforación",
    "Maestría de Anomalía",
}

# Aliases observados → canónico (según audit previo + Roadmap 2.0.2)
KNOWN_ALIASES = {
    "PV": "HP", "Pv": "HP",
    "Ataque": "ATK",
    "Defensa": "DEF",
    "Prob Crítico": "Prob. Crítica",
    "Prob Crítica": "Prob. Crítica",
    "Maestría Anomalía": "Maestría de Anomalía",
    "PV %": "HP%",
    "ATK %": "ATK%",
    "DEF %": "DEF%",
}


def is_main_valid(slot: int, main: str | None) -> bool:
    if main is None:
        return False
    if slot in MAINS_FIXED:
        return main.strip() == MAINS_FIXED[slot]
    valid_set = VALID_MAINS_VARIABLE.get(slot, set())
    return main.strip() in valid_set


def classify_stat(name: str | None) -> str:
    """'canonical' | 'alias' | 'unknown'"""
    if name is None:
        return "unknown"
    s = name.strip()
    if s in VALID_SUBSTATS or s in VALID_MAINS_VARIABLE.get(4, set()) | VALID_MAINS_VARIABLE.get(5, set()) | VALID_MAINS_VARIABLE.get(6, set()) | set(MAINS_FIXED.values()):
        return "canonical"
    if s in KNOWN_ALIASES:
        return "alias"
    return "unknown"


def audit(db_path: Path) -> str:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = list(con.execute("SELECT * FROM inventory_discs"))
    total = len(rows)

    valid_set_ids = {r[0] for r in con.execute("SELECT id FROM disc_sets")}
    valid_agent_ids = {r[0] for r in con.execute("SELECT id FROM agents")}

    lines = []
    w = lines.append

    w(f"# Auditoría inventory_discs — {date.today()}")
    w("")
    w(f"**DB:** `{db_path}`")
    w(f"**Total discos:** {total}  ")
    w(f"**Fecha auditoría:** {date.today()}")
    w("")

    # ------------------------------------------------------------------
    # 1. Distribución de tipos en val1-val4
    # ------------------------------------------------------------------
    w("## 1. Distribución de tipos en val1–val4")
    w("")
    type_counts = defaultdict(Counter)
    for r in rows:
        for i in (1, 2, 3, 4):
            v = r[f"val{i}"]
            if v is None:
                t = "NULL"
            elif isinstance(v, float):
                t = "REAL"
            elif isinstance(v, int):
                t = "INTEGER"
            else:
                t = "TEXT"
            type_counts[f"val{i}"][t] += 1

    w("| Columna | NULL | REAL | INTEGER | TEXT |")
    w("|---------|-----:|-----:|--------:|-----:|")
    for col in ("val1", "val2", "val3", "val4"):
        c = type_counts[col]
        w(f"| `{col}` | {c['NULL']} | {c['REAL']} | {c['INTEGER']} | {c['TEXT']} |")
    w("")
    text_total = sum(type_counts[f"val{i}"]["TEXT"] for i in (1, 2, 3, 4))
    real_total = sum(type_counts[f"val{i}"]["REAL"] + type_counts[f"val{i}"]["INTEGER"] for i in (1, 2, 3, 4))
    w(f"> Total TEXT (requieren conversión): **{text_total}** · Total numérico: **{real_total}**")
    w("")

    # ------------------------------------------------------------------
    # 2. Inventario de strings únicos en main_stat, sub1-4
    # ------------------------------------------------------------------
    w("## 2. Strings únicos en main_stat y sub1–sub4")
    w("")
    stat_counter: Counter = Counter()
    stat_class: dict[str, str] = {}
    for r in rows:
        for field in ("main_stat", "sub1", "sub2", "sub3", "sub4"):
            v = r[field]
            if v:
                s = v.strip()
                stat_counter[s] += 1
                if s not in stat_class:
                    stat_class[s] = classify_stat(s)

    canonical_stats = {s for s, c in stat_class.items() if c == "canonical"}
    alias_stats = {s for s, c in stat_class.items() if c == "alias"}
    unknown_stats = {s for s, c in stat_class.items() if c == "unknown"}

    w(f"**Canónicos** ({len(canonical_stats)}): {', '.join(f'`{s}`' for s in sorted(canonical_stats))}")
    w("")
    if alias_stats:
        w(f"**Aliases** ({len(alias_stats)}) — mapean a un canónico conocido:")
        w("")
        w("| String observado | → Canónico | Ocurrencias |")
        w("|-----------------|-----------|------------|")
        for s in sorted(alias_stats):
            canon = KNOWN_ALIASES.get(s, "?")
            w(f"| `{s}` | `{canon}` | {stat_counter[s]} |")
        w("")

    if unknown_stats:
        w(f"**⚠️ Desconocidos** ({len(unknown_stats)}) — no mapean a ningún canónico ni alias conocido:")
        w("")
        w("| String | Ocurrencias |")
        w("|--------|------------|")
        for s in sorted(unknown_stats):
            w(f"| `{s}` | {stat_counter[s]} |")
        w("")
    else:
        w("> ✅ No hay strings desconocidos — todos canónicos o alias mapeables.")
        w("")

    # ------------------------------------------------------------------
    # 3. Valores fuera de rango
    # ------------------------------------------------------------------
    w("## 3. Valores fuera de rango")
    w("")
    out_of_range = []
    for r in rows:
        issues = []
        for i in (1, 2, 3, 4):
            rv = r[f"rolls{i}"]
            if rv is not None and rv > 5:
                issues.append(f"rolls{i}={rv}")
        if r["nivel"] is not None and r["nivel"] > 15:
            issues.append(f"nivel={r['nivel']}")
        total_rolls = sum(r[f"rolls{i}"] or 0 for i in (1, 2, 3, 4))
        if total_rolls > 5:
            issues.append(f"suma_rolls={total_rolls}")
        if issues:
            out_of_range.append((r["id"], r["slot"], issues))

    if out_of_range:
        w(f"⚠️ **{len(out_of_range)} disco(s) con valores fuera de rango:**")
        w("")
        w("| id | slot | Problemas |")
        w("|----|------|-----------|")
        for rid, slot, issues in out_of_range:
            w(f"| {rid} | {slot} | {', '.join(issues)} |")
        w("")
    else:
        w("> ✅ Ningún disco con valores fuera de rango.")
        w("")

    # ------------------------------------------------------------------
    # 4. FK rotas
    # ------------------------------------------------------------------
    w("## 4. Foreign keys rotas")
    w("")
    fk_broken = []
    for r in rows:
        issues = []
        if r["set_id"] not in valid_set_ids:
            issues.append(f"set_id={r['set_id']} no existe en disc_sets")
        if r["agente_asignado"] is not None and r["agente_asignado"] not in valid_agent_ids:
            issues.append(f"agente_asignado={r['agente_asignado']} no existe en agents")
        if issues:
            fk_broken.append((r["id"], issues))

    if fk_broken:
        w(f"⚠️ **{len(fk_broken)} disco(s) con FK rotas:**")
        w("")
        w("| id | Problema |")
        w("|----|---------|")
        for rid, issues in fk_broken:
            for iss in issues:
                w(f"| {rid} | {iss} |")
        w("")
    else:
        w("> ✅ Ninguna FK rota.")
        w("")

    # ------------------------------------------------------------------
    # 5. main_stat inválido por slot
    # ------------------------------------------------------------------
    w("## 5. main_stat inválido por slot")
    w("")
    invalid_main = []
    for r in rows:
        if not is_main_valid(r["slot"], r["main_stat"]):
            invalid_main.append((r["id"], r["slot"], r["main_stat"]))

    if invalid_main:
        w(f"⚠️ **{len(invalid_main)} disco(s) con main_stat inválido para su slot:**")
        w("")
        w("| id | slot | main_stat observado | Mains esperadas |")
        w("|----|------|---------------------|----------------|")
        for rid, slot, main in invalid_main:
            if slot in MAINS_FIXED:
                expected = MAINS_FIXED[slot]
            else:
                expected = ", ".join(sorted(VALID_MAINS_VARIABLE.get(slot, {"???"})))
            w(f"| {rid} | {slot} | `{main}` | {expected} |")
        w("")
    else:
        w("> ✅ Ningún main_stat inválido por slot.")
        w("")

    # ------------------------------------------------------------------
    # 6. Hallazgo conocido — ids 54 y 185
    # ------------------------------------------------------------------
    w("## 6. Hallazgo conocido — ids 54 y 185")
    w("")
    known_ids = [54, 185]
    rows_known = [r for r in rows if r["id"] in known_ids]
    if rows_known:
        w("Discos reportados en Roadmap §2.0.1 con `main_stat='Tasa Anomalía 30%'` en slot 6 (inválido):")
        w("")
        w("| id | slot | main_stat | sub1 | sub2 | sub3 | sub4 | nivel | equipado |")
        w("|----|------|-----------|------|------|------|------|-------|---------|")
        for r in rows_known:
            w(f"| {r['id']} | {r['slot']} | `{r['main_stat']}` | {r['sub1']} | {r['sub2']} | {r['sub3']} | {r['sub4']} | {r['nivel']} | {r['equipado']} |")
        w("")
        w("> **Diagnóstico probable:** confusión OCR/transcripción entre 'Tasa Anomalía' y 'Maestría de Anomalía'.")
        w("> Corrección pendiente en Hito 2.0.4 (re-estandarización).")
        w("")
    else:
        w("> ids 54 y 185 no encontrados en la DB — puede que ya hayan sido corregidos.")
        w("")

    # ------------------------------------------------------------------
    # 7. Resumen
    # ------------------------------------------------------------------
    w("## 7. Resumen ejecutivo")
    w("")
    w("| Categoría | Hallazgos |")
    w("|-----------|----------|")
    w(f"| Total discos auditados | {total} |")
    w(f"| Valores TEXT en val1-4 (requieren conversión) | {text_total} |")
    w(f"| Stats alias (mapean a canónico) | {len(alias_stats)} tipos distintos |")
    w(f"| Stats desconocidos | {len(unknown_stats)} |")
    w(f"| Discos con valores fuera de rango | {len(out_of_range)} |")
    w(f"| Discos con FK rotas | {len(fk_broken)} |")
    w(f"| Discos con main_stat inválido por slot | {len(invalid_main)} |")
    w("")
    w("**Acción requerida:** Ejecutar Hito 2.0.2 (stats_vocab.py) + Hito 2.0.3 (migración 06) + Hito 2.0.4 (re-estandarización).")
    w("")
    w("---")
    w("*Generado automáticamente por `app/scripts/audit_inventory_discs.py` · Read-only, no modifica DB.*")

    con.close()
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Auditoría read-only de inventory_discs")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = parser.parse_args()

    if not args.db.exists():
        print(f"[ERROR] DB no encontrada: {args.db}")
        return

    print(f"Auditando {args.db} ...")
    report = audit(args.db)

    today = date.today().strftime("%Y%m%d")
    out_path = AUDIT_DIR / f"inventory_discs_audit_{today}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Reporte generado: {out_path}")

    # Resumen rapido en consola (ASCII-safe)
    for line in report.splitlines():
        if line.startswith("| ") and "Hallazgos" not in line and "---" not in line:
            try:
                print(f"  {line}")
            except UnicodeEncodeError:
                print(f"  {line.encode('ascii', errors='replace').decode('ascii')}")


if __name__ == "__main__":
    main()
