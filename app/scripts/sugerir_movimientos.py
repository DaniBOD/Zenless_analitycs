"""Corre el motor de discos sobre TODO el inventario y deja las sugerencias en `audit/sugerencias/`.

Pedido de Daniel (2026-09-22): "la DB tiene más de 300 discos y si cargo mi roster ya podrías
sugerir de un comienzo qué disco puede ser bueno para mis personajes". Es la etapa 1, paso 7.

Qué sugiere, con las reglas de sus casos:
  - **equipar** un disco LIBRE a quien más le mejora el build (compara contra lo que ya lleva);
  - **mover** un disco de un PJ a otro sólo si el que lo tiene NO pierde, contando un disco libre
    como reemplazo;
  - **mejorar** un disco sin terminar que promete, **reserva** uno bueno que hoy no le gana a nadie,
    **descartar** el resto de los libres;
  - **armar_2pc** (R24, 2026-09-27): dos discos libres que cambian el 2pc por el siguiente de la
    guía para que el PJ CUMPLA un stat fijo, sin tocar el 4pc.

Las sugerencias no se pisan: se toman de la de más ganancia para abajo, y una que pide un slot o
un disco ya comprometido por otra queda como "en conflicto" en vez de desaparecer. Cada una está
calculada contra el estado de HOY, no contra el que dejarían las anteriores.

El cálculo vive en `app/core/sugerencias.py` (la pantalla Discos usa el mismo).

**Sólo lee la DB de dominio** (se abre `mode=ro` y se verifica el sha256 antes y después: B3). Lo
único que escribe es el reporte.

Uso (desde la raíz del repo):

    python app/scripts/sugerir_movimientos.py
    python app/scripts/sugerir_movimientos.py --db otra.db
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.audit_paths import reservar_rutas, resolve_audit_dir  # noqa: E402
# El cálculo vive en `app/core/sugerencias.py` (lo usa también la pantalla Discos). Se re-exporta:
# los tests y quien importaba estos nombres desde el script siguen andando.
from app.core.sugerencias import (Sugerencia, _describir, generar,  # noqa: E402,F401
                                  resolver_conflictos)

DB_DEFAULT = Path("db/danibod_zzz_v2.db")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _markdown(rep: dict) -> str:
    t = rep["totales"]
    out = ["# Sugerencias del motor de discos", "",
           f"Inventario activo: **{t['inventario_activo']}** discos ({t['libres']} libres). "
           f"Equipados sin cambio: {t['equipados_sin_cambio']}. Sin nivel leído: {t['sin_nivel_leido']}.",
           "", "Cada sugerencia está calculada contra el estado de HOY. Las que se pisarían entre sí",
           "quedan marcadas **en conflicto**: se toma la de más ganancia.", ""]
    titulos = [("mover", "Mover de un PJ a otro (el que lo tiene NO pierde)"),
               ("equipar", "Equipar un disco libre"),
               ("armar_2pc", "Cambiar el 2pc para cumplir un stat fijo (R24, de a dos discos)"),
               ("mejorar", "Vale la pena subir"),
               ("reserva", "Guardar para un PJ futuro"),
               ("guardar", "Guardar sin subir (sirve, pero subido no le ganaría a nadie de hoy)"),
               ("descartar", "Descartar")]
    for tipo, titulo in titulos:
        lista = rep["sugerencias"].get(tipo, [])
        out += [f"## {titulo} — {len(lista)}", ""]
        if not lista:
            out += ["(ninguna)", ""]
            continue
        for s in lista:
            linea = f"- {s['disco']}"
            if s["destino"]:
                linea += f" → **{s['destino']}**"
                if s.get("prioridad", "normal") != "normal":
                    linea += f" (prioridad {s['prioridad']})"
            if s["origen"]:
                linea += f" (sale de {s['origen']}"
                linea += f"; lo repone el #{s['reemplazo_id']})" if s["reemplazo_id"] else "; queda vacío y no pierde)"
            if s.get("nota"):
                linea += f" — {s['nota']}"
            if s["delta"] is not None:
                linea += f" · mejora {s['delta']:+.2f}"
            if s["conflicto"]:
                linea += f" · ⚠️ en conflicto: {s['conflicto']}"
            out.append(linea)
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sugerencias del motor de discos sobre todo el inventario.")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = ap.parse_args(argv)
    antes = _sha256(args.db)
    rep = generar(args.db)
    if _sha256(args.db) != antes:
        print("ERROR: la DB de dominio cambió durante un proceso de sólo lectura (B3)", file=sys.stderr)
        return 3
    rutas = reservar_rutas(resolve_audit_dir() / "sugerencias", "sugerencias_discos", ("json", "md"))
    rutas[0].write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    rutas[1].write_text(_markdown(rep), encoding="utf-8")
    t = rep["totales"]
    print(f"{t['inventario_activo']} discos · " + " · ".join(
        f"{k} {t.get(k, 0)}" for k in ("mover", "equipar", "armar_2pc", "mejorar", "reserva", "guardar", "descartar")))
    print(f"→ {rutas[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
