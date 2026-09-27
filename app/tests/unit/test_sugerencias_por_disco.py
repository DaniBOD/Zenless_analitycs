"""`app.core.sugerencias`: la autoridad de las sugerencias (SPEC 2026-09-27, sugerencias en Discos).

El cálculo salió del script del reporte para que la pantalla Discos use el MISMO; el script queda
como envoltorio. `por_disco` indexa el reporte por disco, incluidos los que otra sugerencia nombra.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.core.sugerencias import TIPOS, SugerenciaDisco, generar, por_disco

RAIZ = Path(__file__).resolve().parents[3]


def _rep(*sugerencias):
    por_tipo = {}
    for s in sugerencias:
        por_tipo.setdefault(s["tipo"], []).append(s)
    return {"sugerencias": por_tipo}


def _s(tipo, disc_id, **kw):
    return {"tipo": tipo, "disc_id": disc_id, "reemplazo_id": None, "disc_id_2": None, **kw}


def test_la_propia_y_las_que_lo_nombran():
    mover = _s("mover", 211, reemplazo_id=213, destino="Seth")
    par = _s("armar_2pc", 101, disc_id_2=102, destino="Anby")
    equipar_213 = _s("equipar", 213, destino="Lucy")
    idx = por_disco(_rep(mover, par, equipar_213))
    assert idx[211] == SugerenciaDisco(mover, ())
    assert idx[213].propia is equipar_213 and idx[213].lo_nombran == (("repone", mover),)
    assert idx[102] == SugerenciaDisco(None, (("par", par),))
    assert idx[101].propia is par


def test_un_disco_sin_nada_no_aparece():
    assert 999 not in por_disco(_rep(_s("descartar", 5)))
    assert por_disco({}) == {}


def test_el_script_usa_la_misma_autoridad():
    """B1: el reporte y la pantalla calculan con la misma función."""
    sys.path.insert(0, str(RAIZ / "app" / "scripts"))
    try:
        import sugerir_movimientos as sm
    finally:
        sys.path.pop(0)
    assert sm.generar is generar


def test_los_tipos_cubren_lo_que_genera_el_motor():
    from app.core.recommender import RECOMENDACIONES
    assert set(RECOMENDACIONES) <= set(TIPOS) | {"equipar"}
    assert {"mover", "armar_2pc"} <= set(TIPOS)
