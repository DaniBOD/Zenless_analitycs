"""
Test de integración — cierre del gap test↔runtime para S18 (Hito 2.8).

Los tests unitarios de `parse_agent_stats` y `_deep_detect_s18` cubren las
piezas en aislamiento, pero el bug original era que el callback
`on_agent_stats` jamás se disparaba en el .exe a pesar de que las piezas
funcionaban en aislamiento. Este test simula el camino completo:

    frame → ScreenDetector.classify() → _deep_detect_s18 (fallback) →
    TemporalBuffer.promote_now() / .add() → _dispatch_state() →
    _process_agent_stats_continuous() → parse_agent_stats() → on_agent_stats CB

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
# Test 3: Monitor._process_agent_stats_continuous dispara callback on_agent_stats
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


def test_monitor_dispatch_continuo_re_extrae_mismo_estado(monkeypatch):
    """
    Extracción CONTINUA (cambio 2026-05-31, punto 2): dos
    `_dispatch_state(frame, S18)` consecutivos disparan el callback DOS veces.

    Antes había un dedup one-shot (1 sola emisión por entrada a S18); ahora,
    mientras el usuario está en el perfil, cada ciclo de cadencia re-extrae y
    re-emite. La cadencia real (no re-procesar más rápido que ~1500ms) la
    controla el loop `_run`, no `_dispatch_state` — por eso a nivel de
    dispatch directo cada llamada procesa.
    """
    if not S18_FIXTURES:
        pytest.skip("Sin fixtures S18")
    frame = _read_frame(S18_FIXTURES[0])
    if frame is None:
        pytest.skip("No se pudo cargar fixture")

    from app.core.detector import ScreenState
    from app.core.monitor import Monitor
    from app.core import monitor as monitor_mod

    monkeypatch.setattr(
        monitor_mod, "parse_agent_stats",
        lambda f, o: AgentStatsParsed(nivel=60, pv=10797, ataque=2531, defensa=925),
    )

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

    assert len(received) == 2, (
        f"Extracción continua rota: esperaba 2 invocaciones para 2 dispatch "
        f"del mismo estado S18, recibió {len(received)}."
    )


def test_monitor_dispatch_retry_si_stats_son_none(monkeypatch):
    """
    Si la primera extracción dio todos None (frame en transición), el dedup
    NO se compromete y el siguiente dispatch SÍ vuelve a procesar.
    """
    if not S18_FIXTURES:
        pytest.skip("Sin fixtures S18")
    frame = _read_frame(S18_FIXTURES[0])
    if frame is None:
        pytest.skip("No se pudo cargar fixture")

    from app.core.detector import ScreenState
    from app.core.monitor import Monitor
    from app.core import monitor as monitor_mod

    monkeypatch.setattr(
        monitor_mod, "parse_agent_stats",
        lambda f, o: AgentStatsParsed(),  # todos None
    )

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr(banner_text="", stats_text=""),
        detector=ScreenDetector(),
        on_agent_stats=lambda stats, st: received.append((stats, st)),
    )
    s18 = ScreenState("S18", 0.75, "deep_detect", method="deep_detect")
    monitor._dispatch_state(frame, s18)
    monitor._dispatch_state(frame, s18)

    assert len(received) == 2, (
        f"Retry roto: esperaba 2 invocaciones (stats None permite retry), "
        f"recibió {len(received)}"
    )


# ---------------------------------------------------------------------------
# Test 4: S8/S19 — logging persistente + identidad heredada (carry-forward)
# ---------------------------------------------------------------------------

def _frame_with_avatar_highlight(center_norm_x: float) -> np.ndarray:
    """Frame negro con un highlight amarillo en el avatar-row, centrado en x."""
    from app.core.detector import _AVATAR_ROW_ROI
    h, w = 1440, 2560
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    _, y, _, rh = _AVATAR_ROW_ROI
    cy = int((y + rh / 2) * h)
    cx = int(center_norm_x * w)
    cv2.rectangle(frame, (cx - 60, cy - 36), (cx + 60, cy + 36), (0, 255, 255), -1)
    return frame


def _empty_identifier():
    from app.core.agent_identifier import AgentIdentifier
    return AgentIdentifier(autoload=False)


@pytest.mark.parametrize("code", ["S8", "S19"])
def test_agent_detail_hereda_identidad_si_mismo_avatar(code):
    """En S8/S19, si el avatar resaltado sigue en la posición anclada en S18,
    se hereda el nombre del PJ (identified=True, source='heredado')."""
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident, src: received.append((st.code, name, ident, src)),
        agent_identifier=_empty_identifier(),
    )
    monitor._last_agent_name = "Nangong Yu"
    monitor._agent_anchor_x = 0.60

    frame = _frame_with_avatar_highlight(0.60)  # mismo PJ
    monitor._dispatch_state(frame, ScreenState(code, 0.90, f"tab:{code}", method="tab"))

    assert received == [(code, "Nangong Yu", True, "heredado")]


@pytest.mark.parametrize("code", ["S8", "S19"])
def test_agent_detail_sostiene_latch_si_cambio_avatar_y_matcher_falla(code):
    """Latch por contexto (2026-06-06): si el avatar cambió de posición y el
    matcher NO lo reconoce (librería vacía / crop de esquina degradado), NO se
    cae a 'sin identificar' — se SOSTIENE el último PJ con source='sostenido'.
    Esto cierra el bug del PJ de esquina y la contaminación de otros PJs."""
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident, src: received.append((st.code, name, ident, src)),
        agent_identifier=_empty_identifier(),
    )
    monitor._last_agent_name = "Nangong Yu"
    monitor._agent_anchor_x = 0.60
    monitor._detail_source = "heredado"

    frame = _frame_with_avatar_highlight(0.80)  # otra posición, matcher falla
    monitor._dispatch_state(frame, ScreenState(code, 0.90, f"tab:{code}", method="tab"))

    # Sostiene el último PJ reconocido en vez de borrarlo.
    assert received == [(code, "Nangong Yu", True, "sostenido")]


def test_agent_detail_sin_latch_y_matcher_falla_no_identifica():
    """Si NO hay latch previo y el matcher falla, sí cae a 'sin identificar'
    (no hay nada que sostener)."""
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident, src: received.append((st.code, name, ident, src)),
        agent_identifier=_empty_identifier(),
    )
    # Sin _last_agent_name (None por defecto), avatar en posición nueva.
    frame = _frame_with_avatar_highlight(0.80)
    monitor._dispatch_state(frame, ScreenState("S8", 0.90, "tab:S8", method="tab"))

    assert received == [("S8", None, False, None)]


def test_agent_detail_sin_anchor_previo_no_identifica():
    """Sin anchor y con librería vacía, S8 no puede identificar."""
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident, src: received.append((st.code, name, ident, src)),
        agent_identifier=_empty_identifier(),
    )
    frame = _frame_with_avatar_highlight(0.60)
    monitor._dispatch_state(frame, ScreenState("S8", 0.90, "tab:S8", method="tab"))

    assert received == [("S8", None, False, None)]


def test_agent_detail_continuo_re_emite_cada_dispatch():
    """S8/S19 son continuos: 2 dispatch → 2 emisiones (logging persistente)."""
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident, src: received.append(st.code),
        agent_identifier=_empty_identifier(),
    )
    monitor._last_agent_name = "Nangong Yu"
    monitor._agent_anchor_x = 0.60
    frame = _frame_with_avatar_highlight(0.60)
    s8 = ScreenState("S8", 0.90, "tab:S8", method="tab")
    monitor._dispatch_state(frame, s8)
    monitor._dispatch_state(frame, s8)
    assert received == ["S8", "S8"]


@pytest.mark.parametrize("code", ["S8", "S19"])
def test_agent_detail_sostiene_identidad_si_avatar_oculto(code):
    """
    Hysteresis (madurez): si el avatar-row se auto-oculta (selected_avatar_x =
    None) NO se cae a 'sin identificar' — se SOSTIENE la última identidad.
    """
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident, src: received.append((name, ident, src)),
        agent_identifier=_empty_identifier(),
    )
    monitor._last_agent_name = "Dialyn"
    monitor._agent_anchor_x = 0.60
    monitor._detail_source = "heredado"

    hidden = np.zeros((1440, 2560, 3), dtype=np.uint8)  # sin highlight → avatar oculto
    monitor._dispatch_state(hidden, ScreenState(code, 0.90, f"tab:{code}", method="tab"))

    assert received == [("Dialyn", True, "heredado")]


def test_agent_detail_latch_se_resetea_al_salir_a_pantalla_confirmada():
    """Al pasar a una pantalla no-detalle CONFIRMADA (roster/menú, conf alta), el
    latch se limpia; luego en un S8 con avatar oculto NO debe resucitar la
    identidad vieja."""
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident, src: received.append((name, ident, src)),
        agent_identifier=_empty_identifier(),
    )
    monitor._last_agent_name = "Dialyn"
    monitor._agent_anchor_x = 0.60
    monitor._detail_source = "heredado"

    # Salir a un menú CONFIRMADO (conf alta) → debe limpiar el latch
    monitor._dispatch_state(np.zeros((1440, 2560, 3), np.uint8),
                            ScreenState("S12", 0.90, "menu", method="template"))
    assert monitor._last_agent_name is None

    # Volver a S8 con avatar oculto → sin identidad heredada
    monitor._dispatch_state(np.zeros((1440, 2560, 3), np.uint8),
                            ScreenState("S8", 0.90, "tab:S8", method="tab"))
    assert received == [(None, False, None)]


def test_agent_detail_latch_sobrevive_fundido_de_transicion():
    """Zhu Yuan (2026-06-06): un fundido oscuro entre pestañas (S12 conf~0) NO
    debe resetear el latch — la identidad sobrevive el transitorio."""
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor

    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda *a: None,
        agent_identifier=_empty_identifier(),
    )
    monitor._last_agent_name = "Zhu Yuan"
    monitor._agent_anchor_x = 0.60
    monitor._detail_source = "heredado"

    # Fundido de transición: S12 con conf 0.0 (dark_frame_filter). NO resetea.
    monitor._dispatch_state(np.zeros((1440, 2560, 3), np.uint8),
                            ScreenState("S12", 0.0, "dark_frame_filter", method="template"))
    assert monitor._last_agent_name == "Zhu Yuan"
    assert monitor._detail_source == "heredado"


def test_agent_detail_nombra_pj_via_matcher_de_avatar(tmp_path):
    """
    Switch directo: el anchor NO coincide (otro PJ), pero el matcher de avatar
    reconoce a Nangong Yu (aprendida antes desde S18) en su S8 real → la nombra
    con source='avatar'.
    """
    from app.core.detector import ScreenState
    from app.core.monitor import Monitor
    from app.core.agent_identifier import AgentIdentifier

    repo = Path(__file__).resolve().parents[3]
    s18 = repo / "Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/atributos_base_ejemplo_1.png"
    s8 = repo / "Documentacion/Screenshots_Triggers/Discos_Triggers/03_Pantalla_Agente_Discos_Equipados/Ejemplo_1.png"
    f18, f8 = _read_frame(s18), _read_frame(s8)
    if f18 is None or f8 is None:
        pytest.skip("capturas no disponibles")

    ident = AgentIdentifier(library_path=tmp_path / "lib.npz", autoload=False)
    ident.learn(f18, "Nangong Yu")  # bootstrap desde S18

    received: list = []
    monitor = Monitor(
        ocr=_StubOcr("", ""),
        detector=ScreenDetector(),
        on_agent_detail=lambda st, name, ident_, src: received.append((name, ident_, src)),
        agent_identifier=ident,
    )
    # Simular que veníamos de OTRO PJ (anchor en otra posición que no coincide).
    monitor._last_agent_name = "Otro PJ"
    monitor._agent_anchor_x = 0.10

    monitor._dispatch_state(f8, ScreenState("S8", 0.90, "tab:S8", method="tab"))

    assert len(received) == 1
    name, identified, source = received[0]
    assert name == "Nangong Yu"
    assert identified is True
    assert source == "avatar"
