"""S26 — detalle de W-Engine equipado.

La pantalla del arma y la del disco son **el mismo template**: `s17_personalizacion_pistas.png`
matchea las dos a 1.000. No hay forma de separarlas por píxeles baratos — se midió:

  · la fila de 5 estrellas (que solo tiene el arma) NO sirve: un arma P1 tiene 1 estrella
    blanca y 4 grises, así que el llenado de esa banda **es la señal de refinamiento**, no una
    constante. Separación medida 0.58×, solapada.
  · `_detect_s17_slot_by_hexagon` da `None` para los 30 frames de disco de `14_Slots_equipamiento`
    también, no solo para las armas.
  · `read_s17_action_button` devuelve 'reemplazar'/'desequipar' en las dos.

Lo que sí separa sale del texto del panel, que la ruta S17 ya OCRea igual:
"Atributos **avanzados**" / "Efecto de **amplificador**" contra "Atributos **secundarios**" /
"Efecto de **conjunto**". Medido sobre la banda del verify: 40/40 armas, 0/42 discos.

S26 comparte el template con S17 y va ANTES en `_STATE_TEMPLATES`. El sort de candidatos es
estable, así que ante el empate a 1.000 el primer turno de verificación le toca a S26; si su
verify falla (frame de disco), el pipeline cae al siguiente candidato y sale S17 como siempre.
Es el mismo mecanismo de S23/S25, con los roles invertidos porque acá el estricto es el nuevo.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core import detector as det_mod
from app.core.detector import (
    NON_CAPTURE_STATES,
    STATE_DESCRIPTIONS,
    THRESHOLD_BY_STATE,
    ScreenDetector,
    polling_cadence_ms,
)

_ROOT = Path(__file__).resolve().parents[3] / "Documentacion" / "Screenshots_Triggers"
_ARMAS = sorted((_ROOT / "Engines_Triggers" / "Engine_vista_detallada_pj").glob("Ejemplo_*.png"))
_DISCOS_14 = sorted((_ROOT / "Discos_Triggers" / "14_Slots_equipamiento").glob("Ejemplo_*.png"))
_DISCOS_04 = sorted(
    (_ROOT / "Discos_Triggers" / "04_Inventario_Disco_Vista_Individual").glob("Ejemplo_*.png")
)[:12]
_REEMPLAZO = sorted((_ROOT / "Engines_Triggers" / "Reemplazo_engine").glob("Ejemplo_*.png"))
_INVENTARIO = sorted(
    (_ROOT / "Engines_Triggers" / "Inventario_general_engines").glob("Ejemplo_*.png")
)
_FP_DIR = _ROOT / "Triggers_Generales" / "Falsos_positivos"


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


# --- Positivos ------------------------------------------------------------------------------


@pytest.mark.skipif(not _ARMAS, reason="capturas de W-Engine no presentes")
@pytest.mark.parametrize("fx", _ARMAS, ids=lambda p: p.stem)
def test_detalle_de_arma_es_s26(fx):
    """Los 40 frames de detalle de arma → S26, no S17."""
    st = ScreenDetector(use_state_machine=False).classify(_load(fx))
    assert st.code == "S26", f"{fx.name} → {st.code} (conf={st.confidence}, verif={st.verification})"


# --- Que no se rompa lo que ya andaba -------------------------------------------------------


@pytest.mark.skipif(not _DISCOS_14, reason="capturas de disco no presentes")
@pytest.mark.parametrize("fx", _DISCOS_14 + _DISCOS_04, ids=lambda p: f"{p.parent.name[:2]}_{p.stem}")
def test_s26_no_cambia_nada_para_los_frames_de_disco(fx, monkeypatch):
    """La regresión que importa, afirmada como INVARIANZA en vez de como un código esperado.

    Se clasifica cada frame dos veces: una con S26 activo y otra con su verify forzado a False,
    que reproduce exactamente el pipeline anterior a este hito. Los dos resultados deben
    coincidir.

    Es más fuerte que hardcodear "S17" y no miente: en `04_Inventario_Disco_Vista_Individual`
    hay fixtures que legítimamente clasifican S7 (la vista de tienda de música tiene su propio
    template). Esperar S17 en todos habría fallado por un motivo ajeno a S26 — y ese falso
    positivo aparecería como si el hito hubiera roto algo.
    """
    frame = _load(fx)
    con_s26 = ScreenDetector(use_state_machine=False).classify(frame)
    det_mod._s26_sig_cache = None
    monkeypatch.setattr(det_mod, "_verify_s26", lambda f: (False, "desactivado"))
    monkeypatch.setitem(det_mod._VERIFICATION_REGISTRY, "S26", det_mod._verify_s26)
    sin_s26 = ScreenDetector(use_state_machine=False).classify(frame)
    det_mod._s26_sig_cache = None
    assert con_s26.code == sin_s26.code, (
        f"{fx.name}: con S26 → {con_s26.code} (verif={con_s26.verification}), "
        f"sin S26 → {sin_s26.code}"
    )


@pytest.mark.skipif(not _DISCOS_14, reason="capturas de disco no presentes")
def test_los_frames_de_disco_del_equipamiento_siguen_en_s17():
    """Y el caso concreto: los 30 de `14_Slots_equipamiento` son todos detalle de disco
    equipado, así que ahí sí corresponde exigir S17 nominalmente."""
    d = ScreenDetector(use_state_machine=False)
    malos = [(p.name, d.classify(_load(p)).code) for p in _DISCOS_14]
    assert all(c == "S17" for _, c in malos), [x for x in malos if x[1] != "S17"]


@pytest.mark.skipif(not _REEMPLAZO, reason="capturas del reemplazo no presentes")
@pytest.mark.parametrize("fx", _REEMPLAZO, ids=lambda p: p.stem)
def test_el_dialogo_de_reemplazo_sigue_en_s23(fx):
    """H1 no toca los otros dos cruces: el diálogo sigue clasificando S23 (lo que impide la
    contaminación es el contrato de `test_armas_no_contaminan_discos`, no el estado)."""
    assert ScreenDetector(use_state_machine=False).classify(_load(fx)).code == "S23"


@pytest.mark.skipif(not _INVENTARIO, reason="capturas del inventario no presentes")
@pytest.mark.parametrize("fx", _INVENTARIO, ids=lambda p: p.stem)
def test_el_inventario_de_armas_sigue_en_s9(fx):
    """Ídem: el inventario de armas es tramo posterior."""
    assert ScreenDetector(use_state_machine=False).classify(_load(fx)).code == "S9"


@pytest.mark.skipif(not _FP_DIR.exists(), reason="corpus de negativos no presente")
def test_los_negativos_no_disparan_s26():
    """Ninguna pantalla del corpus de falsos positivos debe clasificar como S26."""
    d = ScreenDetector(use_state_machine=False)
    for f in sorted(_FP_DIR.glob("*.png")):
        img = _load(f)
        if img is None:
            continue
        assert d.classify(img).code != "S26", f"{f.name} disparó S26 (FP)"


# --- El fallo cerrado -----------------------------------------------------------------------


@pytest.mark.skipif(not _ARMAS, reason="capturas de W-Engine no presentes")
def test_sin_ocr_s26_no_dispara_y_todo_queda_como_antes(monkeypatch):
    """Sin OCR, `_verify_s26` devuelve False y el arma vuelve a caer en S17 — exactamente el
    comportamiento previo a este hito.

    Es la propiedad que hace seguro el cambio: degradar no puede empeorar nada, porque el
    estado viejo ya se abstenía de producir datos de disco (ver
    `test_armas_no_contaminan_discos`).
    """
    monkeypatch.setattr(det_mod, "_get_panel_verify_ocr", lambda: None)
    monkeypatch.setattr(det_mod, "_s26_sig_cache", None)   # el cache guarda veredictos, no OCR
    st = ScreenDetector(use_state_machine=False).classify(_load(_ARMAS[0]))
    assert st.code == "S17"


@pytest.mark.skipif(not _ARMAS, reason="capturas de W-Engine no presentes")
def test_verify_reporta_el_texto_que_lo_decidio():
    """La verificación debe dejar rastro de POR QUÉ ganó, para poder diagnosticar en el log."""
    st = ScreenDetector(use_state_machine=False).classify(_load(_ARMAS[0]))
    assert st.verification and "txt=" in st.verification


# --- El pre-gate de una sola dirección --------------------------------------------------------


@pytest.mark.skipif(not _ARMAS or not _DISCOS_14, reason="capturas no presentes")
def test_el_pregate_de_estrellas_nunca_descarta_un_arma():
    """El gate solo puede decir "esto NO es un arma", nunca "esto SÍ lo es".

    Existe para que la mayoría de los frames de disco no paguen el OCR del verify (~334 ms por
    cambio de panel, sobre un flujo que hoy ya funciona). Lo que NO puede hacer es descartar un
    arma: ahí el margen es lo único que separa el hito de un falso negativo silencioso.
    """
    fracs_arma = [det_mod._s26_star_row_frac(_load(p)) for p in _ARMAS]
    assert min(fracs_arma) > det_mod._S26_STARS_MIN, (
        f"un arma cayó bajo el gate: min={min(fracs_arma):.4f} vs umbral "
        f"{det_mod._S26_STARS_MIN}"
    )
    margen = min(fracs_arma) / det_mod._S26_STARS_MIN
    assert margen >= 2.0, f"margen insuficiente ({margen:.2f}×) — recalibrar el ROI"


@pytest.mark.skipif(not _DISCOS_14, reason="capturas de disco no presentes")
def test_el_pregate_ahorra_el_ocr_en_la_mayoria_de_los_discos():
    """Si esto cae, el gate dejó de servir para lo único que hace y el flujo de discos volvió a
    pagar el OCR completo — vale enterarse, aunque no sea un bug de corrección."""
    ahorrados = sum(1 for p in _DISCOS_14 + _DISCOS_04
                    if det_mod._s26_star_row_frac(_load(p)) < det_mod._S26_STARS_MIN)
    total = len(_DISCOS_14 + _DISCOS_04)
    assert ahorrados / total >= 0.70, f"solo {ahorrados}/{total} discos evitan el OCR"


# --- Registro -------------------------------------------------------------------------------


def test_s26_registrado_en_el_detector():
    """Los 7 puntos de registro. Un estado a medio registrar se comporta de forma errática:
    clasifica pero no tiene cadencia, o tiene cadencia pero el monitor lo trata como capturable.
    """
    assert THRESHOLD_BY_STATE["S26"] == THRESHOLD_BY_STATE["S17"], "mismo template, mismo umbral"
    assert "S26" in STATE_DESCRIPTIONS
    assert "S26" in NON_CAPTURE_STATES, "observación pura: S26 no captura discos"
    assert "S26" in det_mod._VALID_TRANSITIONS
    assert "S26" in det_mod._VERIFICATION_REGISTRY
    from app.core.detector import ScreenState
    assert (polling_cadence_ms(ScreenState("S26", 1.0, ""))
            == polling_cadence_ms(ScreenState("S17", 1.0, "")))


def test_s26_va_antes_que_s17_en_la_lista():
    """El orden ES el mecanismo: `passing.sort` es estable, así que ante el empate a 1.000 el
    primer turno de verificación le toca al que aparece antes. Si S17 quedara primero, su verify
    genérico (Hough de líneas) pasaría sobre un frame de arma y S26 nunca se probaría.
    """
    codigos = [e["code"] for e in det_mod._STATE_TEMPLATES
               if e["template"] == "s17_personalizacion_pistas.png"]
    assert codigos.index("S26") < codigos.index("S17"), f"orden actual: {codigos}"
