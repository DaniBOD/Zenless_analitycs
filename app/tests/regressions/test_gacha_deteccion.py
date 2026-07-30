"""Regresión de la detección del gacha (S27 banner / S28 resultados).

Los fixtures están GITIGNOREADOS (viven locales, crecen con cada patch), así que todo el módulo
es skip-if-absent — mismo criterio que el resto de tests que consumen `Screenshots_Triggers/`.

El descubrimiento es por glob a propósito: cuando Daniel agregue los banners de 3.2, 3.3, etc.,
la cobertura se extiende sola sin tocar este archivo.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from app.core.detector import ScreenDetector

REPO = Path(__file__).resolve().parents[3]
GACHA = REPO / "Documentacion" / "Screenshots_Triggers" / "Gacha_Sintonizacion"
BANNERS_DIR = GACHA / "Banners"
GRIDS_DIR = GACHA / "Resultados_sintonizacion"

# Los dos fixtures de `Resultados_sintonizacion/` que NO son la grilla: el splash del agente
# contratado y la animación de recolección. Son negativos de S28, no positivos.
NO_GRILLA = {"Ejemplo_3.png", "Ejemplo_6.png"}

# Estados que capturan datos o escriben. Ningún fixture del gacha puede dispararlos: sería
# meter basura en el pipeline de discos.
ESTADOS_PELIGROSOS = {"S2", "S3", "S13", "S17", "S22", "S23", "S24", "S25"}


def _png(d: Path) -> list[Path]:
    return sorted(d.glob("*.png")) if d.is_dir() else []


banners = _png(BANNERS_DIR)
grids = [p for p in _png(GRIDS_DIR) if p.name not in NO_GRILLA]
no_grilla = [p for p in _png(GRIDS_DIR) if p.name in NO_GRILLA]

pytestmark = pytest.mark.skipif(
    not banners or not grids,
    reason=f"fixtures de gacha ausentes (son locales, gitignoreados): {GACHA}",
)


@pytest.fixture(scope="module")
def det() -> ScreenDetector:
    # Sin máquina de estados: se clasifica cada frame aislado, sin filtro de transiciones.
    return ScreenDetector(use_state_machine=False)


@pytest.mark.parametrize("path", banners, ids=lambda p: p.name)
def test_banner_da_s27(det: ScreenDetector, path: Path):
    st = det.classify(cv2.imread(str(path)))
    assert st.code == "S27", f"{path.name} → {st.code} ({st.confidence:.3f}, {st.template_name})"


@pytest.mark.parametrize("path", grids, ids=lambda p: p.name)
def test_grilla_da_s28(det: ScreenDetector, path: Path):
    st = det.classify(cv2.imread(str(path)))
    assert st.code == "S28", f"{path.name} → {st.code} ({st.confidence:.3f}, {st.template_name})"


@pytest.mark.parametrize("path", no_grilla, ids=lambda p: p.name)
def test_splash_y_animacion_no_son_s28(det: ScreenDetector, path: Path):
    """El splash del agente y la animación comparten pantalla con la grilla pero no tienen
    recompensas legibles. Que caigan a S12 es lo correcto."""
    st = det.classify(cv2.imread(str(path)))
    assert st.code != "S28", f"{path.name} dio S28 ({st.confidence:.3f})"


@pytest.mark.parametrize("path", banners + grids + no_grilla, ids=lambda p: p.name)
def test_gacha_no_dispara_estados_de_captura(det: ScreenDetector, path: Path):
    """Anti-FP. Nace de una medición concreta: `Aria.png` matchea 0.773 contra el template de
    S2, cuyo umbral es 0.80 — margen de 0.027 contra un estado que captura discos. Por eso S28
    va antes que S2 en `_STATE_TEMPLATES`."""
    st = det.classify(cv2.imread(str(path)))
    assert st.code not in ESTADOS_PELIGROSOS, (
        f"{path.name} disparó {st.code} ({st.confidence:.3f}, {st.template_name})")
