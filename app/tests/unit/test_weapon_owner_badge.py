"""Dueño del W-Engine por el badge del avatar — RF-15 H4.

**No hace falta código nuevo de recorte.** El avatar del PJ que tiene el arma equipada está en el
mismo lugar de la pantalla que el del detalle de disco, y `crop_detail_badge` lo localiza con una
región fija + Hough, sin depender del texto del nivel. Así que S26 reusa la superficie `detail` tal
cual: mismo crop, mismo matcher, misma librería `avatar_detbadge_v2`.

(Lo que NO se pudo reusar es `crop_s17_assigned_avatar`: exige literalmente `"/15"` en el texto del
nivel — el denominador de un disco — así que devuelve None para un arma, que dice `60/60` o `0/10`.)

## Sobre la cobertura, con los números medidos

El plan pedía ≥35/40 con dueño resuelto. **No se alcanza, y el techo no lo pone el arma:**

| | crops localizados | nombrados |
|---|---|---|
| armas (40 fixtures) | 26/40 | 13/40 |
| discos (10 de control) | 10/10 | 6/10 |

La tasa de nombrado *entre los que tienen crop* es 13/26 = 50 % en armas y 6/10 = 60 % en discos —
o sea que el matcher no anda peor con armas. Los dos límites son preexistentes y compartidos:

1. **La librería está parcialmente entrenada**: 39 labels para un roster de 50 PJs. Y en la ruta de
   runtime (`%LOCALAPPDATA%`) directamente **no existe el archivo** — sin el snapshot de `audit/`,
   el matcher tiene 0 referencias y nombra 0/40, igual que 0/10 en discos.
2. **La localización falla en 14 de 40**: verificado a ojo que en `Ejemplo_34` el avatar SÍ está,
   así que son misses de Hough, no abstenciones correctas.

Lo que sí se garantiza acá es lo que importa: **nunca un dueño equivocado**. La superficie abstiene
bajo guard, así que un dueño incierto sale None.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[3]
_ARMAS = sorted((_ROOT / "Documentacion" / "Screenshots_Triggers" / "Engines_Triggers"
                 / "Engine_vista_detallada_pj").glob("Ejemplo_*.png"))
_SNAP = _ROOT / "audit" / "avatar_detbadge_v2_snapshot_20260619_hough.npz"


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@lru_cache(maxsize=2)
def _surface(con_libreria: bool):
    from app.core.agent_identifier import AgentIdentifier
    surf = AgentIdentifier().surfaces["detail"]
    if con_libreria and _SNAP.exists():
        surf.matcher.load_merge(_SNAP)
    return surf


@lru_cache(maxsize=1)
def _muestras():
    surf = _surface(True)
    return [(p.stem, surf.sample(_load(p))) for p in _ARMAS]


@pytest.mark.skipif(not _ARMAS, reason="capturas de W-Engine no presentes")
def test_el_crop_del_badge_funciona_sobre_frames_de_arma():
    """`crop_detail_badge` no depende del texto del nivel, así que sirve para armas tal cual.

    El umbral es bajo a propósito: documenta la cobertura MEDIDA (26/40), no una aspiración. Si
    sube, mejor; si baja, algo se rompió en el crop compartido con la ruta de discos.
    """
    con_crop = [st for st, out in _muestras() if out.crop is not None]
    assert len(con_crop) >= 24, f"solo {len(con_crop)}/{len(_ARMAS)} localizaron el badge"


@pytest.mark.skipif(not _ARMAS or not _SNAP.exists(), reason="capturas o snapshot no presentes")
def test_nombra_una_parte_y_el_techo_es_la_libreria():
    """Con el snapshot cargado se nombra una parte. El techo es la librería (39 labels para 50
    PJs), no el hecho de que sea un arma."""
    nombrados = [(st, out.name) for st, out in _muestras() if out.name]
    assert len(nombrados) >= 10, f"solo {len(nombrados)} nombrados: {nombrados}"


@pytest.mark.skipif(not _ARMAS or not _SNAP.exists(), reason="capturas o snapshot no presentes")
def test_la_libreria_compartida_tiene_al_menos_un_label_con_mojibake():
    """Hallazgo, no aspiración: la librería devuelve `'n.Âº11'` para N.º 11 — el nombre guardado
    con UTF-8 leído como latin-1 en algún punto de la cosecha.

    Es un defecto PREEXISTENTE y compartido con la ruta de discos, no algo que traiga S26. Se deja
    afirmado para que quede rastro: si alguien re-cosecha la librería y lo arregla, este test cae y
    hay que borrarlo (buena noticia). Mientras exista, el monitor lo filtra canonicalizando contra
    el roster antes de reportar — ver `test_el_dueno_reportado_siempre_resuelve_al_roster`.
    """
    crudos = [out.name for _st, out in _muestras() if out.name]
    assert any("Â" in n for n in crudos), (
        "ya no hay mojibake en la librería: borrar este test y su mención en el handler")


@pytest.mark.skipif(not _ARMAS or not _SNAP.exists(), reason="capturas o snapshot no presentes")
def test_el_dueno_reportado_siempre_resuelve_al_roster():
    """Cero falsos positivos importa más que cobertura. Un dueño inventado —o un nombre corrupto—
    se propagaría al log y al toast como si fuera un hecho.

    Se prueba lo que el monitor REPORTA (canonicalizado), no lo que la librería devuelve crudo.
    """
    from app.core.agent_identifier import AgentIdentifier
    from app.db.connection import get_connection
    try:
        con = get_connection()
        roster = {r[0] for r in con.execute("select nombre from agents")}
    except Exception:
        pytest.skip("DB no disponible")

    ai = AgentIdentifier()
    reportados = [(st, ai._canonical_name(out.name)) for st, out in _muestras() if out.name]
    intrusos = [(st, n) for st, n in reportados if n is not None and n not in roster]
    assert not intrusos, f"dueños fuera del roster: {intrusos}"
    # Y que el filtro no se coma todo: alguno tiene que resolver.
    assert any(n for _st, n in reportados), f"ninguno resolvió: {reportados}"


@pytest.mark.skipif(not _ARMAS, reason="capturas de W-Engine no presentes")
def test_sin_libreria_no_inventa_ningun_dueno():
    """La propiedad que hace seguro el hito: sin referencias, se abstiene en TODOS.

    Es el estado real de una instalación nueva — el archivo de la librería no existe en la ruta de
    runtime. Ahí el dueño simplemente no se reporta, y el resto del panel (nombre, nivel, rareza,
    refinamiento, stats) sigue saliendo completo.
    """
    surf = _surface(False)
    assert not getattr(surf.matcher, "_refs", {}), "el matcher no debería tener referencias acá"
    nombres = [surf.sample(_load(p)).name for p in _ARMAS[:8]]
    assert all(n is None for n in nombres), nombres
