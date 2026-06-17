"""Hito E.1 — Exporta el embedder elegido (MobileNetV3) de timm a ONNX + verifica
PARIDAD onnxruntime↔torch.

Corre en `.venv_spike` (torch + timm + onnx + onnxruntime). Produce:
  - `app/resources/avatar_embedder.onnx`   (el modelo, ~22 MB, se ENVÍA en el build)
  - `app/resources/avatar_embedder.json`   (preprocesado: input/mean/std/crop_pct + dim)

La paridad es crítica: la librería de refs (E.1) y el runtime (E.2) usan
`onnx_embedder.py` (onnxruntime + cv2/numpy, SIN torch). Si el preprocesado de
`onnx_embedder` no replica el de timm, los vectores no viven en el mismo espacio
que validó el spike. Acá confirmamos que el ONNX + preprocesado numpy reproduce el
vector de timm (coseno ≈ 1.0) sobre crops reales.

Uso:
    .venv_spike\\Scripts\\python.exe tools/export_embedder_onnx.py
    ... --model mobilenetv3_large_100.ra_in1k --opset 17
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_OUT_ONNX = ROOT / "app" / "resources" / "avatar_embedder.onnx"
_OUT_JSON = ROOT / "app" / "resources" / "avatar_embedder.json"


def _preprocess_numpy(bgr, cfg) -> np.ndarray:
    """Replica el transform de timm con cv2/numpy (lo que hará `onnx_embedder.py`
    en el build, sin torch): máscara circular → resize a input/crop_pct → center-crop
    → normalización ImageNet → CHW float32. Devuelve (1,3,H,W)."""
    import cv2
    from tools.spike_embedding import _circular_fill
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb = _circular_fill(rgb)
    inp = cfg["input_size"][1]
    resize_to = int(round(inp / cfg["crop_pct"]))
    interp = cv2.INTER_AREA if resize_to < rgb.shape[0] else cv2.INTER_LINEAR
    rgb = cv2.resize(rgb, (resize_to, resize_to), interpolation=interp)
    off = (resize_to - inp) // 2
    rgb = rgb[off:off + inp, off:off + inp]
    x = rgb.astype(np.float32) / 255.0
    x = (x - np.array(cfg["mean"], np.float32)) / np.array(cfg["std"], np.float32)
    return np.transpose(x, (2, 0, 1))[None].astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mobilenetv3_large_100.ra_in1k")
    ap.add_argument("--opset", type=int, default=17)
    args = ap.parse_args()

    import torch
    import timm

    model = timm.create_model(args.model, pretrained=True, num_classes=0).eval()
    try:
        dc = timm.data.resolve_model_data_config(model)
    except AttributeError:
        dc = timm.data.resolve_data_config({}, model=model)
    cfg = {
        "model": args.model,
        "input_size": list(dc["input_size"]),
        "mean": [float(x) for x in dc["mean"]],
        "std": [float(x) for x in dc["std"]],
        "crop_pct": float(dc.get("crop_pct", 0.875)),
        "interpolation": dc.get("interpolation", "bicubic"),
        "dim": int(getattr(model, "num_features", 0) or 0),
    }
    print("data config:", json.dumps(cfg, indent=2))

    inp = cfg["input_size"][1]
    dummy = torch.randn(1, 3, inp, inp)
    _OUT_ONNX.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model, dummy, str(_OUT_ONNX),
        input_names=["input"], output_names=["embedding"],
        dynamic_axes={"input": {0: "batch"}, "embedding": {0: "batch"}},
        opset_version=args.opset, do_constant_folding=True,
    )
    print(f"ONNX → {_OUT_ONNX} ({_OUT_ONNX.stat().st_size/1e6:.1f} MB)")
    _OUT_JSON.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"config → {_OUT_JSON}")

    # --- paridad onnxruntime ↔ torch sobre crops reales ---
    import onnxruntime as ort
    sess = ort.InferenceSession(str(_OUT_ONNX), providers=["CPUExecutionProvider"])
    paths = sorted(glob.glob(str(ROOT / "audit/harvest/*__S17__*.png")))[:12]
    import cv2

    def _imread(p):
        d = np.fromfile(p, dtype=np.uint8)
        return cv2.imdecode(d, cv2.IMREAD_COLOR) if d.size else None

    cosines = []
    tf = timm.data.create_transform(**{k: cfg[k] for k in ("input_size", "mean", "std", "crop_pct")},
                                    is_training=False)
    from PIL import Image
    from tools.spike_embedding import _circular_fill
    for p in paths:
        bgr = _imread(p)
        if bgr is None:
            continue
        x = _preprocess_numpy(bgr, cfg)
        v_onnx = sess.run(None, {"input": x})[0][0].astype(np.float32)
        v_onnx /= (np.linalg.norm(v_onnx) + 1e-9)
        rgb = _circular_fill(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        with torch.no_grad():
            v_torch = model(tf(Image.fromarray(rgb)).unsqueeze(0)).squeeze(0).numpy().astype(np.float32)
        v_torch /= (np.linalg.norm(v_torch) + 1e-9)
        cosines.append(float(np.dot(v_onnx, v_torch)))
    if cosines:
        arr = np.array(cosines)
        print(f"\nPARIDAD onnx↔torch sobre {len(arr)} crops: "
              f"coseno min={arr.min():.5f} mean={arr.mean():.5f} max={arr.max():.5f}")
        ok = arr.min() > 0.999
        print("  ✅ PARIDAD OK (>0.999)" if ok else "  ⚠️ paridad baja — revisar preprocesado")
        return 0 if ok else 2
    print("[warn] sin crops para verificar paridad")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
