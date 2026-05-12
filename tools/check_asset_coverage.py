"""
Diagnóstico de cobertura de assets: lista qué entidades de la DB
(sets, agentes) tienen vs no tienen imagen en disco.

Uso:
    python tools/check_asset_coverage.py
    python tools/check_asset_coverage.py --variant ico
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="extend", choices=["extend", "ico", "pj_stats"])
    args = parser.parse_args()

    from app.db.connection import get_connection
    from app.db.repositories import AgentRepo, DiscSetRepo
    from app.core.asset_resolver import audit_coverage, set_logo_path, agent_avatar_path

    con = get_connection()
    sr = DiscSetRepo(con)
    ar = AgentRepo(con)

    print(f"=== Cobertura de assets (variant={args.variant}) ===")
    res = audit_coverage(sr, ar, variant=args.variant)

    n_sets_hit = len(res["sets"]["hits"])
    n_sets_miss = len(res["sets"]["misses"])
    n_agents_hit = len(res["agents"]["hits"])
    n_agents_miss = len(res["agents"]["misses"])

    print(f"Sets:   {n_sets_hit} / {n_sets_hit + n_sets_miss}")
    if res["sets"]["misses"]:
        print("  MISSING:")
        for name in res["sets"]["misses"]:
            print(f"    - {name!r}")

    print(f"Agents: {n_agents_hit} / {n_agents_hit + n_agents_miss}")
    if res["agents"]["misses"]:
        print("  MISSING:")
        for name in res["agents"]["misses"]:
            print(f"    - {name!r}")

    print()
    print("=== Sample paths ===")
    samples_set = ["Yunkui Tales", "Branch & Blade Song", "Dawn's Bloom", "Astral Voice"]
    for en in samples_set:
        p = set_logo_path(en)
        ok = "OK " if p else "NO "
        print(f"  set/{ok} {en:<30} -> {p}")

    samples_ag = ["Yanagi", "Cissia", "Sporos", "Gatillo", "César", "N.° 0: Anby", "N.° 11", "Lucía"]
    for n in samples_ag:
        p = agent_avatar_path(n, variant=args.variant)
        ok = "OK " if p else "NO "
        print(f"  agt/{ok} {n:<30} -> {p}")

    # Exit code != 0 si hay misses
    if n_sets_miss + n_agents_miss > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
