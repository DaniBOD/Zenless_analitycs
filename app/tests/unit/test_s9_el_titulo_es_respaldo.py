"""El título del panel S9 se lee sólo cuando hace falta (Fase 2D, 2026-09-20).

**El problema.** La espera click→log en el inventario era de 2766 ms y el 92 % era OCR. Dentro de
eso, 552 ms se iban en leer la franja del título para sacar el slot — dos lecturas por disco a
~286 ms cada una. Y peor: de las 479 lecturas de la pasada del 20/09, **378 las hizo el LOOP**
sobre frames que nadie iba a parsear, para dejar un `state.slot` que sólo consumía el sufijo de
una línea de log.

**Lo que se midió antes de tocar** (corpus de 19 capturas de `09_Inventario_discos_general`):
el panel llega al MISMO slot por su cuenta en 18, no dice nada distinto en ninguna, y la que
falta (Ejemplo_6, donde el "(6)" cae en una línea aparte) necesita el título. O sea: la lectura
no sobra, sobra pagarla **por adelantado**. Pasó de autoridad a respaldo.

Lo que fijan estos tests es la parte que se rompe en silencio: que en el camino normal no se pague
OCR ninguno, y que en el caso que lo necesita SÍ se pague. Un respaldo que nunca se ejerce y una
lectura que vuelve a hacerse siempre fallan las dos para el mismo lado — nadie se entera.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import app.core.detector as det_mod
from app.core.detector import ScreenDetector
from app.core.monitor import Monitor
from app.tests.unit.arnes_loop_monitor import correr_loop

REPO = Path(__file__).resolve().parents[3]
_S9 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "09_Inventario_discos_general"


class _DummyOcr:
    def text(self, *a, **kw):
        return "", 0.0

    def number(self, *a, **kw):
        return 0.0, 0.0


@pytest.fixture
def espia_titulo(monkeypatch):
    """Cuenta las lecturas de la franja del título, sin impedirlas."""
    real = det_mod.extract_s9_slot
    hechas: list[int] = []

    def contando(frame, ocr):
        hechas.append(1)
        return real(frame, ocr)

    monkeypatch.setattr(det_mod, "extract_s9_slot", contando)
    return hechas


# --- el loop --------------------------------------------------------------------------------

def test_el_loop_en_S9_no_lee_el_titulo_NUNCA(monkeypatch):
    """Corre el `_run` verdadero sobre 5 pasadas de S9. Antes del 2026-09-20 cada una pagaba una
    lectura del título (~286 ms en vivo) para dejar `state.slot`; ahora el slot lo resuelve el
    parser en el despacho, que es el único que lo necesita."""
    monkeypatch.delenv("DANIBOD_METRICS", raising=False)
    monkeypatch.delenv("DANIBOD_S9_DESPACHO_RAPIDO", raising=False)
    mon = Monitor(ocr=_DummyOcr(), detector=ScreenDetector())

    def prohibido(frame, ocr):
        raise AssertionError("el loop volvió a leer el título con OCR en cada vuelta")

    monkeypatch.setattr(det_mod, "extract_s9_slot", prohibido)
    reg = correr_loop(monkeypatch, mon, firmas=[0.0, 0.0, 0.0, 255.0, 255.0])
    assert reg.clasificados, "el arnés no corrió el loop"


# --- el parser ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _ocr():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


def _frame(nombre: str):
    import cv2
    p = _S9 / f"{nombre}.png"
    if not p.exists():
        pytest.skip(f"captura {nombre} no presente")
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
@pytest.mark.parametrize("nombre,slot", [("Ejemplo_1", 2), ("Ejemplo_5", 6), ("Ejemplo_19", 4)])
def test_el_camino_normal_no_paga_la_lectura_del_titulo(nombre, slot, _ocr, espia_titulo):
    """El panel ya vio el "(N)": pedirlo de nuevo aparte es pagar dos veces por el mismo dato."""
    from app.core.parser_disc_s17 import parse_disc_s9
    d = parse_disc_s9(_frame(nombre), _ocr)
    assert d.slot == slot, f"{nombre}: slot {d.slot} != {slot}"
    assert espia_titulo == [], f"{nombre}: se leyó el título {len(espia_titulo)} vez/veces de más"


@pytest.mark.skipif(not (_S9 / "Ejemplo_6.png").exists(), reason="captura Ejemplo_6 no presente")
def test_cuando_el_panel_no_sabe_el_titulo_lo_rescata(_ocr, espia_titulo):
    """Ejemplo_6: PaddleOCR deja el "(6)" en una línea aparte y el core se queda en slot 0. Es el
    único caso de los 19 del corpus, y es la razón por la que la lectura sigue existiendo."""
    from app.core.parser_disc_s17 import parse_disc_s9
    d = parse_disc_s9(_frame("Ejemplo_6"), _ocr)
    assert d.slot == 6, f"slot {d.slot} != 6 — el respaldo no entró"
    assert len(espia_titulo) == 1, f"lecturas del título: {len(espia_titulo)} (debía ser 1)"
    assert "slot_rescatado_por_titulo" in d.notas, d.notas


@pytest.mark.skipif(not (_S9 / "Ejemplo_1.png").exists(), reason="capturas S9 no presentes")
def test_el_slot_pasado_a_mano_sigue_mandando(_ocr, espia_titulo):
    """El parámetro `slot=` sigue ganando sobre todo lo demás: es lo que usan los tests del parser
    y cualquier llamador que ya tenga el dato. Un respaldo no puede convertirse en autoridad."""
    from app.core.parser_disc_s17 import parse_disc_s9
    d = parse_disc_s9(_frame("Ejemplo_1"), _ocr, slot=4)
    assert d.slot == 4
    assert espia_titulo == []
