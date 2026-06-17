"""Fase 5R — Embedder ONNX para identidad de badge (motor del pivote E.0/E.1).

Convierte un crop BGR del ícono circular (badge de la grilla S17 / avatar de fila)
en un vector L2-normalizado (~1280-d MobileNetV3) que vive en un espacio donde
"parecido visual" = "coseno alto". Reemplaza el *motor de similitud* del descriptor
hand-crafted (`avatar_descriptor.py`: HSV-hist + NCC-Lab) — que el spike E.0 mostró
que colapsa con la degradación del scroll en vivo (6% top-1@0-wrong vs 79% del
embedding; ver `audit/spike_embedding_20260616.md`).

Runtime = **onnxruntime CPU puro** (RNF-03: solo inferencia local; sin torch — el
build PaddleOCR está fijado y `rebuild.ps1` aborta con torch/numpy-2). El modelo y
su config de preprocesado se ENVÍAN en `app/resources/avatar_embedder.{onnx,json}`
(generados por `tools/export_embedder_onnx.py`).

Lazy-load (como `ocr_paddle`): la sesión ORT se crea recién en el primer `embed`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Modelo + config envasados con la app.
_RES = Path(__file__).resolve().parents[1] / "resources"
_ONNX_PATH = _RES / "avatar_embedder.onnx"
_CFG_PATH = _RES / "avatar_embedder.json"

# Máscara circular consistente con `avatar_descriptor._MASK` (erosión ~6%): anula el
# aro/fondo del filo fuera del círculo. Acá se RELLENA con gris ImageNet-neutro (no
# se zerea) para no inyectar un anillo negro que sesgue las features de la CNN.
_FILL = 114


def _circular_fill(rgb: np.ndarray, erode_frac: float = 0.06) -> np.ndarray:
    h, w = rgb.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    r = min(h, w) / 2.0 - max(2.0, erode_frac * min(h, w))
    m = ((xx - cx) ** 2 + (yy - cy) ** 2) <= r * r
    out = rgb.copy()
    out[~m] = _FILL
    return out


class OnnxEmbedder:
    """Embedder lazy. `embed(bgr) → vector L2-norm float32` o None si el crop es
    inválido. Singleton-friendly: una instancia por proceso (la sesión ORT es cara)."""

    def __init__(self, onnx_path: str | Path = _ONNX_PATH, cfg_path: str | Path = _CFG_PATH):
        self._onnx_path = Path(onnx_path)
        self._cfg_path = Path(cfg_path)
        self._sess = None
        self._inp_name: str | None = None
        self._cfg: dict | None = None
        self._dim: int = 0

    # ---- estado ----
    @property
    def available(self) -> bool:
        """True si el modelo está en disco y onnxruntime es importable."""
        if not self._onnx_path.exists():
            return False
        try:
            import onnxruntime  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    @property
    def dim(self) -> int:
        return self._dim

    def _ensure(self) -> bool:
        if self._sess is not None:
            return True
        if not self._onnx_path.exists():
            log.warning("OnnxEmbedder: modelo ausente en %s", self._onnx_path)
            return False
        try:
            import onnxruntime as ort
            self._cfg = json.loads(self._cfg_path.read_text(encoding="utf-8")) \
                if self._cfg_path.exists() else {}
            so = ort.SessionOptions()
            so.intra_op_num_threads = 1  # RNF-06: no monopolizar CPU en el voto 10 fps
            self._sess = ort.InferenceSession(str(self._onnx_path), sess_options=so,
                                              providers=["CPUExecutionProvider"])
            self._inp_name = self._sess.get_inputs()[0].name
            out = self._sess.get_outputs()[0]
            self._dim = int(out.shape[-1]) if isinstance(out.shape[-1], int) else 0
            log.info("OnnxEmbedder cargado: %s (dim=%s)", self._onnx_path.name, self._dim or "?")
            return True
        except Exception:
            log.exception("OnnxEmbedder: fallo al cargar la sesión ONNX")
            self._sess = None
            return False

    # ---- preprocesado (replica el transform de timm con cv2/numpy) ----
    def _preprocess(self, bgr: np.ndarray) -> np.ndarray | None:
        if bgr is None or getattr(bgr, "size", 0) == 0:
            return None
        cfg = self._cfg or {}
        inp = int(cfg.get("input_size", [3, 224, 224])[-1])
        crop_pct = float(cfg.get("crop_pct", 0.875))
        mean = np.array(cfg.get("mean", [0.485, 0.456, 0.406]), np.float32)
        std = np.array(cfg.get("std", [0.229, 0.224, 0.225]), np.float32)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb = _circular_fill(rgb)
        resize_to = max(inp, int(round(inp / crop_pct)))
        interp = cv2.INTER_AREA if resize_to < rgb.shape[0] else cv2.INTER_CUBIC
        rgb = cv2.resize(rgb, (resize_to, resize_to), interpolation=interp)
        off = (resize_to - inp) // 2
        rgb = rgb[off:off + inp, off:off + inp]
        x = rgb.astype(np.float32) / 255.0
        x = (x - mean) / std
        return np.transpose(x, (2, 0, 1))[None].astype(np.float32)

    # ---- embed ----
    def embed(self, bgr: np.ndarray) -> np.ndarray | None:
        """Crop BGR → vector L2-normalizado. None si el modelo no está o el crop es
        inválido."""
        if not self._ensure():
            return None
        x = self._preprocess(bgr)
        if x is None:
            return None
        try:
            v = self._sess.run(None, {self._inp_name: x})[0][0].astype(np.float32)
        except Exception:
            log.exception("OnnxEmbedder.embed: fallo en la inferencia")
            return None
        n = float(np.linalg.norm(v))
        return v / n if n > 1e-6 else v


# Singleton perezoso del proceso (la sesión ORT es cara; una sola instancia).
_DEFAULT: OnnxEmbedder | None = None


def get_embedder() -> OnnxEmbedder:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = OnnxEmbedder()
    return _DEFAULT
