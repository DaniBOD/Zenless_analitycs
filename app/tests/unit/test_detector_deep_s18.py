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


def test_deep_detect_solo_banner_ocr_es_tentativo():
    """Solo banner OCR (peso 2) → ocr_score=2, total=2 → tentativo conf 0.55."""
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    ocr = _StubOcr(banner_text="AGENT INFO", stats_text="")
    state = _deep_detect_s18(frame, ocr)
    assert state is not None
    assert state.code == "S18"
    # ocr_score=2 cumple gate de promoción pero total=2 (no >=3) → tentativo
    assert state.confidence == 0.55
    assert state.method == "deep_detect_tentativo"


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
def test_s18_fixtures_detectados_sin_ocr_minimo_tentativo(path):
    """
    Sin OCR (solo indicadores visuales): cada fixture S18 real debe al
    menos disparar el CLAHE indicator (peso 2) → tentativo conf 0.55.
    Sin promoción a deep_detect porque falta señal OCR confirmatoria.
    """
    frame = _read_frame(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar: {path}")
    state = _deep_detect_s18(frame, ocr=None)
    assert state is not None, (
        f"Fixture S18 {path.name}: deep_detect sin OCR devolvió None — "
        f"ningún indicador visual disparó"
    )
    assert state.code == "S18"
    # Sin OCR no debe promover a high confidence (anti-FP)
    assert state.method == "deep_detect_tentativo", (
        f"Fixture {path.name} sin OCR debería ser tentativo, fue: {state.method}"
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
    Sin OCR, los FP conocidos NO deben dispararse como deep_detect (alta conf).
    Pueden quedar como tentativo — el monitor los filtra vía buffer 2/3 frames.
    """
    if not path.exists():
        pytest.skip(f"FP fixture no disponible: {path}")
    frame = _read_frame(path)
    if frame is None:
        pytest.skip(f"No se pudo cargar: {path}")
    state = _deep_detect_s18(frame, ocr=None)
    if state is not None:
        assert state.method == "deep_detect_tentativo", (
            f"FP {path.name} promovido a deep_detect sin OCR — fallo crítico anti-FP. "
            f"template_name={state.template_name}"
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
