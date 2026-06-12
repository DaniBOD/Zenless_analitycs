"""Fase 5R.2 — Harness de validación del descriptor de avatar (READ-ONLY).

Mide la robustez del matcher con NÚMEROS, sobre 3 frentes:

  1. AUTO-SEPARACIÓN: distancia al vecino más cercano entre las refs (¿son
     distinguibles entre sí?). Pares más confundibles.
  2. RECUPERACIÓN SINTÉTICA: degrada cada ref como un badge in-game (downscale a
     ~36px, jitter de brillo/contraste/hue, traslación, blur) y la vuelve a
     matchear contra la librería → top-1 / margen / tasa de abstención. Mide si el
     descriptor + gates aguantan la degradación del ícono real.
  3. REJECT-SET: matchea las muestras no-PJ → tasa de reject (esperado ~100%).

Opcional: `--labeled <dir>` con subcarpetas por PJ (`<dir>/<NombrePJ>/*.png`) de
recortes REALES etiquetados (los cosecha 5R.3) → top-1 real vs ground-truth. Ese
es el número GO/NO-GO definitivo de la Fase 5.

Uso:  .venv\\Scripts\\python.exe tools\\validate_descriptor.py [--labeled audit/labeled_badges] [--n 6]
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "app" / "resources" / "avatar_refs"
REJECT = ROOT / "app" / "resources" / "avatar_reject"

import sys
sys.path.insert(0, str(ROOT))
from app.core.avatar_descriptor import AvatarMatcher, build_descriptor, descriptor_distance  # noqa: E402


def augment(bgr: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Simula un badge in-game: downscale agresivo + jitter + traslación + blur."""
    h, w = bgr.shape[:2]
    # downscale a ~30-44px y reupscale (pérdida de info como el ícono real)
    s = int(rng.integers(30, 45))
    img = cv2.resize(bgr, (s, s), interpolation=cv2.INTER_AREA)
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
    # brillo/contraste
    alpha = float(rng.uniform(0.82, 1.18)); beta = float(rng.integers(-18, 18))
    img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
    # hue shift leve
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[:, :, 0] = (hsv[:, :, 0] + int(rng.integers(-3, 4))) % 180
    img = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    # traslación ±3px (error de localización)
    tx, ty = int(rng.integers(-3, 4)), int(rng.integers(-3, 4))
    M = np.float32([[1, 0, tx], [0, 1, ty]])
    img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    if rng.random() < 0.5:
        img = cv2.GaussianBlur(img, (3, 3), 0)
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labeled", type=str, default=None)
    ap.add_argument("--n", type=int, default=6, help="augmentaciones por ref")
    args = ap.parse_args()

    m = AvatarMatcher.from_folders(REFS, REJECT)
    names = m.names
    print(f"Matcher: {len(names)} refs + {len(m._rejects)} rejects\n")

    # --- 1. Auto-separación ---
    refs = {k: m._refs[k] for k in names}
    nn = sorted((min(descriptor_distance(refs[a], refs[b]) for b in names if b != a), a)
                for a in names)
    print("== 1. Auto-separación de refs ==")
    print(f"  vecino más cercano: min={nn[0][0]:.3f} ({nn[0][1]}) "
          f"media={np.mean([d for d, _ in nn]):.3f}")
    pairs = sorted((descriptor_distance(refs[a], refs[b]), a, b)
                   for i, a in enumerate(names) for b in names[i + 1:])[:5]
    print("  5 pares más confundibles:")
    for d, a, b in pairs:
        print(f"    {d:.3f}  {a} ~ {b}")

    # --- 2. Recuperación sintética ---
    rng = np.random.default_rng(42)
    total = ok = abst = wrong = 0
    margins = []
    confused: dict[tuple[str, str], int] = {}
    for name in names:
        img = cv2.imread(str(REFS / f"{name}.png"))
        for _ in range(args.n):
            r = m.match(augment(img, rng))
            total += 1
            if r.name is None:
                abst += 1
            elif r.name == name:
                ok += 1; margins.append(r.margin)
            else:
                wrong += 1
                confused[(name, r.name)] = confused.get((name, r.name), 0) + 1
    print(f"\n== 2. Recuperación sintética ({args.n}×/ref, {total} casos) ==")
    print(f"  top-1 correcto = {ok/total:.1%} | abstención = {abst/total:.1%} | "
          f"ERRÓNEO = {wrong/total:.1%}")
    if margins:
        print(f"  margen medio (aciertos) = {np.mean(margins):.3f}")
    if confused:
        print("  confusiones top:")
        for (a, b), c in sorted(confused.items(), key=lambda kv: -kv[1])[:5]:
            print(f"    {a} → {b}  ×{c}")

    # --- 3. Reject-set ---
    rfiles = sorted(glob.glob(str(REJECT / "*.png")))
    rj = sum(1 for p in rfiles if m.match(cv2.imread(p)).rejected)
    print(f"\n== 3. Reject-set ==")
    print(f"  no-PJ descartados = {rj}/{len(rfiles)} ({rj/max(1,len(rfiles)):.0%})")

    # --- 4. Etiquetado real (opcional) ---
    if args.labeled and Path(args.labeled).is_dir():
        print(f"\n== 4. Etiquetado REAL ({args.labeled}) ==")
        lt = lok = labst = 0
        for pjdir in sorted(glob.glob(os.path.join(args.labeled, "*"))):
            if not os.path.isdir(pjdir):
                continue
            gt = os.path.basename(pjdir)
            for p in glob.glob(os.path.join(pjdir, "*.png")):
                r = m.match(cv2.imread(p))
                lt += 1
                if r.name is None:
                    labst += 1
                elif r.name == gt:
                    lok += 1
        if lt:
            print(f"  top-1 real = {lok/lt:.1%} | abstención = {labst/lt:.1%}  ({lt} crops)")
            print("  *** Este es el número GO/NO-GO de la Fase 5 ***")
        else:
            print("  (sin crops etiquetados todavía — los cosecha 5R.3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
