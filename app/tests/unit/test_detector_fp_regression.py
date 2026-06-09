"""Tests de regresión — FPs conocidos que NO deben clasificarse como capturables."""
import sys
from pathlib import Path
import cv2
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.detector import ScreenDetector, CAPTURE_DISC_STATES


FP_SCREENSHOTS = [
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Dispara_disco_descarte.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_1.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_2.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_3.png",
    "Documentacion/Screenshots_Triggers/Triggers_Generales/Falsos_positivos/Detalle_set_disco_ejemplo_4.png",
]

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("rel_path", FP_SCREENSHOTS)
def test_fp_no_capture(rel_path):
    """Ningún FP screenshot debe clasificarse como estado capturable."""
    path = REPO / rel_path
    if not path.exists():
        pytest.skip(f"Archivo no encontrado: {path}")

    img = cv2.imread(str(path))
    if img is None:
        pytest.skip(f"No se pudo leer: {path}")

    detector = ScreenDetector()
    state = detector.classify(img)

    assert state.code not in CAPTURE_DISC_STATES, (
        f"FP {rel_path} clasificado como {state.code} (conf={state.confidence:.3f}, "
        f"tmpl={state.template_name}) — debe ser NO capturable"
    )
    assert state.code != "S12" or state.template_name != "", (
        f"FP {rel_path} debe tener template_name informativo aunque sea S12"
    )


def test_dark_frame_filter_detects_fp_screenshot():
    """Verificar que el filtro de frame oscuro detecta correctamente el FP conocido."""
    path = REPO / FP_SCREENSHOTS[0]
    if not path.exists():
        pytest.skip(f"Archivo no encontrado: {path}")

    img = cv2.imread(str(path))
    assert bool(ScreenDetector._is_dark_frame(img)), (
        "El FP screenshot debe ser detectado como frame oscuro"
    )


# Calibración del dark_frame_filter (2026-06-06): el umbral (0.68) debe quedar
# ENTRE el dark_ratio de los S18 legítimos (≤0.595) y el de los frames oscuros
# reales (≥0.760). Estos dos tests blindan que no se vuelva a calibrar muy justo
# (regresión Zhu Yuan: S18 de PJ oscuro mal clasificada como S12).

S18_FIXTURES = [f"app/tests/fixtures/atributos_base_ejemplo_{i}.png" for i in range(1, 8)]
# Zhu Yuan: caso real que disparó la regresión. Su S18 mide dark_ratio=0.610
# (traje azul marino + fondo CRIT oscuro), apenas sobre el viejo umbral 0.60.
# Con 0.68 ya no gatea. Fixture explícito para blindar el caso para siempre.
S18_FIXTURES.append("app/tests/fixtures/atributos_base_zhuyuan_oscuro.png")


@pytest.mark.parametrize("rel_path", S18_FIXTURES)
def test_s18_no_es_frame_oscuro(rel_path):
    """Las pantallas S18 legítimas NO deben gatear como frame oscuro (Zhu Yuan)."""
    path = REPO / rel_path
    if not path.exists():
        pytest.skip(f"Archivo no encontrado: {path}")
    img = cv2.imread(str(path))
    if img is None:
        pytest.skip(f"No se pudo leer: {path}")
    assert not ScreenDetector._is_dark_frame(img), (
        f"S18 legítimo {rel_path} clasificado como frame oscuro → no extraería stats"
    )


@pytest.mark.parametrize("rel_path", FP_SCREENSHOTS)
def test_frames_oscuros_reales_siguen_gateando(rel_path):
    """Los frames oscuros reales (loading/transición) DEBEN seguir gateando."""
    path = REPO / rel_path
    if not path.exists():
        pytest.skip(f"Archivo no encontrado: {path}")
    img = cv2.imread(str(path))
    if img is None:
        pytest.skip(f"No se pudo leer: {path}")
    assert ScreenDetector._is_dark_frame(img), (
        f"Frame oscuro real {rel_path} ya no gatea → riesgo de FP en transición"
    )


# Regresión 2026-06-08 (QA Burnice/Caesar): las S17 de PJs con FONDO OSCURO de
# elemento (dark-ratio centro 0.68-0.71) se filtraban como dark → S12 ANTES del
# template match → no se capturaba NADA (mientras Yixuan, 0.63, pasaba). El filtro
# ahora es TEMPLATE-AWARE: corre DESPUÉS del template y solo gatea si ningún
# template matchó. Estas capturas son "dark" por el filtro crudo pero matchean S17.
_SLOTS = "Documentacion/Screenshots_Triggers/Discos_Triggers/14_Slots_equipamiento"
S17_DARK_BG = [
    f"{_SLOTS}/Ejemplo_Slot1_3.png",  # Burnice
    f"{_SLOTS}/Ejemplo_Slot6_3.png",  # Burnice
    f"{_SLOTS}/Ejemplo_Slot1_5.png",  # Caesar
    f"{_SLOTS}/Ejemplo_Slot6_5.png",  # Caesar
]


@pytest.mark.parametrize("rel_path", S17_DARK_BG)
def test_s17_fondo_oscuro_se_reconoce(rel_path):
    """S17 de PJ con fondo oscuro: 'dark' por el filtro crudo pero matchea S17 →
    el clasificador template-aware NO debe tirarla a S12."""
    path = REPO / rel_path
    if not path.exists():
        pytest.skip(f"Archivo no encontrado: {path}")
    img = cv2.imread(str(path))
    if img is None:
        pytest.skip(f"No se pudo leer: {path}")
    # Escenario de la regresión: el frame ESTÁ en la zona dark del filtro crudo...
    assert ScreenDetector._is_dark_frame(img), (
        f"{rel_path}: se esperaba dark-ratio > umbral (fixture del caso de regresión)"
    )
    # ...pero el clasificador completo debe reconocerlo como S17 igualmente.
    state = ScreenDetector().classify(img)
    assert state.code == "S17", (
        f"{rel_path} → {state.code} (conf={state.confidence:.2f}); debe ser S17"
    )
