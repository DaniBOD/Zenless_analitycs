"""UpgradeSyncer — tracking PRE→POST del modal de mejora (S10), display-only.

Niveles de test:
  - `_roll_diff` / `_same_disc` puros (sin OCR).
  - Confirmación por S17 (synthetic): el resumen final usa el disco asentado del inventario
    del PJ, que incluye el último roll que S10 pierde al auto-cerrar en MAX (QA 2026-07-10).
  - Integración con la secuencia REAL (Fábula Yunkui slot 1, OCR real): PRE, diff incremental,
    y resumen 0→15 completo confirmado por la S17 posterior.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_disc import DiscParsed, SubstatParsed
from app.core.sync_upgrade import (
    UpgradeSyncer,
    _Snap,
    _roll_diff,
    _same_disc,
    _target_from_notas,
)

_ROOT = Path(__file__).resolve().parents[3]
_BASE = _ROOT / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
_SHOTS = {
    "nivel0": _BASE / "05_Upgrade_PRE_nivel0" / "Ejemplo_1.png",
    "nivel12": _BASE / "06_Upgrade_PRE_nivel3_6_9_12" / "Ejemplo_1_(nivel12).png",
    "max15": _BASE / "07_Upgrade_POST_animacion_confirmacion" / "Ejemplo_1(detallado).png",
}


def _sub(name, canon, valor, rolls):
    return SubstatParsed(nombre_raw=name, nombre_canon=canon, valor=valor,
                         unidad="%" if canon and canon.endswith("%") else "flat",
                         rolls=rolls, confianza=1.0)


def _disc(nivel, subs, set_name="X", slot=1, notas=None):
    return DiscParsed(set_name_raw=set_name, set_name_canon=None, slot=slot,
                      main_stat_raw="PV", main_stat_canon="HP", main_valor=1.0,
                      main_unidad="flat", nivel=nivel, rareza="S", subs=subs,
                      notas=notas or [])


# --- lógica pura --------------------------------------------------------------

def test_roll_diff_detecta_incremento_y_substat_nuevo():
    pre = _disc(0, [_sub("Ataque", "ATK", 19, 0), _sub("Defensa", "DEF%", 4.8, 0),
                    _sub("Daño Crítico", "Daño Crítico", 4.8, 0)])
    post = _disc(12, [_sub("Ataque", "ATK", 19, 0), _sub("Defensa", "DEF%", 9.6, 1),
                      _sub("Daño Crítico", "Daño Crítico", 4.8, 0),
                      _sub("Perforación", "Perforación", 27, 2)])
    assert _roll_diff(pre, post) == {"DEF%": 1, "Perforación": 2}


def test_roll_diff_vacio_si_nada_cambia():
    d = _disc(6, [_sub("Ataque", "ATK", 19, 0)])
    assert _roll_diff(d, d) == {}


def test_target_from_notas():
    assert _target_from_notas(["s10_pre", "s10_target:15"]) == 15
    assert _target_from_notas(["s10_target:10", "otra"]) == 10
    assert _target_from_notas(["s10_pre"]) is None
    assert _target_from_notas([]) is None


def test_pre_max_preview_arma_target_y_lo_usa_en_fallback():
    """Materiales cargados (target=15) pero el modal auto-cerró antes de que S10 viera el
    level-up (last quedó en el PRE). Si NO llega la S17, el fallback resume con el PROYECTADO
    en vez de 'sin cambios'."""
    diags: list[str] = []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append)
    pre = _disc(0, [_sub("Ataque", "ATK", 19, 0)], set_name="Firmamento llameante", slot=2)
    # last == pre (nunca vio el level-up), pero conocemos target=15 del preview.
    s._pending = (_Snap(0, pre), _Snap(0, pre), 15, 0.0)
    # Un nuevo modal abre (o expira) sin confirmación de inventario → fallback.
    s._flush_pending(confirmado=False)
    res = [d for d in diags if "resumen" in d]
    assert res, diags
    assert "0→15" in res[-1] and "proyectado" in res[-1].lower()
    assert s._pending is None


def test_material_refund_refresca_timer_y_anuncia_una_vez():
    """El popup 'Materiales recuperados' (S20) refresca el ts del pendiente (así no expira por
    la espera del click) y loguea una sola vez aunque se llame por cada ciclo."""
    diags: list[str] = []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append)
    pre = _disc(0, [_sub("Defensa", "DEF%", 4.8, 0)], set_name="Salón huracanado", slot=6)
    s._pending = (_Snap(0, pre), _Snap(0, pre), 15, 0.0)
    s.on_material_refund(now=5.0)
    s.on_material_refund(now=8.0)   # segundo ciclo del mismo popup
    # ts refrescado al último now; anuncio una sola vez.
    assert s._pending[3] == 8.0
    anuncios = [d for d in diags if "vuelto de materiales" in d]
    assert len(anuncios) == 1, diags
    # Con el timer refrescado, una S17 "tardía" (t=100, <120 desde el refresh) confirma.
    final = _disc(15, [_sub("Defensa", "DEF%", 9.6, 1)], set_name="Salón huracanado", slot=6)
    s.on_post_upgrade_disc(final, now=100.0)
    assert any("resumen" in d and "0→15" in d for d in diags), diags


def test_material_refund_sin_pendiente_no_hace_nada():
    diags: list[str] = []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append)
    s.on_material_refund(now=1.0)
    assert not diags
    assert s._pending is None


def test_same_disc_por_set_y_slot():
    a = _disc(0, [], set_name="Salón huracanado", slot=1)
    b = _disc(15, [], set_name="Salon huracanado", slot=1)   # sin tilde (canon vs raw)
    assert _same_disc(a, b)
    assert not _same_disc(a, _disc(15, [], set_name="Salón huracanado", slot=2))
    assert not _same_disc(a, _disc(15, [], set_name="Otro set", slot=1))


# --- confirmación por S17 (synthetic, sin OCR) --------------------------------

def test_confirmacion_s17_completa_el_ultimo_roll():
    """S10 solo llegó a ver nivel 12 (maxeó y auto-cerró); la S17 posterior muestra el disco a
    nivel 15 con Perforación +3 → el resumen debe reflejar el estado FINAL completo."""
    diags: list[str] = []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append)
    pre = _disc(0, [_sub("Ataque", "ATK", 19, 0), _sub("Defensa", "DEF%", 4.8, 0)])
    last = _disc(12, [_sub("Ataque", "ATK", 19, 0), _sub("Defensa", "DEF%", 9.6, 1),
                      _sub("Perforación", "Perforación", 27, 2)])
    s._pending = (_Snap(0, pre), _Snap(12, last), 15, 0.0)
    final = _disc(15, [_sub("Ataque", "ATK", 19, 0), _sub("Defensa", "DEF%", 9.6, 1),
                       _sub("Perforación", "Perforación", 36, 3)])
    s.on_post_upgrade_disc(final, now=0.0)
    res = [d for d in diags if "resumen" in d]
    assert res, diags
    assert "0→15" in res[-1] and "MÁXIMO" in res[-1]
    assert "Perforación: +3" in res[-1] and "DEF%: +1" in res[-1]
    assert s._pending is None


def test_confirmacion_ignora_disco_distinto_y_expira():
    diags: list[str] = []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append)
    pre = _disc(0, [_sub("Defensa", "DEF%", 4.8, 0)])
    last = _disc(3, [_sub("Defensa", "DEF%", 4.8, 0)])
    s._pending = (_Snap(0, pre), _Snap(3, last), None, 0.0)
    # Otro disco (slot distinto) NO confirma, y el pendiente sigue vivo.
    s.on_post_upgrade_disc(_disc(15, [], slot=2), now=1.0)
    assert not any("resumen" in d for d in diags)
    assert s._pending is not None
    # Pasada la ventana (TTL 120 s), cualquier confirmación descarta el pendiente sin emitir.
    s.on_post_upgrade_disc(_disc(15, [], slot=1), now=200.0)
    assert s._pending is None
    assert not any("resumen" in d for d in diags)


def test_confirmacion_s17_tardia_dentro_de_ttl_extendido():
    """El popup 'Materiales recuperados' demora la S17 ~47 s: con TTL 120 s la confirmación
    tardía SÍ entra (con el viejo TTL de 30 s se perdía → no salía el resumen)."""
    diags: list[str] = []
    s = UpgradeSyncer(ocr=None, on_diagnostic=diags.append)
    pre = _disc(0, [_sub("Defensa", "DEF%", 4.8, 0)], set_name="Salón huracanado", slot=6)
    last = _disc(0, [_sub("Defensa", "DEF%", 4.8, 0)], set_name="Salón huracanado", slot=6)
    s._pending = (_Snap(0, pre), _Snap(0, last), 15, 0.0)
    final = _disc(15, [_sub("Defensa", "DEF%", 9.6, 1)], set_name="Salón huracanado", slot=6)
    s.on_post_upgrade_disc(final, now=47.0)     # dentro de 120 s
    res = [d for d in diags if "resumen" in d]
    assert res and "0→15" in res[-1] and "DEF%: +1" in res[-1]
    assert s._pending is None


# --- integración con OCR real -------------------------------------------------

def _ocr_or_skip():
    try:
        from app.core.ocr_paddle import PaddleBackend
        return PaddleBackend()
    except Exception:
        pytest.skip("PaddleOCR no disponible")


def _load(name):
    p = _SHOTS[name]
    if not p.exists():
        pytest.skip(f"screenshot S10 no presente: {p.name}")
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def test_upgrade_tracking_secuencia_real_con_confirmacion_s17():
    from app.core.parser_disc_s10 import parse_disc_s10
    ocr = _ocr_or_skip()
    diags: list[str] = []
    syncer = UpgradeSyncer(ocr=ocr, on_diagnostic=diags.append, set_repo=None)

    f0, f12, f15 = _load("nivel0"), _load("nivel12"), _load("max15")
    syncer.on_s10_enter(f0)          # PRE nivel 0
    syncer.on_s10_update(f12)        # 0→12 (parse-on-change)
    syncer.on_s10_exit()             # maxeó+auto-cerró → pending (S10 vio hasta 12), sin resumen aún
    assert not any("resumen" in d for d in diags), diags

    # PRE + salto 0→12 emitidos en vivo.
    assert any("Yunkui" in d and "nivel 0" in d for d in diags), diags
    j1 = [d for d in diags if "nivel 0" in d and "12" in d and "→" in d]
    assert j1 and "DEF%" in j1[-1] and "Perforación" in j1[-1]

    # La S17 posterior (disco final asentado, nivel 15, Perforación +3) confirma el resumen.
    disc_final = parse_disc_s10(f15, ocr)
    syncer.on_post_upgrade_disc(disc_final)
    res = [d for d in diags if "resumen" in d]
    assert res, diags
    assert "0→15" in res[-1] and "MÁXIMO" in res[-1]
    assert "Perforación: +3" in res[-1]   # el último roll, que S10 perdía


def test_pre_max_preview_real_emite_proyectado_al_entrar():
    """Al ENTRAR a S10 con materiales ya cargados (pill_der=15), el log muestra el
    'antes→proyectado' de una — es el 'antes y después' que pide el flujo de leveleo."""
    ocr = _ocr_or_skip()
    p = _BASE / "07_Upgrade_POST_animacion_confirmacion" / "Ejemplo_1(pre-15-max).png"
    if not p.exists():
        pytest.skip("screenshot pre-15-max no presente")
    frame = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    diags: list[str] = []
    syncer = UpgradeSyncer(ocr=ocr, on_diagnostic=diags.append, set_repo=None)
    syncer.on_s10_enter(frame)
    assert syncer._target == 15
    enter = [d for d in diags if "[mejora]" in d and "proyectado" in d.lower()]
    assert enter, diags
    assert "15" in enter[-1]
