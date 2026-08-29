"""El re-arme del disco S9: cuándo la firma declara "estoy mirando otro disco".

Nace de la pasada de censo del 2026-08-20: en el grupo de discos que comparten set + slot +
main con el anterior el p90 del intervalo salta a 29 s contra 12 s del resto. La firma vieja
mira **sólo el panel derecho** —título del set y bloque main/substats—, así que para dos discos
con la misma cabecera el único diferenciador queda siendo el texto de los substats.

Medido sobre las capturas del 2026-08-29 (`Ejemplo_15..18`), eso alcanza **cuando los substats
difieren**: `Ejemplo_17`/`Ejemplo_18` son los dos Fábula Yunkui slot 3 DEF 184 y el cuerpo los
separa 6.11 contra un umbral de 3.0.

Lo que NO alcanza —y no puede alcanzar— es el disco GEMELO: mismo set, slot, main **y** substats.
Ahí el panel es idéntico pixel a pixel, la diferencia es exactamente 0 y ningún umbral sobre el
panel puede ayudar. En el inventario real hay 22 pares así.

Para esos, la única señal es **dónde está la selección en la grilla**: al moverte de disco el
recuadro se mueve, aunque los dos discos sean iguales. Es el mismo patrón que `_s17_disc_signature`
ya usa con el anillo del hexágono.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

REPO = Path(__file__).resolve().parents[3]
_S9 = (REPO / "Documentacion" / "Screenshots_Triggers" / "Discos_Triggers"
       / "09_Inventario_discos_general")

pytestmark = pytest.mark.skipif(not (_S9 / "Ejemplo_18.png").exists(),
                                reason="capturas S9 no presentes")


def _frame(n: int):
    p = _S9 / f"Ejemplo_{n}.png"
    return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)


def _monitor():
    import app.core.monitor as mon
    return mon.Monitor(ocr=None, detector=None, on_disc=lambda *a, **k: None)


def _gemelo_sintetico(base: int, panel_de: int):
    """Frame con la GRILLA de `base` y el PANEL de `panel_de`.

    No hay captura real de dos gemelos —para tenerla habría que dar con uno de los 22 pares y
    fotografiarlo—, así que se construye el caso: se pega el panel derecho de un frame sobre el
    otro. El resultado es exactamente lo que ve la app frente a un gemelo: **panel idéntico,
    selección en otro lado**. Los dos frames son del mismo tamaño (2559×1439).
    """
    dst, src = _frame(base).copy(), _frame(panel_de)
    W = dst.shape[1]
    x0 = int(0.69 * W)                       # todo el panel derecho, con margen sobre las ROIs
    dst[:, x0:] = src[:, x0:]
    return dst


# --- lo que la firma vieja YA hacía bien (no-regresión) ---------------------------------------

def test_dos_discos_del_mismo_set_slot_y_main_re_arman_por_los_substats():
    """`Ejemplo_17` y `Ejemplo_18`: Fábula Yunkui, slot 3, DEF 184 los dos. Es el caso que
    motivó todo esto, y el panel SÍ los separa porque sus substats difieren. Este test fija
    que la componente nueva no rompa lo que ya andaba."""
    m = _monitor()
    m._s9_agg_sig = m._s9_disc_signature(_frame(17))
    assert m._is_new_s9_disc(m._s9_disc_signature(_frame(18))) is True


def test_el_mismo_frame_no_re_arma():
    """El caso más básico y el que paga el costo del error: si un frame idéntico disparara
    re-arme, el aggregator se reiniciaría en cada ciclo y el disco no maduraría nunca."""
    m = _monitor()
    f = _frame(17)
    m._s9_agg_sig = m._s9_disc_signature(f)
    assert m._is_new_s9_disc(m._s9_disc_signature(f)) is False


# --- lo que sólo la posición puede resolver ---------------------------------------------------

def test_un_disco_GEMELO_re_arma_aunque_el_panel_sea_identico():
    """EL TEST QUE IMPORTA. Panel idéntico (diff 0.00) y selección en otro tile.

    Con la firma vieja esto devuelve False —"es el mismo disco"— y el usuario se queda esperando
    un toast que no va a llegar hasta que se mueva a un disco distinto. Es la falla que no depende
    de ningún umbral: sobre un panel idéntico no hay nada que medir.
    """
    m = _monitor()
    m._s9_agg_sig = m._s9_disc_signature(_frame(17))
    gemelo = _gemelo_sintetico(base=18, panel_de=17)     # grilla de 18, panel de 17

    from app.core.monitor import Monitor
    sig_a, sig_b = m._s9_agg_sig, Monitor._s9_disc_signature(gemelo)
    assert Monitor._sig_component_diff(sig_a[0], sig_b[0]) == 0.0, "el panel debería ser idéntico"
    assert Monitor._sig_component_diff(sig_a[1], sig_b[1]) == 0.0, "el panel debería ser idéntico"

    assert m._is_new_s9_disc(sig_b) is True, \
        "gemelo en otro tile: el panel no puede distinguirlo, la posición sí"


def test_sin_tile_resaltado_la_posicion_NO_decide():
    """`Ejemplo_4` no tiene tile localizable (el bbox da None). Ausencia de posición es ausencia
    de dato, no evidencia de que sea el mismo disco ni de que sea otro: la decisión tiene que
    quedar en manos del panel, como antes. Si no, un frame sin selección re-armaría porque sí.
    """
    m = _monitor()
    f4 = _frame(4)
    m._s9_agg_sig = m._s9_disc_signature(f4)
    assert m._is_new_s9_disc(m._s9_disc_signature(f4)) is False, \
        "mismo frame sin tile localizable: la posición no debe forzar un re-arme"


def test_no_introduce_falsos_re_armes_en_el_corpus():
    """Regresión sobre los pares del corpus: la componente nueva puede AGREGAR re-armes (el error
    se sesga a re-armar de más, que cuesta ~1 s contra los 20-60 s de un re-arme perdido), pero
    los pares que ya re-armaban tienen que seguir haciéndolo."""
    from app.core.monitor import Monitor
    frames = {n: _frame(n) for n in range(1, 19)}
    sigs = {n: Monitor._s9_disc_signature(f) for n, f in frames.items()}
    m = _monitor()
    for a, sig_a in sigs.items():
        for b, sig_b in sigs.items():
            if a >= b:
                continue
            m._s9_agg_sig = sig_a
            nuevo = m._is_new_s9_disc(sig_b)
            viejo = (Monitor._sig_component_diff(sig_a[0], sig_b[0]) > 3.0
                     or Monitor._sig_component_diff(sig_a[1], sig_b[1]) > 3.0)
            if viejo:
                assert nuevo, f"Ej_{a} vs Ej_{b}: re-armaba antes y ahora no"
