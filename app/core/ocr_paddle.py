"""
Hito 2.4.3 — Backend OCR: PaddleOCR (números densos, substats con dígitos).
Lazy-load: solo inicializa en primera invocación para no bloquear el arranque.

Nota: en sistemas Windows con MAX_PATH limitado, paddlepaddle/paddleocr
se instalan en un path corto (D:\\paddle_site). Este módulo agrega ese
path automáticamente si paddleocr no es importable desde site-packages.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np

from app.core import mem_diag
from app.core.metrics import measure_latency
from app.core.ocr_backend import OcrBackend

log = logging.getLogger(__name__)

# Flags de memoria de paddlepaddle (RNF-06) — DEBEN setearse ANTES de importar paddle.
# `eager_delete_tensor_gb=0.0` libera los tensores intermedios apenas dejan de usarse
# (mitiga el crecimiento nativo per-inferencia que detectamos: ~1.8 GB/min, ver
# audit/mem_diag_20260613.md). `allocator_strategy=auto_growth` evita sobre-reservar el pool.
# Idempotente vía setdefault → respeta overrides externos.
os.environ.setdefault("FLAGS_eager_delete_tensor_gb", "0.0")
os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")

_PADDLE_SITE = r"D:\paddle_site"


def _ensure_paddle_site() -> bool:
    """Agrega D:\\paddle_site a sys.path si existe y paddleocr no es importable."""
    if _PADDLE_SITE in sys.path:
        return True
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        pass
    import os
    if os.path.isdir(_PADDLE_SITE):
        sys.path.insert(0, _PADDLE_SITE)
        return True
    return False


_ensure_paddle_site()


# --- Fase 2E (2026-09-21): el MOTOR es ONNX Runtime, el pipeline sigue siendo PaddleOCR ---------
#
# Medido sobre el panel de S9 (19 capturas, ramas intercaladas y orden sorteado, IC bootstrap):
#
#   | máquina                  | paddle inference | onnxruntime |        |
#   |--------------------------|------------------|-------------|--------|
#   | quieta                   | 881 ms           | 781 ms      | −11 %  |
#   | con los 6 núcleos llenos | 2767 ms          | 1669 ms     | −40 %  |
#
# La diferencia se agranda justo donde importa: en vivo el juego ocupa la máquina, y ahí el panel
# costaba 1784 ms contra 526-800 en el banco. Paddle pide 10 hilos sobre 6 núcleos y se degrada
# feo cuando no los consigue; ORT reparte mejor. **Lecturas idénticas en 19 de 19.**
#
# Lo que cambia es SÓLO el motor de inferencia: el pre-proceso (DBNet resize/normalize), el
# post-proceso (unclip de cajas, decodificación CTC) y los pesos son los mismos, porque los corre
# el mismo PaddleOCR. Los `.onnx` salen de convertir los MISMOS modelos que ya usaba
# (`tools/export_ocr_onnx.py`).
#
# Y de yapa arregla una deuda de D1: con `use_onnx=True` PaddleOCR **no descarga nada**
# (`maybe_download` queda del otro lado del `if not params.use_onnx`), así que los modelos dejan
# de vivir en `~/.paddleocr` —fuera de la app, bajados en el primer arranque— y pasan a viajar
# adentro de `app/resources/`.
_RES_OCR = Path(__file__).resolve().parents[1] / "resources" / "ocr"
_DET_ONNX = _RES_OCR / "ppocrv3_det_en.onnx"
_REC_ONNX = _RES_OCR / "ppocrv3_rec_latin.onnx"

#: Vuelve al motor de siempre sin tocar código ni reempaquetar (`DANIBOD_OCR_ENGINE=paddle`).
_ENV_MOTOR = "DANIBOD_OCR_ENGINE"


def motivo_sin_onnx() -> str | None:
    """`None` si se puede usar ONNX; si no, POR QUÉ no — para poder loguearlo.

    Devuelve el motivo en vez de un bool a propósito: un backend que se cae al camino lento sin
    decir cuál de las dos cosas le faltó es justamente la degradación silenciosa que la regla D2
    prohíbe. Acá el que llama tiene con qué escribir una línea accionable.
    """
    if os.environ.get(_ENV_MOTOR, "").strip().lower() == "paddle":
        return f"{_ENV_MOTOR}=paddle (pedido a mano)"
    faltan = [p.name for p in (_DET_ONNX, _REC_ONNX) if not p.is_file()]
    if faltan:
        return f"no están los modelos {', '.join(faltan)} en {_RES_OCR}"
    try:
        import onnxruntime  # noqa: F401
    except Exception as exc:                      # noqa: BLE001 — cualquier fallo de carga vale
        return f"onnxruntime no se pudo importar ({type(exc).__name__}: {exc})"
    return None


class PaddleBackend(OcrBackend):
    """
    Adapter sobre PaddleOCR. Mejor que Tesseract para números pequeños
    y texto con anti-aliasing en fondos oscuros (ej. valores de substats).
    """

    def __init__(self, lang: str = "es", use_gpu: bool = False):
        self._lang = lang
        self._use_gpu = use_gpu
        self._ocr = None  # lazy-loaded

    def _get_ocr(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                _ensure_paddle_site()
                kwargs = dict(
                    use_textline_orientation=False,
                    lang=self._lang,
                )
                # El motor: ONNX si se puede, y si no el de siempre DICIENDO por qué (D2).
                motivo = motivo_sin_onnx()
                if motivo is None:
                    kwargs.update(use_onnx=True, det_model_dir=str(_DET_ONNX),
                                  rec_model_dir=str(_REC_ONNX))
                    log.info("OCR: motor onnxruntime (modelos de app/resources/ocr)")
                else:
                    log.warning("OCR: se usa paddle inference porque %s. Es ~40 %% más lento "
                                "cuando la máquina está ocupada, que es siempre que el juego "
                                "corre al lado.", motivo)
                # Detectar parámetros soportados por la versión instalada
                import inspect
                sig = inspect.signature(PaddleOCR.__init__)
                if "use_gpu" in sig.parameters:
                    kwargs["use_gpu"] = self._use_gpu
                self._ocr = PaddleOCR(**kwargs)
            except ImportError as e:
                raise RuntimeError(
                    "paddleocr no instalado. Ejecutar: pip install paddleocr"
                ) from e
        return self._ocr

    @measure_latency("ocr_text")
    def text(self, img: np.ndarray, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        # Instrumentada (QA-06 §3.1, presupuesto 180 ms para el OCR completo). Es la etapa que el
        # doc de latencia señala como la única con margen real, así que es la que hay que medir
        # antes de decidir si conviene NCC o DirectML.
        # PaddleOCR no usa PSM — el parámetro se ignora para compatibilidad
        ocr = self._get_ocr()
        mem_diag.bump_ocr()
        try:
            result = ocr.ocr(img, cls=False)
        except Exception:
            return "", 0.0

        if not result or not result[0]:
            return "", 0.0

        texts = []
        confs = []
        for line in result[0]:
            if line and len(line) >= 2:
                txt = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                conf = float(line[1][1]) if isinstance(line[1], (list, tuple)) and len(line[1]) > 1 else 0.5
                texts.append(txt.strip())
                confs.append(conf)

        text = " ".join(texts).strip()
        avg_conf = (sum(confs) / len(confs)) if confs else 0.0
        return text, round(avg_conf, 3)

    def text_with_bboxes(self, img: np.ndarray) -> list[tuple[str, float, tuple[int, int, int, int]]]:
        """
        Devuelve [(texto, confianza, (x1,y1,x2,y2)), ...] con bboxes reales
        detectados por PaddleOCR. Cada bbox es la bounding box del polígono
        cuadrilátero que devuelve el detector DBNet.
        """
        ocr = self._get_ocr()
        mem_diag.bump_ocr()
        try:
            result = ocr.ocr(img, cls=False)
        except Exception:
            return []

        if not result or not result[0]:
            return []

        out: list[tuple[str, float, tuple[int, int, int, int]]] = []
        for line in result[0]:
            if not line or len(line) < 2:
                continue
            polygon, (text, conf) = line[0], line[1]
            if not polygon or len(polygon) < 4:
                continue
            xs = [int(p[0]) for p in polygon]
            ys = [int(p[1]) for p in polygon]
            x1, y1 = min(xs), min(ys)
            x2, y2 = max(xs), max(ys)
            txt = str(text).strip()
            conf_val = float(conf) if conf else 0.5
            if txt:
                out.append((txt, conf_val, (x1, y1, x2, y2)))

        return out

    def number(self, img: np.ndarray) -> tuple[float, float]:
        import re
        text, conf = self.text(img)
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if not m:
            return 0.0, 0.0
        return float(m.group(1)), conf
