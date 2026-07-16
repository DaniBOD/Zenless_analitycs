"""Identidad del PJ en Equipamiento (S8) y Habilidades (S19) por el descriptor de avatar
de la barra superior deslizante — descriptor PRIMARIO (ya no requiere el latch de S18).

`_update_detail_identity` corre el matcher de fila y ACUMULA votos multi-frame en vez de
commitear el primer match: la librería de fila cubre el roster y es fiable, la robustez la
da la votación (un frame malo de esquina/animación no queda clavado).
"""
from __future__ import annotations

import numpy as np
import pytest


class _DummyOcr:
    def text(self, img, psm=6, lang="spa"):
        return ("", 0.0)

    def text_with_bboxes(self, frame):
        return []


class _SeqIdent:
    """Identificador stub: `identify` devuelve la secuencia dada (la última se repite)."""

    def __init__(self, results):
        self._it = iter(results)
        self._last = None

    def identify(self, frame):
        try:
            self._last = next(self._it)
        except StopIteration:
            pass
        return self._last


def _monitor(identify_results):
    from app.core.detector import ScreenDetector
    from app.core.monitor import Monitor
    m = Monitor(ocr=_DummyOcr(), detector=ScreenDetector())
    m._identifier = _SeqIdent(identify_results)
    return m


def _frame():
    return np.zeros((1440, 2560, 3), np.uint8)


def test_fresh_entry_identifica_por_avatar(monkeypatch):
    """Sin latch (nunca se pasó por Atributos base): el descriptor identifica el PJ
    directo de la barra y marca source='avatar'."""
    m = _monitor([("Miyabi", 0.95)])
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: 0.50)
    for _ in range(3):
        m._update_detail_identity(_frame())
    assert m._last_agent_name == "Miyabi"
    assert m._detail_source == "avatar"


def test_voto_ignora_primer_frame_malo(monkeypatch):
    """El 1er frame identifica MAL (crop de esquina/animación); los siguientes dan el PJ
    correcto. La votación multi-frame gana → NO queda clavado en el malo.
    (En el código viejo el 1er match se commiteaba y el early-return lo dejaba fijo.)"""
    m = _monitor([("Equivocado", 0.85), ("Miyabi", 0.95), ("Miyabi", 0.95)])
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: 0.50)  # misma ranura
    for _ in range(3):
        m._update_detail_identity(_frame())
    assert m._last_agent_name == "Miyabi"


def test_barra_oculta_sostiene(monkeypatch):
    """La barra superior se auto-oculta: sin avatar visible NO se pierde el PJ reconocido."""
    m = _monitor([("NoDeberia", 0.99)])
    m._last_agent_name = "Ellen"
    m._detail_source = "avatar"
    m._agent_anchor_x = 0.50
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: None)
    m._update_detail_identity(_frame())
    assert m._last_agent_name == "Ellen"


def test_switch_a_otro_pj_reidentifica(monkeypatch):
    """Deslizar a otro PJ (posición nueva, fuera de tolerancia) → re-vota y cambia."""
    m = _monitor([("Nicole", 0.95)])
    m._last_agent_name = "Ellen"
    m._detail_source = "avatar"
    m._agent_anchor_x = 0.30
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: 0.60)
    for _ in range(3):
        m._update_detail_identity(_frame())
    assert m._last_agent_name == "Nicole"


def test_autohide_posicion_espuria_sostiene_ultimo_reconocido(monkeypatch):
    """QA 2026-07-16 (caso 3): al auto-ocultarse, la barra devuelve una posición ESPURIA
    del highlight desvaneciéndose (no None) y el matcher ya no puede leer el avatar. NO se
    debe perder al PJ: se sostiene como 'sostenido' (→ 'sostenido del último reconocido')."""
    m = _monitor([("Velina", 0.95), ("Velina", 0.95), None, None])
    xs = iter([0.50, 0.50, 0.70, 0.70])   # confirma en 0.50, luego highlight espurio en 0.70
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: next(xs, 0.70))
    m._update_detail_identity(_frame())
    m._update_detail_identity(_frame())
    assert m._last_agent_name == "Velina" and m._detail_source == "avatar"
    m._update_detail_identity(_frame())   # posición espuria + matcher se abstiene
    m._update_detail_identity(_frame())
    assert m._last_agent_name == "Velina"          # NO se pierde
    assert m._detail_source == "sostenido"         # y se etiqueta como sostenido


def test_reconfirmar_ranura_restaura_etiqueta_avatar(monkeypatch):
    """Tras un 'sostenido' (parpadeo), al volver el avatar a la ranura confirmada la
    etiqueta vuelve a la real ('por avatar'), no queda pegada en 'sostenido'."""
    m = _monitor([("Velina", 0.95), ("Velina", 0.95), None])
    xs = iter([0.50, 0.50, 0.70, 0.50])
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: next(xs, 0.50))
    m._update_detail_identity(_frame()); m._update_detail_identity(_frame())
    m._update_detail_identity(_frame())            # espuria → sostenido
    assert m._detail_source == "sostenido"
    m._update_detail_identity(_frame())            # vuelve a la ranura confirmada
    assert m._last_agent_name == "Velina" and m._detail_source == "avatar"


def test_abstencion_sin_latch_queda_sin_identificar(monkeypatch):
    """Barra visible pero el matcher se abstiene siempre (crop ilegible) y sin latch previo
    → queda 'sin identificar' (no inventa un PJ)."""
    m = _monitor([None, None, None])
    monkeypatch.setattr("app.core.monitor.selected_avatar_x", lambda f: 0.50)
    for _ in range(3):
        m._update_detail_identity(_frame())
    assert m._last_agent_name is None
