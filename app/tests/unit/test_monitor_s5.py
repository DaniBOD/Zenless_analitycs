"""Handler CONTINUO del resultado de afinación (S5) en el monitor (`_process_disc_s5_continuous`).

S5 replica el patrón aggregator/maturity de S3 sobre la ficha izquierda del resultado de
afinación (el usuario clickea cada disco de la grilla → se re-extrae). Emite vía on_disc al
madurar; dedup por identidad + feedback 'ya capturado'. Tests de frame real (PaddleOCR)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
_S5 = REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers" / "11_Tienda_Musica_Afinacion"


def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


def _monitor(on_disc):
    import app.core.monitor as mon
    return mon.Monitor(ocr=_paddle(), detector=None, on_disc=on_disc)


def _load(name):
    return cv2.imdecode(np.fromfile(str(_S5 / name), np.uint8), cv2.IMREAD_COLOR)


class _NullOcr:
    def text(self, img, psm: int = 6, lang: str = "spa"):
        return "", 0.0

    def text_with_bboxes(self, img):
        return []


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion.png").exists(), reason="capturas S5 no presentes")
def test_s5_emite_disco_afinacion():
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append((d, st)))
    m._dispatch_state(_load("Tienda_musica_afinacion.png"), ScreenState("S5", 1.0, "s5_afinacion"))
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"
    d, st = emitted[0]
    assert st.code == "S5"
    assert d.slot == 3
    assert d.main_stat_canon == "DEF"


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion_3.png").exists(), reason="fixture 10 discos no presente")
def test_s5_preview_grilla_al_entrar():
    """Al entrar a S5, el monitor emite 1× un preview `[disco] slot N · <set>` por cada disco de
    la grilla (antes de ver detalles), como el resumen por-disco de S2. Fixture de 10 discos.
    El preview se DEBOUNCE-a (2 lecturas iguales) → despachamos 2× la grilla estable."""
    import sqlite3
    from app.core.detector import ScreenState
    from app.db.repositories import DiscSetRepo
    import app.core.monitor as mon
    diags = []
    con = sqlite3.connect(str(REPO / "db" / "danibod_zzz_v2.db")); con.row_factory = sqlite3.Row
    m = mon.Monitor(ocr=_paddle(), detector=None, on_diagnostic=diags.append, set_repo=DiscSetRepo(con))
    st = ScreenState("S5", 1.0, "s5_afinacion")
    m._dispatch_state(_load("Tienda_musica_afinacion_3.png"), st)
    m._dispatch_state(_load("Tienda_musica_afinacion_3.png"), st)
    preview = [d for d in diags if d.startswith("[disco]")]
    assert len(preview) == 10, f"esperaba 10 líneas de preview, hubo {len(preview)}: {preview}"
    assert all("Firmamento llameante" in d for d in preview), preview
    assert any("slot 6" in d for d in preview) and any("slot 2" in d for d in preview), preview


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion_4.png").exists(), reason="fixtures re-afinación no presentes")
def test_s5_reafinacion_reemite_preview_desde_misma_pantalla():
    """Re-afinar desde la MISMA pantalla de resultados (botón 'Afinar ×N', sin salir de S5) genera
    una tanda nueva (slots distintos) → el preview se re-emite. La secuencia de slots de la grilla
    (no la firma de imagen, que el highlight de selección arruina) detecta la nueva tanda."""
    import sqlite3
    from app.core.detector import ScreenState
    from app.db.repositories import DiscSetRepo
    import app.core.monitor as mon
    diags = []
    con = sqlite3.connect(str(REPO / "db" / "danibod_zzz_v2.db")); con.row_factory = sqlite3.Row
    m = mon.Monitor(ocr=_paddle(), detector=None, on_diagnostic=diags.append, set_repo=DiscSetRepo(con))
    st = ScreenState("S5", 1.0, "s5_afinacion")
    # Tanda A (slots 2,2,2,2,3,4,4,5,5,6) y luego re-afinar → Tanda B (1,1,1,1,4,4,5,6,6,6),
    # ambas dispatchadas como S5 consecutivas (prev=S5 en la 2ª → NO hay reset por entrada).
    # Cada tanda se despacha 2× (debounce de grilla: 2 lecturas iguales confirman antes de emitir).
    m._dispatch_state(_load("Tienda_musica_afinacion_3.png"), st)
    m._dispatch_state(_load("Tienda_musica_afinacion_3.png"), st)
    n_after_A = len([d for d in diags if d.startswith("[disco]")])
    m._dispatch_state(_load("Tienda_musica_afinacion_4.png"), st)
    m._dispatch_state(_load("Tienda_musica_afinacion_4.png"), st)
    preview = [d for d in diags if d.startswith("[disco]")]
    assert n_after_A == 10, f"tanda A: esperaba 10 preview, hubo {n_after_A}"
    assert len(preview) == 20, f"tras re-afinar: esperaba 20 (10+10), hubo {len(preview)}: {preview[-12:]}"
    assert any("slot 1" in d for d in preview), "la tanda B (slots 1) no se previsualizó"


def test_s5_preview_debounce_espera_animacion(monkeypatch):
    """REGRESIÓN (QA 2026-07-10, set Salón huracanado): la grilla se revela con ANIMACIÓN (los
    tiles entran escalonados) y el OCR de grilla tarda ~2.7s → un frame temprano lee las filas
    inferiores en blanco → badge '?' (slot 0). El bug: el preview se emitía de esa 1ª lectura
    animada y NO se re-evaluaba al asentarse → '?' pegado. El fix debounce-a: espera 2 lecturas
    iguales antes de emitir. Simulamos 3 lecturas animadas distintas + 1 estable repetida."""
    import app.core.monitor as mon
    import app.core.parser_disc_s3 as P
    diags = []
    m = mon.Monitor(ocr=_NullOcr(), detector=None, on_diagnostic=diags.append)
    # Secuencia de lecturas de grilla que devolvería el OCR mientras la animación corre y se asienta.
    reads = [
        [(1, "Salón"), (1, "Salón"), (1, "Salón"), (2, "Salón"), (3, "Salón"),
         (0, "Salón"), (0, "Salón"), (0, "Salón"), (0, "Salón"), (6, "Salón")],   # fila 2 en blanco
        [(1, "Salón"), (1, "Salón"), (1, "Salón"), (2, "Salón"), (3, "Salón"),
         (5, "Salón"), (0, "Salón"), (0, "Salón"), (6, "Salón"), (6, "Salón")],   # entrando
        [(1, "Salón"), (1, "Salón"), (1, "Salón"), (2, "Salón"), (3, "Salón"),
         (5, "Salón"), (5, "Salón"), (5, "Salón"), (6, "Salón"), (6, "Salón")],   # asentada
        [(1, "Salón"), (1, "Salón"), (1, "Salón"), (2, "Salón"), (3, "Salón"),
         (5, "Salón"), (5, "Salón"), (5, "Salón"), (6, "Salón"), (6, "Salón")],   # estable (=3ª)
    ]
    it = iter(reads)
    monkeypatch.setattr(P, "parse_s5_grid", lambda frame, ocr: next(it))
    frame = np.zeros((10, 10, 3), np.uint8)
    for i in range(3):
        m._maybe_new_s5_batch(frame)
        assert not [d for d in diags if d.startswith("[disco]")], (
            f"NO debe emitir mientras la grilla no se estabiliza (lectura {i+1}): {diags}")
    m._maybe_new_s5_batch(frame)   # 4ª lectura == 3ª → estable → emite
    preview = [d for d in diags if d.startswith("[disco]")]
    assert len(preview) == 10, f"esperaba 10 tras estabilizar, hubo {len(preview)}: {preview}"
    assert not any("slot ?" in d for d in preview), f"no debe quedar ningún '?': {preview}"


def test_s5_preview_no_reemite_por_clic_jitter(monkeypatch):
    """REGRESIÓN (QA 2026-07-10): clickear un disco para ver su detalle resalta su tile y mete
    jitter de 1-2 badges al re-leer la grilla → NO es una tanda nueva y NO debe re-emitir las 10
    líneas. Sólo re-afinar (≥`_S5_BATCH_MIN_DIFF` slots distintos por multiset) re-emite. Antes,
    cada clic spameaba el preview completo."""
    import app.core.monitor as mon
    import app.core.parser_disc_s3 as P
    diags = []
    m = mon.Monitor(ocr=_NullOcr(), detector=None, on_diagnostic=diags.append)
    A = [(s, "Salón") for s in (1, 1, 1, 2, 3, 5, 5, 5, 6, 6)]
    A_jit = [(s, "Salón") for s in (1, 1, 1, 2, 3, 3, 5, 5, 6, 6)]   # 1 badge 5→3 (tile seleccionado)
    B = [(s, "Salón") for s in (1, 1, 1, 1, 4, 4, 5, 6, 6, 6)]       # re-afinación real (multiset ≠)
    seq = iter([A, A, A_jit, A_jit, B, B])
    monkeypatch.setattr(P, "parse_s5_grid", lambda f, o: next(seq))
    fr = np.zeros((10, 10, 3), np.uint8)

    def _click_reset():   # un cambio de foco (clic/re-afinación) re-abre la evaluación de grilla
        m._s5_grid_settled = False; m._s5_grid_pending = None; m._s5_grid_tries = 0

    m._maybe_new_s5_batch(fr); m._maybe_new_s5_batch(fr)          # estabiliza batch A → emite
    n_A = len([d for d in diags if d.startswith("[disco]")])
    _click_reset(); m._maybe_new_s5_batch(fr); m._maybe_new_s5_batch(fr)   # clic (jitter) → NO re-emite
    n_click = len([d for d in diags if d.startswith("[disco]")])
    _click_reset(); m._maybe_new_s5_batch(fr); m._maybe_new_s5_batch(fr)   # re-afinación → re-emite
    n_reaf = len([d for d in diags if d.startswith("[disco]")])
    assert n_A == 10, n_A
    assert n_click == 10, f"el jitter de 1 badge por clic NO debe re-emitir (hubo {n_click - n_A} de más)"
    assert n_reaf == 20, f"la re-afinación real (multiset ≠) SÍ re-emite: {n_reaf}"


def test_s5_preview_usa_nombre_limpio_del_set_evocado_s4(monkeypatch):
    """El label del tile se trunca en la celda angosta → los nombres largos no resuelven desde ahí
    (QA 2026-07-10: 'Baladadela ramayla...'). El preview usa el set EVOCADO en el selector S4, que lo
    leyó completo y limpio. Simulamos labels truncados + `_s4_evoked_set` seteado por S4."""
    import time
    import app.core.monitor as mon
    import app.core.parser_disc_s3 as P
    diags = []
    m = mon.Monitor(ocr=_NullOcr(), detector=None, on_diagnostic=diags.append)
    m._s4_evoked_set = (25, "Balada de la rama y la espada", time.monotonic())   # lo que setea S4
    trunc = [(1, "Baladadela ramayla"), (3, "Balada dela ramayla"), (4, "Baladadela ramayla"), (6, "Balada de la ramayla")]
    monkeypatch.setattr(P, "parse_s5_grid", lambda f, o: trunc)
    fr = np.zeros((10, 10, 3), np.uint8)
    m._maybe_new_s5_batch(fr); m._maybe_new_s5_batch(fr)   # 2 lecturas iguales → estabiliza → emite
    preview = [d for d in diags if d.startswith("[disco]")]
    assert len(preview) == 4, preview
    assert all("Balada de la rama y la espada" in d for d in preview), preview   # nombre canónico limpio
    assert not any("Baladadela" in d for d in preview), preview                  # nada del label roto


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion.png").exists(), reason="capturas S5 no presentes")
def test_s5_dedup_una_emision():
    """El mismo disco (firma estable) emite 1× aunque la cadencia repita el frame."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d))
    fr = _load("Tienda_musica_afinacion.png")
    st = ScreenState("S5", 1.0, "s5_afinacion")
    for _ in range(3):
        m._dispatch_state(fr, st)
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"


@pytest.mark.skipif(not (_S5 / "Tienda_musica_afinacion_2.png").exists(), reason="capturas S5 no presentes")
def test_s5_cambio_de_disco_reemite():
    """Clickear otro disco de la grilla (firma distinta: slot 3 → 4) resetea y vuelve a emitir."""
    from app.core.detector import ScreenState
    emitted = []
    m = _monitor(on_disc=lambda d, st: emitted.append(d))
    st = ScreenState("S5", 1.0, "s5_afinacion")
    m._dispatch_state(_load("Tienda_musica_afinacion.png"), st)
    m._dispatch_state(_load("Tienda_musica_afinacion_2.png"), st)
    assert len(emitted) == 2, f"esperaba 2 emisiones (distinto disco), hubo {len(emitted)}"
    assert {emitted[0].slot, emitted[1].slot} == {3, 4}


def test_s5_no_re_emite_disco_ya_capturado():
    """Re-abrir un disco ya capturado avisa 'ya capturado' y NO re-emite (dedup por identidad)."""
    import app.core.monitor as mon
    from app.core.detector import ScreenState
    import types
    emitted, diags = [], []
    m = mon.Monitor(ocr=_NullOcr(), detector=None,
                    on_disc=lambda d, st: emitted.append(d), on_diagnostic=diags.append)
    st = ScreenState("S5", 1.0, "s5_afinacion")
    sub = types.SimpleNamespace(nombre_canon="DEF%", nombre_raw="DEF%", rolls=0, valor=4.8)
    d = types.SimpleNamespace(
        set_name_canon="Nana a la luz cenicienta", set_name_raw="Nana a la luz cenicienta",
        slot=3, main_stat_canon="DEF", main_stat_raw="DEF", main_valor=46.0, nivel=0,
        confianza_global=0.9, subs=[sub])
    m._emit_s5_disc(d, st)
    m._s5_emitted = False
    m._emit_s5_disc(d, st)
    assert len(emitted) == 1, f"esperaba 1 emisión, hubo {len(emitted)}"
    assert any("ya capturado" in x for x in diags), diags
