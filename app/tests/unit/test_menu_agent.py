"""Reconocimiento del PJ seleccionado en el MENÚ DE PERSONAJES (S15, Fase M.1).

Cubre: (1) `identify_menu_agent` — OCR del nombre bottom-left → `_match_agent` → rol+elemento
de la DB, con abstención (RNF-02) si el nombre no se lee; (2) dispatch + log edge-triggered en
el monitor (gate RNF-06: re-OCR solo si cambió la selección). Los tests de frame real se saltean
si las capturas no están presentes.
"""
from __future__ import annotations
import logging
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_agent_stats import identify_menu_agent

REPO = Path(__file__).resolve().parents[3]
_MENU = REPO / "Documentacion" / "Screenshots_Triggers" / "Triggers_Generales" / "Menu_Personajes"


class _StubOcr:
    """Backend OCR de prueba: devuelve un texto fijo para cualquier ROI."""
    def __init__(self, text="Nangong Yu", conf=0.99):
        self._text = text; self._conf = conf
    def text(self, img, psm=6, lang="spa"):
        return self._text, self._conf


def _frame():
    return np.zeros((1439, 2559, 3), np.uint8)


# --- identify_menu_agent (hermético con stub OCR + DB real) -------------------

def test_identify_menu_agent_pasa_texto_a_match(monkeypatch):
    """El texto OCR del nombre se enruta a _match_agent y se devuelve su (nombre,rol,elem)."""
    import app.core.parser_agent_stats as p
    captured = {}

    def _fake_match(t, *a, **k):
        captured["t"] = t
        return ("Nangong Yu", "Aturdimiento", "Éter")

    monkeypatch.setattr(p, "_match_agent", _fake_match)
    n, r, e = identify_menu_agent(_frame(), _StubOcr("Nangong Yu"))
    assert (n, r, e) == ("Nangong Yu", "Aturdimiento", "Éter")
    assert captured["t"] == "Nangong Yu"


def test_identify_menu_agent_ocr_vacio_abstiene():
    """Nombre ilegible (OCR vacío) → (None,None,None), sin inventar PJ (RNF-02)."""
    assert identify_menu_agent(_frame(), _StubOcr("", 0.0)) == (None, None, None)


def test_match_agent_prefiere_el_nombre_mas_especifico():
    """Bug QA 2026-06-21: con OCR del nombre LARGO, `_match_agent` devolvía el PJ
    CORTO que es substring (Billy ⊂ 'Billy Estelar', Anby ⊂ 'N.º 0: Anby') porque el
    subconjunto puntuaba 1.0 plano → empate → ganaba el 1º del roster. Ahora el match
    más específico (más tokens) gana, sin perder el corto cuando va solo. Requiere el
    roster real (ambos PJs); se saltea si no están."""
    from app.core.parser_agent_stats import _match_agent, _get_roster
    if not _get_roster():
        pytest.skip("roster DB no disponible")
    nombres = {ag["nombre"] for ag in _get_roster()}
    if {"Billy", "Billy Estelar"} <= nombres:
        assert _match_agent("Billy Estelar")[0] == "Billy Estelar"
        assert _match_agent("Billy")[0] == "Billy"          # el corto solo → el corto
    n0 = next((n for n in nombres if n.startswith("N.") and "Anby" in n), None)
    if n0 and "Anby" in nombres:
        assert _match_agent("N.º 0: Anby")[0] == n0
        assert _match_agent("Anby")[0] == "Anby"            # el corto solo → Anby base


def test_identify_menu_agent_tolera_subicono_y_sin_espacios(monkeypatch):
    """El match recibe el texto crudo ('Astra Yao &' / 'OrfiayMagas'); la canonicalización
    la hace _match_agent (probado aparte). Acá: el ROI/abstención y el ruteo no rompen."""
    import app.core.parser_agent_stats as p
    monkeypatch.setattr(p, "_match_agent", lambda t, *a, **k: ("Astra Yao", "Soporte", "Éter"))
    assert identify_menu_agent(_frame(), _StubOcr("Astra Yao &"))[0] == "Astra Yao"


# --- Dispatch + log en el monitor --------------------------------------------

def _monitor(stub_ocr, on_agent_detail=None):
    import app.core.monitor as mon
    return mon.Monitor(ocr=stub_ocr, detector=None, on_agent_detail=on_agent_detail)


class _SeqOcr:
    """OCR de prueba que devuelve nombres en secuencia (simula cambiar de selección)."""
    def __init__(self, texts):
        self._texts = list(texts); self._i = 0
    def text(self, img, psm=6, lang="spa"):
        t = self._texts[min(self._i, len(self._texts) - 1)]; self._i += 1
        return t, 0.99


def test_monitor_s15_emite_edge_triggered(monkeypatch):
    """S15 → _process_agent_menu emite 1× por PJ (vía on_agent_detail source='menu'); el
    mismo frame NO re-emite (gate RNF-06); cambiar de selección (firma distinta + otro PJ)
    SÍ re-emite."""
    import app.core.parser_agent_stats as p
    from app.core.detector import ScreenState
    monkeypatch.setattr(p, "_match_agent", lambda t, *a, **k: (t.strip(), "rol", "elem"))
    emitted = []
    # El gate visual deja pasar f_a y f_b (firmas distintas); el OCR devuelve PJs distintos.
    m = _monitor(_SeqOcr(["Nangong Yu", "Jane"]),
                 on_agent_detail=lambda st, name, ident, src: emitted.append((name, src)))
    st = ScreenState("S15", 1.0, "s15_menu_personajes.png")
    f_a = np.zeros((1439, 2559, 3), np.uint8)
    f_b = np.full((1439, 2559, 3), 200, np.uint8)
    m._dispatch_state(f_a, st)
    m._dispatch_state(f_a, st)                       # mismo frame → gate visual, no OCR ni emite
    m._dispatch_state(f_b, st)                       # firma distinta → re-OCR → otro PJ → emite
    assert emitted == [("Nangong Yu", "menu"), ("Jane", "menu")]


def test_monitor_s15_siembra_el_latch_de_identidad(monkeypatch):
    """El PJ del menú queda LATCHEADO (QA 2026-07-30).

    Antes S15 era puramente informativo: reconocía al PJ, lo logueaba y lo tiraba. Al ir
    del menú directo a Equipamiento el latch venía vacío y S8 salía `PJ=?` hasta pasar por
    S18. El nombre del menú está ESCRITO en pantalla y ya viene canonicalizado contra el
    roster, así que es la evidencia más barata y certera que hay: se siembra.
    """
    import app.core.parser_agent_stats as p
    from app.core.detector import ScreenState
    monkeypatch.setattr(p, "_match_agent", lambda t, *a, **k: (t.strip(), "rol", "elem"))
    m = _monitor(_StubOcr("Nangong Yu"))
    m._dispatch_state(np.zeros((1439, 2559, 3), np.uint8), ScreenState("S15", 1.0, "t"))
    assert m._last_agent_name == "Nangong Yu"
    assert m._detail_source == "menu"
    # Siembra ≠ confirmación: sin ancla, el matcher de avatar todavía puede CORREGIRLA
    # cuando aparezca la barra (el usuario pudo deslizar de PJ al entrar).
    assert m._agent_anchor_x is None


def test_monitor_s15_abstencion_no_borra_el_latch(monkeypatch):
    """Un frame de transición del menú (OCR abstiene) NO debe borrar al PJ ya sembrado.

    Regresión del log real: el último `[S15]` antes de salir a Equipamiento decía
    `PJ=incierto` — justo el frame del click. Si la abstención borrara el latch, la siembra
    no serviría de nada exactamente en el caso que la motiva.
    """
    import app.core.parser_agent_stats as p
    from app.core.detector import ScreenState
    monkeypatch.setattr(p, "_match_agent", lambda t, *a, **k: (None, None, None))
    m = _monitor(_StubOcr("basura ilegible"))
    m._last_agent_name = "Remielle Dan"
    m._detail_source = "menu"
    m._dispatch_state(np.zeros((1439, 2559, 3), np.uint8), ScreenState("S15", 1.0, "t"))
    assert m._last_agent_name == "Remielle Dan"


def test_monitor_menu_a_equipamiento_hereda_el_pj(monkeypatch):
    """S15 → S8: Equipamiento reporta al PJ del menú en vez de `PJ=?` (el caso de Daniel)."""
    import app.core.parser_agent_stats as p
    from app.core.detector import ScreenState
    monkeypatch.setattr(p, "_match_agent", lambda t, *a, **k: (t.strip(), "rol", "elem"))
    emitted = []
    m = _monitor(_StubOcr("Remielle Dan"),
                 on_agent_detail=lambda st, name, ident, src: emitted.append((name, ident, src)))
    frame = np.zeros((1439, 2559, 3), np.uint8)
    m._dispatch_state(frame, ScreenState("S15", 1.0, "t"))
    m._dispatch_state(frame, ScreenState("S8", 0.90, "t"))
    assert emitted[-1] == ("Remielle Dan", True, "menu")


def test_monitor_salir_de_s15_resetea_gate(monkeypatch):
    """Al pasar por un estado != S15 se olvida la firma → re-entrar re-identifica."""
    from app.core.detector import ScreenState
    m = _monitor(_StubOcr("Nangong Yu"))
    m._menu_last_sig = np.zeros((32, 32), np.float32)
    m._last_menu_log_sig = ("Nangong Yu", "x", "y")
    m._dispatch_state(np.zeros((1439, 2559, 3), np.uint8), ScreenState("S12", 1.0, "t"))
    assert m._menu_last_sig is None and m._last_menu_log_sig is None


# --- Frame real (skip si no están las capturas) ------------------------------

_REAL = {"Ejemplo_1": "Nangong Yu", "Ejemplo_2": "Astra Yao", "Ejemplo_3": "Jane",
         "Ejemplo_4": "Orfia y Magas", "Ejemplo_5": "César",
         # QA 2026-06-21: nombres LARGOS que contienen a un PJ corto (regresión del
         # matcher de especificidad). Billy Estelar ⊃ Billy; N.º 0: Anby ⊃ Anby.
         "Ejemplo_7": "Billy Estelar", "Ejemplo_8": "N.º 0: Anby"}


@pytest.mark.skipif(not (_MENU / "Ejemplo_1.png").exists(),
                    reason="capturas del menú no presentes")
@pytest.mark.parametrize("name,esperado", list(_REAL.items()))
def test_identify_menu_agent_frames_reales(name, esperado):
    """Sobre las 5 capturas reales del menú: identifica el PJ correcto (OCR real).
    Requiere la DB con el roster; se saltea si no carga."""
    from app.core.parser_agent_stats import _get_roster
    if not _get_roster():
        pytest.skip("roster DB no disponible")
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    p = _MENU / f"{name}.png"
    frame = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
    nombre, rol, elemento = identify_menu_agent(frame, PaddleBackend())
    assert nombre == esperado, f"{name}: esperaba {esperado}, salió {nombre}"
    assert rol and elemento     # rol+elemento de la DB
