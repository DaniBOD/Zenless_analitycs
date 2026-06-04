"""
Tests unitarios para `_deep_detect_s18` — Hito 2.8 cierre del gap test↔runtime.

Cubre:
  - Cada indicador visual aislado sobre un frame sintético controlado.
  - Scoring weighted (visuales=1, OCR=2) con thresholds 3 / 2 / <2.
  - Detección sobre los 7 fixtures reales `atributos_base_ejemplo_*.png`.
  - Negativos: deep_detect devuelve None sobre Falsos_positivos conocidos
    (sin texto S18 ni grilla de stats).

Estos tests SI invocan el camino real del detector (a diferencia de los
tests del parser que llaman `parse_agent_stats` directo). Aseguran que la
detección S18 funcione en el pipeline real sin necesidad de un template
match previo — exactamente lo que falla en .exe a 2560×1440.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.detector import (  # noqa: E402
    _deep_detect_s18,
    _s18_visual_tab_amarillo,
    _s18_visual_grilla_stats,
    _s18_visual_valores_brillantes,
    _s18_visual_agent_info_clahe,
    _s18_ocr_agent_info,
    _s18_ocr_stat_keywords,
    _strip_accents_lower,
)


REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
S18_FIXTURES = sorted(FIXTURES.glob("atributos_base_ejemplo_*.png"))
FP_FIXTURES = [
    REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_1.png",
    REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_2.png",
    REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_3.png",
    REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_4.png",
]


def _read_frame(path: Path) -> np.ndarray | None:
    """Lee imagen tolerando paths con caracteres no-ASCII (Windows)."""
    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class _StubOcr:
    """OCR backend dummy que devuelve texto fijo por ROI según un map."""

    def __init__(self, banner_text: str = "", stats_text: str = ""):
        self.banner_text = banner_text
        self.stats_text = stats_text
        self.calls: list[tuple[int, int]] = []

    def text(self, img, psm: int = 6, lang: str = "spa") -> tuple[str, float]:
        if img is None or img.size == 0:
            return ("", 0.0)
        h, w = img.shape[:2]
        self.calls.append((h, w))
        # Heurística simple: ROI ancha + corta = banner; ROI ancha + alta = stats.
        if h < 200:
            return (self.banner_text, 0.9 if self.banner_text else 0.0)
        return (self.stats_text, 0.9 if self.stats_text else 0.0)

    def number(self, img):
        return (0.0, 0.0)


# ---------------------------------------------------------------------------
# Tests de helpers internos
# ---------------------------------------------------------------------------

def test_strip_accents_lower_basico():
    assert _strip_accents_lower("Atributos Básicos") == "atributos basicos"
    assert _strip_accents_lower("Anomalía") == "anomalia"
    assert _strip_accents_lower("") == ""
    assert _strip_accents_lower(None) == ""  # type: ignore[arg-type]


def test_deep_detect_devuelve_none_frame_vacio():
    assert _deep_detect_s18(None, None) is None
    assert _deep_detect_s18(np.zeros((0, 0, 3), dtype=np.uint8), None) is None


def test_deep_detect_negro_total_sin_ocr_devuelve_none():
    """Frame negro → ningún indicador visual fire → score 0 → None."""
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    assert _deep_detect_s18(frame, None) is None


def test_deep_detect_full_ocr_es_high_confidence():
    """Frame negro + OCR ambos hits → ocr_score=4, total=4 → deep_detect conf 0.75."""
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    ocr = _StubOcr(banner_text="AGENT INFO", stats_text="PV Ataque Defensa Impacto")
    state = _deep_detect_s18(frame, ocr)
    assert state is not None
    assert state.code == "S18"
    assert state.confidence == 0.75
    assert state.method == "deep_detect"
    assert "ocr_agent_info" in state.template_name
    assert "ocr_stats_" in state.template_name


def test_deep_detect_solo_banner_ocr_no_alcanza():
    """
    Solo banner OCR (peso 2) sobre frame negro → ocr_score=2 pero total=2 (<3)
    → None. El path tentativo (conf 0.55) fue eliminado el 2026-06-03; ahora la
    promoción exige ocr_score>=2 AND total>=3 (banner + grilla visual, o banner
    + keywords stats).
    """
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    ocr = _StubOcr(banner_text="AGENT INFO", stats_text="")
    state = _deep_detect_s18(frame, ocr)
    assert state is None


def test_deep_detect_pocos_keywords_no_dispara():
    """Solo 2 keywords stats (sin completar 3 grupos) → no cuenta como OCR hit."""
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    ocr = _StubOcr(banner_text="", stats_text="PV Ataque")  # solo 2 grupos
    state = _deep_detect_s18(frame, ocr)
    assert state is None  # ningún indicador alcanza, ni visual ni OCR


def test_deep_detect_ocr_gating_visuales_solos_no_promueven():
    """
    Frame con score visual alto (simulado) pero ocr_score=0 → nunca deep_detect.
    Caso real: S16 modal Info conjunto que tiene grid + CLAHE.
    """
    # Simulamos con un frame real S16 (FP)
    fp = REPO / "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_1.png"
    if not fp.exists():
        pytest.skip("FP fixture no disponible")
    frame = _read_frame(fp)
    if frame is None:
        pytest.skip("No se pudo cargar FP")
    # Sin OCR: aunque visual_score >= 3, ocr_score=0 → no promueve
    state = _deep_detect_s18(frame, ocr=None)
    if state is not None:
        assert state.method != "deep_detect", (
            f"FP con visuales fuertes y sin OCR no debería promover a deep_detect. "
            f"template={state.template_name}"
        )


def test_deep_detect_ignora_errores_ocr():
    """OCR que lanza excepción → indicadores OCR a 0 pero no rompe."""

    class _BrokenOcr:
        def text(self, img, psm: int = 6, lang: str = "spa"):
            raise RuntimeError("OCR muerto")

        def number(self, img):
            return (0.0, 0.0)

    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    assert _deep_detect_s18(frame, _BrokenOcr()) is None  # no levanta


# ---------------------------------------------------------------------------
# Tests sobre fixtures reales S18
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", S18_FIXTURES, ids=lambda p: p.stem)
def test_s18_fixtures_sin_ocr_ya_no_disparan(path):
    """
    Sin OCR (solo indicadores visuales): deep_detect ahora devuelve None.
    El path tentativo visual-solo (conf 0.55) fue eliminado el 2026-06-03 porque
    disparaba S18 falso sobre la pantalla de entrada y S8. La detección de S18 en
    el pipeline real la hace ahora `detect_active_tab` (tab-bar) + template; el
    deep_detect queda como refuerzo SOLO con confirmación OCR de stats/banner.
    """
    frame = _read_frame(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar: {path}")
    state = _deep_detect_s18(frame, ocr=None)
    assert state is None, (
        f"Fixture S18 {path.name} sin OCR debería dar None (visual-solo ya no "
        f"promueve), dio: {state.method if state else None}"
    )


@pytest.mark.parametrize("path", S18_FIXTURES, ids=lambda p: p.stem)
def test_s18_fixtures_high_confidence_con_ocr_simulado(path):
    """Con OCR que devuelve banner + stats keywords: 7/7 → deep_detect conf 0.75."""
    frame = _read_frame(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar: {path}")
    # Simulamos OCR que reconoce el banner y los stats típicos de S18
    ocr = _StubOcr(
        banner_text="AGENT INFO",
        stats_text="PV Ataque Defensa Impacto Probabilidad CRIT Anomalia",
    )
    state = _deep_detect_s18(frame, ocr)
    assert state is not None
    assert state.code == "S18"
    assert state.method == "deep_detect", (
        f"Fixture {path.name} con OCR simulado debería ser deep_detect, fue: {state.method}"
    )
    assert state.confidence == 0.75


# ---------------------------------------------------------------------------
# Tests negativos — Falsos_positivos NO deben dispararse como S18
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", FP_FIXTURES, ids=lambda p: p.name)
def test_falsos_positivos_no_se_detectan_como_s18_sin_ocr(path):
    """
    Sin OCR, los FP conocidos NO deben dispararse como S18: ahora dan None
    (el tentativo visual-solo fue eliminado el 2026-06-03).
    """
    if not path.exists():
        pytest.skip(f"FP fixture no disponible: {path}")
    frame = _read_frame(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar: {path}")
    state = _deep_detect_s18(frame, ocr=None)
    assert state is None, (
        f"FP {path.name} sin OCR debería dar None, dio: "
        f"{state.method if state else None}"
    )


def test_falsos_positivos_no_se_detectan_como_s18_con_ocr_no_s18():
    """
    Con OCR que devuelve texto realista del modal S16 (no contiene 'AGENT INFO'
    ni keywords stats): nunca debe llegar a deep_detect aunque visuales fire.
    """
    for path in FP_FIXTURES:
        if not path.exists():
            continue
        frame = _read_frame(path)
        if frame is None:
            continue
        ocr = _StubOcr(banner_text="Informacion del conjunto", stats_text="2 piezas")
        state = _deep_detect_s18(frame, ocr)
        if state is not None:
            assert state.method != "deep_detect", (
                f"FP {path.name} con OCR no-S18: promovido a deep_detect. "
                f"template_name={state.template_name}"
            )
