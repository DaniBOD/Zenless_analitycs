"""
Test de integración — cierre del gap test↔runtime para S18 (Hito 2.8).

Los tests unitarios de `parse_agent_stats` y `_deep_detect_s18` cubren las
piezas en aislamiento, pero el bug original era que el callback
`on_agent_stats` jamás se disparaba en el .exe a pesar de que las piezas
funcionaban en aislamiento. Este test simula el camino completo:

    frame → ScreenDetector.classify() → _deep_detect_s18 (fallback) →
    TemporalBuffer.promote_now() / .add() → _dispatch_state() →
    _maybe_process_agent_stats() → parse_agent_stats() → on_agent_stats CB

Si pasa, la cadena entera está conectada y futuras regresiones de wiring
se detectan en CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.detector import ScreenDetector, _deep_detect_s18  # noqa: E402
from app.core.parser_agent_stats import AgentStatsParsed  # noqa: E402


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
S18_FIXTURES = sorted(FIXTURES.glob("atributos_base_ejemplo_*.png"))


def _read_frame(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class _StubOcr:
    """OCR stub que simula resultados de S18 sin invocar Tesseract real."""

    def __init__(self, banner_text: str, stats_text: str, profile_text: str = ""):
        self.banner_text = banner_text
        self.stats_text = stats_text
        self.profile_text = profile_text or stats_text

    def text(self, img, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        if img is None or img.size == 0:
            return ("", 0.0)
        h, w = img.shape[:2]
        # Heurística por tamaño: banner pequeño = banner_text
        if h < 200:
            return (self.banner_text, 0.85)
        return (self.profile_text, 0.85)

    def number(self, img):
        return (0.0, 0.0)

    def text_with_bboxes(self, img):
        # Compatibilidad con parser_agent_stats PaddleOCR path: devuelve
        # texto completo concatenado para que el parser pueda regex sobre él.
        return [(self.profile_text, 0.85, (0, 0, img.shape[1], img.shape[0]))]


def _dispatch_pipeline(frame: np.ndarray, detector: ScreenDetector, ocr) -> tuple:
    """
    Reproduce el camino real del monitor:
      1. classify(frame)
      2. si S12 → deep_detect_s18 fallback
      3. devuelve el ScreenState resultante (post-fallback)
    """
    raw_state = detector.classify(frame)
    if raw_state.code == "S12":
        deep = _deep_detect_s18(frame, ocr)
        if deep is not None:
            raw_state = deep
    return raw_state


# ---------------------------------------------------------------------------
# Test 1: el pipeline completo detecta S18 sobre los 7 fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", S18_FIXTURES, ids=lambda p: p.stem)
def test_pipeline_detecta_s18_via_template_o_deep_detect(path):
    """
    Cada fixture S18 debe terminar con state.code == 'S18' después del
    pipeline completo (template match O deep_detect fallback con OCR).
    """
    frame = _read_frame(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar: {path}")

    detector = ScreenDetector()
    # OCR stub que cumple las dos señales (AGENT INFO + stats keywords)
    ocr = _StubOcr(
        banner_text="AGENT INFO",
        stats_text=(
            "Nv 60 PV 17245 Ataque 1907 Defensa 667 Impacto 119 "
            "Probabilidad CRIT 65% Daño CRIT 162% Tasa Anomalia 110 "
            "Maestria Anomalia 95 Tasa Perforacion 0% Recuperacion Energia 1.20"
        ),
    )

    state = _dispatch_pipeline(frame, detector, ocr)

    assert state.code == "S18", (
        f"Pipeline para {path.name} terminó en {state.code} "
        f"(conf={state.confidence}, tmpl={state.template_name}, method={state.method})"
    )


def test_pipeline_deep_detect_se_dispara_cuando_template_falla(monkeypatch):
    """
    Simula la situación del .exe: classify devuelve S12 → deep_detect
    debe activarse como fallback y devolver S18.

    Forzamos `classify` a devolver S12 para que el camino deep_detect
    se ejecute, sobre un fixture S18 real.
    """
    if not S18_FIXTURES:
        pytest.skip("Sin fixtures S18")
    frame = _read_frame(S18_FIXTURES[0])
    if frame is None:
        pytest.skip("No se pudo cargar fixture")

    detector = ScreenDetector()

    # Monkey-patch classify para forzar S12 (como pasa en .exe a 2560×1440)
    from app.core.detector import ScreenState

    def _fake_classify(_self, _frame):
        return ScreenState(
            code="S12",
            confidence=0.0,
            template_name="forced_no_match",
            method="template",
        )

    monkeypatch.setattr(ScreenDetector, "classify", _fake_classify)

    ocr = _StubOcr(
        banner_text="AGENT INFO",
        stats_text="PV Ataque Defensa Impacto Probabilidad CRIT",
    )
    state = _dispatch_pipeline(frame, detector, ocr)

    assert state.code == "S18", (
        f"Con classify forzado a S12, deep_detect debió rescatar a S18. "
        f"Resultado: {state.code} method={state.method} tmpl={state.template_name}"
    )
    assert state.method == "deep_detect", (
        f"Resultado debería marcado como deep_detect, fue: {state.method}"
    )


# ---------------------------------------------------------------------------
# Test 2: TemporalBuffer.promote_now dispara emisión sin esperar 2/3
# ---------------------------------------------------------------------------

def test_temporal_buffer_promote_emite_en_primer_frame():
    """`promote_now` emite el state en el primer frame, sin votación 2/3."""
    from app.core.detector import TemporalBuffer, ScreenState

    buf = TemporalBuffer(window_size=3)
    s18 = ScreenState("S18", 0.75, "deep_detect", method="deep_detect")
    voted = buf.promote_now(s18)
    assert voted is not None
    assert voted.code == "S18"
    assert buf.last_emitted == "S18"


def test_temporal_buffer_promote_dedup_segundo_frame_mismo_codigo():
    """`promote_now` con mismo código consecutivo devuelve None (dedup)."""
    from app.core.detector import TemporalBuffer, ScreenState

    buf = TemporalBuffer(window_size=3)
    s18 = ScreenState("S18", 0.75, "deep_detect", method="deep_detect")
    first = buf.promote_now(s18)
    second = buf.promote_now(s18)
    assert first is not None
    assert second is None


def test_temporal_buffer_promote_no_rompe_voting_normal():
    """Después de un promote, add() para otro código debe seguir funcionando."""
    from app.core.detector import TemporalBuffer, ScreenState

    buf = TemporalBuffer(window_size=3)
    s18 = ScreenState("S18", 0.75, "deep_detect", method="deep_detect")
    buf.promote_now(s18)
    # Usuario sale de S18 — frames sucesivos S15
    s15 = ScreenState("S15", 0.90, "s15_menu", method="template")
    r1 = buf.add(s15)  # ventana: [S18, S15] (sin alcanzar window_size=3)
    r2 = buf.add(s15)  # ventana: [S18, S15, S15] → mayoría S15
    assert r1 is None  # buffer aún no full
    assert r2 is not None and r2.code == "S15"


# ---------------------------------------------------------------------------
# Test 3: Monitor._maybe_process_agent_stats dispara callback on_agent_stats
# ---------------------------------------------------------------------------

def test_monitor_dispatch_invoca_on_agent_stats():
    """
    Simula `monitor._dispatch_state(frame, S18_state)` directo y verifica que
    `on_agent_stats` callback es invocado con un `AgentStatsParsed` válido.

    Esta es la pieza crítica que el .exe estaba saltándose: aunque el parser
    funcionaba, el callback nunca corría porque S18 jamás se clasificaba.
    """
    if not S18_FIXTURES:
        pytest.skip("Sin fixtures S18")
    frame = _read_frame(S18_FIXTURES[0])
    if frame is None:
        pytest.skip("No se pudo cargar fixture")

    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list[tuple[AgentStatsParsed, ScreenState]] = []

    ocr = _StubOcr(
        banner_text="AGENT INFO",
        stats_text=(
            "Nv 60 PV 17245 Ataque 1907 Defensa 667 Impacto 119 "
            "Probabilidad CRIT 65% Daño CRIT 162%"
        ),
    )

    monitor = Monitor(
        ocr=ocr,
        detector=ScreenDetector(),
        on_agent_stats=lambda stats, st: received.append((stats, st)),
    )

    s18_state = ScreenState(
        code="S18",
        confidence=0.75,
        template_name="deep_detect:test",
        method="deep_detect",
    )

    monitor._dispatch_state(frame, s18_state)

    assert len(received) == 1, (
        f"Se esperaba 1 invocación de on_agent_stats, hubo {len(received)}. "
        f"El callback NO fue disparado — el wiring entre _dispatch_state y "
        f"_process_agent_stats está roto."
    )
    stats, state = received[0]
    assert isinstance(stats, AgentStatsParsed)
    assert state.code == "S18"


def test_monitor_dispatch_dedup_no_re_invoca_mismo_estado():
    """Dos `_dispatch_state(frame, S18)` consecutivos disparan UNA sola vez."""
    if not S18_FIXTURES:
        pytest.skip("Sin fixtures S18")
    frame = _read_frame(S18_FIXTURES[0])
    if frame is None:
        pytest.skip("No se pudo cargar fixture")

    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    ocr = _StubOcr(banner_text="AGENT INFO", stats_text="PV Ataque Defensa")
    monitor = Monitor(
        ocr=ocr,
        detector=ScreenDetector(),
        on_agent_stats=lambda stats, st: received.append((stats, st)),
    )

    s18 = ScreenState("S18", 0.75, "deep_detect", method="deep_detect")
    monitor._dispatch_state(frame, s18)
    monitor._dispatch_state(frame, s18)

    assert len(received) == 1, (
        f"Dedup roto: {len(received)} invocaciones para 2 dispatch del mismo estado."
    )
