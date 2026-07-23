"""El handler S17 no puede quedarse mudo.

QA 2026-07-23: el monitor pasó 6 minutos en S17 con el OCR corriendo y el log NO dijo
absolutamente nada. Ya había pasado antes (8m42s el 2026-07-20) y por eso se agregó
`_note_stall` — pero solo cubrió dos de los returns silenciosos, y el que estaba activo era
un tercero.

La causa que estos tests fijan: un reset de firma devuelve `_disc_agg_cycles` a 0, así que si
la firma cambia en CADA ciclo el techo nunca se alcanza, el disco nunca madura, y el handler
devuelve en silencio para siempre.

Estos tests no prueban que el parseo ande — prueban que **cuando no anda, se nota**.
"""
from __future__ import annotations

import logging

import numpy as np
import pytest

from app.core.detector import ScreenState

_ST17 = ScreenState("S17", 1.0, "s17")


def _monitor():
    import app.core.monitor as mon_mod
    return mon_mod.Monitor(ocr=object(), detector=None)


def _sig(valor: float):
    """Firma híbrida sintética (name 48×24, detail 48×48, hex 24×24)."""
    return (
        np.full((24, 48), valor, np.float32),
        np.full((48, 48), valor, np.float32),
        np.full((24, 24), valor, np.float32),
    )


def test_firma_inestable_deja_de_ser_muda(caplog):
    """El trabe del QA: la firma cambia en cada ciclo → debe loguearse, no callarse."""
    import app.core.monitor as mon_mod
    m = _monitor()
    with caplog.at_level(logging.INFO, logger="app.core.monitor"):
        for i in range(mon_mod._S17_SIG_RESET_ALERT + 2):
            # Cada firma difiere de la anterior MUY por encima de los umbrales.
            m._disc_agg_sig = _sig(0.0) if i else None
            sig = _sig(100.0 * (i + 1))
            if m._is_new_s17_disc(sig):
                if m._disc_agg_sig is not None:
                    m._s17_sig_resets += 1
                    if m._s17_sig_resets >= mon_mod._S17_SIG_RESET_ALERT:
                        m._note_stall("S17", "la firma cambia en cada ciclo — el aggregator "
                                             "se reinicia y el disco nunca madura")
    assert any("firma cambia en cada ciclo" in r.message for r in caplog.records), \
        "el trabe por firma inestable volvió a ser mudo"


def test_el_trabe_de_firma_no_lo_limpia_el_chequeo_de_confianza(caplog):
    """REGRESIÓN (QA 2026-07-23): el trabe de firma usaba el scope "S17", que el chequeo de
    confianza limpia en CADA ciclo — el parse anda bien, lo que falla es la firma. Resultado:
    nota/destrabe alternando a varios Hz, log inundado. Scope propio: solo lo cierra la emisión."""
    m = _monitor()
    with caplog.at_level(logging.INFO, logger="app.core.monitor"):
        for _ in range(10):
            m._note_stall("S17/firma", "la firma cambia en cada ciclo")
            m._clear_stall("S17")          # lo que hace el ciclo cuando el parse sale bien
    notas = sum("firma cambia" in r.message for r in caplog.records)
    destrabes = sum("destrabado" in r.message for r in caplog.records)
    assert notas == 1, f"el trabe de firma se re-logueó {notas} veces"
    assert destrabes == 0, "el chequeo de confianza no debe cerrar el trabe de firma"
    assert "S17/firma" in m._stalls


def test_el_trabe_se_loguea_una_sola_vez(caplog):
    """RNF-06: por flanco, no por ciclo. El log corre a varios Hz."""
    m = _monitor()
    with caplog.at_level(logging.INFO, logger="app.core.monitor"):
        for _ in range(20):
            m._note_stall("S17", "la firma cambia en cada ciclo")
    assert sum("firma cambia" in r.message for r in caplog.records) == 1


def test_al_destrabarse_reporta_cuantos_ciclos(caplog):
    """El cierre del trabe dice cuánto duró — sin eso no se sabe si fue un parpadeo o 6 minutos."""
    m = _monitor()
    with caplog.at_level(logging.INFO, logger="app.core.monitor"):
        for _ in range(7):
            m._note_stall("S17", "la firma cambia en cada ciclo")
        m._clear_stall("S17")
    assert any("destrabado tras 7 ciclo" in r.message for r in caplog.records)


def test_emitir_limpia_el_contador_de_resets():
    """Navegar entre discos genera resets LEGÍTIMOS (uno por disco). Solo son patológicos si se
    encadenan SIN emisión de por medio — por eso emitir tiene que poner el contador en cero."""
    m = _monitor()
    m._s17_sig_resets = 5
    m._stalls["S17/firma"] = ("la firma cambia en cada ciclo", 5)

    disc = _disc_maduro()
    m._emit_s17_disc(disc, _ST17, True)

    assert m._s17_sig_resets == 0
    assert "S17/firma" not in m._stalls


def test_el_reset_de_tracking_limpia_el_contador():
    """Salir de S17 olvida el disco → también la cuenta de resets."""
    m = _monitor()
    m._s17_sig_resets = 4
    m._reset_s17_disc_tracking()
    assert m._s17_sig_resets == 0


def test_la_mascara_ignora_el_centro_animado_pero_conserva_los_slots():
    """La CAUSA del trabe: el arte animado del centro del hexágono entraba en la firma.

    Se prueban las dos mitades del contrato — que el centro deje de contar (si no, el trabe
    vuelve) y que el borde SIGA contando (si no, se pierde la detección de cambio de slot, que
    es lo único que esta componente aporta)."""
    import app.core.monitor as mon_mod
    W, H = 2557, 1439
    base = np.zeros((H, W, 3), np.uint8)

    def _sig_hex_de(frame):
        return mon_mod.Monitor._s17_disc_signature(frame)[2]

    # (a) Un cambio VIOLENTO solo en el centro del hexágono → la firma no se inmuta.
    animado = base.copy()
    cx, cy = int((0.58 + 0.42 * 0.37) * W), int((0.18 + 0.45 * 0.70) * H)
    r = int(0.05 * W)
    animado[cy - r:cy + r, cx - r:cx + r] = 255
    diff_centro = mon_mod.Monitor._sig_component_diff(_sig_hex_de(base), _sig_hex_de(animado))
    assert diff_centro <= mon_mod._S17_SIG_HEX_MAX, (
        f"el centro animado sigue moviendo la firma (diff={diff_centro:.1f})")

    # (b) Un cambio en el BORDE (donde vive el anillo de selección de slot) SÍ se ve.
    borde = base.copy()
    bx = int(0.60 * W)                      # columna izquierda del hexágono ≈ slot 3
    borde[int(0.20 * H):int(0.85 * H), bx:bx + int(0.03 * W)] = 255
    diff_borde = mon_mod.Monitor._sig_component_diff(_sig_hex_de(base), _sig_hex_de(borde))
    assert diff_borde > mon_mod._S17_SIG_HEX_MAX, (
        f"la máscara se comió el anillo de slot (diff={diff_borde:.1f})")


def _disc_maduro():
    from app.core.parser_disc import DiscParsed, SubstatParsed
    return DiscParsed(
        set_name_raw="Jazz caótico", set_name_canon="Jazz caótico", slot=1,
        main_stat_raw="PV", main_stat_canon="HP", main_valor=2200.0, main_unidad="flat",
        nivel=15, rareza="S", confianza_global=0.95,
        subs=[SubstatParsed(nombre_raw=n, nombre_canon=n, valor=1.0, unidad="flat",
                            rolls=0, confianza=1.0)
              for n in ("CR", "CD", "ATK%", "DEF")],
    )
