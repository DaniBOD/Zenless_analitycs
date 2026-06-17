"""Analiza las líneas `[id_diag]` del app.log (instrumentación L.0) y arma el scorecard
del cuello de identidad de badges, cruzando contra el equip_map (verdad de tierra).

Por cada disco emitido en el QA en vivo (`qa_launch -ReadOnly -IdDiag`) la app loguea:
    [id_diag] id=<firma> slot=N assigned=<flujo-ancla> voted=<voto badge> samples=N
              grid_loc=N grid_match=N det_loc=N det_match=N grid_votes=[...] det_votes=[...]

Este parser responde: de los discos que el equip_map dice de quién son, ¿cuántos se
identifican bien por voto?, ¿cuántos quedan 'incierto'?, y cuando quedan incierto, ¿es
porque el GRID no localizó, porque el DETALLE no matcheó, o porque el voto eligió mal?
→ ubica el cuello (localización vs voto vs discriminación) antes de tocar L.1/L.2.

Uso:
    .venv/Scripts/python.exe tools/parse_id_diag.py                 # app.log + equip_map por defecto
    .venv/Scripts/python.exe tools/parse_id_diag.py <app.log> <equip_map.json>
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MAP = ROOT / "audit" / "equip_map_20260612.json"

_LINE = re.compile(
    r"\[id_diag\] id=(?P<id>.+?) slot=(?P<slot>\S+) assigned=(?P<assigned>.+?) "
    r"voted=(?P<voted>.+?) samples=(?P<samples>\d+) grid_loc=(?P<grid_loc>\d+) "
    r"grid_match=(?P<grid_match>\d+) det_loc=(?P<det_loc>\d+) det_match=(?P<det_match>\d+) "
    r"grid_votes=\[(?P<grid_votes>.*?)\] det_votes=\[(?P<det_votes>.*?)\]"
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _default_log() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "DaniBOD_ZZZ_Analytics", "app.log")


def main() -> int:
    log_path = sys.argv[1] if len(sys.argv) > 1 else _default_log()
    map_path = sys.argv[2] if len(sys.argv) > 2 else str(_DEFAULT_MAP)
    if not os.path.exists(log_path):
        print(f"No existe el log: {log_path}. ¿Corriste con -IdDiag?")
        return 1
    truth = {}
    if os.path.exists(map_path):
        em = json.loads(Path(map_path).read_text(encoding="utf-8"))
        truth = {k: v for k, v in em.items()}
    else:
        print(f"[warn] equip_map no encontrado ({map_path}) — sin verdad de tierra, solo conteos.")

    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    starts = [i for i, ln in enumerate(lines) if "Logging a archivo iniciado" in ln]
    if starts:
        lines = lines[starts[-1]:]   # solo la última sesión

    # Dedup por id (el último log gana — el disco pudo re-emitir tras parpadeo).
    rows: dict[str, dict] = {}
    for ln in lines:
        m = _LINE.search(ln)
        if m:
            rows[m.group("id")] = m.groupdict()
    if not rows:
        print(f"Sin líneas [id_diag] en {log_path}. ¿Corriste con DANIBOD_ID_DIAG=1?")
        return 1

    n = len(rows)
    in_map = sum(1 for k in rows if k in truth)
    grid_loc_any = sum(1 for r in rows.values() if int(r["grid_loc"]) > 0)
    det_loc_any = sum(1 for r in rows.values() if int(r["det_loc"]) > 0)
    no_loc = sum(1 for r in rows.values() if int(r["grid_loc"]) == 0 and int(r["det_loc"]) == 0)

    # Outcome del VOTO vs verdad (solo discos con verdad conocida).
    okv = wrv = incierto = 0
    inc_breakdown = Counter()
    wrongs = []
    assigned_ok = assigned_wr = 0
    for k, r in rows.items():
        t = truth.get(k)
        voted = r["voted"]
        if t is not None:
            if voted == "-" or not voted:
                incierto += 1
                # ¿por qué incierto? ¿localizó algo? ¿matcheó algo?
                if int(r["grid_loc"]) == 0 and int(r["det_loc"]) == 0:
                    inc_breakdown["sin localización (grid+det NOLOC)"] += 1
                elif int(r["grid_match"]) == 0 and int(r["det_match"]) == 0:
                    inc_breakdown["localizó pero ningún match (discriminación/guard)"] += 1
                else:
                    inc_breakdown["matcheó algo pero el voto no superó el guard"] += 1
            elif _norm(voted) == _norm(t):
                okv += 1
            else:
                wrv += 1
                wrongs.append((k[:40], voted, t))
        # assigned (flujo-ancla) vs verdad
        a = r["assigned"]
        if t is not None and a not in ("-", ""):
            if _norm(a) == _norm(t):
                assigned_ok += 1
            else:
                assigned_wr += 1

    def pct(x):
        return f"{x}/{n} = {x/max(1,n):.0%}"

    print(f"Log: {log_path}")
    print(f"equip_map: {map_path} ({len(truth)} discos)\n")
    print(f"Discos emitidos (únicos): {n}  |  con verdad en equip_map: {in_map}")
    print(f"\n— LOCALIZACIÓN —")
    print(f"  grid localizó ≥1 frame : {pct(grid_loc_any)}")
    print(f"  detalle localizó ≥1     : {pct(det_loc_any)}")
    print(f"  NINGUNO localizó        : {pct(no_loc)}")

    base = max(1, in_map)
    print(f"\n— VOTO vs verdad (sobre {in_map} con verdad) —")
    print(f"  ✅ correcto : {okv}/{in_map} = {okv/base:.0%}")
    print(f"  ❌ WRONG    : {wrv}/{in_map} = {wrv/base:.0%}   (RNF-02: debe ser 0)")
    print(f"  ⬜ incierto : {incierto}/{in_map} = {incierto/base:.0%}")
    if inc_breakdown:
        print("    desglose del incierto (= dónde está el cuello):")
        for r, c in inc_breakdown.most_common():
            print(f"      {c:3d}  {r}")
    if wrongs:
        print("  WRONGS (id→voto vs verdad):")
        for idp, v, t in wrongs[:15]:
            print(f"      {idp}…  {v}  ≠  {t}")
    print(f"\n— FLUJO-ANCLA (assigned) vs verdad —")
    print(f"  ✅ {assigned_ok}  |  ❌ {assigned_wr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
