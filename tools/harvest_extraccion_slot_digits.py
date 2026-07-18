"""Cosecha los badges de dígito de slot del modal "Obtenido" (S22, farmeo por baterías).

Por qué existe (medido 2026-07-16 sobre los 4 fixtures de `20_Extraccion_Baterias/`):

  * El OCR es estructuralmente malo con el glifo estilizado de ZZZ. Por clase, Tesseract
    devuelve: 1 → 'LV:'/'IV:'/'y.' (NUNCA un dígito) · 4 → 'a' SIEMPRE · 6 → '(7'/'(FF'/'e:'.
    Solo 2/3/5 salen fiables. Y 'a' no se puede mapear a 4: un '2' por la pasada Otsu y un '3'
    de las refs de S5 también devuelven 'a' → mapearlo convertiría 2s y 3s en 4s en silencio.
  * El `SlotDigitMatcher` (NCC del residuo) SÍ resuelve este badge: leave-one-sample-out sobre
    los 11 tiles da 9/9 aciertos, con los tres '4' en score 0.999.
  * Pero las refs de S2 (`slot_digits/`) y de S5 (`slot_digits_s5/`) NO transfieren: abstienen
    en los 11 tiles (el matcher resta el template promedio de SU set, así que un badge de otro
    estilo deja un residuo dominado por la diferencia de estilo). Peor: usarlas como base hace
    que un dígito ausente se conteste con score ~0.94 y EQUIVOCADO (11/11 wrong). Cada pantalla
    necesita su propio set — por eso ya existen dos.

De ahí el gate de 6 clases en `parser_extraccion._get_slot_matcher_extraccion()`: con clases
faltantes el matcher NO abstiene, INVENTA. Medido por leave-one-CLASS-out sobre estos 11 tiles:
6 de 11 devolvieron un dígito equivocado con score hasta 0.799, solapado con los aciertos
(mínimo 0.755) → no hay umbral que los separe.

Los 4 fixtures dan {2:3, 3:1, 4:3, 5:2, 6:2} y CERO del slot 1, así que el set queda incompleto
y el matcher permanece apagado (se sigue usando solo OCR, 8/11 con 0 errores). Para completarlo
alcanza con UNA captura del "Obtenido" que contenga un disco de slot 1 — sale sola en cualquier
sesión de farmeo, sin gastar baterías de más. Dejarla en `20_Extraccion_Baterias/` y correr:

    .venv/Scripts/python.exe tools/harvest_extraccion_slot_digits.py --write

El script NO etiqueta solo: vuelca los crops a `--out` con el slot que dice el OCR (o `X` si se
abstiene) en el nombre, para revisarlos a ojo y renombrar el prefijo si hace falta. El prefijo
`<digito>_` es lo único que lee `SlotDigitMatcher.from_resources`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import app.core.parser_extraccion as PE   # noqa: E402

_FIXTURES = (REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
             / "20_Extraccion_Baterias")
_OUT = REPO / "app" / "resources" / "slot_digits_extraccion"


def _load(path: Path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=_FIXTURES,
                    help="carpeta con capturas del 'Obtenido' (default: fixtures del repo)")
    ap.add_argument("--out", type=Path, default=_OUT,
                    help="carpeta destino de las refs")
    ap.add_argument("--glob", default="Resultados_discos*.png",
                    help="patrón de las capturas del 'Obtenido'")
    ap.add_argument("--write", action="store_true",
                    help="escribir los crops (sin esto solo reporta: dry-run)")
    args = ap.parse_args()

    frames = sorted(args.src.glob(args.glob))
    if not frames:
        print(f"No hay capturas que matcheen {args.glob} en {args.src}")
        return 1

    found: dict[str, int] = {}
    n = 0
    for path in frames:
        frame = _load(path)
        if frame is None:
            print(f"  ! no se pudo leer {path.name}")
            continue
        for cy in PE.strip_rows(frame):
            for box in PE.gold_boxes(frame, cy):
                slot = PE.read_slot(frame, box)          # etiqueta TENTATIVA (OCR)
                tag = str(slot) if slot else "X"
                crop = PE.crop_slot(frame, box)
                if crop is None or crop.size == 0:
                    continue
                n += 1
                found[tag] = found.get(tag, 0) + 1
                name = f"{tag}_{path.stem}_{box.x0}.png"
                if args.write:
                    args.out.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(args.out / name), crop)
                print(f"  {path.name:24s} x={box.x0:5d} → {name}")

    print(f"\n{n} badges dorados · por etiqueta OCR: "
          f"{ {k: found[k] for k in sorted(found)} }")
    faltan = sorted({str(d) for d in range(1, 7)} - set(found))
    if faltan:
        print(f"CLASES SIN COSECHAR: {', '.join(faltan)} → el matcher sigue APAGADO "
              f"(gate de 6 clases). Hace falta un 'Obtenido' con esos slots.")
    if "X" in found:
        print(f"{found['X']} badge(s) sin etiqueta ('X_*.png'): el OCR se abstuvo → "
              f"mirarlos y renombrar el prefijo al dígito real.")
    if not args.write:
        print("\n(dry-run: nada escrito — volver a correr con --write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
