"""Reporte de latencia por superficie — QA-06 §3.2.

Lee `metrics.db` (la que llena `DANIBOD_METRICS=1`) y contrasta cada superficie contra su
presupuesto de QA-06 §3.1. READ-ONLY: abre la DB en modo `ro` y no toca nada.

    .venv\\Scripts\\python.exe -m app.scripts.qa.report_latency
    .venv\\Scripts\\python.exe -m app.scripts.qa.report_latency --dias 1

Qué mirar: **el p99, no el promedio.** Un promedio bajo con una cola larga es exactamente el caso
que RNF-06 quiere evitar — el usuario nota la vez que llegó tarde, no las cien que llegaron a
tiempo.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core import metrics

# Presupuestos de QA-06 §3.1, en ms. Solo las superficies que hoy están instrumentadas; las demás
# se agregan cuando se les ponga el decorator.
_PRESUPUESTO = {
    "capturer": 50.0,
    "detector": 50.0,
    "ocr_text": 180.0,
    # Pantalla-a-log: el presupuesto de RNF-06 para "algo pasa → el usuario se entera". Incluye
    # la espera del tick rápido y la votación 2/3 del buffer temporal, que son latencia real.
    "frescura_estado_a_log": 500.0,
}

# `dispatch:SXX` no tiene un presupuesto fijo: su techo es la cadencia de ESE estado. Si el ciclo
# se acerca a su propia cadencia, el loop está saturado ahí — y recién entonces el cómputo es el
# problema. Se resuelve al vuelo consultando `polling_cadence_ms`.
_DISPATCH_PREFIJO = "dispatch:"


def _budget_dispatch(superficie: str) -> float | None:
    """Techo de un `dispatch:SXX`: la cadencia de polling de ESE estado."""
    if not superficie.startswith(_DISPATCH_PREFIJO):
        return None
    code = superficie[len(_DISPATCH_PREFIJO):]
    try:
        from app.core.detector import ScreenState, polling_cadence_ms
        return float(polling_cadence_ms(ScreenState(code, 1.0, "métricas")))
    except Exception:                                    # noqa: BLE001 — reporte, no producción
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dias", type=float, default=7.0, help="ventana a resumir (default 7)")
    args = ap.parse_args()

    path = metrics.db_path()
    print(f"metrics.db : {path}")
    if not path.exists():
        print("\n⚠️  no existe todavía. Corré la app con -Metrics (o DANIBOD_METRICS=1) y volvé.")
        return 1

    filas = metrics.resumen(dias=args.dias)
    if not filas:
        print(f"\n⚠️  sin muestras en los últimos {args.dias:g} días.")
        return 1

    print(f"\nÚltimos {args.dias:g} días · {sum(f['n'] for f in filas)} muestras\n")
    print(f"{'superficie':<16}{'n':>7}{'p50 ms':>10}{'p99 ms':>10}{'max ms':>10}"
          f"{'budget':>9}  veredicto")
    print("-" * 78)
    excedidas = 0
    for f in filas:
        bud = _PRESUPUESTO.get(f["superficie"]) or _budget_dispatch(f["superficie"])
        if bud is None:
            veredicto = "(sin presupuesto declarado)"
        elif f["p99"] > bud:
            veredicto = f"⚠️  p99 excede en {f['p99'] - bud:.0f} ms"
            excedidas += 1
        else:
            veredicto = f"ok · {100 * f['p99'] / bud:.0f}% del budget"
        print(f"{f['superficie']:<16}{f['n']:>7}{f['p50']:>10.1f}{f['p99']:>10.1f}"
              f"{f['max']:>10.1f}{(f'{bud:.0f}' if bud else '-'):>9}  {veredicto}")

    if excedidas:
        print(f"\n{excedidas} superficie(s) fuera de presupuesto → QA-06 §3.2 dice por dónde "
              f"seguir según cuál sea.")
    else:
        print("\nTodas dentro de presupuesto. Optimizar acá sería trabajar sin un problema que "
              "resolver — ver §9 del doc de latencia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
