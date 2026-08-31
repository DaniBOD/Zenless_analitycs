"""El guard de identidad es POR SUPERFICIE — la grilla y el detalle no miden lo mismo.

Nace de dos casos de campo del censo (2026-08-30) y de una medición sobre la librería.

En la GRILLA, Ben y Soukaku son indistinguibles: 0.90 vs 0.90, margen 0.00, y se dan vuelta entre
frames. En el DETALLE el mismo disco da `top=[Soukaku:0.79, Jane:0.44, Lucía:0.44]` — el nombre
correcto, con Ben fuera del top-3 y un margen de 0.346, que es 8,6x el mínimo exigido. Y se
descartaba igual, porque sobre las dos superficies se aplicaba el mismo guard de confianza 0.80.

Barrido leave-one-out sobre la librería del detalle (73 consultas, 32 clases con >=2 refs
distintas):

    guard   acierta   MAL   se abstiene
     0.80        45     1            27
     0.70        56     1            16      <- 11 rescates, CERO errores nuevos
     0.45        56     1            16      <- por debajo de 0.70 no cambia nada

Las 11 rescatadas son 11 aciertos, e incluyen Soukaku x2 y Manato. El único error de la librería
(Seth->Zhao) viene con conf 0.916: ningún guard lo detiene, es un problema de datos.
"""
from __future__ import annotations

import pytest

from app.core.agent_identifier import _DETAIL_GUARD, _S17_GUARD_DEFAULT


def test_el_detalle_tiene_su_PROPIO_guard_mas_bajo_que_la_grilla():
    """La confianza del detalle corre sistemáticamente más baja que la de la grilla (sesgo medido
    -0.042 sobre los fixtures donde ambas aciertan). Un solo número para las dos era el número de
    la grilla aplicado a una escala que no es la suya."""
    assert _DETAIL_GUARD < _S17_GUARD_DEFAULT
    assert _S17_GUARD_DEFAULT == 0.80, "la grilla NO se toca: su calibración sigue valiendo"


class _MatcherFalso:
    """Devuelve un MatchResult armado, para probar el guard sin depender de la librería real."""

    def __init__(self, name, conf, margin):
        from app.core.avatar_descriptor import MatchResult
        self._r = MatchResult(name, conf, margin, False, [(name, 1 - conf)])
        self._refs = {name: [object()]}

    def match(self, face):
        return self._r


def _identifier_con(matcher):
    from app.core.agent_identifier import AgentIdentifier
    ident = AgentIdentifier.__new__(AgentIdentifier)   # sin cargar librerías del disco
    ident._detbadge = matcher
    return ident


def test_el_caso_de_SOUKAKU_ahora_se_nombra():
    """EL TEST QUE IMPORTA. Los números son los del log del 2026-08-30 a las 23:29, cinco frames
    seguidos: conf 0.79 (una centésima bajo el guard viejo) con margen 0.346."""
    ident = _identifier_con(_MatcherFalso("Soukaku", 0.79, 0.346))
    nombre, _conf, margen, _rej = ident.s17_match_detail(object())
    assert nombre == "Soukaku", "el detalle sabía la respuesta y el guard se la comía por 0.01"
    assert margen == pytest.approx(0.346)


def test_una_confianza_GENUINAMENTE_baja_sigue_sin_nombrar():
    """Bajar el guard no puede volverlo decorativo. Por debajo del nuevo umbral se sigue
    absteniendo, que es lo que evita nombrar mal con confianza."""
    ident = _identifier_con(_MatcherFalso("Quien Sea", 0.55, 0.30))
    assert ident.s17_match_detail(object())[0] is None


def test_el_llamador_puede_seguir_exigiendo_mas():
    """El guard es un default, no una imposición: quien necesite ser más estricto lo pasa."""
    ident = _identifier_con(_MatcherFalso("Soukaku", 0.79, 0.346))
    assert ident.s17_match_detail(object(), min_sim=0.95)[0] is None
