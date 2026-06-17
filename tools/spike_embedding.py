"""Hito E.0 — Spike de validación OFFLINE de embeddings vs descriptor hand-crafted.

De-risk del pivote de Fase 5R: ¿algún embedder off-the-shelf identifica al dueño
del badge (avatar circular de la grilla S17) MEJOR que el descriptor actual
(`app/core/avatar_descriptor.py`: HSV-hist + NCC-Lab) manteniendo CERO wrong
(RNF-02)?

Este script NO toca la app ni el build. Corre en un venv SEPARADO (`.venv_spike`)
con torch + timm para EXPERIMENTAR (el build env está fijado y prohíbe torch).
La elección del modelo se exporta a ONNX recién en E.1/E.2; acá solo medimos
discriminación con torch directo (más simple para de-riskear).

Protocolo (espeja `tools/measure_badge_lib.py`):
  - Set GOLD de medición = crops S17 de `audit/harvest/` (etiqueta = latch, dueño
    certero). 1 surface = S17 (el badge de la grilla, la superficie objetivo).
  - Librería de refs = `app/resources/avatar_refs/` (ico limpios) + el resto del set
    GOLD (multi-ref por PJ). Reject-set = `app/resources/avatar_reject/`.
  - Leave-one-out: por cada crop GOLD se lo saca de las refs de su PJ y se matchea
    contra todo lo demás. Distancia a un PJ = mínimo sobre sus refs.
  - Para cada motor (descriptor + cada embedder): reporta top-1 sin guarda, wrong
    sin guarda, y el punto de operación de CERO-WRONG (umbral de margen) con su
    top-1/abstención. Más matriz de confusión (look-alikes) y latencia ms/crop.
  - `audit/grid_diag/` (conf>=umbral) se puede sumar como refs EXTRA (label-plata,
    lectura del descriptor — circular, off por default).

Uso (desde la raíz del repo, en .venv_spike):
    .venv_spike\\Scripts\\python.exe tools/spike_embedding.py
    ... --models dinov2,efficientnet_lite0,mobilenetv3,clip
    ... --grid-diag-refs --grid-diag-conf 0.95
    ... --no-descriptor --no-mask
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# `_norm_key` y `build_name_map` son livianos (solo stdlib + el dict de alias) →
# importables en el venv del spike sin arrastrar el stack pesado.
from app.core.avatar_descriptor import build_name_map  # noqa: E402
from app.core.stats_vocab import _norm_key  # noqa: E402

# Modelos timm por alias corto. Todos exportables a ONNX (constraint de envío).
# DINOv2/EfficientNet-lite/MobileNet son chicos (candidatos a ENVÍO); CLIP es el
# baseline generalista pesado (NO se envía — solo referencia de precisión).
_MODEL_ALIAS = {
    "dinov2":          "vit_small_patch14_dinov2.lvd142m",   # 384-d, ~85 MB
    "efficientnet_lite0": "tf_efficientnet_lite0.in1k",      # 1280-d, ~18 MB
    "mobilenetv3":     "mobilenetv3_large_100.ra_in1k",      # 1280-d, ~22 MB
    "clip":            "vit_base_patch32_clip_224.openai",   # 768-d, ~350 MB
}

# Pares look-alike conocidos (caras animales / siluetas parecidas) — foco RNF-02.
_LOOKALIKES = [("Lycaon", "Pan Yinhu"), ("Ben", "Soukaku"), ("Nicole", "Zhao")]

# Modo de degradación (lo fija main desde --realistic). El modo 'full' mete artefactos
# (downscale fuerte, JPEG, rotación) que NO ocurren en una captura de pantalla; 'realistic'
# usa SOLO lo que pasa de verdad en scroll: jitter de localización + motion blur vertical.
_DEGRADE_REALISTIC = False


# --------------------------------------------------------------------------- #
# Carga de crops + preprocesado (máscara circular consistente con el descriptor)
# --------------------------------------------------------------------------- #

def _circular_fill(rgb: np.ndarray, erode_frac: float = 0.06, fill: int = 114) -> np.ndarray:
    """Anula el aro/fondo fuera del círculo (como `_MASK` del descriptor) rellenando
    con gris ImageNet-neutro para no meter un anillo negro que confunda al modelo."""
    h, w = rgb.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    r = min(h, w) / 2.0 - max(2.0, erode_frac * min(h, w))
    m = ((xx - cx) ** 2 + (yy - cy) ** 2) <= r * r
    out = rgb.copy()
    out[~m] = fill
    return out


def _degrade(bgr: np.ndarray, seed: int, level: int) -> np.ndarray:
    """Simula la degradación de un badge a mitad de scroll en vivo: desalineación
    (traslación+escala+rotación), pérdida de resolución, blur y JPEG. Determinista
    por `seed` (= hash de la ruta) → TODOS los motores ven el MISMO píxel degradado
    para el mismo crop (comparación justa). `level` 1=leve 2=medio 3=duro."""
    import cv2
    rng = np.random.default_rng(seed)
    h, w = bgr.shape[:2]
    sev = {1: 0.5, 2: 1.0, 3: 1.6}.get(level, 1.0)
    if _DEGRADE_REALISTIC:
        # SOLO lo que produce una captura de pantalla en scroll: jitter de localización
        # (traslación+escala, sin rotación) + motion blur vertical. Sin downscale/JPEG.
        tx = rng.uniform(-0.06, 0.06) * w * sev
        ty = rng.uniform(-0.06, 0.06) * h * sev
        sc = 1.0 + rng.uniform(-0.08, 0.08) * sev
        M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, sc)
        M[0, 2] += tx
        M[1, 2] += ty
        out = cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        kk = max(3, int(round(3 + 4 * sev))) | 1   # kernel impar
        ker = np.zeros((kk, kk), np.float32)
        ker[:, kk // 2] = 1.0 / kk                  # blur vertical (scroll)
        return cv2.filter2D(out, -1, ker)
    # 1) afín: traslación + escala + rotación leve (el badge no cae centrado/al tamaño)
    tx = rng.uniform(-0.08, 0.08) * w * sev
    ty = rng.uniform(-0.08, 0.08) * h * sev
    scale = 1.0 + rng.uniform(-0.15, 0.15) * sev
    ang = rng.uniform(-6, 6) * sev
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, scale)
    M[0, 2] += tx
    M[1, 2] += ty
    out = cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    # 2) downscale→upscale (pérdida de resolución del frame en movimiento)
    f = max(0.35, 1.0 - 0.4 * sev * float(rng.uniform(0.6, 1.0)))
    small = cv2.resize(out, (max(8, int(w * f)), max(8, int(h * f))), interpolation=cv2.INTER_AREA)
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    # 3) blur gaussiano
    k = int(rng.integers(0, 2 + int(2 * sev))) * 2 + 1
    if k >= 3:
        out = cv2.GaussianBlur(out, (k, k), 0)
    # 4) artefactos JPEG
    q = int(rng.integers(35, 75))
    ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, q])
    if ok:
        out = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return out


def _imread(path: str) -> np.ndarray | None:
    """imread unicode-safe (Windows): `cv2.imread` falla con rutas no-ASCII (p.ej.
    `n.º11`). `np.fromfile` + `cv2.imdecode` lee por bytes y respeta la ruta."""
    import cv2
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _load_rgb(path: str, mask: bool, degrade_level: int = 0) -> np.ndarray | None:
    import cv2
    bgr = _imread(path)
    if bgr is None or bgr.size == 0:
        return None
    if degrade_level:
        bgr = _degrade(bgr, abs(hash(path)) % (2 ** 32), degrade_level)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return _circular_fill(rgb) if mask else rgb


# --------------------------------------------------------------------------- #
# Dataset: GOLD (harvest S17 latch) + ico refs + reject + grid_diag silver
# --------------------------------------------------------------------------- #

def _roster() -> list[str]:
    try:
        from app.db.connection import get_connection
        con = get_connection()
        r = [str(x[0]) for x in con.execute("SELECT nombre FROM agents")]
        con.close()
        return r
    except Exception as e:  # noqa: BLE001
        print(f"[warn] roster desde DB falló ({e}); name_map por _norm_key sola.")
        return []


def _gold_badges(kind: str = "grid") -> list[tuple[str, str]]:
    """(label_latch, path) de los badges GOLD extraídos por `extract_harvest_badges.py`
    (crops reales in-game, label = latch del flujo-ancla = dueño CERTERO; NO la lectura
    del descriptor como grid_diag). `kind`: 'grid' (badge grilla S17, target runtime),
    'det' (panel detalle S18), 'both'. Label = prefijo antes de `__{tag}__`."""
    tags = {"grid": ["grid"], "det": ["det"], "both": ["grid", "det"]}.get(kind, ["grid"])
    out = []
    for tag in tags:
        for p in sorted(glob.glob(str(ROOT / f"audit/harvest_badges/*__{tag}__*.png"))):
            label = os.path.basename(p).split(f"__{tag}__")[0]
            out.append((label, p))
    return out


def _grid_diag_silver(min_conf: float) -> list[tuple[str, str]]:
    """(label_lectura, path) de grid_diag con conf>=min_conf. Label-PLATA (lectura
    del descriptor, circular) → solo como refs extra, nunca como set de medición."""
    out = []
    pat = re.compile(r"^[a-z0-9]+_\d+_badge_(.+)_([01]\.\d+)\.png$")
    for p in sorted(glob.glob(str(ROOT / "audit/grid_diag/*_badge_*.png"))):
        m = pat.match(os.path.basename(p))
        if not m:
            continue
        if float(m.group(2)) >= min_conf:
            out.append((m.group(1), p))
    return out


def _ico_refs(name_map: dict[str, str]) -> list[tuple[str, str]]:
    out = []
    for p in sorted(glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))):
        stem = os.path.splitext(os.path.basename(p))[0]
        out.append((name_map.get(stem, stem), p))
    return out


# --------------------------------------------------------------------------- #
# Motores: descriptor hand-crafted + embedders timm. Interfaz común:
#   embed_paths(paths) -> np.ndarray (N, D) L2-normalizada
# --------------------------------------------------------------------------- #

class DescriptorEngine:
    """Baseline: el descriptor actual. 'Embedding' = el vector concatenado
    (hist|ncc|regions) ponderado; pero la distancia REAL del descriptor no es
    coseno, así que medimos con su `descriptor_distance` propia vía un shim."""
    name = "descriptor(hist+ncc)"
    is_descriptor = True

    def __init__(self, mask: bool):
        self.mask = mask
        from app.core.avatar_descriptor import build_descriptor, descriptor_distance
        self._build = build_descriptor
        self._dist = descriptor_distance
        import cv2
        self._cv2 = cv2

    def descriptors(self, paths: list[str], degrade_level: int = 0):
        out = []
        for p in paths:
            bgr = _imread(p)
            if bgr is not None and degrade_level:
                bgr = _degrade(bgr, abs(hash(p)) % (2 ** 32), degrade_level)
            out.append(self._build(bgr) if bgr is not None else None)
        return out

    def distance(self, a, b) -> float:
        if a is None or b is None:
            return 1.0
        return self._dist(a, b, None, a.is_gray)


class TimmEngine:
    """Embedder off-the-shelf vía timm. embed → vector L2-normalizado; distancia =
    1 - coseno."""
    is_descriptor = False

    def __init__(self, alias: str, mask: bool):
        import torch
        import timm
        self.alias = alias
        self.name = f"emb:{alias}"
        self.mask = mask
        self._torch = torch
        self._model = timm.create_model(_MODEL_ALIAS[alias], pretrained=True, num_classes=0)
        self._model.eval()
        try:  # timm reciente
            cfg = timm.data.resolve_model_data_config(self._model)
        except AttributeError:  # timm viejo
            cfg = timm.data.resolve_data_config({}, model=self._model)
        self._tf = timm.data.create_transform(**cfg)
        self.dim = int(getattr(self._model, "num_features", 0) or 0)

    def descriptors(self, paths: list[str], degrade_level: int = 0):
        from PIL import Image
        torch = self._torch
        vecs = []
        with torch.no_grad():
            for p in paths:
                rgb = _load_rgb(p, self.mask, degrade_level)
                if rgb is None:
                    vecs.append(None)
                    continue
                x = self._tf(Image.fromarray(rgb)).unsqueeze(0)
                f = self._model(x).squeeze(0).cpu().numpy().astype(np.float32)
                n = float(np.linalg.norm(f))
                vecs.append(f / n if n > 1e-6 else f)
        return vecs

    def distance(self, a, b) -> float:
        if a is None or b is None:
            return 1.0
        return 1.0 - float(np.dot(a, b))


class OnnxEngine:
    """El pipeline RUNTIME real: `app/core/onnx_embedder.py` (onnxruntime + cv2, SIN
    torch). Validar que reproduce al TimmEngine confirma el preprocesado/export ONNX
    end-to-end (no hace falta paridad de coseno con timm: lo que importa es que
    discrimine igual)."""
    is_descriptor = False

    def __init__(self, mask: bool):
        self.mask = mask  # el onnx_embedder ya enmascara; `mask` se ignora acá
        from app.core.onnx_embedder import OnnxEmbedder
        self._emb = OnnxEmbedder()
        self.name = "emb:onnx(mobilenetv3)"
        self.dim = 0

    def descriptors(self, paths: list[str], degrade_level: int = 0):
        out = []
        for p in paths:
            bgr = _imread(p)
            if bgr is not None and degrade_level:
                bgr = _degrade(bgr, abs(hash(p)) % (2 ** 32), degrade_level)
            v = self._emb.embed(bgr) if bgr is not None else None
            if v is not None and not self.dim:
                self.dim = int(v.shape[0])
            out.append(v)
        return out

    def distance(self, a, b) -> float:
        if a is None or b is None:
            return 1.0
        return 1.0 - float(np.dot(a, b))


# --------------------------------------------------------------------------- #
# Matcher genérico (espeja AvatarMatcher.match) sobre cualquier motor
# --------------------------------------------------------------------------- #

def _match(engine, q, refs: dict[str, list], rejects: list):
    """Devuelve (best_name, d1, margin, rejected). Distancia a un PJ = mínimo
    sobre sus refs. Salta PJs sin refs (p.ej. el único crop quedó held-out)."""
    scored = sorted(
        ((name, min(engine.distance(q, r) for r in lst))
         for name, lst in refs.items() if lst),
        key=lambda t: t[1],
    )
    if not scored:
        return None, 2.0, 0.0, False, []
    best, d1 = scored[0]
    d2 = scored[1][1] if len(scored) > 1 else 1.0
    rej = False
    if rejects:
        d_rej = min(engine.distance(q, r) for r in rejects)
        rej = d_rej <= d1
    return best, d1, d2 - d1, rej, scored[:5]


def _leave_one_out(engine, gold, ico, reject_descs, extra_refs):
    """gold = [(label, clean_desc, query_desc)] — refs usan clean_desc (limpio),
    el match usa query_desc (posiblemente degradado). ico/extra = {name:[desc]}.
    Leave-one-out: se saca el clean_desc fuente y se matchea su query_desc contra
    el resto. Devuelve lista de (gt, pred, d1, margin, rejected)."""
    # refs por PJ = ico + extra + gold-limpios (todos), LOO sobre el fuente.
    refs: dict[str, list] = defaultdict(list)
    for name, lst in ico.items():
        refs[_norm_key(name)].extend(lst)
    for name, lst in extra_refs.items():
        refs[_norm_key(name)].extend(lst)
    for label, clean_desc, _q in gold:
        refs[_norm_key(label)].append(clean_desc)

    results = []
    for label, clean_desc, query_desc in gold:
        k = _norm_key(label)
        lst = refs.get(k)
        held_idx = next((j for j, x in enumerate(lst) if x is clean_desc), None)
        if held_idx is not None:
            held = lst.pop(held_idx)
        pred, d1, margin, rej, _top = _match(engine, query_desc, refs, reject_descs)
        if held_idx is not None:
            lst.insert(held_idx, held)
        results.append((k, pred, d1, margin, rej))
    return results


# --------------------------------------------------------------------------- #
# Métricas: sin guarda + punto de operación CERO-WRONG por umbral de margen
# --------------------------------------------------------------------------- #

def _unguarded(results):
    ok = wr = ab = 0
    confusion = defaultdict(int)
    for gt, pred, d1, margin, rej in results:
        if rej or pred is None:
            ab += 1
        elif _norm_key(pred) == gt:
            ok += 1
        else:
            wr += 1
            confusion[(gt, _norm_key(pred))] += 1
    return ok, wr, ab, confusion


def _zero_wrong_op(results):
    """Barre el umbral de margen τ: acepta el top-1 solo si margin>=τ y no-reject.
    Devuelve (τ*, top1, abstain, wrong) en el τ* mínimo con wrong==0."""
    margins = sorted({round(m, 4) for _, _, _, m, _ in results} | {0.0})
    best = None
    for tau in margins:
        ok = wr = ab = 0
        for gt, pred, d1, margin, rej in results:
            if rej or pred is None or margin < tau:
                ab += 1
            elif _norm_key(pred) == gt:
                ok += 1
            else:
                wr += 1
        if wr == 0:
            best = (tau, ok, ab, wr)
            break
    if best is None:  # nunca llega a 0 wrong → reportar el τ más alto
        tau = margins[-1]
        ok = sum(1 for gt, p, _, m, r in results
                 if not r and p is not None and m >= tau and _norm_key(p) == gt)
        ab = sum(1 for _, p, _, m, r in results if r or p is None or m >= tau)
        wr = len(results) - ok - ab
        best = (tau, ok, ab, wr)
    return best


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    try:  # consola Windows = cp1252; el reporte usa τ/acentos
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="dinov2,efficientnet_lite0,mobilenetv3",
                    help="alias separados por coma (dinov2,efficientnet_lite0,mobilenetv3,clip)")
    ap.add_argument("--no-descriptor", action="store_true", help="omitir el baseline descriptor")
    ap.add_argument("--no-mask", action="store_true", help="no aplicar máscara circular")
    ap.add_argument("--grid-diag-refs", action="store_true",
                    help="sumar grid_diag (conf>=umbral) como refs EXTRA (label-plata)")
    ap.add_argument("--grid-diag-conf", type=float, default=0.95)
    ap.add_argument("--gold", default="grid", choices=["grid", "det", "both"],
                    help="set GOLD: 'grid' badge grilla S17 (target runtime), 'det' panel, 'both'")
    ap.add_argument("--degrade", type=int, default=0, choices=[0, 1, 2, 3],
                    help="degradar las QUERIES gold (1 leve, 2 medio, 3 duro); refs limpias. "
                         "Simula frames a mitad de scroll en vivo — el test real del gate.")
    ap.add_argument("--realistic", action="store_true",
                    help="degradación REALISTA de captura (jitter de localización + motion blur "
                         "vertical, sin downscale/JPEG/rotación) en vez del battery 'full'.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    global _DEGRADE_REALISTIC
    _DEGRADE_REALISTIC = args.realistic
    mask = not args.no_mask

    roster = _roster()
    ico_stems = [os.path.splitext(os.path.basename(p))[0]
                 for p in glob.glob(str(ROOT / "app/resources/avatar_refs/*.png"))]
    name_map = build_name_map(ico_stems, roster)

    gold = _gold_badges(args.gold)
    ico = _ico_refs(name_map)
    reject = [(None, p) for p in sorted(glob.glob(str(ROOT / "app/resources/avatar_reject/*.png")))]
    extra = _grid_diag_silver(args.grid_diag_conf) if args.grid_diag_refs else []

    # cobertura vs equip_map (sanity: ¿todo label gold es dueño real?)
    owners = set()
    try:
        import json
        em = json.loads((ROOT / "audit/equip_map_20260612.json").read_text(encoding="utf-8"))
        owners = {_norm_key(v) for v in em.values()}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] equip_map no cargó: {e}")
    gold_labels = {_norm_key(l) for l, _ in gold}
    orphan = sorted(gold_labels - owners) if owners else []

    print(f"GOLD (harvest_badges/{args.gold}): {len(gold)} crops, {len(gold_labels)} PJs"
          f"{f' | DEGRADE nivel {args.degrade} en queries' if args.degrade else ''}")
    print(f"ico refs: {len(ico)} | reject: {len(reject)} | extra(grid_diag): {len(extra)}")
    if owners:
        print(f"equip_map owners: {len(owners)} | labels gold fuera de owners: {orphan or 'ninguno'}")

    aliases = [a.strip() for a in args.models.split(",") if a.strip()]
    engines = []
    if not args.no_descriptor:
        engines.append(("descriptor", lambda: DescriptorEngine(mask)))
    for a in aliases:
        if a == "onnx":  # el pipeline runtime real (onnx_embedder)
            engines.append(("onnx", lambda: OnnxEngine(mask)))
            continue
        if a not in _MODEL_ALIAS:
            print(f"[warn] alias desconocido: {a} (válidos: {list(_MODEL_ALIAS)} + onnx)")
            continue
        engines.append((a, lambda a=a: TimmEngine(a, mask)))

    rows = []  # (engine_name, dim, lat_ms, ok0, wr0, ab0, tau, ok1, ab1, confusion)
    for key, factory in engines:
        print(f"\n=== Motor: {key} ===")
        try:
            eng = factory()
        except ImportError as e:
            print(f"  [SKIP] dependencia faltante: {e}\n  "
                  f"Instalá el venv del spike (ver instrucciones del README/E.0).")
            continue

        gold_paths = [p for _, p in gold]
        all_paths = gold_paths + [p for _, p in ico] + \
                    [p for _, p in reject] + [p for _, p in extra]
        t0 = time.perf_counter()
        all_desc = eng.descriptors(all_paths)
        lat_ms = 1000.0 * (time.perf_counter() - t0) / max(1, len(all_paths))

        i = 0
        clean_gold = [all_desc[i + j] for j in range(len(gold))]
        i += len(gold)
        ico_d: dict[str, list] = defaultdict(list)
        for j in range(len(ico)):
            d = all_desc[i + j]
            if d is not None:
                ico_d[ico[j][0]].append(d)
        i += len(ico)
        reject_d = [all_desc[i + j] for j in range(len(reject)) if all_desc[i + j] is not None]
        i += len(reject)
        extra_d: dict[str, list] = defaultdict(list)
        for j in range(len(extra)):
            d = all_desc[i + j]
            if d is not None:
                extra_d[extra[j][0]].append(d)

        # queries: degradadas si se pidió (refs limpias), si no = las limpias.
        query_gold = eng.descriptors(gold_paths, degrade_level=args.degrade) \
            if args.degrade else clean_gold
        gold_tri = [(gold[j][0], clean_gold[j], query_gold[j]) for j in range(len(gold))
                    if clean_gold[j] is not None and query_gold[j] is not None]
        results = _leave_one_out(eng, gold_tri, ico_d, reject_d, extra_d)
        ok0, wr0, ab0, confusion = _unguarded(results)
        tau, ok1, ab1, wr1 = _zero_wrong_op(results)
        dim = getattr(eng, "dim", 0)
        rows.append((eng.name, dim, lat_ms, ok0, wr0, ab0, tau, ok1, ab1, confusion))
        t = max(1, len(results))
        print(f"  dim={dim} lat={lat_ms:.1f}ms/crop | SIN GUARDA: top1={ok0}/{t}={ok0/t:.1%} "
              f"wrong={wr0}={wr0/t:.1%} | CERO-WRONG@τ={tau:.3f}: top1={ok1/t:.1%} abst={ab1/t:.1%}")
        if confusion:
            top = sorted(confusion.items(), key=lambda kv: -kv[1])[:8]
            print("  confusiones:", "  ".join(f"{a}->{b}×{c}" for (a, b), c in top))

    # --- reporte markdown ---
    out = Path(args.out) if args.out else ROOT / "audit" / f"spike_embedding_{date.today():%Y%m%d}.md"
    _write_report(out, rows, gold, ico, reject, extra, mask, args, orphan)
    print(f"\nReporte → {out}")
    return 0


def _write_report(out: Path, rows, gold, ico, reject, extra, mask, args, orphan):
    deg = {0: "no (crops limpios)", 1: "leve", 2: "medio", 3: "duro"}.get(args.degrade, str(args.degrade))
    L = []
    L.append(f"# Spike embedding (Hito E.0) — {date.today():%Y-%m-%d}\n")
    L.append("> ¿Algún embedder off-the-shelf supera al descriptor con **0 wrong** (RNF-02)?\n")
    L.append("## Setup")
    L.append(f"- **GOLD** (medición, leave-one-out): `audit/harvest_badges/*__{args.gold}__*` — "
             f"{len(gold)} crops de badge REALES in-game (recortados de los frames harvest con la "
             f"lógica de la app `detector.crop_*`; etiqueta = latch = dueño certero).")
    L.append(f"- Refs: `avatar_refs` ico ({len(ico)}) + GOLD-limpio multi-ref. Reject: {len(reject)}.")
    L.append(f"- Refs extra grid_diag (label-plata, conf>={args.grid_diag_conf}): "
             f"{'sí, ' + str(len(extra)) + ' crops' if args.grid_diag_refs else 'no'}.")
    L.append(f"- Máscara circular: {'sí' if mask else 'NO'}.")
    L.append(f"- **Degradación de queries:** {deg} (refs siempre limpias). "
             f"{'⭐ test real del gate (simula scroll en vivo)' if args.degrade else '— no separa motores (ver caveat)'}")
    if orphan:
        L.append(f"- ⚠️ labels gold fuera de equip_map owners: {orphan}")
    L.append("\n## Resultados\n")
    L.append("| Motor | dim | lat ms/crop | top-1 s/guarda | wrong s/guarda | CERO-WRONG top-1 | abst | τ |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name, dim, lat, ok0, wr0, ab0, tau, ok1, ab1, _conf in rows:
        t = max(1, ok0 + wr0 + ab0)
        L.append(f"| `{name}` | {dim or '—'} | {lat:.1f} | {ok0/t:.1%} | {wr0/t:.1%} "
                 f"| **{ok1/t:.1%}** | {ab1/t:.1%} | {tau:.3f} |")
    L.append("\n## Confusiones (sin guarda) — foco look-alikes (RNF-02)\n")
    for name, *_rest, conf in rows:
        if not conf:
            L.append(f"- `{name}`: sin confusiones ✅")
            continue
        top = sorted(conf.items(), key=lambda kv: -kv[1])[:10]
        L.append(f"- `{name}`: " + "  ".join(f"{a}→{b}×{c}" for (a, b), c in top))
    L.append("\n## Lectura del gate\n")
    L.append("- **GATE E.0:** ¿algún embedder da más top-1 que el descriptor en CERO-WRONG? "
             "SÍ → E.1 (preferir el chico si empata). NO → evaluar E.4 (fine-tuning).")
    L.append("- Caveat: GOLD = crops de flujo-ancla (limpios). El gap real de 'dueño incierto' "
             "en vivo (frames a mitad de scroll) se mide recién en E.3 contra equip_map.")
    L.append("- Latencia objetivo RNF-06: <~30 ms/crop (voto a 10 fps). El modelo a ENVIAR debe "
             "cumplirlo; CLIP suele exceder → solo baseline de precisión.\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
