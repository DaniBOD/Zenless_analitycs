"""QA NEGATIVO MASIVO — ninguna pantalla del folder de FP debe gatillar un estado de
captura/reporte.

Replica la decisión de detección REAL del monitor (`_monitor_decision`): `classify()` +
fallback `_deep_detect_s18` (con OCR real) cuando classify da S12 y no hay tab-bar. Cada
screenshot del folder tiene un `allowed` set según su grupo (ver GROUPS): la mayoría debe ser
S12 (no reconocida); los modales no-capturables reales (S16 detalle-set, S11 desmontaje) se
permiten como clasificación correcta.

Los mensajes de assert vuelcan `code · conf · method · template` → sirven de BASELINE de
diagnóstico (qué dispara y por qué path) además de guardia de regresión.

Corre con PaddleOCR real (se saltea si no está disponible), como test_monitor_s9.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.detector import ScreenDetector, detect_active_tab, _deep_detect_s18

REPO = Path(__file__).resolve().parents[3]
FP_DIR = REPO / "Documentacion" / "Screenshots_Triggers" / "Triggers_Generales" / "Falsos_positivos"

# Allowed-set por prefijo de nombre de archivo (ver plan). Default estricto = {S12}.
GROUPS: dict[str, set[str]] = {
    "Detalle_set_disco": {"S16", "S12"},        # modal Info de conjunto (no captura)
    "Dispara_disco_descarte": {"S11", "S12"},   # desmontaje (no captura)
    # Todo lo demás debe ser NO reconocido (S12), incl. Resultado_desafio_otro_farmeo
    # (es un resultado real pero SIN discos → no es farmeo de discos → forzar S12).
    "Resultado_desafio_otro_farmeo": {"S12"},
    "Eventos": {"S12"},
    "Guia_Rapida": {"S12"},
    "Modo_Libre": {"S12"},
    "Modo_foto": {"S12"},
    "Menu_Pausa": {"S12"},
    "Pase_batalla": {"S12"},
    "Banners": {"S12"},
}


def _allowed_for(name: str) -> set[str]:
    for prefix, allowed in GROUPS.items():
        if name.startswith(prefix):
            return allowed
    return {"S12"}


def _load(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def ocr():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@pytest.fixture(scope="module")
def detector():
    return ScreenDetector()


def _monitor_decision(frame, detector, ocr):
    """Réplica de la decisión del monitor (monitor.py _run): classify + fallback deep_detect
    S18 (si S12 y sin tab-bar). El tab-override ya vive dentro de classify()."""
    state = detector.classify(frame)
    if state.code == "S12" and detect_active_tab(frame) is None:
        deep = _deep_detect_s18(frame, ocr)
        if deep is not None:
            return deep
    return state


_FP_FILES = sorted(FP_DIR.glob("*.png")) if FP_DIR.exists() else []


@pytest.mark.skipif(not _FP_FILES, reason="folder de FP no presente")
@pytest.mark.parametrize("path", _FP_FILES, ids=lambda p: p.name)
def test_fp_no_gatilla_captura(path, detector, ocr):
    frame = _load(path)
    if frame is None:
        pytest.skip(f"No se pudo leer: {path.name}")
    decision = _monitor_decision(frame, detector, ocr)
    allowed = _allowed_for(path.name)
    assert decision.code in allowed, (
        f"FP {path.name} → {decision.code} (conf={decision.confidence:.2f}, "
        f"method={decision.method}, tmpl={decision.template_name}); allowed={sorted(allowed)}"
    )


# ---- Regresión POSITIVA: los fixes no deben romper la detección real -------------------
_TRIG = REPO / "Documentacion" / "Screenshots_Triggers"
_FIX = REPO / "app" / "tests" / "fixtures"

# S2 farmeo real (debe SEGUIR clasificando como S2: _verify_s2 no debe sobre-rechazar).
_S2_POS = sorted((_TRIG / "Discos_Triggers" / "01_Pantalla_Resultado_Desafio").glob("*.png"))
_S2_POS += [_FIX / "s2_resultado_ejemplo_1.png", _FIX / "s2_resultado_ejemplo_2.png"]
# S18 (debe SEGUIR clasificando como S18 tras remover la rama HSV: template/tab/deep_detect).
_S18_POS = [_FIX / f"atributos_base_ejemplo_{i}.png" for i in range(1, 8)]


@pytest.mark.skipif(not _S2_POS, reason="fixtures S2 no presentes")
@pytest.mark.parametrize("path", _S2_POS, ids=lambda p: p.name)
def test_s2_farmeo_real_sigue_siendo_s2(path, detector, ocr):
    """Un farmeo de discos real debe seguir clasificando como S2 (verify_s2 pasa: hay franjas)."""
    frame = _load(path)
    if frame is None:
        pytest.skip(f"No se pudo leer: {path.name}")
    decision = _monitor_decision(frame, detector, ocr)
    assert decision.code == "S2", (
        f"S2 farmeo real {path.name} → {decision.code} (conf={decision.confidence:.2f}, "
        f"tmpl={decision.template_name}); _verify_s2 sobre-rechazó"
    )


@pytest.mark.skipif(not all(p.exists() for p in _S18_POS), reason="fixtures S18 no presentes")
@pytest.mark.parametrize("path", _S18_POS, ids=lambda p: p.name)
def test_s18_real_sigue_siendo_s18(path, detector, ocr):
    """S18 real debe seguir detectándose tras remover la rama HSV (template/tab/deep_detect)."""
    frame = _load(path)
    if frame is None:
        pytest.skip(f"No se pudo leer: {path.name}")
    decision = _monitor_decision(frame, detector, ocr)
    assert decision.code == "S18", (
        f"S18 real {path.name} → {decision.code} (conf={decision.confidence:.2f}, "
        f"method={decision.method}, tmpl={decision.template_name}); la remoción HSV lo rompió"
    )
