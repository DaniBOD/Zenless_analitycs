"""Quién tiene cada arma en el inventario (S30), contra verdad de tierra dictada por Daniel.

Los otros tests de S30 miden el PARSER (nombre, nivel, rareza, refinamiento, ATK: 6/6). Este mide
lo único que sigue fallando: **el dueño**. Y lo mide con las cinco armas cuyo dueño real Daniel
confirmó a ojo el 2026-08-13, después de dos pasadas de QA en vivo.

## Por qué existe este archivo

La pasada del 2026-08-11 dio 5/11 y el diagnóstico fue "faltan referencias". Se cosecharon refs
nuevas para tres de los cinco que fallaban (Jane, Nangong Yu, Zhao) y la pasada del 2026-08-13 dio
1/5 *nombrados*... pero ese número esconde el resultado real. Sobre los 10 fixtures:

| fixture | arma | dueño | qué pasa hoy | distancia |
|---|---|---|---|---|
| `Ejemplo_4`  | Llanto mielgo        | Vivian     | nombrado ✓ | 0.080 |
| `Ejemplo_6`  | Caldero de la claridad| Yixuan    | nombrado ✓ | 0.087 |
| `Ejemplo_8`  | Aguijón agudo        | Jane       | nombrado ✓ | 0.235 |
| `Ejemplo_3`  | Última cena          | Gatillo    | nombrado ✓ | 0.255 |
| `Ejemplo_2`  | Florescencia         | *(libre)*  | LIBRE ✓ | — |
| `Ejemplo_5`  | Repercusión Modelo II| *(libre)*  | LIBRE ✓ | — |
| `Ejemplo_9`  | Fósil preciado       | Nangong Yu | top-1 correcto, margen 0.002 ⇒ abstiene | 0.203 |
| `Ejemplo_10` | Transmorfer original | Zhao       | top-1 correcto, margen 0.032 ⇒ abstiene | 0.302 |
| `Ejemplo_1`  | Engranaje infernal   | Dialyn     | **nombra a otro** (Orfia y Magas) | 0.227 (2º) |
| `Ejemplo_7`  | Compilador quimérico | Grace      | **afirma LIBRE** | — |

6 de 10 salen bien, 2 se abstienen con el ranking correcto y 2 fallan. **En los 8 que localizan el
badge, el dueño correcto está en el puesto 1 siete veces.**

**Los tres que recibieron refs tienen al dueño correcto en el puesto 1.** No fallan por identificar
mal: dos fallan por el gate de margen (`_MIN_MARGIN` = 0.04), que es otra cosa y se arregla de otra
forma. Los dos que NO recibieron refs (Dialyn, Grace) siguen fallando, y fallan distinto entre sí.

Dos cosas que las distancias dejan ver y conviene no olvidar:

- **La cantidad de refs no explica el resultado.** Gatillo tiene 3 refs y cae en 0.255; Vivian tiene
  2 y cae en 0.080. Lo que decide no es cuántas hay sino si alguna se parece a ESTA vista.
- **Hay dos regímenes**, no un continuo: los seguros caen por debajo de 0.09 y los dudosos se
  amontonan entre 0.20 y 0.31. Nadie aterriza en el medio.

O sea que acá hay tres defectos separados, y este archivo los separa para que nadie los vuelva a
tratar como uno solo:

1. **margen** (`Ejemplo_9`, `Ejemplo_10`) — ranking bien, gate corto. Se cierra bajando la distancia
   con más refs, NO aflojando el 0.04: ese umbral es lo único que impide nombrar mal.
2. **discriminación** (`Ejemplo_1`) — el dueño correcto sale segundo. Es un problema de librería.
3. **detección** (`Ejemplo_7`) — el círculo del dueño no se localiza y se AFIRMA que el arma está
   libre. El peor de los tres: los otros dos se abstienen, este miente. Y **no es que el camino
   esté roto**: `Ejemplo_2` y `Ejemplo_5` son armas realmente libres y las dos se reportan LIBRE
   bien. O sea que `present=False` funciona y lo de Grace es un miss de Hough en ESE frame, no un
   `present=False` que sobre-dispare. Eso acota mucho dónde buscar.

Los dos defectos abiertos van como `xfail(strict=True)`: si alguien los arregla, el test falla por
pasar de más y avisa que hay que actualizar esta tabla.

## Sobre la reproducibilidad

La librería del runtime vive en `%LOCALAPPDATA%` y no está versionada, así que un test que la use
mide la cosecha local de quien lo corra. Acá se carga el snapshot versionado de `audit/`, que es la
misma disciplina de `test_weapon_owner_badge.py`. El `conftest` ya redirige `DANIBOD_AVATAR_LIB` a
un tmp por test, así que `AgentIdentifier()` arranca sin la librería del usuario.

Los fixtures de `Engines_Triggers/` son locales (gitignoreados, ~150 MB) ⇒ skip-if-absent.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.parser_weapon_s26 import parse_weapon_s30, read_weapon_owner_badge_s30

_ROOT = Path(__file__).resolve().parents[3]
_FX = (_ROOT / "Documentacion" / "Screenshots_Triggers" / "Engines_Triggers"
       / "Inventario_general_engines")
_SNAP = _ROOT / "audit" / "avatar_detbadge_v2_snapshot_20260813_cosecha89.npz"

# Verdad de tierra dictada por Daniel el 2026-08-13, mirando la pantalla. No sale del sistema:
# es justamente contra lo que se lo mide. `None` = el arma NO tiene dueño (libre).
#
# Ojo con `Ejemplo_3`: Daniel dijo "trigger", que es el nombre en inglés. El roster de la DB está
# en español y la clave de la librería es **Gatillo** — traducir acá y no en el test evita que el
# día de mañana alguien "corrija" el assert.
_DUENOS: dict[str, str | None] = {
    "Ejemplo_1": "Dialyn",
    "Ejemplo_2": None,
    "Ejemplo_3": "Gatillo",
    "Ejemplo_4": "Vivian",
    "Ejemplo_5": None,
    "Ejemplo_6": "Yixuan",
    "Ejemplo_7": "Grace",
    "Ejemplo_8": "Jane",
    "Ejemplo_9": "Nangong Yu",
    "Ejemplo_10": "Zhao",
}
# Los tres que recibieron refs nuevas en la cosecha del 2026-08-12.
_COSECHADOS = ("Ejemplo_8", "Ejemplo_9", "Ejemplo_10")
# Los que hoy se nombran bien de punta a punta: localizan, rankean y pasan el gate.
_NOMBRADOS_OK = ("Ejemplo_3", "Ejemplo_4", "Ejemplo_6", "Ejemplo_8")
# Armas realmente libres. Son el control del defecto 3.
_LIBRES = ("Ejemplo_2", "Ejemplo_5")


def _load(p: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


@lru_cache(maxsize=1)
def _paddle():
    try:
        from app.core.ocr_paddle import PaddleBackend
    except Exception:  # noqa: BLE001  # pragma: no cover — Paddle falla de varias formas distintas
        pytest.skip("PaddleOCR no disponible")
    return PaddleBackend()


@lru_cache(maxsize=1)
def _matcher():
    """El matcher del detalle con el snapshot versionado — nunca la librería del usuario."""
    from app.core.agent_identifier import AgentIdentifier
    surf = AgentIdentifier().surfaces["detail"]
    surf.matcher.load_merge(_SNAP)
    return surf.matcher


@lru_cache(maxsize=8)
def _badge(stem: str):
    """(OwnerBadge, MatchResult) del fixture. `MatchResult` es None si no hubo recorte."""
    d = parse_weapon_s30(_load(_FX / f"{stem}.png"), _paddle(), catalogo=None)
    b = read_weapon_owner_badge_s30(_load(_FX / f"{stem}.png"), d.pill_bbox)
    if b is None or b.crop is None:
        return b, None
    return b, _matcher().match(b.crop)


def _falta(stem: str) -> bool:
    return not (_FX / f"{stem}.png").exists() or not _SNAP.exists()


_skip = pytest.mark.skipif(not _FX.exists() or not _SNAP.exists(),
                           reason="capturas del inventario o snapshot no presentes")


# --- Lo que YA funciona: hay que dejarlo clavado -----------------------------------------------

@_skip
@pytest.mark.parametrize("stem", _COSECHADOS)
def test_los_cosechados_tienen_al_dueno_en_el_puesto_uno(stem):
    """El resultado real de la cosecha del 2026-08-12, y la evidencia de que sirvió.

    Antes, `Transmorfer original` daba `Nicole:0.33, Zhao:0.35` — Nicole primera. Después de
    cosechar, `Zhao:0.30, Nicole:0.33`. El ranking es la medida limpia de la librería porque no
    depende del gate de abstención, que es un problema aparte.
    """
    if _falta(stem):
        pytest.skip(f"falta {stem}")
    _b, r = _badge(stem)
    assert r is not None and r.top, f"{stem}: no se localizó el badge"
    assert r.top[0][0] == _DUENOS[stem], f"{stem}: top-1 = {r.top[:3]}"


@_skip
@pytest.mark.parametrize("stem", _NOMBRADOS_OK)
def test_se_nombran_de_punta_a_punta(stem):
    """Los casos completos: localizan, rankean bien y además pasan el gate.

    Vivian (0.080) y Yixuan (0.087) están MUY cerca; Gatillo (0.255) y Jane (0.235) apenas
    alcanzan. Los cuatro se nombran, pero los dos últimos lo hacen con poco aire — si el encuadre
    se corre un poco, caen del lado de la abstención.
    """
    if _falta(stem):
        pytest.skip(f"falta {stem}")
    _b, r = _badge(stem)
    assert r.name == _DUENOS[stem], f"name={r.name} conf={r.conf:.2f} margin={r.margin:.2f}"


@_skip
@pytest.mark.parametrize("stem", _LIBRES)
def test_un_arma_sin_dueno_se_reporta_libre(stem):
    """El control del defecto 3, y por eso importa que estén acá.

    `Ejemplo_7` (Grace) sale LIBRE siendo de alguien, y la lectura fácil sería "el camino de
    `present=False` sobre-dispara". Estas dos armas son realmente libres y las dos se reportan bien,
    así que ese camino FUNCIONA: lo de Grace es un miss de Hough en ese frame concreto. Sin este
    par, el defecto 3 no se puede acotar — y alguien podría "arreglarlo" quitando el
    `present=False`, que es justo lo que estos dos tests impiden.
    """
    if _falta(stem):
        pytest.skip(f"falta {stem}")
    b, r = _badge(stem)
    assert b is not None and not b.present, f"no se reportó libre (badge={b}, match={r})"


@_skip
@pytest.mark.parametrize("stem", ["Ejemplo_9", "Ejemplo_10"])
def test_a_estos_dos_los_frena_el_MARGEN_y_no_el_ranking(stem):
    """Diagnóstico clavado como contrato: el dueño correcto está PRIMERO y aun así no se nombra.

    Importa distinguirlo porque el remedio es distinto. Si alguien lee "no identifica al dueño" y
    sale a cambiar el descriptor o el encuadre, está arreglando algo que no está roto: lo que falta
    es distancia, y eso se consigue con más referencias del mismo PJ.
    """
    if _falta(stem):
        pytest.skip(f"falta {stem}")
    _b, r = _badge(stem)
    from app.core.avatar_descriptor import _MIN_MARGIN
    assert r.top[0][0] == _DUENOS[stem]                  # el ranking está bien...
    assert r.margin < _MIN_MARGIN                        # ...y aun así se abstiene
    assert r.name is None


# --- Los dos defectos abiertos -----------------------------------------------------------------

@_skip
@pytest.mark.xfail(strict=True, reason="defecto abierto: el dueño correcto sale 2º (Dialyn 0.227 "
                                       "contra Orfia y Magas 0.166). Dialyn no recibió refs "
                                       "nuevas en la cosecha del 2026-08-12 — es el control.")
def test_engranaje_infernal_no_deberia_nombrar_a_otro():
    """Nombrar mal es peor que abstenerse: se propaga al log y al toast como un hecho.

    Ojo con un efecto lateral medido: el 2026-08-11 este mismo frame daba `Orfia y Magas:0.17,
    Seth:0.18` con margen 0.02 y se ABSTENÍA. El arreglo de la ruta gris (commit f18ace7) separó a
    Seth —era uno de los PJs de paleta oscura que se comparaban sin color— y al irse el vecino, el
    margen alrededor de una respuesta EQUIVOCADA se ensanchó a 0.06 y pasó el gate. La métrica
    mejoró en promedio y este caso empeoró.
    """
    if _falta("Ejemplo_1"):
        pytest.skip("falta Ejemplo_1")
    _b, r = _badge("Ejemplo_1")
    assert r.name in (None, "Dialyn"), f"nombró a {r.name}"


@_skip
@pytest.mark.xfail(strict=True, reason="defecto abierto: Hough no localiza el círculo del dueño y "
                                       "se afirma LIBRE. Misma arma, mismo fallo, el 2026-08-11.")
def test_compilador_quimerico_no_esta_libre():
    """El peor de los tres modos: los otros dos se abstienen, este AFIRMA algo falso.

    `present=False` significa "el arma no tiene dueño" y se reporta como LIBRE. La distinción está
    escrita en `read_weapon_owner_badge_s30`: si no se ve NINGÚN círculo se devuelve None ("no pude
    ver"), pero si se ve el de especialidad y no el del dueño se concluye LIBRE. Acá cae en el
    segundo caso y concluye mal.
    """
    if _falta("Ejemplo_7"):
        pytest.skip("falta Ejemplo_7")
    b, _r = _badge("Ejemplo_7")
    assert b is None or b.present, "se afirmó LIBRE un arma que tiene dueño"
