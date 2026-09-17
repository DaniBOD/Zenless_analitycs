"""Todo el OCR que pasa por el proxy se mide — no sólo el método que alguien se acordó de decorar.

Hasta el 2026-09-16 `OcrProxy` instrumentaba **sólo `text`**. `text_with_bboxes`, que es el OCR
PRINCIPAL del pipeline (el panel de S9 y S17, S26, S3, S10, desmontaje, extracción), no dejaba
rastro. Medido offline sobre el panel de S9: **735 ms contra 89 ms** de una lectura de texto. O sea
que `ocr_text` reportó durante meses la parte chica del OCR, y la grande aparecía como tiempo sin
explicar: ~1,5 s por disco en la Pasada A del censo, ~2,5 s por arma en S26.

Es la práctica C3 en otra forma: una métrica que PARECE completa ("ocr_text") y omite el costo
principal se lee igual que una métrica completa y baja. Por eso el test que importa acá no es
"estos dos miden" sino **"ningún método del contrato de OCR puede quedar sin medir"**.
"""
from __future__ import annotations

import inspect
import sqlite3

import numpy as np
import pytest

from app.core.ocr_backend import OcrBackend
from app.core.ocr_service import OcrProxy

IMG = np.zeros((8, 8, 3), dtype=np.uint8)


@pytest.fixture
def met(tmp_path, monkeypatch):
    import app.core.metrics as m
    monkeypatch.setenv("DANIBOD_METRICS", "1")
    monkeypatch.setenv("DANIBOD_METRICS_DB", str(tmp_path / "metrics.db"))
    m.reset()
    yield m
    m.reset()


def _n(path, superficie):
    if not path.exists():
        return 0
    con = sqlite3.connect(str(path))
    try:
        return con.execute("SELECT COUNT(*) FROM metrics_latency WHERE superficie=?",
                           (superficie,)).fetchone()[0]
    finally:
        con.close()


def _proxy_sin_worker(monkeypatch):
    """El proxy con `_despachar` de mentira: se prueba la medición, no el worker."""
    px = OcrProxy()
    respuestas = {"text": ("", 0.0), "number": (0.0, 0.0), "text_with_bboxes": []}
    monkeypatch.setattr(px, "_despachar", lambda metodo, args, por_defecto: respuestas[metodo])
    return px


@pytest.mark.parametrize("metodo,args,superficie", [
    ("text", (IMG,), "ocr_text"),
    ("number", (IMG,), "ocr_number"),
    ("text_with_bboxes", (IMG,), "ocr_bboxes"),
])
def test_cada_llamada_de_ocr_deja_su_muestra(met, tmp_path, monkeypatch, metodo, args, superficie):
    px = _proxy_sin_worker(monkeypatch)
    getattr(px, metodo)(*args)
    met.flush()
    assert _n(tmp_path / "metrics.db", superficie) == 1


def test_las_superficies_no_se_mezclan(met, tmp_path, monkeypatch):
    """`ocr_text` conserva su serie histórica: un panel con cajas no puede entrar ahí, o la serie
    vieja y la nueva dejarían de ser comparables (C1)."""
    px = _proxy_sin_worker(monkeypatch)
    px.text_with_bboxes(IMG)
    px.number(IMG)
    met.flush()
    assert _n(tmp_path / "metrics.db", "ocr_text") == 0


def _metodos_del_contrato() -> list[str]:
    """Los métodos de OCR del contrato: los públicos de `OcrBackend` que se llaman sobre una
    instancia. `preprocess` es un helper estático de imagen, no una lectura."""
    return sorted(
        nombre for nombre, attr in vars(OcrBackend).items()
        if not nombre.startswith("_") and callable(attr) and not isinstance(attr, staticmethod)
    )


def test_ningun_metodo_de_ocr_del_proxy_queda_sin_medir():
    """**El test que habría evitado el agujero.** Si mañana el contrato gana un método nuevo
    (`boxes`, `layout`…) y el proxy lo implementa sin decorar, esto cae con su nombre — en vez de
    que el costo aparezca otra vez como tiempo sin explicación en una pasada en vivo."""
    metodos = _metodos_del_contrato()
    assert {"text", "number", "text_with_bboxes"} <= set(metodos), metodos
    sin_medir = [m for m in metodos if not hasattr(inspect.getattr_static(OcrProxy, m), "__wrapped__")]
    assert not sin_medir, f"métodos de OCR del proxy sin instrumentar: {sin_medir}"
